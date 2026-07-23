export type Mode = "single" | "batch";
export type SourceMode = "url" | "upload";
export type OutputKind = "video" | "audio" | "original";
export type ItemStatus = "queued" | "running" | "ready" | "failed" | "cancelled";
export type JobStatus = "queued" | "running" | "completed" | "failed" | "cancelled";
export type TranscriptStrategy = "captions" | "unavailable" | "unsupported";
export type SummaryStage =
  | "queued"
  | "fetching_captions"
  | "parsing"
  | "summarizing"
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
  caption_source: "manual_caption" | "automatic_caption";
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

export const terminalJobStatuses: JobStatus[] = ["completed", "failed", "cancelled"];

export function isTerminalStatus(status: JobStatus) {
  return terminalJobStatuses.includes(status);
}
