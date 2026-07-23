import { durationLabel, timestampUrl } from "../../../lib/api/format";
import type { Chapter } from "../../../lib/api/types";
import type { BubbleDictionary } from "../../../lib/i18n/messages/en-US";

export function ChapterView({
  chapters,
  sourceUrl,
  dictionary,
}: {
  chapters: Chapter[];
  sourceUrl: string;
  dictionary: BubbleDictionary;
}) {
  return (
    <div className="chapter-view">
      <header className="artifact-view-header">
        <p className="section-kicker">{dictionary.workspace.tabs.chapters}</p>
        <h2>{dictionary.workspace.chaptersHeading}</h2>
      </header>
      <ol className="chapter-list">
        {chapters.map((chapter, index) => (
          <li id={chapter.id} key={chapter.id}>
            <div className="chapter-marker">
              <span>{String(index + 1).padStart(2, "0")}</span>
              <i aria-hidden="true" />
            </div>
            <div className="chapter-content">
              <a
                className="timestamp-link"
                href={timestampUrl(sourceUrl, chapter.start_seconds)}
                target="_blank"
                rel="noreferrer"
              >
                {durationLabel(chapter.start_seconds)} –{" "}
                {durationLabel(chapter.end_seconds)} ↗
              </a>
              <h3>{chapter.title}</h3>
              <p>{chapter.summary.text}</p>
              <ul className="chapter-key-points">
                {chapter.key_points.map((point, pointIndex) => (
                  <li key={`${chapter.id}-${pointIndex}`}>{point.text}</li>
                ))}
              </ul>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
