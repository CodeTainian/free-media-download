"use client";

import { useCallback, useRef, useState } from "react";
import {
  cancelAnalysis,
  createAnalysis,
  getAnalysis,
  getAnalysisResult,
  getArtifact,
  normalizeApiError,
  requestArtifact,
} from "../lib/api/client";
import type {
  AnalysisDetail,
  AnalysisEventPayload,
  AnalysisLanguage,
  AnalysisResult,
  AnalysisSnapshot,
  ApiError,
  ArtifactKind,
  ArtifactPayloadMap,
  MediaSelection,
} from "../lib/api/types";
import type { BubbleDictionary } from "../lib/i18n/messages/en-US";
import { useTaskStream } from "./use-task-stream";

const analysisEvents = [
  "analysis.queued",
  "analysis.started",
  "analysis.stage_changed",
  "analysis.progress",
  "analysis.completed",
  "analysis.partial",
  "analysis.failed",
  "analysis.cancelled",
  "artifact.queued",
  "artifact.started",
  "artifact.progress",
  "artifact.completed",
  "artifact.failed",
  "artifact.cancelled",
  "transcript.completed",
] as const;

const terminalAnalysisStatuses = new Set([
  "completed",
  "partial",
  "failed",
  "cancelled",
]);

function parseAnalysisEvent(value: string): AnalysisEventPayload | null {
  try {
    const payload = JSON.parse(value) as AnalysisEventPayload;
    return typeof payload.sequence === "number" &&
      typeof payload.analysis_id === "string"
      ? payload
      : null;
  } catch {
    return null;
  }
}

function selectionFromSnapshot(snapshot: AnalysisSnapshot): MediaSelection | null {
  if (!snapshot.source) return null;
  return {
    source_url: snapshot.source.source_url,
    title: snapshot.source.title,
    platform: snapshot.source.platform,
    duration: snapshot.source.duration_seconds,
    is_playlist_item: false,
    summary_supported: true,
    caption_languages: snapshot.source.transcript_language
      ? [snapshot.source.transcript_language]
      : [],
    transcript_strategy_hint:
      snapshot.source.transcript_source === "audio_transcription"
        ? "audio_transcription"
        : "captions",
    presets: [],
    selectionId: `analysis-${snapshot.id}`,
    presetId: "best",
  };
}

function setAnalysisQuery(id: string | null) {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  if (id) url.searchParams.set("analysis", id);
  else url.searchParams.delete("analysis");
  window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
}

