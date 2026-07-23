import type { SummaryResult } from "./types";

export function durationLabel(seconds?: number | null, unknown = "Unknown") {
  if (seconds === undefined || seconds === null) return unknown;
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = total % 60;
  return hours
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`
    : `${minutes}:${String(rest).padStart(2, "0")}`;
}

export function timestampUrl(sourceUrl: string, seconds: number) {
  try {
    const url = new URL(sourceUrl);
    const time = Math.max(0, Math.floor(seconds));
    url.searchParams.set("t", url.hostname.includes("youtu") ? `${time}s` : String(time));
    return url.toString();
  } catch {
    return sourceUrl;
  }
}

export function summaryMarkdown(result: SummaryResult) {
  const chapters = result.outline
    .map(
      (item) =>
        `### ${durationLabel(item.timestamp_seconds)} — ${item.title}\n\n${item.summary}`,
    )
    .join("\n\n");
  const points = result.key_points
    .map((item) => `- **${item.title}:** ${item.explanation}`)
    .join("\n");
  return `# ${result.title}\n\n## Overview\n\n${result.overview}\n\n## Chapters\n\n${chapters}\n\n## Key points\n\n${points}\n\nSource: ${result.source_url}\n`;
}

export function chaptersMarkdown(result: SummaryResult) {
  return `# ${result.title} — Chapters\n\n${result.outline
    .map(
      (item) =>
        `## ${durationLabel(item.timestamp_seconds)} — ${item.title}\n\n${item.summary}\n\n[Open source](${timestampUrl(result.source_url, item.timestamp_seconds)})`,
    )
    .join("\n\n")}\n`;
}

export function downloadTextFile(filename: string, value: string, type = "text/plain") {
  const blob = new Blob([value], { type: `${type};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function safeFilename(value: string) {
  return (
    value
      .trim()
      .replace(/[^\p{L}\p{N}._-]+/gu, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 80) || "bubble-video-ai"
  );
}
