import type {
  ApiError,
  CreateDownloadJobResponse,
  CreateSummaryJobResponse,
  DownloadJobSnapshot,
  MediaSelection,
  ProbeResponse,
  SummaryJobSnapshot,
} from "./types";

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/$/, "");

export class ApiClientError extends Error implements ApiError {
  code: string;
  retryable?: boolean;
  itemIndex?: number;

  constructor(error: ApiError) {
    super(error.message);
    this.name = "ApiClientError";
    this.code = error.code;
    this.retryable = error.retryable;
    this.itemIndex = error.itemIndex;
  }
}

export function apiUrl(path: string) {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE}${normalized}`;
}

async function readError(response: Response): Promise<ApiError> {
  try {
    const value = (await response.json()) as Partial<ApiError>;
    return {
      code: value.code ?? "REQUEST_FAILED",
      message: value.message ?? "Bubble Video AI could not complete that request.",
      retryable: value.retryable,
      itemIndex: value.itemIndex,
    };
  } catch {
    return {
      code: "REQUEST_FAILED",
      message: "Bubble Video AI could not reach the media service.",
      retryable: true,
    };
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) throw new ApiClientError(await readError(response));
  return (await response.json()) as T;
}

async function requestVoid(path: string, init?: RequestInit) {
  const response = await fetch(apiUrl(path), init);
  if (!response.ok) throw new ApiClientError(await readError(response));
}

export function normalizeApiError(
  caught: unknown,
  fallback: Pick<ApiError, "code" | "message">,
): ApiError {
  if (caught instanceof ApiClientError) {
    return {
      code: caught.code,
      message: caught.message,
      retryable: caught.retryable,
      itemIndex: caught.itemIndex,
    };
  }
  return { ...fallback, retryable: true };
}

export function probeMedia(url: string) {
  return requestJson<ProbeResponse>("/api/v1/media/probe", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

export function createDownloadJob(items: MediaSelection[]) {
  return requestJson<CreateDownloadJobResponse>("/api/v1/jobs", {
    method: "POST",
    body: JSON.stringify({
      bundle: items.length > 1,
      items: items.map((item) => ({
        url: item.source_url,
        preset_id: item.presetId,
        title: item.title,
      })),
    }),
  });
}

export function getDownloadJob(id: string) {
  return requestJson<DownloadJobSnapshot>(`/api/v1/jobs/${encodeURIComponent(id)}`);
}

export function cancelDownloadJob(id: string) {
  return requestVoid(`/api/v1/jobs/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export function createSummaryJob(item: MediaSelection) {
  return requestJson<CreateSummaryJobResponse>("/api/v1/summaries", {
    method: "POST",
    body: JSON.stringify({
      url: item.source_url,
      title: item.title,
      output_language: "en",
    }),
  });
}

export function getSummaryJob(id: string) {
  return requestJson<SummaryJobSnapshot>(`/api/v1/summaries/${encodeURIComponent(id)}`);
}

export function cancelSummaryJob(id: string) {
  return requestVoid(`/api/v1/summaries/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}
