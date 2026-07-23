"use client";

import { useCallback, useMemo, useState } from "react";
import {
  cancelDownloadJob,
  createDownloadJob,
  getDownloadJob,
  normalizeApiError,
  probeMedia,
} from "../lib/api/client";
import type {
  ApiError,
  DownloadEventPayload,
  DownloadJobSnapshot,
  MediaSelection,
  Mode,
  Preset,
  ProbeFailure,
} from "../lib/api/types";
import { isTerminalStatus } from "../lib/api/types";
import type { BubbleDictionary } from "../lib/i18n/messages/en-US";
import { useTaskStream } from "./use-task-stream";

const downloadEvents = [
  "queued",
  "started",
  "item_started",
  "item_progress",
  "item_ready",
  "item_failed",
  "bundle_ready",
  "completed",
  "cancelled",
] as const;

export function parseInputUrls(input: string) {
  return Array.from(
    new Set(
      input
        .split(/[\n\s]+/)
        .map((value) => value.trim())
        .filter(Boolean),
    ),
  ).slice(0, 10);
}

export function defaultPreset(presets: Preset[]) {
  return (
    presets.find((preset) => preset.id === "mp4-1080") ??
    presets.find((preset) => preset.id === "mp4-720") ??
    presets.find((preset) => preset.id === "best") ??
    presets[0]
  )?.id;
}

function parseDownloadEvent(value: string): DownloadEventPayload | null {
  try {
    const payload = JSON.parse(value) as DownloadEventPayload;
    return typeof payload.sequence === "number" && Boolean(payload.job) ? payload : null;
  } catch {
    return null;
  }
}

export function useDownloadJob(dictionary: BubbleDictionary) {
  const [mode, setMode] = useState<Mode>("single");
  const [input, setInput] = useState("");
  const [items, setItems] = useState<MediaSelection[]>([]);
  const [probeFailures, setProbeFailures] = useState<ProbeFailure[]>([]);
  const [job, setJob] = useState<DownloadJobSnapshot | null>(null);
  const [eventsUrl, setEventsUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const urls = useMemo(() => parseInputUrls(input), [input]);

  const updateFromStream = useCallback((snapshot: DownloadJobSnapshot) => {
    setJob(snapshot);
    if (isTerminalStatus(snapshot.status)) setEventsUrl(null);
  }, []);

  useTaskStream<DownloadJobSnapshot, DownloadEventPayload>({
    streamKey: eventsUrl && job ? job.id : null,
    eventsUrl,
    eventNames: downloadEvents,
    parse: parseDownloadEvent,
    getSnapshot: () => {
      if (!job) return Promise.reject(new Error("Missing job"));
      return getDownloadJob(job.id);
    },
    onUpdate: updateFromStream,
    snapshotFromPayload: (payload) => payload.job,
    isTerminal: (snapshot) => isTerminalStatus(snapshot.status),
    onExhausted: () =>
      setError({
        code: "SSE_DISCONNECTED",
        message: dictionary.errors.SERVICE_OFFLINE,
        retryable: true,
      }),
  });

  const clearTaskState = useCallback(() => {
    setItems([]);
    setProbeFailures([]);
    setJob(null);
    setEventsUrl(null);
    setError(null);
  }, []);

  const changeMode = useCallback(
    (nextMode: Mode) => {
      setMode(nextMode);
      setInput("");
      clearTaskState();
    },
    [clearTaskState],
  );

  const analyze = useCallback(async () => {
    if (!urls.length) {
      setError({ code: "MISSING_URL", message: dictionary.errors.MISSING_URL });
      return;
    }
    if (mode === "single" && urls.length > 1) {
      setError({ code: "TOO_MANY_URLS", message: dictionary.errors.TOO_MANY_URLS });
      return;
    }

    setBusy(true);
    setError(null);
    setProbeFailures([]);
    setJob(null);
    setEventsUrl(null);
    const nextItems: MediaSelection[] = [];
    const failures: ProbeFailure[] = [];

    for (const url of urls) {
      try {
        const data = await probeMedia(url);
        for (const media of data.items) {
          if (nextItems.length >= 10) break;
          const presetId = defaultPreset(media.presets);
          if (!presetId) continue;
          nextItems.push({
            ...media,
            selectionId: `${nextItems.length}-${media.source_url}`,
            presetId,
          });
        }
      } catch (caught) {
        failures.push({
          url,
          error: normalizeApiError(caught, {
            code: "SERVICE_OFFLINE",
            message: dictionary.errors.SERVICE_OFFLINE,
          }),
        });
      }
    }

    setItems(nextItems);
    setProbeFailures(failures);
    if (!nextItems.length && failures.length) setError(failures[0].error);
    setBusy(false);
  }, [dictionary.errors.MISSING_URL, dictionary.errors.SERVICE_OFFLINE, dictionary.errors.TOO_MANY_URLS, mode, urls]);

  const updatePreset = useCallback((selectionId: string, presetId: string) => {
    setItems((current) =>
      current.map((item) =>
        item.selectionId === selectionId ? { ...item, presetId } : item,
      ),
    );
  }, []);

  const applyPresetToAll = useCallback((presetId: string) => {
    setItems((current) =>
      current.map((item) =>
        item.presets.some((preset) => preset.id === presetId)
          ? { ...item, presetId }
          : item,
      ),
    );
  }, []);

  const startDownload = useCallback(async () => {
    if (!items.length) return;
    setBusy(true);
    setError(null);
    try {
      const response = await createDownloadJob(items);
      setJob(response.job);
      setEventsUrl(
        isTerminalStatus(response.job.status) ? null : response.events_url,
      );
    } catch (caught) {
      setError(
        normalizeApiError(caught, {
          code: "JOB_FAILED",
          message: dictionary.errors.JOB_FAILED,
        }),
      );
    } finally {
      setBusy(false);
    }
  }, [dictionary.errors.JOB_FAILED, items]);

  const cancelJob = useCallback(async () => {
    if (!job) return;
    setError(null);
    try {
      await cancelDownloadJob(job.id);
      setEventsUrl(null);
      setJob({
        ...job,
        status: "cancelled",
        items: job.items.map((item) => ({
          ...item,
          status: item.status === "ready" ? "ready" : "cancelled",
        })),
      });
    } catch (caught) {
      setError(
        normalizeApiError(caught, {
          code: "JOB_CANCEL_FAILED",
          message: dictionary.errors.JOB_CANCEL_FAILED,
        }),
      );
    }
  }, [dictionary.errors.JOB_CANCEL_FAILED, job]);

  const reset = useCallback(() => {
    setInput("");
    clearTaskState();
  }, [clearTaskState]);

  return {
    mode,
    changeMode,
    input,
    setInput,
    urls,
    items,
    probeFailures,
    job,
    busy,
    error,
    clearError: () => setError(null),
    analyze,
    updatePreset,
    applyPresetToAll,
    startDownload,
    cancelJob,
    reset,
  };
}

export type DownloadJobController = ReturnType<typeof useDownloadJob>;
