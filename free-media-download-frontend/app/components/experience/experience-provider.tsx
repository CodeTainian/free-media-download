"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useAnalysisJob } from "../../hooks/use-analysis-job";
import { useDownloadJob } from "../../hooks/use-download-job";
import type {
  AnalysisDetail,
  AnalysisLanguage,
  MediaSelection,
} from "../../lib/api/types";
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
  const [detail, setDetail] = useState<AnalysisDetail>("balanced");
  const [outputLanguage, setOutputLanguage] =
    useState<AnalysisLanguage>("auto");
  const restored = useRef(false);
  const download = useDownloadJob(dictionary);
  const analysis = useAnalysisJob(dictionary);

  useEffect(() => {
    if (restored.current) return;
    restored.current = true;
    const analysisId = new URL(window.location.href).searchParams.get("analysis");
    if (!analysisId) return;
    void analysis.restore(analysisId).then((found) => {
      setView(found ? "workspace" : "landing");
      if (found) window.scrollTo({ top: 0, behavior: "auto" });
    });
  }, [analysis]);

  const value = useMemo(
    () => ({
      locale,
      dictionary,
      view,
      download,
      analysis,
      analysisPreferences: { detail, outputLanguage },
      setAnalysisDetail: setDetail,
      setAnalysisLanguage: setOutputLanguage,
      startAnalysis: (item: MediaSelection) => {
        setView("workspace");
        window.scrollTo({ top: 0, behavior: "auto" });
        void analysis.start(item, { detail, outputLanguage });
      },
      showLanding: () => {
        setView("landing");
        window.scrollTo({ top: 0, behavior: "auto" });
      },
      openWorkspace: () => {
        if (analysis.source) {
          setView("workspace");
          window.scrollTo({ top: 0, behavior: "auto" });
        }
      },
    }),
    [
      analysis,
      detail,
      dictionary,
      download,
      locale,
      outputLanguage,
      view,
    ],
  );

  return (
    <ExperienceContext.Provider value={value}>
      <div hidden={view === "workspace"}>{children}</div>
      {view === "workspace" ? <ResultWorkspace /> : null}
    </ExperienceContext.Provider>
  );
}
