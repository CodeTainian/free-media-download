"use client";

/* eslint-disable @next/next/no-img-element -- thumbnails are displayed directly from supported public media hosts. */

import { durationLabel } from "../../lib/api/format";
import type { MediaSelection } from "../../lib/api/types";
import type { BubbleDictionary } from "../../lib/i18n/messages/en-US";
import { summaryUnavailableReason } from "../../lib/media/summary-availability";
import { ActionButton } from "../ui/action-button";

export function MediaResults({
  items,
  dictionary,
  summaryStarting,
  onAnalyze,
  onPresetChange,
  onApply1080,
}: {
  items: MediaSelection[];
  dictionary: BubbleDictionary;
  summaryStarting: boolean;
  onAnalyze: (item: MediaSelection) => void;
  onPresetChange: (selectionId: string, presetId: string) => void;
  onApply1080: () => void;
}) {
  return (
    <section className="media-results" aria-live="polite">
      <div className="media-results-head">
        <div>
          <span className="status-dot status-dot-success" aria-hidden="true" />
          <strong>
            {items.length}{" "}
            {items.length === 1
              ? dictionary.input.resultsReady
              : dictionary.input.resultsReadyPlural}
          </strong>
        </div>
        {items.length > 1 ? (
          <button type="button" onClick={onApply1080}>
            {dictionary.input.apply1080}
          </button>
        ) : null}
      </div>

      <p className="ai-consent-note">
        <span aria-hidden="true">AI</span>
        {dictionary.media.aiConsent}
      </p>

      <div className="media-result-list">
        {items.map((item, index) => {
          const unavailable = summaryUnavailableReason(item, dictionary);
          const usesAudioTranscription =
            item.transcript_strategy_hint === "audio_transcription";
          return (
            <article className="media-result-card" key={item.selectionId}>
              <div className="media-result-index">
                {String(index + 1).padStart(2, "0")}
              </div>
              {item.thumbnail ? (
                <img
                  src={item.thumbnail}
                  alt=""
                  referrerPolicy="no-referrer"
                />
              ) : (
                <div className="media-thumbnail-placeholder" aria-hidden="true">
                  ▶
                </div>
              )}
              <div className="media-result-copy">
                <p>
                  {item.platform} ·{" "}
                  {durationLabel(item.duration, dictionary.input.unknownPlatform)}
                </p>
                <h3>{item.title}</h3>
                {item.uploader ? <span>{item.uploader}</span> : null}
              </div>
              <div className="media-result-actions">
                <ActionButton
                  type="button"
                  onClick={() => onAnalyze(item)}
                  disabled={Boolean(unavailable) || summaryStarting}
                  loading={summaryStarting}
                >
                  {usesAudioTranscription
                    ? dictionary.media.transcribeAndSummarize
                    : dictionary.media.analyzeKnowledge}
                </ActionButton>
                {usesAudioTranscription ? (
                  <p className="asr-consent-note">
                    {dictionary.media.asrConsent}
                  </p>
                ) : null}
                <label>
                  <span className="sr-only">
                    {dictionary.media.downloadTitle}: {item.title}
                  </span>
                  <select
                    value={item.presetId}
                    onChange={(event) =>
                      onPresetChange(item.selectionId, event.target.value)
                    }
                  >
                    {item.presets.map((preset) => (
                      <option value={preset.id} key={preset.id}>
                        {preset.label}
                      </option>
                    ))}
                  </select>
                </label>
                <small className={unavailable ? "unavailable" : ""}>
                  {usesAudioTranscription
                    ? `${dictionary.media.audioTranscriptionAvailable}${unavailable ? ` · ${unavailable}` : ""}`
                    : unavailable ??
                      `${item.caption_languages.length} ${dictionary.media.captions} · ${dictionary.media.englishOutput}`}
                </small>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
