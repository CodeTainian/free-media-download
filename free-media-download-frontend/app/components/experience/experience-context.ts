"use client";

import { createContext, useContext } from "react";
import type { AnalysisJobController } from "../../hooks/use-analysis-job";
import type { DownloadJobController } from "../../hooks/use-download-job";
import type {
  AnalysisDetail,
  AnalysisLanguage,
  MediaSelection,
} from "../../lib/api/types";
import type { Locale } from "../../lib/i18n/locales";
import type { BubbleDictionary } from "../../lib/i18n/messages/en-US";

export type ExperienceContextValue = {
  locale: Locale;
  dictionary: BubbleDictionary;
  view: "landing" | "workspace";
  download: DownloadJobController;
  analysis: AnalysisJobController;
  analysisPreferences: {
    detail: AnalysisDetail;
    outputLanguage: AnalysisLanguage;
  };
  setAnalysisDetail: (detail: AnalysisDetail) => void;
  setAnalysisLanguage: (language: AnalysisLanguage) => void;
  startAnalysis: (item: MediaSelection) => void;
  showLanding: () => void;
  openWorkspace: () => void;
};

export const ExperienceContext = createContext<ExperienceContextValue | null>(null);

export function useBubbleExperience() {
  const value = useContext(ExperienceContext);
  if (!value) throw new Error("Bubble experience components require ExperienceProvider.");
  return value;
}
