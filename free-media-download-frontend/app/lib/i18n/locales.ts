import { enUS, type BubbleDictionary } from "./messages/en-US";
import { zhCN } from "./messages/zh-CN";

export const locales = ["en-US", "zh-CN"] as const;
export type Locale = (typeof locales)[number];

export function isLocale(value: string): value is Locale {
  return locales.includes(value as Locale);
}

export function getDictionary(locale: Locale): BubbleDictionary {
  return locale === "zh-CN" ? zhCN : enUS;
}

export function otherLocale(locale: Locale): Locale {
  return locale === "zh-CN" ? "en-US" : "zh-CN";
}

export function localizedPath(locale: Locale, path = "") {
  const normalized = path === "/" ? "" : path.startsWith("/") ? path : `/${path}`;
  return `/${locale}${normalized}`;
}
