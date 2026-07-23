import type { SummaryJobSnapshot } from "../api/types";
import type { BubbleDictionary } from "../i18n/messages/en-US";
import type { WorkspaceModel } from "./types";
import type { MediaSelection } from "../api/types";

export function createWorkspaceModel(
  source: MediaSelection,
  job: SummaryJobSnapshot | null,
  startError: { code: string; message: string; retryable?: boolean } | null,
  dictionary: BubbleDictionary,
): WorkspaceModel {
  const future = {
    status: "backend-required" as const,
    reason: dictionary.workspace.unavailableDescription,
  };
  const transcript = {
    status: "backend-required" as const,
    reason: dictionary.workspace.transcriptUnavailable,
  };

  if (startError) {
    const failed = {
      status: "failed" as const,
      code: startError.code,
      message: startError.message,
      retryable: startError.retryable !== false,
    };
    return {
      source,
      artifacts: {
        summary: failed,
        chapters: failed,
        mind_map: future,
        visual_story: future,
        dynamic_website: future,
        interactive_guide: future,
        transcript,
      },
    };
  }

  if (!job || ["queued", "running"].includes(job.status)) {
    const loading = { status: "loading" as const, progress: job?.progress ?? 0 };
    return {
      source,
      artifacts: {
        summary: loading,
        chapters: loading,
        mind_map: future,
        visual_story: future,
        dynamic_website: future,
        interactive_guide: future,
        transcript,
      },
    };
  }

  if (job.status === "failed" || job.status === "cancelled") {
    const failed = {
      status: "failed" as const,
      code: job.error?.code ?? job.status.toUpperCase(),
      message:
        job.error?.message ??
        (job.status === "cancelled"
          ? dictionary.workspace.analysisCancelled
          : dictionary.workspace.failedTitle),
      retryable: job.status === "failed" && job.error?.retryable !== false,
    };
    return {
      source,
      artifacts: {
        summary: failed,
        chapters: failed,
        mind_map: future,
        visual_story: future,
        dynamic_website: future,
        interactive_guide: future,
        transcript,
      },
    };
  }

  if (!job.result) {
    const empty = { status: "empty" as const };
    return {
      source,
      artifacts: {
        summary: empty,
        chapters: empty,
        mind_map: future,
        visual_story: future,
        dynamic_website: future,
        interactive_guide: future,
        transcript,
      },
    };
  }

  return {
    source,
    artifacts: {
      summary: { status: "completed", data: job.result },
      chapters: job.result.outline.length
        ? { status: "completed", data: job.result.outline }
        : { status: "empty" },
      mind_map: future,
      visual_story: future,
      dynamic_website: future,
      interactive_guide: future,
      transcript,
    },
  };
}
