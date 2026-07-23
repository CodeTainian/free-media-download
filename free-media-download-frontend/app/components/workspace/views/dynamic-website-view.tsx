"use client";

import { useState } from "react";
import { artifactExportUrl } from "../../../lib/api/client";
import { durationLabel, timestampUrl } from "../../../lib/api/format";
import type {
  WebsiteManifest,
  WebsiteTheme,
} from "../../../lib/api/types";
import type { BubbleDictionary } from "../../../lib/i18n/messages/en-US";

const themes: WebsiteTheme[] = [
  "editorial",
  "learning",
  "documentary",
  "product_brief",
];

export function DynamicWebsiteView({
  analysisId,
  manifest,
  dictionary,
}: {
  analysisId: string;
  manifest: WebsiteManifest;
  dictionary: BubbleDictionary;
}) {
  const [theme, setTheme] = useState<WebsiteTheme>(manifest.theme);
  const [device, setDevice] = useState<"desktop" | "mobile">("desktop");
  const [shared, setShared] = useState(false);
  const sourceUrl = manifest.sources[0]?.url;

  async function copyShareLink() {
    await navigator.clipboard.writeText(window.location.href);
    setShared(true);
    window.setTimeout(() => setShared(false), 1800);
  }

  return (
    <div className="website-view">
      <header className="artifact-view-header">
        <p className="section-kicker">{dictionary.workspace.tabs.dynamic_website}</p>
        <h2>{dictionary.workspace.websiteHeading}</h2>
        <div className="website-controls">
          <div aria-label={dictionary.workspace.template}>
            {themes.map((item) => (
              <button
                type="button"
                aria-pressed={theme === item}
                key={item}
                onClick={() => setTheme(item)}
              >
                {dictionary.workspace.themes[item]}
              </button>
            ))}
          </div>
          <div aria-label={dictionary.workspace.previewDevice}>
            <button type="button" aria-pressed={device === "desktop"} onClick={() => setDevice("desktop")}>
              {dictionary.workspace.desktop}
            </button>
            <button type="button" aria-pressed={device === "mobile"} onClick={() => setDevice("mobile")}>
              {dictionary.workspace.mobile}
            </button>
          </div>
          <a href={artifactExportUrl(analysisId, "dynamic_website", "html", theme)}>
            HTML
          </a>
          <a href={artifactExportUrl(analysisId, "dynamic_website", "zip", theme)}>
            ZIP
          </a>
          <button type="button" onClick={() => void copyShareLink()}>
            {shared ? dictionary.common.copied : dictionary.workspace.copyShareLink}
          </button>
        </div>
      </header>
      <div className="website-preview-shell" data-device={device} data-theme={theme}>
        <article className="website-preview">
          <header>
            <span>{manifest.hero.eyebrow}</span>
            <h3>{manifest.hero.title}</h3>
            <p>{manifest.hero.subtitle}</p>
          </header>
          <section>
            {manifest.chapters.map((chapter) => (
              <article key={chapter.id}>
                {sourceUrl ? (
                  <a
                    className="timestamp-link"
                    href={timestampUrl(sourceUrl, chapter.start_seconds)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {durationLabel(chapter.start_seconds)} ↗
                  </a>
                ) : (
                  <small>{Math.round(chapter.start_seconds)}s</small>
                )}
                <h4>{chapter.title}</h4>
                <p>{chapter.summary.text}</p>
              </article>
            ))}
          </section>
          <div className="website-callouts">
            {manifest.callouts.map((item, index) => (
              <blockquote key={`${item.start_seconds}-${index}`}>{item.text}</blockquote>
            ))}
          </div>
          <dl>
            {manifest.glossary.map((item) => (
              <div key={item.id}>
                <dt>{item.term}</dt>
                <dd>{item.definition.text}</dd>
              </div>
            ))}
          </dl>
        </article>
      </div>
      <p className="safe-render-note">{dictionary.workspace.safeWebsite}</p>
    </div>
  );
}
