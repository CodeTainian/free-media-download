"use client";

import { useEffect, useMemo, useState } from "react";
import { durationLabel, timestampUrl } from "../../../lib/api/format";
import type { InteractiveGuide } from "../../../lib/api/types";
import type { BubbleDictionary } from "../../../lib/i18n/messages/en-US";

export function InteractiveGuideView({
  analysisId,
  guide,
  sourceUrl,
  dictionary,
}: {
  analysisId: string;
  guide: InteractiveGuide;
  sourceUrl: string;
  dictionary: BubbleDictionary;
}) {
  const storageKey = `bubble-guide:${analysisId}`;
  const [current, setCurrent] = useState(0);
  const [completed, setCompleted] = useState<Set<string>>(new Set());
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const step = guide.steps[current];

  useEffect(() => {
    const timer = window.setTimeout(() => {
      try {
        const saved = localStorage.getItem(storageKey);
        if (!saved) return;
        const value = JSON.parse(saved) as {
          current?: number;
          completed?: string[];
        };
        setCurrent(
          Math.min(guide.steps.length - 1, Math.max(0, value.current ?? 0)),
        );
        setCompleted(new Set(value.completed ?? []));
      } catch {
        // Invalid local progress is ignored and never sent to the server.
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, [guide.steps.length, storageKey]);

  useEffect(() => {
    try {
      localStorage.setItem(
        storageKey,
        JSON.stringify({ current, completed: [...completed] }),
      );
    } catch {
      // Progress remains available for this session when storage is unavailable.
    }
  }, [completed, current, storageKey]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.altKey && event.key === "ArrowRight") {
        setCurrent((value) => Math.min(guide.steps.length - 1, value + 1));
      }
      if (event.altKey && event.key === "ArrowLeft") {
        setCurrent((value) => Math.max(0, value - 1));
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [guide.steps.length]);

  const progress = useMemo(
    () => Math.round((completed.size / guide.steps.length) * 100),
    [completed.size, guide.steps.length],
  );

  function toggleComplete() {
    setCompleted((value) => {
      const next = new Set(value);
      if (next.has(step.id)) next.delete(step.id);
      else next.add(step.id);
      return next;
    });
  }

  function restart() {
    setCurrent(0);
    setCompleted(new Set());
    setAnswers({});
    try {
      localStorage.removeItem(storageKey);
    } catch {
      // The in-memory reset is still complete.
    }
  }

  return (
    <div className="guide-view">
      <header className="artifact-view-header">
        <p className="section-kicker">{dictionary.workspace.tabs.interactive_guide}</p>
        <h2>{guide.title}</h2>
        <p>{guide.audience} · {guide.estimated_time_minutes} min · {progress}%</p>
      </header>
      {guide.safety_notice ? (
        <p className="guide-safety" role="note">{guide.safety_notice}</p>
      ) : null}
      <nav className="guide-step-nav" aria-label={dictionary.workspace.guideSteps}>
        {guide.steps.map((item, index) => (
          <button
            type="button"
            aria-current={index === current ? "step" : undefined}
            data-completed={completed.has(item.id)}
            onClick={() => setCurrent(index)}
            key={item.id}
          >
            {index + 1}
          </button>
        ))}
      </nav>
      <article className="guide-step">
        <span>{dictionary.workspace.step} {current + 1}/{guide.steps.length}</span>
        <h3>{step.title}</h3>
        <p>{step.explanation.text}</p>
        <a href={timestampUrl(sourceUrl, step.timestamp_seconds)} target="_blank" rel="noreferrer">
          {durationLabel(step.timestamp_seconds)} ↗
        </a>
        <section>
          <h4>{dictionary.workspace.action}</h4>
          <p>{step.action.instruction}</p>
        </section>
        <section>
          <h4>{dictionary.workspace.checkpoint}</h4>
          <p>{step.checkpoint.prompt}</p>
          <small>{step.checkpoint.success_criteria}</small>
        </section>
        <button type="button" aria-pressed={completed.has(step.id)} onClick={toggleComplete}>
          {completed.has(step.id)
            ? dictionary.workspace.markIncomplete
            : dictionary.workspace.markComplete}
        </button>
      </article>
      <div className="guide-pager">
        <button type="button" disabled={current === 0} onClick={() => setCurrent((value) => value - 1)}>
          ← {dictionary.workspace.previous}
        </button>
        <button type="button" disabled={current === guide.steps.length - 1} onClick={() => setCurrent((value) => value + 1)}>
          {dictionary.workspace.next} →
        </button>
        <button type="button" onClick={restart}>{dictionary.workspace.restart}</button>
      </div>
      {guide.quiz.length ? (
        <section className="guide-quiz">
          <h3>{dictionary.workspace.quiz}</h3>
          {guide.quiz.map((item) => (
            <fieldset key={item.id}>
              <legend>{item.question}</legend>
              {item.choices.map((choice, index) => (
                <label key={`${item.id}-${index}`}>
                  <input
                    type="radio"
                    name={item.id}
                    checked={answers[item.id] === index}
                    onChange={() => setAnswers((value) => ({ ...value, [item.id]: index }))}
                  />
                  {choice}
                </label>
              ))}
              {answers[item.id] !== undefined ? (
                <p role="status">
                  {answers[item.id] === item.correct_index
                    ? dictionary.workspace.correct
                    : dictionary.workspace.tryAgain}
                  {" "}{item.explanation.text}
                </p>
              ) : null}
            </fieldset>
          ))}
        </section>
      ) : null}
    </div>
  );
}
