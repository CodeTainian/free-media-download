import { describe, expect, it } from "vitest";
import { createWorkspaceModel } from "../app/lib/workspace/adapter";
import { enUS } from "../app/lib/i18n/messages/en-US";
import type { MediaSelection, SummaryJobSnapshot } from "../app/lib/api/types";

const source: MediaSelection = {
  source_url: "https://www.youtube.com/watch?v=test",
  title: "Test video",
  platform: "YouTube",
  is_playlist_item: false,
  summary_supported: true,
  caption_languages: ["en"],
  transcript_strategy_hint: "captions",
  presets: [{ id: "best", label: "Best", detail: "", kind: "video", extension: "mp4" }],
  selectionId: "one",
  presetId: "best",
};

const result = {
  source_url: source.source_url,
  title: source.title,
  platform: "YouTube",
  caption_language: "en",
  caption_source: "manual_caption" as const,
  output_language: "en" as const,
  overview: "Overview",
  outline: [
    {
      timestamp_seconds: 12,
      title: "Chapter",
      summary: "Chapter summary",
      evidence: [{ id: "s1", start_seconds: 12, end_seconds: 18, text: "Evidence" }],
    },
  ],
  key_points: [
    {
      title: "Point",
      explanation: "Explanation",
      evidence: [{ id: "s1", start_seconds: 12, end_seconds: 18, text: "Evidence" }],
    },
  ],
};

function job(overrides: Partial<SummaryJobSnapshot>): SummaryJobSnapshot {
  return {
    id: "summary",
    status: "running",
    stage: "summarizing",
    progress: 56,
    created_at: new Date(0).toISOString(),
    ...overrides,
  };
}

describe("createWorkspaceModel", () => {
  it("maps loading, failed, empty, completed and backend-required states", () => {
    const loading = createWorkspaceModel(source, job({}), null, enUS);
    expect(loading.artifacts.summary).toEqual({ status: "loading", progress: 56 });

    const failed = createWorkspaceModel(
      source,
      job({
        status: "failed",
        error: { code: "SUMMARY_FAILED", message: "Failed", retryable: true },
      }),
      null,
      enUS,
    );
    expect(failed.artifacts.summary.status).toBe("failed");

    const empty = createWorkspaceModel(
      source,
      job({ status: "completed", stage: "completed", progress: 100 }),
      null,
      enUS,
    );
    expect(empty.artifacts.summary.status).toBe("empty");

    const completed = createWorkspaceModel(
      source,
      job({
        status: "completed",
        stage: "completed",
        progress: 100,
        result,
      }),
      null,
      enUS,
    );
    expect(completed.artifacts.summary.status).toBe("completed");
    expect(completed.artifacts.chapters.status).toBe("completed");
    expect(completed.artifacts.mind_map.status).toBe("backend-required");
    expect(completed.artifacts.transcript.status).toBe("backend-required");
  });
});
