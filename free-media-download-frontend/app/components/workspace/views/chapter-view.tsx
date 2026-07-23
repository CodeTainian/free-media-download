import { durationLabel, timestampUrl } from "../../../lib/api/format";
import type { SummaryResult } from "../../../lib/api/types";
import type { BubbleDictionary } from "../../../lib/i18n/messages/en-US";
import { EvidenceList } from "../evidence-list";

export function ChapterView({
  result,
  dictionary,
}: {
  result: SummaryResult;
  dictionary: BubbleDictionary;
}) {
  return (
    <div className="chapter-view">
      <header className="artifact-view-header">
        <p className="section-kicker">{dictionary.workspace.tabs.chapters}</p>
        <h2>{dictionary.workspace.chaptersHeading}</h2>
      </header>
      <ol className="chapter-list">
        {result.outline.map((chapter, index) => (
          <li id={`chapter-${index}`} key={`${chapter.timestamp_seconds}-${chapter.title}`}>
            <div className="chapter-marker">
              <span>{String(index + 1).padStart(2, "0")}</span>
              <i aria-hidden="true" />
            </div>
            <div className="chapter-content">
              <a
                className="timestamp-link"
                href={timestampUrl(result.source_url, chapter.timestamp_seconds)}
                target="_blank"
                rel="noreferrer"
              >
                {durationLabel(chapter.timestamp_seconds)} ↗
              </a>
              <h3>{chapter.title}</h3>
              <p>{chapter.summary}</p>
              <EvidenceList
                evidence={chapter.evidence}
                sourceUrl={result.source_url}
                language={result.caption_language}
                dictionary={dictionary}
              />
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
