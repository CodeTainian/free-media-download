import type { SummaryResult } from "../../../lib/api/types";
import type { BubbleDictionary } from "../../../lib/i18n/messages/en-US";
import { EvidenceList } from "../evidence-list";

export function SummaryView({
  result,
  dictionary,
}: {
  result: SummaryResult;
  dictionary: BubbleDictionary;
}) {
  return (
    <div className="summary-view">
      <header className="artifact-view-header">
        <p className="section-kicker">{dictionary.workspace.overview}</p>
        <h2>{dictionary.workspace.summaryHeading}</h2>
      </header>
      <section className="overview-card">
        <p>{result.overview}</p>
      </section>
      <section className="key-points-section">
        <div className="artifact-section-heading">
          <p className="section-kicker">02</p>
          <h3>{dictionary.workspace.keyPoints}</h3>
        </div>
        <div className="key-point-list">
          {result.key_points.map((point, index) => (
            <article key={`${point.title}-${index}`}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <div>
                <h4>{point.title}</h4>
                <p>{point.explanation}</p>
                <EvidenceList
                  evidence={point.evidence}
                  sourceUrl={result.source_url}
                  language={result.caption_language}
                  dictionary={dictionary}
                />
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
