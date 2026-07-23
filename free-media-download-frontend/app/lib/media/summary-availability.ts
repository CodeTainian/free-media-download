import type { MediaSelection } from "../api/types";
import type { BubbleDictionary } from "../i18n/messages/en-US";

export const SUMMARY_MAX_DURATION_SECONDS = 2 * 60 * 60;

export function summaryUnavailableReason(
  item: MediaSelection,
  dictionary: BubbleDictionary,
) {
  if (item.duration && item.duration > SUMMARY_MAX_DURATION_SECONDS) {
    return dictionary.media.tooLong;
  }
  if (item.summary_supported) return null;
  if (item.transcript_strategy_hint === "unavailable") {
    return dictionary.media.noCaptions;
  }
  return dictionary.media.unsupported;
}
