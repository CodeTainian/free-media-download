import type { MediaSelection, SummaryResult } from "../api/types";

export type ArtifactKind =
  | "summary"
  | "chapters"
  | "mind_map"
  | "visual_story"
  | "dynamic_website"
  | "interactive_guide"
  | "transcript";

export type ArtifactState<T> =
  | { status: "idle" }
  | { status: "loading"; progress: number }
  | { status: "empty" }
  | { status: "failed"; code: string; message: string; retryable: boolean }
  | { status: "completed"; data: T }
  | { status: "backend-required"; reason: string };

export type WorkspaceModel = {
  source: MediaSelection;
  artifacts: {
    summary: ArtifactState<SummaryResult>;
    chapters: ArtifactState<SummaryResult["outline"]>;
    mind_map: ArtifactState<never>;
    visual_story: ArtifactState<never>;
    dynamic_website: ArtifactState<never>;
    interactive_guide: ArtifactState<never>;
    transcript: ArtifactState<never>;
  };
};
