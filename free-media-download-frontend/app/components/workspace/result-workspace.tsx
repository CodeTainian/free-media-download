"use client";

/* eslint-disable @next/next/no-img-element -- source thumbnails are displayed directly from supported public media hosts. */

import { useMemo, useState } from "react";
import {
  chaptersMarkdown,
  downloadTextFile,
  durationLabel,
  safeFilename,
  summaryMarkdown,
  timestampUrl,
} from "../../lib/api/format";
import { createWorkspaceModel } from "../../lib/workspace/adapter";
import type { ArtifactKind } from "../../lib/workspace/types";
import { DownloadPanel } from "../downloads/download-panel";
import { useBubbleExperience } from "../experience/experience-context";
import { BrandLogo } from "../marketing/brand-logo";
import { LanguageSwitcher } from "../marketing/language-switcher";
import { ActionButton } from "../ui/action-button";
import { AlertBanner } from "../ui/alert-banner";
import { EmptyState } from "../ui/empty-state";
import { ProgressBar } from "../ui/progress-bar";
import { ContentSkeleton } from "../ui/skeleton";
import { ArtifactTabs } from "./artifact-tabs";
import { ChapterView } from "./views/chapter-view";
import { SummaryView } from "./views/summary-view";

export function ResultWorkspace() {
  const { locale, dictionary, download, summary, showLanding } =
    useBubbleExperience();
  const [active, setActive] = useState<ArtifactKind>("summary");
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const source = summary.source;

  const model = useMemo(
    () =>
      source
        ? createWorkspaceModel(source, summary.job, summary.error, dictionary)
        : null,
    [dictionary, source, summary.error, summary.job],
  );

  if (!source || !model) {
    return (
      <main className="workspace-empty-shell">
        <EmptyState
          eyebrow={dictionary.workspace.title}
          title={dictionary.workspace.emptyTitle}
          description={dictionary.workspace.emptyDescription}
          action={
            <ActionButton type="button" onClick={showLanding}>
              {dictionary.common.back}
            </ActionButton>
          }
        />
      </main>
    );
  }

  const artifact = model.artifacts[active];
  const result = summary.job?.result ?? null;
  const stage = summary.job?.stage ?? "queued";
  const stageCopy = dictionary.workspace.stages[stage];
  const canExport =
    Boolean(result) && (active === "summary" || active === "chapters");

  async function copyCurrentView() {
    if (!result || !canExport) return;
    try {
      await navigator.clipboard.writeText(
        active === "chapters" ? chaptersMarkdown(result) : summaryMarkdown(result),
      );
      setCopyState("copied");
      window.setTimeout(() => setCopyState("idle"), 2200);
    } catch {
      setCopyState("failed");
    }
  }

  function exportCurrentView(format: "markdown" | "json") {
    if (!result || !canExport) return;
    const base = safeFilename(result.title);
    const suffix = active === "chapters" ? "chapters" : "summary";
    if (format === "json") {
      const value = active === "chapters" ? result.outline : result;
      downloadTextFile(
        `${base}-${suffix}.json`,
        JSON.stringify(value, null, 2),
        "application/json",
      );
      return;
    }
    downloadTextFile(
      `${base}-${suffix}.md`,
      active === "chapters" ? chaptersMarkdown(result) : summaryMarkdown(result),
      "text/markdown",
    );
  }

  return (
    <div className="workspace-shell">
      <a className="skip-link" href="#workspace-content">
        {dictionary.common.skipToContent}
      </a>
      <header className="workspace-header">
        <BrandLogo locale={locale} />
        <div className="workspace-name">
          <span>{dictionary.workspace.title}</span>
          <small>Bubble Video AI</small>
        </div>
        <div className="workspace-header-actions">
          <LanguageSwitcher locale={locale} dictionary={dictionary} />
          <ActionButton type="button" variant="quiet" onClick={showLanding}>
            ← {dictionary.common.back}
          </ActionButton>
        </div>
      </header>

      <ArtifactTabs active={active} onChange={setActive} dictionary={dictionary} />

      <div className="workspace-grid">
        <aside className="workspace-source">
          <p className="section-kicker">{dictionary.workspace.sourceInfo}</p>
          {source.thumbnail ? (
            <img src={source.thumbnail} alt="" referrerPolicy="no-referrer" />
          ) : (
            <div className="workspace-thumbnail-placeholder" aria-hidden="true">
              ▶
            </div>
          )}
          <h1>{source.title}</h1>
          <div className="source-meta">
            <span>{source.platform}</span>
            <span>{durationLabel(source.duration)}</span>
            {source.uploader ? <span>{source.uploader}</span> : null}
          </div>
          <a
            className="source-link"
            href={timestampUrl(source.source_url, 0)}
            target="_blank"
            rel="noreferrer"
          >
            {dictionary.common.openSource} ↗
          </a>
          <div className="retention-note">
            <span aria-hidden="true">◷</span>
            <p>{dictionary.workspace.retention}</p>
          </div>
          {locale === "zh-CN" ? (
            <div className="language-notice">{dictionary.workspace.englishNotice}</div>
          ) : null}
          <DownloadPanel
            controller={download}
            dictionary={dictionary}
            locale={locale}
            compact
          />
        </aside>

        <main
          id="workspace-content"
          className="workspace-content"
          aria-live="polite"
          aria-busy={artifact.status === "loading"}
        >
          <div className="workspace-toolbar">
            <div>
              <span className="status-dot status-dot-success" aria-hidden="true" />
              {stageCopy[0]}
            </div>
            <div className="workspace-export-actions">
              <ActionButton
                type="button"
                variant="quiet"
                onClick={() => void copyCurrentView()}
                disabled={!canExport}
              >
                {copyState === "copied"
                  ? dictionary.common.copied
                  : copyState === "failed"
                    ? dictionary.common.copyFailed
                    : dictionary.workspace.copyView}
              </ActionButton>
              <ActionButton
                type="button"
                variant="quiet"
                onClick={() => exportCurrentView("markdown")}
                disabled={!canExport}
              >
                {dictionary.common.exportMarkdown}
              </ActionButton>
              <ActionButton
                type="button"
                variant="quiet"
                onClick={() => exportCurrentView("json")}
                disabled={!canExport}
              >
                {dictionary.common.exportJson}
              </ActionButton>
            </div>
          </div>

          <section
            id={`panel-${active}`}
            role="tabpanel"
            aria-labelledby={`tab-${active}`}
            tabIndex={0}
          >
            {summary.error && summary.job && !["failed", "cancelled"].includes(summary.job.status) ? (
              <AlertBanner error={summary.error} />
            ) : null}
            {artifact.status === "loading" ? (
              <div className="analysis-loading">
                <div className="analysis-loading-copy">
                  <p className="section-kicker">{dictionary.workspace.status}</p>
                  <h2>{stageCopy[0]}</h2>
                  <p>{stageCopy[1]}</p>
                </div>
                <ProgressBar
                  value={summary.job?.progress ?? 0}
                  label={dictionary.workspace.status}
                />
                <div className="progress-meta">
                  <span>{Math.round(summary.job?.progress ?? 0)}%</span>
                  <span>{dictionary.common.temporary}</span>
                </div>
                <ContentSkeleton />
                {summary.job ? (
                  <ActionButton
                    type="button"
                    variant="quiet"
                    onClick={() => void summary.cancel()}
                  >
                    {dictionary.workspace.cancelAnalysis}
                  </ActionButton>
                ) : null}
              </div>
            ) : null}
            {artifact.status === "failed" ? (
              <EmptyState
                eyebrow={artifact.code.replaceAll("_", " ")}
                title={dictionary.workspace.failedTitle}
                description={artifact.message}
                action={
                  artifact.retryable ? (
                    <ActionButton type="button" onClick={summary.retry}>
                      {dictionary.common.retry}
                    </ActionButton>
                  ) : undefined
                }
              />
            ) : null}
            {artifact.status === "empty" ? (
              <EmptyState
                eyebrow={dictionary.workspace.title}
                title={dictionary.workspace.emptyTitle}
                description={dictionary.workspace.emptyDescription}
                action={
                  <ActionButton type="button" onClick={summary.retry}>
                    {dictionary.common.retry}
                  </ActionButton>
                }
              />
            ) : null}
            {artifact.status === "backend-required" ? (
              <EmptyState
                eyebrow={dictionary.common.backendRequired}
                title={dictionary.workspace.unavailableTitle}
                description={artifact.reason}
              />
            ) : null}
            {artifact.status === "completed" && result && active === "summary" ? (
              <SummaryView result={result} dictionary={dictionary} />
            ) : null}
            {artifact.status === "completed" && result && active === "chapters" ? (
              <ChapterView result={result} dictionary={dictionary} />
            ) : null}
          </section>
        </main>

        <aside className="workspace-context">
          <section>
            <p className="section-kicker">{dictionary.workspace.tabs.chapters}</p>
            {result?.outline.length ? (
              <ol>
                {result.outline.map((chapter) => (
                  <li key={`${chapter.timestamp_seconds}-${chapter.title}`}>
                    <button type="button" onClick={() => setActive("chapters")}>
                      <span>{durationLabel(chapter.timestamp_seconds)}</span>
                      <strong>{chapter.title}</strong>
                    </button>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="context-muted">{stageCopy[1]}</p>
            )}
          </section>
          <section>
            <p className="section-kicker">{dictionary.workspace.suggested}</p>
            <ul className="suggested-list">
              {dictionary.workspace.suggestedItems.map((item) => (
                <li key={item}>
                  <span aria-hidden="true">?</span>
                  {item}
                </li>
              ))}
            </ul>
          </section>
        </aside>
      </div>

      <div className="workspace-mobile-actions">
        <ActionButton type="button" variant="quiet" onClick={showLanding}>
          ← {dictionary.common.back}
        </ActionButton>
        <ActionButton
          type="button"
          onClick={() => void copyCurrentView()}
          disabled={!canExport}
        >
          {dictionary.common.copy}
        </ActionButton>
      </div>
      <div className="sr-only" aria-live="polite">
        {dictionary.workspace.liveRegion}: {dictionary.workspace.tabs[active]}
      </div>
    </div>
  );
}
