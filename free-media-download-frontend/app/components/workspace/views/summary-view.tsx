import { durationLabel, timestampUrl } from "../../../lib/api/format";
import type { SummaryContent } from "../../../lib/api/types";
import type { BubbleDictionary } from "../../../lib/i18n/messages/en-US";

export function SummaryView({
  summary,
  sourceUrl,
  dictionary,
}: {
  summary: SummaryContent;
  sourceUrl: string;
  dictionary: BubbleDictionary;
}) {
  return (
    <div className="summary-view">
      <header className="artifact-view-header">
        <p className="section-kicker">{dictionary.workspace.overview}</p>
        <h2>{dictionary.workspace.summaryHeading}</h2>
      </header>
      <section className="overview-card">
        <strong>{dictionary.workspace.tldr}</strong>
        <p>{summary.tldr.text}</p>
        <a
          className="timestamp-link"
          href={timestampUrl(sourceUrl, summary.tldr.start_seconds)}
          target="_blank"
          rel="noreferrer"
        >
          {durationLabel(summary.tldr.start_seconds)} ↗
        </a>
        <hr />
        <strong>{dictionary.workspace.overview}</strong>
        <p>{summary.overview.text}</p>
      </section>
      <section className="key-points-section">
        <div className="artifact-section-heading">
          <p className="section-kicker">02</p>
          <h3>{dictionary.workspace.keyPoints}</h3>
        </div>
        <div className="key-point-list">
          {summary.key_takeaways.map((point, index) => (
            <article key={`${point.evidence_segment_ids.join("-")}-${index}`}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <div>
                <p>{point.text}</p>
                <a
                  className="timestamp-link"
                  href={timestampUrl(sourceUrl, point.start_seconds)}
                  target="_blank"
                  rel="noreferrer"
                >
                  {dictionary.workspace.openAt}{" "}
                  {durationLabel(point.start_seconds)} ↗
                </a>
              </div>
            </article>
          ))}
        </div>
      </section>
      {summary.important_facts.length ? (
        <section className="artifact-list-section">
          <h3>{dictionary.workspace.importantFacts}</h3>
          <ul>
            {summary.important_facts.map((claim) => (
              <li key={claim.id}>
                <span data-importance={claim.importance}>{claim.importance}</span>
                {claim.statement.text}
                {" "}
                <a
                  className="timestamp-link"
                  href={timestampUrl(sourceUrl, claim.statement.start_seconds)}
                  target="_blank"
                  rel="noreferrer"
                >
                  {durationLabel(claim.statement.start_seconds)} ↗
                </a>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {summary.conclusions.length ? (
        <section className="artifact-list-section">
          <h3>{dictionary.workspace.conclusions}</h3>
          <ul>
            {summary.conclusions.map((item, index) => (
              <li key={`${item.start_seconds}-${index}`}>
                {item.text}{" "}
                <a
                  className="timestamp-link"
                  href={timestampUrl(sourceUrl, item.start_seconds)}
                  target="_blank"
                  rel="noreferrer"
                >
                  {durationLabel(item.start_seconds)} ↗
                </a>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {summary.suggested_questions.length ? (
        <section className="artifact-list-section">
          <h3>{dictionary.workspace.questions}</h3>
          <ul>
            {summary.suggested_questions.map((item) => (
              <li key={item.id}>
                {item.question}{" "}
                <a
                  className="timestamp-link"
                  href={timestampUrl(sourceUrl, item.reason.start_seconds)}
                  target="_blank"
                  rel="noreferrer"
                >
                  {durationLabel(item.reason.start_seconds)} ↗
                </a>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
