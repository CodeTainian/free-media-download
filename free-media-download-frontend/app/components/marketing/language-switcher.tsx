"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { otherLocale, type Locale } from "../../lib/i18n/locales";
import type { BubbleDictionary } from "../../lib/i18n/messages/en-US";

export function LanguageSwitcher({
  locale,
  dictionary,
}: {
  locale: Locale;
  dictionary: BubbleDictionary;
}) {
  const pathname = usePathname();
  const nextLocale = otherLocale(locale);
  const segments = pathname.split("/");
  segments[1] = nextLocale;
  const href = segments.join("/") || `/${nextLocale}`;

  return (
    <Link
      className="language-switcher"
      href={href}
      hrefLang={nextLocale}
      aria-label={`${dictionary.common.language}: ${nextLocale}`}
    >
      <span aria-hidden="true">◎</span>
      {locale === "en-US" ? "中文" : "EN"}
    </Link>
  );
}
