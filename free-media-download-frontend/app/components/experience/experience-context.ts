"use client";

import { createContext, useContext } from "react";
import type { DownloadJobController } from "../../hooks/use-download-job";
import type { SummaryJobController } from "../../hooks/use-summary-job";
import type { Locale } from "../../lib/i18n/locales";
import type { BubbleDictionary } from "../../lib/i18n/messages/en-US";
import type { MediaSelection } from "../../lib/api/types";

export type ExperienceContextValue = {
  locale: Locale;
  dictionary: BubbleDictionary;
  view: "landing" | "workspace";
  download: DownloadJobController;
  summary: SummaryJobController;
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
