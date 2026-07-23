import { durationLabel, timestampUrl } from "../../../lib/api/format";
import type { TranscriptDocument } from "../../../lib/api/types";
import type { BubbleDictionary } from "../../../lib/i18n/messages/en-US";

export function TranscriptView({
  transcript,
  sourceUrl,
  dictionary,
}: {
  transcript: TranscriptDocument;
  sourceUrl: string;
  dictionary: BubbleDictionary;
}) {
  return (
    <div className="transcript-view">
      <header className="artifact-view-header">
        <p className="section-kicker">{dictionary.workspace.tabs.transcript}</p>
        <h2>{dictionary.workspace.transcriptHeading}</h2>
        <p>{transcript.language} · {transcript.source_kind.replaceAll("_", " ")}</p>
      </header>
      <ol>
        {transcript.segments.map((segment) => (
          <li id={segment.id} key={segment.id}>
            <a href={timestampUrl(sourceUrl, segment.start)} target="_blank" rel="noreferrer">
              {durationLabel(segment.start)}
            </a>
            <p lang={transcript.language}>{segment.text}</p>
            {segment.speaker ? <small>{segment.speaker}</small> : null}
          </li>
        ))}
      </ol>
    </div>
  );
}
