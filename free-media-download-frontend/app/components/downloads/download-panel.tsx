"use client";

import { apiUrl } from "../../lib/api/client";
import type { DownloadJobController } from "../../hooks/use-download-job";
import type { BubbleDictionary } from "../../lib/i18n/messages/en-US";
import { ActionButton } from "../ui/action-button";
import { ProgressBar } from "../ui/progress-bar";

function statusLabel(status: string, locale: "en-US" | "zh-CN") {
  if (locale === "zh-CN") {
    const labels: Record<string, string> = {
      queued: "排队中",
      running: "处理中",
      ready: "可下载",
      completed: "已完成",
      failed: "失败",
      cancelled: "已取消",
    };
    return labels[status] ?? status;
  }
  return status.replaceAll("_", " ");
}

export function DownloadPanel({
  controller,
  dictionary,
  locale,
  compact = false,
}: {
  controller: DownloadJobController;
  dictionary: BubbleDictionary;
  locale: "en-US" | "zh-CN";
  compact?: boolean;
}) {
  const { items, job, busy, startDownload, cancelJob, reset } = controller;
  if (!items.length && !job) return null;

  return (
    <section className={`download-panel ${compact ? "download-panel-compact" : ""}`}>
      <div className="download-panel-head">
        <div>
          <p className="section-kicker">{dictionary.media.downloadTitle}</p>
          <h3>{job ? statusLabel(job.status, locale) : dictionary.media.downloadTitle}</h3>
        </div>
        {job ? (
          <span className={`status-badge status-${job.status}`}>
            {statusLabel(job.status, locale)}
          </span>
        ) : null}
      </div>

      {!job ? (
        <>
          <p className="download-panel-description">
            {dictionary.media.downloadDescription}
          </p>
          <ActionButton
            type="button"
            variant="secondary"
            onClick={() => void startDownload()}
            loading={busy}
          >
            {busy ? dictionary.media.downloading : dictionary.media.download}
          </ActionButton>
        </>
      ) : (
        <>
          <div className="download-job-list">
            {job.items.map((item) => (
              <article key={item.id}>
                <div className="download-job-meta">
                  <strong>{item.title}</strong>
                  <span>
                    {item.status === "running"
                      ? `${Math.round(item.progress)}%`
                      : statusLabel(item.status, locale)}
                  </span>
                </div>
                <ProgressBar
                  value={item.status === "ready" ? 100 : item.progress}
                  label={`${item.title} ${statusLabel(item.status, locale)}`}
                />
                <div className="download-job-detail">
                  <span>
                    {item.error?.message ??
                      (item.speed
                        ? `${item.speed}${item.eta ? ` · ${item.eta}s` : ""}`
                        : "")}
                  </span>
                  {item.download_url ? (
                    <a href={apiUrl(item.download_url)} download>
                      {dictionary.media.downloadFile}
                    </a>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
          <div className="download-job-actions">
            {job.bundle_url ? (
              <a className="download-link-button" href={apiUrl(job.bundle_url)} download>
                {dictionary.media.downloadAll}
              </a>
            ) : null}
            {!["completed", "failed", "cancelled"].includes(job.status) ? (
              <ActionButton
                type="button"
                variant="quiet"
                onClick={() => void cancelJob()}
              >
                {dictionary.media.cancelDownload}
              </ActionButton>
            ) : (
              <ActionButton type="button" variant="quiet" onClick={reset}>
                {dictionary.media.startAnother}
              </ActionButton>
            )}
          </div>
        </>
      )}
    </section>
  );
}
