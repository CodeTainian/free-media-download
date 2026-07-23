/* eslint-disable @next/next/no-img-element -- frame paths are isolated, same-origin analysis assets. */

import { apiUrl } from "../../../lib/api/client";
import { durationLabel, timestampUrl } from "../../../lib/api/format";
import type { VisualStory } from "../../../lib/api/types";
import type { BubbleDictionary } from "../../../lib/i18n/messages/en-US";

export function VisualStoryView({
  story,
  sourceUrl,
  dictionary,
}: {
  story: VisualStory;
  sourceUrl: string;
  dictionary: BubbleDictionary;
}) {
  return (
    <div className="visual-story-view">
      <header className="artifact-view-header">
        <p className="section-kicker">{dictionary.workspace.tabs.visual_story}</p>
        <h2>{story.title}</h2>
      </header>
      {story.warnings.map((warning) => (
        <p className="artifact-warning" role="status" key={warning}>{warning}</p>
      ))}
      <div className="story-track">
        {story.frames.map((frame, index) => (
          <article className="story-card" key={frame.id}>
            <div className="story-frame">
              {frame.image_url ? (
                <img src={apiUrl(frame.image_url)} alt="" loading="lazy" />
              ) : (
                <div aria-hidden="true">{String(index + 1).padStart(2, "0")}</div>
              )}
            </div>
            <a
              className="timestamp-link"
              href={timestampUrl(sourceUrl, frame.timestamp_seconds)}
              target="_blank"
              rel="noreferrer"
            >
              {durationLabel(frame.timestamp_seconds)} ↗
            </a>
            <h3>{frame.title}</h3>
            <p>{frame.caption}</p>
            <small>{frame.narrative}</small>
          </article>
        ))}
      </div>
    </div>
  );
}
