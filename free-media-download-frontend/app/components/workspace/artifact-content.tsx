import type {
  AnalysisSnapshot,
  ApiError,
  ArtifactKind,
  ArtifactPayloadMap,
} from "../../lib/api/types";
import type { BubbleDictionary } from "../../lib/i18n/messages/en-US";
import { ActionButton } from "../ui/action-button";
import { EmptyState } from "../ui/empty-state";
import { ProgressBar } from "../ui/progress-bar";
import { ContentSkeleton } from "../ui/skeleton";
import { ChapterView } from "./views/chapter-view";
import { DynamicWebsiteView } from "./views/dynamic-website-view";
import { InteractiveGuideView } from "./views/interactive-guide-view";
import { MindMapView } from "./views/mind-map-view";
import { SummaryView } from "./views/summary-view";
import { TranscriptView } from "./views/transcript-view";
import { VisualStoryView } from "./views/visual-story-view";

export function ArtifactContent({
  active,
  job,
  data,
  startError,
  sourceUrl,
  dictionary,
  onRetry,
  onCancel,
}: {
  active: ArtifactKind;
  job: AnalysisSnapshot | null;
  data: Partial<ArtifactPayloadMap>;
  startError: ApiError | null;
  sourceUrl: string;
  dictionary: BubbleDictionary;
  onRetry: () => void;
  onCancel: () => void;
}) {
  const artifact = job?.artifacts[active];
  const payload = data[active];
  const isLoading =
    !startError &&
    (!job ||
      !artifact ||
      artifact.status === "not_started" ||
      artifact.status === "queued" ||
      artifact.status === "running" ||
      (artifact.status === "completed" && !payload));
  const error = startError ?? artifact?.error ?? null;

  if (isLoading) {
    const stage = job?.stage ?? "queued";
    const stageCopy = dictionary.workspace.stages[stage];
    return (
      <div className="analysis-loading">
        <div className="analysis-loading-copy">
          <p className="section-kicker">{dictionary.workspace.status}</p>
          <h2>{stageCopy[0]}</h2>
          <p>{stageCopy[1]}</p>
        </div>
        <ProgressBar
          value={artifact?.progress ?? job?.progress ?? 0}
          label={dictionary.workspace.status}
        />
        <ContentSkeleton />
        {job && ["queued", "running"].includes(job.status) ? (
          <ActionButton type="button" variant="quiet" onClick={onCancel}>
            {dictionary.workspace.cancelAnalysis}
          </ActionButton>
        ) : null}
      </div>
    );
  }

  if (error || artifact?.status === "failed" || artifact?.status === "cancelled") {
    return (
      <EmptyState
        eyebrow={(error?.code ?? artifact?.status ?? "FAILED").replaceAll("_", " ")}
        title={dictionary.workspace.failedTitle}
        description={
          error?.message ??
          (artifact?.status === "cancelled"
            ? dictionary.workspace.analysisCancelled
            : dictionary.workspace.emptyDescription)
        }
        action={
          error?.retryable !== false && artifact?.status !== "cancelled" ? (
            <ActionButton type="button" onClick={onRetry}>
              {dictionary.common.retry}
            </ActionButton>
          ) : undefined
        }
      />
    );
  }

  if (!payload) {
    return (
      <EmptyState
        eyebrow={dictionary.workspace.title}
        title={dictionary.workspace.emptyTitle}
        description={dictionary.workspace.emptyDescription}
        action={
          <ActionButton type="button" onClick={onRetry}>
            {dictionary.common.retry}
          </ActionButton>
        }
      />
    );
  }

  if (active === "summary") {
    return (
      <SummaryView
        summary={payload as ArtifactPayloadMap["summary"]}
        sourceUrl={sourceUrl}
        dictionary={dictionary}
      />
    );
  }
  if (active === "chapters") {
    return (
      <ChapterView
        chapters={payload as ArtifactPayloadMap["chapters"]}
        sourceUrl={sourceUrl}
        dictionary={dictionary}
      />
    );
  }
  if (active === "mind_map") {
    return (
      <MindMapView
        map={payload as ArtifactPayloadMap["mind_map"]}
        sourceUrl={sourceUrl}
        dictionary={dictionary}
      />
    );
  }
  if (active === "visual_story") {
    return (
      <VisualStoryView
        story={payload as ArtifactPayloadMap["visual_story"]}
        sourceUrl={sourceUrl}
        dictionary={dictionary}
      />
    );
  }
  if (active === "dynamic_website" && job) {
    return (
      <DynamicWebsiteView
        analysisId={job.id}
        manifest={payload as ArtifactPayloadMap["dynamic_website"]}
        dictionary={dictionary}
      />
    );
  }
  if (active === "interactive_guide" && job) {
    return (
      <InteractiveGuideView
        analysisId={job.id}
        guide={payload as ArtifactPayloadMap["interactive_guide"]}
        sourceUrl={sourceUrl}
        dictionary={dictionary}
      />
    );
  }
  return (
    <TranscriptView
      transcript={payload as ArtifactPayloadMap["transcript"]}
      sourceUrl={sourceUrl}
      dictionary={dictionary}
    />
  );
}
