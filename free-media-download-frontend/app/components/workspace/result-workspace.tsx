"use client";

/* eslint-disable @next/next/no-img-element -- supported source thumbnails are displayed without proxying. */

import { useEffect, useState } from "react";
import { artifactExportUrl } from "../../lib/api/client";
import {
  downloadTextFile,
  durationLabel,
  safeFilename,
  timestampUrl,
} from "../../lib/api/format";
import type { ArtifactKind } from "../../lib/api/types";
import { DownloadPanel } from "../downloads/download-panel";
import { useBubbleExperience } from "../experience/experience-context";
import { BrandLogo } from "../marketing/brand-logo";
import { LanguageSwitcher } from "../marketing/language-switcher";
import { ActionButton } from "../ui/action-button";
import { AlertBanner } from "../ui/alert-banner";
import { EmptyState } from "../ui/empty-state";
import { ArtifactContent } from "./artifact-content";
import { ArtifactTabs } from "./artifact-tabs";

const coreKinds = new Set<ArtifactKind>(["summary", "chapters", "transcript"]);

export function ResultWorkspace() {
  const {
    locale,
    dictionary,
    download,
    analysis,
    analysisPreferences,
    showLanding,
  } = useBubbleExperience();
  const [active, setActive] = useState<ArtifactKind>("summary");
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">(
    "idle",
  );
  const source = analysis.source;
  const job = analysis.job;
  const artifact = job?.artifacts[active];
  const payload = analysis.artifactData[active];

  useEffect(() => {
    if (
      !job ||
      coreKinds.has(active) ||
      artifact?.status === "queued" ||
      artifact?.status === "running" ||
      artifact?.status === "completed"
    ) {
      return;
    }
    void analysis.generateArtifact(active);
  }, [active, analysis, artifact?.status, job]);

  if (!source) {
    return (
      <main className="workspace-empty-shell">
        <EmptyState
          eyebrow={dictionary.workspace.title}
          title={
            analysis.starting
              ? dictionary.workspace.restoring
              : dictionary.workspace.emptyTitle
          }
          description={
            analysis.error?.message ?? dictionary.workspace.emptyDescription
          }
          action={
            <ActionButton type="button" onClick={showLanding}>
              {dictionary.common.back}
            </ActionButton>
          }
        />
      </main>
    );
  }

  const canExport = artifact?.status === "completed" && Boolean(payload) && job;

  async function copyCurrentView() {
    if (!payload) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
      setCopyState("copied");
      window.setTimeout(() => setCopyState("idle"), 2200);
    } catch {
      setCopyState("failed");
    }
  }

  function exportClientJson() {
    if (!payload) return;
    downloadTextFile(
      `${safeFilename(source!.title)}-${active}.json`,
      JSON.stringify(payload, null, 2),
      "application/json",
    );
  }

  function retryCurrent() {
    if (!job || job.status === "failed" || job.status === "cancelled") {
      analysis.retry(analysisPreferences);
      return;
    }
    void analysis.generateArtifact(active);
  }

  const chapters = analysis.artifactData.chapters ?? [];
  const questions =
    analysis.result?.canonical_analysis.suggested_questions ?? [];

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
          {job ? (
            <div className="analysis-metadata">
              <span>{job.output_language}</span>
              <span>{job.detail}</span>
              <span>{job.status}</span>
            </div>
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
          aria-busy={!payload && artifact?.status !== "failed"}
        >
          <div className="workspace-toolbar">
            <div>
              <span
                className={`status-dot ${
                  artifact?.status === "completed"
                    ? "status-dot-success"
                    : "status-dot-brand"
                }`}
                aria-hidden="true"
              />
              {artifact
                ? dictionary.workspace.artifactStatuses[artifact.status]
                : dictionary.workspace.artifactStatuses.queued}
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
              {canExport ? (
                <a
                  className="action-button action-button-quiet"
                  href={artifactExportUrl(job.id, active, "markdown")}
                >
                  {dictionary.common.exportMarkdown}
                </a>
              ) : (
                <ActionButton type="button" variant="quiet" disabled>
                  {dictionary.common.exportMarkdown}
                </ActionButton>
              )}
              <ActionButton
                type="button"
                variant="quiet"
                onClick={exportClientJson}
                disabled={!canExport}
              >
                {dictionary.common.exportJson}
              </ActionButton>
            </div>
          </div>

          {analysis.error && job ? <AlertBanner error={analysis.error} /> : null}
          <section
            id={`panel-${active}`}
            role="tabpanel"
            aria-labelledby={`tab-${active}`}
            tabIndex={0}
          >
            <ArtifactContent
              active={active}
              job={job}
              data={analysis.artifactData}
              startError={analysis.error}
              sourceUrl={source.source_url}
              dictionary={dictionary}
              onRetry={retryCurrent}
              onCancel={() => void analysis.cancel()}
            />
          </section>
        </main>

        <aside className="workspace-context">
          <section>
            <p className="section-kicker">{dictionary.workspace.tabs.chapters}</p>
            {chapters.length ? (
              <ol>
                {chapters.map((chapter) => (
                  <li key={chapter.id}>
                    <button
                      type="button"
                      onClick={() => {
                        setActive("chapters");
                        requestAnimationFrame(() =>
                          document.getElementById(chapter.id)?.focus(),
                        );
                      }}
                    >
                      <span>{durationLabel(chapter.start_seconds)}</span>
                      <strong>{chapter.title}</strong>
                    </button>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="context-muted">{dictionary.workspace.waitingForChapters}</p>
            )}
          </section>
          <section>
            <p className="section-kicker">{dictionary.workspace.suggested}</p>
            <ul className="suggested-list">
              {(questions.length
                ? questions.map((item) => item.question)
                : dictionary.workspace.suggestedItems
              ).map((item) => (
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
