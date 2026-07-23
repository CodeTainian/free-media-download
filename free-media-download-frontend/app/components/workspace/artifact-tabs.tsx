"use client";

import { useRef, type KeyboardEvent } from "react";
import type { ArtifactKind } from "../../lib/workspace/types";
import type { BubbleDictionary } from "../../lib/i18n/messages/en-US";

export const artifactKinds: ArtifactKind[] = [
  "summary",
  "chapters",
  "mind_map",
  "visual_story",
  "dynamic_website",
  "interactive_guide",
  "transcript",
];

export function ArtifactTabs({
  active,
  onChange,
  dictionary,
}: {
  active: ArtifactKind;
  onChange: (kind: ArtifactKind) => void;
  dictionary: BubbleDictionary;
}) {
  const refs = useRef(new Map<ArtifactKind, HTMLButtonElement>());

  function moveFocus(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let nextIndex = index;
    if (event.key === "ArrowRight") nextIndex = (index + 1) % artifactKinds.length;
    else if (event.key === "ArrowLeft")
      nextIndex = (index - 1 + artifactKinds.length) % artifactKinds.length;
    else if (event.key === "Home") nextIndex = 0;
    else if (event.key === "End") nextIndex = artifactKinds.length - 1;
    else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onChange(artifactKinds[index]);
      return;
    } else return;

    event.preventDefault();
    const next = artifactKinds[nextIndex];
    onChange(next);
    refs.current.get(next)?.focus();
  }

  return (
    <div className="artifact-tabs" role="tablist" aria-label={dictionary.workspace.title}>
      {artifactKinds.map((kind, index) => {
        const current = active === kind;
        return (
          <button
            key={kind}
            id={`tab-${kind}`}
            ref={(element) => {
              if (element) refs.current.set(kind, element);
              else refs.current.delete(kind);
            }}
            type="button"
            role="tab"
            tabIndex={current ? 0 : -1}
            aria-selected={current}
            aria-controls={`panel-${kind}`}
            onClick={() => onChange(kind)}
            onKeyDown={(event) => moveFocus(event, index)}
          >
            <span>{dictionary.workspace.tabs[kind]}</span>
          </button>
        );
      })}
    </div>
  );
}
