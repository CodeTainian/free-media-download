"use client";

import { useMemo, useState } from "react";
import type { ApiError, SourceMode } from "../../lib/api/types";
import { detectPlatform } from "../../lib/media/platform";
import { useBubbleExperience } from "../experience/experience-context";
import { DownloadPanel } from "../downloads/download-panel";
import { MediaResults } from "../media/media-results";
import { ActionButton } from "../ui/action-button";
import { AlertBanner } from "../ui/alert-banner";

const uploadEnabled = process.env.NEXT_PUBLIC_ENABLE_UPLOAD === "true";

export function BubbleInput() {
  const {
    locale,
    dictionary,
    download,
    analysis,
    analysisPreferences,
    setAnalysisDetail,
    setAnalysisLanguage,
    startAnalysis,
    openWorkspace,
  } = useBubbleExperience();
  const [sourceMode, setSourceMode] = useState<SourceMode>("url");
  const [clipboardError, setClipboardError] = useState<ApiError | null>(null);
  const platform = useMemo(() => detectPlatform(download.input), [download.input]);

  async function pasteFromClipboard() {
    try {
      const value = await navigator.clipboard.readText();
      if (value) download.setInput(value);
      setClipboardError(null);
    } catch {
      setClipboardError({
        code: "CLIPBOARD_BLOCKED",
        message: dictionary.errors.CLIPBOARD_BLOCKED,
      });
    }
  }

  return (
    <section className="bubble-input-card" id="bubble-input" aria-labelledby="input-title">
      <div className="bubble-input-heading">
        <div>
          <p className="section-kicker">Bubble Input</p>
          <h2 id="input-title">{dictionary.input.title}</h2>
          <p>{dictionary.input.subtitle}</p>
        </div>
        <span className="privacy-chip">
          <span aria-hidden="true">●</span>
          {dictionary.hero.proofs[1]}
        </span>
      </div>

      <div className="source-mode-tabs" aria-label={dictionary.input.title}>
        <button
          type="button"
          aria-pressed={sourceMode === "url"}
          className={sourceMode === "url" ? "active" : ""}
          onClick={() => setSourceMode("url")}
        >
          {dictionary.input.url}
        </button>
        <button
          type="button"
          aria-pressed={sourceMode === "upload"}
          className={sourceMode === "upload" ? "active" : ""}
          onClick={() => setSourceMode("upload")}
        >
          {dictionary.input.upload}
          <span>{dictionary.common.preview}</span>
        </button>
      </div>

      {sourceMode === "upload" ? (
        <div className="upload-preview" role="status">
          <div className="upload-preview-icon" aria-hidden="true">
            ↑
          </div>
          <div>
            <strong>{dictionary.input.uploadTitle}</strong>
            <p>{dictionary.input.uploadDescription}</p>
          </div>
          <span>{uploadEnabled ? dictionary.common.comingSoon : dictionary.common.preview}</span>
        </div>
      ) : (
        <>
          <fieldset className="mode-switch">
            <legend className="sr-only">{dictionary.input.title}</legend>
            <button
              type="button"
              aria-pressed={download.mode === "single"}
              className={download.mode === "single" ? "active" : ""}
              onClick={() => download.changeMode("single")}
            >
              {dictionary.input.single}
            </button>
            <button
              type="button"
              aria-pressed={download.mode === "batch"}
              className={download.mode === "batch" ? "active" : ""}
              onClick={() => download.changeMode("batch")}
            >
              {dictionary.input.batch}
            </button>
          </fieldset>

          <div className="media-url-field">
            {download.mode === "single" ? (
              <input
                id="media-url"
                type="url"
                aria-label={dictionary.input.urlLabel}
                value={download.input}
                onChange={(event) => download.setInput(event.target.value)}
                placeholder={dictionary.input.urlPlaceholder}
                aria-invalid={download.error?.code === "MISSING_URL"}
              />
            ) : (
              <textarea
                id="media-urls"
                aria-label={dictionary.input.batchLabel}
                value={download.input}
                onChange={(event) => download.setInput(event.target.value)}
                placeholder={dictionary.input.batchPlaceholder}
                rows={4}
                aria-invalid={download.error?.code === "MISSING_URL"}
              />
            )}
            <button type="button" onClick={() => void pasteFromClipboard()}>
              {dictionary.input.paste}
            </button>
          </div>

          <div className="input-context">
            <span>
              {platform
                ? `${dictionary.input.platformDetected}: ${platform}`
                : dictionary.input.unknownPlatform}
            </span>
            <span>
              {download.mode === "batch"
                ? `${download.urls.length}/10 · ${dictionary.input.batchLimit}`
                : dictionary.common.temporary}
            </span>
          </div>

          <div
            className="analysis-options"
            aria-label={dictionary.input.analysisOptions}
          >
            <label>
              <span>{dictionary.input.detail}</span>
              <select
                value={analysisPreferences.detail}
                onChange={(event) =>
                  setAnalysisDetail(
                    event.target.value as typeof analysisPreferences.detail,
                  )
                }
              >
                <option value="concise">{dictionary.input.concise}</option>
                <option value="balanced">{dictionary.input.balanced}</option>
                <option value="detailed">{dictionary.input.detailed}</option>
              </select>
            </label>
            <label>
              <span>{dictionary.input.outputLanguage}</span>
              <select
                value={analysisPreferences.outputLanguage}
                onChange={(event) =>
                  setAnalysisLanguage(
                    event.target
                      .value as typeof analysisPreferences.outputLanguage,
                  )
                }
              >
                <option value="auto">{dictionary.input.languageAuto}</option>
                <option value="en">{dictionary.input.languageEnglish}</option>
                <option value="zh-CN">{dictionary.input.languageChinese}</option>
              </select>
            </label>
          </div>

          {clipboardError ? (
            <AlertBanner
              dismissLabel={dictionary.common.close}
              error={clipboardError}
              onDismiss={() => setClipboardError(null)}
            />
          ) : null}
          {download.error ? (
            <AlertBanner
              dismissLabel={dictionary.common.close}
              error={download.error}
              onDismiss={download.clearError}
            />
          ) : null}
          {download.probeFailures.length ? (
            <div className="partial-failure" role="status">
              <strong>{dictionary.input.partialFailure}</strong>
              <ul>
                {download.probeFailures.map((failure) => (
                  <li key={failure.url}>
                    <span>{failure.url}</span>
                    <span>{failure.error.message}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {download.items.length ? (
            <>
              <MediaResults
                items={download.items}
                dictionary={dictionary}
                summaryStarting={analysis.starting}
                onAnalyze={startAnalysis}
                onPresetChange={download.updatePreset}
                onApply1080={() => download.applyPresetToAll("mp4-1080")}
              />
              <DownloadPanel
                controller={download}
                dictionary={dictionary}
                locale={locale}
              />
            </>
          ) : (
            <ActionButton
              className="analyze-link-button"
              type="button"
              onClick={() => void download.analyze()}
              loading={download.busy}
            >
              {download.busy ? dictionary.input.analyzing : dictionary.input.analyze}
            </ActionButton>
          )}

          {analysis.source ? (
            <button className="open-workspace-button" type="button" onClick={openWorkspace}>
              {dictionary.input.openWorkspace}
              <span aria-hidden="true">→</span>
            </button>
          ) : null}
        </>
      )}

      <div className="input-legal">
        <p>{dictionary.input.consent}</p>
        <p>{dictionary.input.privacy}</p>
      </div>
    </section>
  );
}
