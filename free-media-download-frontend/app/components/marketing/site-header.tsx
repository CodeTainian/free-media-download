import type { Locale } from "../../lib/i18n/locales";
import type { BubbleDictionary } from "../../lib/i18n/messages/en-US";
import { BrandLogo } from "./brand-logo";
import { LanguageSwitcher } from "./language-switcher";

const repository = "https://github.com/CodeTainian/free-media-download";

export function SiteHeader({
  locale,
  dictionary,
}: {
  locale: Locale;
  dictionary: BubbleDictionary;
}) {
  return (
    <header className="site-header">
      <BrandLogo locale={locale} />
      <nav aria-label={dictionary.nav.primaryLabel}>
        <a href="#product">{dictionary.nav.product}</a>
        <a href="#use-cases">{dictionary.nav.useCases}</a>
        <a href="#pricing">{dictionary.nav.pricing}</a>
        <a href={`${repository}#readme`} target="_blank" rel="noreferrer">
          {dictionary.nav.docs}
        </a>
        <a href={repository} target="_blank" rel="noreferrer">
          {dictionary.nav.github}
        </a>
      </nav>
      <div className="site-header-actions">
        <LanguageSwitcher locale={locale} dictionary={dictionary} />
        <a className="header-cta" href="#bubble-input">
          {dictionary.nav.start}
          <span aria-hidden="true">→</span>
        </a>
      </div>
    </header>
  );
}
