"use client";

import { useCallback, useState } from "react";
import {
  cancelSummaryJob,
  createSummaryJob,
  getSummaryJob,
  normalizeApiError,
} from "../lib/api/client";
import type {
  ApiError,
  MediaSelection,
  SummaryEventPayload,
  SummaryJobSnapshot,
} from "../lib/api/types";
import { isTerminalStatus } from "../lib/api/types";
import type { BubbleDictionary } from "../lib/i18n/messages/en-US";
import { useTaskStream } from "./use-task-stream";

const summaryEvents = [
  "queued",
  "started",
  "stage_changed",
  "progress",
  "completed",
  "failed",
  "cancelled",
] as const;

function parseSummaryEvent(value: string): SummaryEventPayload | null {
  try {
    const payload = JSON.parse(value) as SummaryEventPayload;
    return typeof payload.sequence === "number" && Boolean(payload.summary)
      ? payload
      : null;
  } catch {
    return null;
  }
}

export function useSummaryJob(dictionary: BubbleDictionary) {
  const [source, setSource] = useState<MediaSelection | null>(null);
  const [job, setJob] = useState<SummaryJobSnapshot | null>(null);
  const [eventsUrl, setEventsUrl] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const updateFromStream = useCallback((snapshot: SummaryJobSnapshot) => {
    setJob(snapshot);
    if (isTerminalStatus(snapshot.status)) setEventsUrl(null);
  }, []);

  useTaskStream<SummaryJobSnapshot, SummaryEventPayload>({
    streamKey: eventsUrl && job ? job.id : null,
    eventsUrl,
    eventNames: summaryEvents,
    parse: parseSummaryEvent,
    getSnapshot: () => {
      if (!job) return Promise.reject(new Error("Missing summary job"));
      return getSummaryJob(job.id);
    },
    onUpdate: updateFromStream,
    snapshotFromPayload: (payload) => payload.summary,
    isTerminal: (snapshot) => isTerminalStatus(snapshot.status),
    onExhausted: () =>
      setError({
        code: "SSE_DISCONNECTED",
        message: dictionary.errors.SERVICE_OFFLINE,
        retryable: true,
      }),
  });

  const start = useCallback(
    async (item: MediaSelection) => {
      setSource(item);
      setJob(null);
      setEventsUrl(null);
      setError(null);
      setStarting(true);
      try {
        const response = await createSummaryJob(item);
        setJob(response.summary);
        setEventsUrl(
          isTerminalStatus(response.summary.status) ? null : response.events_url,
        );
      } catch (caught) {
        setError(
          normalizeApiError(caught, {
            code: "SUMMARY_FAILED",
            message: dictionary.errors.SUMMARY_FAILED,
          }),
        );
      } finally {
        setStarting(false);
      }
    },
    [dictionary.errors.SUMMARY_FAILED],
  );

  const cancel = useCallback(async () => {
    if (!job) return;
    setError(null);
    try {
      await cancelSummaryJob(job.id);
      setEventsUrl(null);
      setJob({ ...job, status: "cancelled" });
    } catch (caught) {
      setError(
        normalizeApiError(caught, {
          code: "SUMMARY_CANCEL_FAILED",
          message: dictionary.errors.SUMMARY_CANCEL_FAILED,
        }),
      );
    }
  }, [dictionary.errors.SUMMARY_CANCEL_FAILED, job]);

  const retry = useCallback(() => {
    if (source) void start(source);
  }, [source, start]);

  const reset = useCallback(() => {
    setSource(null);
    setJob(null);
    setEventsUrl(null);
    setError(null);
    setStarting(false);
  }, []);

  return { source, job, starting, error, start, cancel, retry, reset };
}

export type SummaryJobController = ReturnType<typeof useSummaryJob>;
