"use client";

import { useMemo, useState, type ReactNode } from "react";
import { useDownloadJob } from "../../hooks/use-download-job";
import { useSummaryJob } from "../../hooks/use-summary-job";
import type { MediaSelection } from "../../lib/api/types";
import type { Locale } from "../../lib/i18n/locales";
import type { BubbleDictionary } from "../../lib/i18n/messages/en-US";
import { ResultWorkspace } from "../workspace/result-workspace";
import { ExperienceContext } from "./experience-context";

export function ExperienceProvider({
  locale,
  dictionary,
  children,
}: {
  locale: Locale;
  dictionary: BubbleDictionary;
  children: ReactNode;
}) {
  const [view, setView] = useState<"landing" | "workspace">("landing");
  const download = useDownloadJob(dictionary);
  const summary = useSummaryJob(dictionary);

  const value = useMemo(
    () => ({
      locale,
      dictionary,
      view,
      download,
      summary,
      startAnalysis: (item: MediaSelection) => {
        setView("workspace");
        void summary.start(item);
      },
      showLanding: () => setView("landing"),
      openWorkspace: () => {
        if (summary.source) setView("workspace");
      },
    }),
    [dictionary, download, locale, summary, view],
  );

  return (
    <ExperienceContext.Provider value={value}>
      <div hidden={view === "workspace"}>{children}</div>
      {view === "workspace" ? <ResultWorkspace /> : null}
    </ExperienceContext.Provider>
  );
}
