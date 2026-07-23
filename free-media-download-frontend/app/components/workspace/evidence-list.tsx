import { durationLabel, timestampUrl } from "../../lib/api/format";
import type { SummaryEvidence } from "../../lib/api/types";
import type { BubbleDictionary } from "../../lib/i18n/messages/en-US";

export function EvidenceList({
  evidence,
  sourceUrl,
  language,
  dictionary,
}: {
  evidence: SummaryEvidence[];
  sourceUrl: string;
  language: string;
  dictionary: BubbleDictionary;
}) {
  if (!evidence.length) return null;
  return (
    <div className="evidence-list">
      {evidence.map((quote, index) => (
        <details key={`${quote.id}-${index}`}>
          <summary>
            <span>
              {dictionary.workspace.evidence} · {durationLabel(quote.start_seconds)}
            </span>
            <span aria-hidden="true">+</span>
          </summary>
          <blockquote lang={language}>{quote.text}</blockquote>
          <a
            href={timestampUrl(sourceUrl, quote.start_seconds)}
            target="_blank"
            rel="noreferrer"
          >
            {dictionary.workspace.openAt} {durationLabel(quote.start_seconds)}
            <span aria-hidden="true"> ↗</span>
          </a>
        </details>
      ))}
    </div>
  );
}