export function useAnalysisJob(dictionary: BubbleDictionary) {
  const [source, setSource] = useState<MediaSelection | null>(null);
  const [job, setJob] = useState<AnalysisSnapshot | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [artifactData, setArtifactData] = useState<
    Partial<ArtifactPayloadMap>
  >({});
  const [eventsUrl, setEventsUrl] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const dataRef = useRef<Partial<ArtifactPayloadMap>>({});
  const loadingArtifacts = useRef(new Set<ArtifactKind>());

  const loadCompletedArtifact = useCallback(
    async <K extends ArtifactKind>(analysisId: string, kind: K) => {
      if (dataRef.current[kind] || loadingArtifacts.current.has(kind)) return;
      loadingArtifacts.current.add(kind);
      try {
        const payload = await getArtifact(analysisId, kind);
        dataRef.current = { ...dataRef.current, [kind]: payload };
        setArtifactData(dataRef.current);
      } catch (caught) {
        setError(
          normalizeApiError(caught, {
            code: "ARTIFACT_LOAD_FAILED",
            message: dictionary.errors.ARTIFACT_LOAD_FAILED,
          }),
        );
      } finally {
        loadingArtifacts.current.delete(kind);
      }
    },
    [dictionary.errors.ARTIFACT_LOAD_FAILED],
  );

  const applySnapshot = useCallback(
    (snapshot: AnalysisSnapshot) => {
      setError(null);
      setJob(snapshot);
      const restored = selectionFromSnapshot(snapshot);
      if (restored) setSource((current) => current ?? restored);
      for (const kind of Object.keys(snapshot.artifacts) as ArtifactKind[]) {
        if (snapshot.artifacts[kind].status === "completed") {
          void loadCompletedArtifact(snapshot.id, kind);
        }
      }
      if (
        snapshot.artifacts.summary.status === "completed" &&
        !result
      ) {
        void getAnalysisResult(snapshot.id)
          .then(setResult)
          .catch(() => {
            // Individual artifact views remain usable if canonical metadata expires first.
          });
      }
      if (terminalAnalysisStatuses.has(snapshot.status)) setEventsUrl(null);
    },
    [loadCompletedArtifact, result],
  );

  const refresh = useCallback(
    async (analysisId: string) => {
      const snapshot = await getAnalysis(analysisId);
      applySnapshot(snapshot);
      return snapshot;
    },
    [applySnapshot],
  );

  useTaskStream<AnalysisSnapshot, AnalysisEventPayload>({
    streamKey: eventsUrl && job ? job.id : null,
    eventsUrl,
    eventNames: analysisEvents,
    parse: parseAnalysisEvent,
    getSnapshot: () =>
      job ? refresh(job.id) : Promise.reject(new Error("Missing analysis")),
    onUpdate: applySnapshot,
    onEvent: (payload) => {
      void refresh(payload.analysis_id).catch(() => {
        // The stream reconnect path performs a bounded snapshot recovery.
      });
    },
    snapshotFromPayload: () => null,
    isTerminal: (snapshot) => terminalAnalysisStatuses.has(snapshot.status),
    onExhausted: () =>
      setError({
        code: "SSE_DISCONNECTED",
        message: dictionary.errors.SERVICE_OFFLINE,
        retryable: true,
      }),
  });

  const start = useCallback(
    async (
      item: MediaSelection,
      options: {
        detail: AnalysisDetail;
        outputLanguage: AnalysisLanguage;
      },
    ) => {
      setSource(item);
      setJob(null);
      setResult(null);
      dataRef.current = {};
      setArtifactData({});
      setEventsUrl(null);
      setError(null);
      setStarting(true);
      try {
        const response = await createAnalysis(item, options);
        setJob(response.analysis);
        setEventsUrl(
          terminalAnalysisStatuses.has(response.analysis.status)
            ? null
            : response.events_url,
        );
        setAnalysisQuery(response.analysis.id);
        applySnapshot(response.analysis);
      } catch (caught) {
        setError(
          normalizeApiError(caught, {
            code: "ANALYSIS_FAILED",
            message: dictionary.errors.ANALYSIS_FAILED,
          }),
        );
      } finally {
        setStarting(false);
      }
    },
    [applySnapshot, dictionary.errors.ANALYSIS_FAILED],
  );

  const restore = useCallback(
    async (analysisId: string) => {
      setStarting(true);
      setError(null);
      try {
        const snapshot = await refresh(analysisId);
        setAnalysisQuery(snapshot.id);
        if (!terminalAnalysisStatuses.has(snapshot.status)) {
          setEventsUrl(`/api/v1/analyses/${encodeURIComponent(snapshot.id)}/events`);
        }
        return true;
      } catch (caught) {
        setError(
          normalizeApiError(caught, {
            code: "ANALYSIS_RESTORE_FAILED",
            message: dictionary.errors.ANALYSIS_RESTORE_FAILED,
          }),
        );
        setAnalysisQuery(null);
        return false;
      } finally {
        setStarting(false);
      }
    },
    [dictionary.errors.ANALYSIS_RESTORE_FAILED, refresh],
  );

  const generateArtifact = useCallback(
    async (kind: ArtifactKind) => {
      if (!job) return;
      const current = job.artifacts[kind];
      if (current.status === "completed") {
        await loadCompletedArtifact(job.id, kind);
        return;
      }
      if (current.status === "queued" || current.status === "running") return;
      setError(null);
      try {
        const artifact = await requestArtifact(job.id, kind);
        setJob({
          ...job,
          status: artifact.status === "completed" ? job.status : "running",
          artifacts: { ...job.artifacts, [kind]: artifact },
        });
        if (artifact.status === "completed") {
          await loadCompletedArtifact(job.id, kind);
        } else {
          setEventsUrl(`/api/v1/analyses/${encodeURIComponent(job.id)}/events`);
        }
      } catch (caught) {
        setError(
          normalizeApiError(caught, {
            code: "ARTIFACT_FAILED",
            message: dictionary.errors.ARTIFACT_FAILED,
          }),
        );
        await refresh(job.id).catch(() => undefined);
      }
    },
    [
      dictionary.errors.ARTIFACT_FAILED,
      job,
      loadCompletedArtifact,
      refresh,
    ],
  );

  const cancel = useCallback(async () => {
    if (!job) return;
    setError(null);
    try {
      await cancelAnalysis(job.id);
      setEventsUrl(null);
      await refresh(job.id);
    } catch (caught) {
      setError(
        normalizeApiError(caught, {
          code: "ANALYSIS_CANCEL_FAILED",
          message: dictionary.errors.ANALYSIS_CANCEL_FAILED,
        }),
      );
    }
  }, [dictionary.errors.ANALYSIS_CANCEL_FAILED, job, refresh]);

  const retry = useCallback(
    (options: {
      detail: AnalysisDetail;
      outputLanguage: AnalysisLanguage;
    }) => {
      if (source) void start(source, options);
    },
    [source, start],
  );

  const reset = useCallback(() => {
    setSource(null);
    setJob(null);
    setResult(null);
    dataRef.current = {};
    setArtifactData({});
    setEventsUrl(null);
    setError(null);
    setStarting(false);
    setAnalysisQuery(null);
  }, []);

  return {
    source,
    job,
    result,
    artifactData,
    starting,
    error,
    start,
    restore,
    generateArtifact,
    cancel,
    retry,
    reset,
  };
}

export type AnalysisJobController = ReturnType<typeof useAnalysisJob>;
