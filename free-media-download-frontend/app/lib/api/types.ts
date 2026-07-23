export type Mode = "single" | "batch";
export type SourceMode = "url" | "upload";
export type OutputKind = "video" | "audio" | "original";
export type ItemStatus = "queued" | "running" | "ready" | "failed" | "cancelled";
export type JobStatus = "queued" | "running" | "completed" | "failed" | "cancelled";
export type TranscriptStrategy =
  | "captions"
  | "audio_transcription"
  | "unavailable"
  | "unsupported";
export type SummaryStage =
  | "queued"
  | "probing"
  | "fetching_captions"
  | "extracting_audio"
  | "preparing_audio"
  | "transcribing"
  | "parsing_transcript"
  | "summarizing"
  | "generating_chapters"
  | "finalizing"
  | "completed";

export type ApiError = {
  code: string;
  message: string;
  retryable?: boolean;
  itemIndex?: number;
};

export type Preset = {
  id: string;
  label: string;
  detail: string;
  kind: OutputKind;
  extension: string;
  height?: number | null;
};

export type MediaItem = {
  source_url: string;
  title: string;
  platform: string;
  duration?: number | null;
  thumbnail?: string | null;
  uploader?: string | null;
  is_playlist_item: boolean;
  summary_supported: boolean;
  caption_languages: string[];
  transcript_strategy_hint: TranscriptStrategy;
  presets: Preset[];
};

export type MediaSelection = MediaItem & {
  selectionId: string;
  presetId: string;
};

export type ProbeResponse = {
  items: MediaItem[];
  truncated: boolean;
};

export type ProbeFailure = {
  url: string;
  error: ApiError;
};

export type JobItem = {
  id: string;
  title: string;
  status: ItemStatus;
  progress: number;
  speed?: string | null;
  eta?: number | null;
  filename?: string | null;
  download_url?: string | null;
  error?: ApiError | null;
};

export type DownloadJobSnapshot = {
  id: string;
  status: JobStatus;
  created_at: string;
  expires_at?: string | null;
  items: JobItem[];
  bundle_url?: string | null;
  bundle_ready: boolean;
};

export type SummaryEvidence = {
  id: string;
  start_seconds: number;
  end_seconds: number;
  text: string;
};

export type SummaryOutlineItem = {
  timestamp_seconds: number;
  title: string;
  summary: string;
  evidence: SummaryEvidence[];
};

export type SummaryKeyPoint = {
  title: string;
  explanation: string;
  evidence: SummaryEvidence[];
};

export type SummaryResult = {
  source_url: string;
  title: string;
  platform: string;
  duration?: number | null;
  caption_language: string;
  caption_source:
    | "manual_caption"
    | "automatic_caption"
    | "audio_transcription";
  output_language: "en";
  overview: string;
  outline: SummaryOutlineItem[];
  key_points: SummaryKeyPoint[];
};

export type SummaryJobSnapshot = {
  id: string;
  status: JobStatus;
  stage: SummaryStage;
  progress: number;
  created_at: string;
  expires_at?: string | null;
  result?: SummaryResult | null;
  error?: ApiError | null;
};

export type DownloadEventPayload = {
  sequence: number;
  type: string;
  item_id?: string | null;
  job: DownloadJobSnapshot;
};

export type SummaryEventPayload = {
  sequence: number;
  type: string;
  summary: SummaryJobSnapshot;
};

export type CreateDownloadJobResponse = {
  job: DownloadJobSnapshot;
  events_url: string;
};

export type CreateSummaryJobResponse = {
  summary: SummaryJobSnapshot;
  events_url: string;
};

export type AnalysisStatus =
  | "queued"
  | "running"
  | "completed"
  | "partial"
  | "failed"
  | "cancelled";
export type AnalysisStage =
  | "queued"
  | "probing"
  | "acquiring_transcript"
  | "semantic_segmentation"
  | "canonical_analysis"
  | "generating_artifacts"
  | "validating"
  | "finalizing"
  | "completed";
export type AnalysisDetail = "concise" | "balanced" | "detailed";
export type AnalysisLanguage = "auto" | "en" | "zh-CN";
export type ArtifactKind =
  | "summary"
  | "chapters"
  | "mind_map"
  | "visual_story"
  | "dynamic_website"
  | "interactive_guide"
  | "transcript";
export type ArtifactStatus =
  | "not_started"
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export type AnalysisSource = {
  source_url: string;
  title: string;
  platform: string;
  duration_seconds?: number | null;
  transcript_source?:
    | "manual_caption"
    | "automatic_caption"
    | "audio_transcription"
    | null;
  transcript_language?: string | null;
};

export type GroundedText = {
  text: string;
  evidence_segment_ids: string[];
  start_seconds: number;
  end_seconds: number;
};

export type Topic = {
  id: string;
  label: string;
  summary: GroundedText;
};

export type Entity = {
  id: string;
  name: string;
  category: string;
  description: GroundedText;
};

export type Claim = {
  id: string;
  statement: GroundedText;
  importance: "low" | "medium" | "high";
};

export type Chapter = {
  id: string;
  title: string;
  start_seconds: number;
  end_seconds: number;
  summary: GroundedText;
  key_points: GroundedText[];
  evidence_segment_ids: string[];
};

export type GlossaryEntry = {
  id: string;
  term: string;
  definition: GroundedText;
};

export type SuggestedQuestion = {
  id: string;
  question: string;
  reason: GroundedText;
};

export type CanonicalContentAnalysis = {
  concise_summary: GroundedText;
  detailed_summary: GroundedText;
  topics: Topic[];
  entities: Entity[];
  claims: Claim[];
  chapters: Chapter[];
  key_points: GroundedText[];
  conclusions: GroundedText[];
  glossary: GlossaryEntry[];
  suggested_questions: SuggestedQuestion[];
  evidence_segment_ids: string[];
};

export type SummaryContent = {
  detail: AnalysisDetail;
  output_language: string;
  tldr: GroundedText;
  overview: GroundedText;
  key_takeaways: GroundedText[];
  important_facts: Claim[];
  conclusions: GroundedText[];
  suggested_questions: SuggestedQuestion[];
};

export type MindMapNode = {
  id: string;
  label: string;
  description: string;
  type: "root" | "topic" | "entity" | "claim" | "term";
  timestamp_seconds: number;
  evidence_segment_ids: string[];
  children: string[];
};

export type MindMap = {
  root_id: string;
  nodes: MindMapNode[];
  edges: {
    id: string;
    source_id: string;
    target_id: string;
    label: string;
  }[];
};

export type StoryFrame = {
  id: string;
  timestamp_seconds: number;
  image_url?: string | null;
  title: string;
  caption: string;
  narrative: string;
  related_chapter_id: string;
  evidence_segment_ids: string[];
};

export type VisualStory = {
  title: string;
  frames: StoryFrame[];
  warnings: string[];
};

export type WebsiteTheme =
  | "editorial"
  | "learning"
  | "documentary"
  | "product_brief";
export type WebsiteManifest = {
  language: "en" | "zh-CN";
  title: string;
  subtitle: string;
  theme: WebsiteTheme;
  hero: {
    eyebrow: string;
    title: string;
    subtitle: string;
    evidence_segment_ids: string[];
  };
  sections: {
    id: string;
    kind:
      | "overview"
      | "key_points"
      | "chapters"
      | "timeline"
      | "glossary"
      | "questions";
    title: string;
    item_ids: string[];
  }[];
  chapters: Chapter[];
  quotes: GroundedText[];
  timeline: {
    id: string;
    timestamp_seconds: number;
    title: string;
    text: string;
    evidence_segment_ids: string[];
  }[];
  glossary: GlossaryEntry[];
  callouts: GroundedText[];
  sources: { label: string; url: string }[];
};

export type InteractiveGuide = {
  title: string;
  audience: string;
  learning_objectives: GroundedText[];
  prerequisites: string[];
  estimated_time_minutes: number;
  steps: {
    id: string;
    title: string;
    explanation: GroundedText;
    timestamp_seconds: number;
    action: {
      kind: "review" | "reflect" | "compare" | "verify";
      instruction: string;
    };
    checkpoint: { prompt: string; success_criteria: string };
    evidence_segment_ids: string[];
  }[];
  checkpoints: { prompt: string; success_criteria: string }[];
  quiz: {
    id: string;
    question: string;
    choices: string[];
    correct_index: number;
    explanation: GroundedText;
  }[];
  glossary: GlossaryEntry[];
  next_actions: string[];
  safety_notice?: string | null;
};

export type TranscriptSegment = {
  id: string;
  start: number;
  end: number;
  text: string;
  speaker?: string | null;
  confidence?: number | null;
};

export type TranscriptDocument = {
  source_url: string;
  title: string;
  platform: string;
  duration?: number | null;
  language: string;
  source_kind:
    | "manual_caption"
    | "automatic_caption"
    | "audio_transcription";
  segments: TranscriptSegment[];
  detected_language?: string | null;
  requested_language?: string | null;
  provider?: string | null;
  confidence?: number | null;
  transcription_duration?: number | null;
  audio_duration?: number | null;
};

export type ArtifactPayloadMap = {
  summary: SummaryContent;
  chapters: Chapter[];
  mind_map: MindMap;
  visual_story: VisualStory;
  dynamic_website: WebsiteManifest;
  interactive_guide: InteractiveGuide;
  transcript: TranscriptDocument;
};

export type ArtifactView = {
  kind: ArtifactKind;
  status: ArtifactStatus;
  progress: number;
  error?: ApiError | null;
  generated_at?: string | null;
};

export type AnalysisSnapshot = {
  id: string;
  status: AnalysisStatus;
  stage: AnalysisStage;
  progress: number;
  source?: AnalysisSource | null;
  output_language: string;
  detail: AnalysisDetail;
  artifacts: Record<ArtifactKind, ArtifactView>;
  error?: ApiError | null;
  created_at: string;
  expires_at?: string | null;
};

export type AnalysisResult = {
  id: string;
  source: AnalysisSource;
  canonical_analysis: CanonicalContentAnalysis;
  generation_metadata: {
    schema_version: "2.0";
    output_language: string;
    detail: AnalysisDetail;
    transcript_sha256: string;
    semantic_unit_count: number;
    provider: string;
    model: string;
    warnings: string[];
    created_at: string;
  };
};

export type AnalysisEventPayload = {
  schema_version: "1.0";
  sequence: number;
  event: string;
  analysis_id: string;
  emitted_at: string;
  stage: AnalysisStage;
  overall_progress: number;
  artifact?: ArtifactView | null;
  error?: ApiError | null;
};

export type CreateAnalysisResponse = {
  analysis: AnalysisSnapshot;
  events_url: string;
};

export const terminalJobStatuses: JobStatus[] = ["completed", "failed", "cancelled"];

export function isTerminalStatus(status: JobStatus) {
  return terminalJobStatuses.includes(status);
}
