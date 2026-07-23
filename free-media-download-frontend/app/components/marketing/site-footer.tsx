import Link from "next/link";
import type { Locale } from "../../lib/i18n/locales";
import type { BubbleDictionary } from "../../lib/i18n/messages/en-US";
import { BrandLogo } from "./brand-logo";

const repository = "https://github.com/CodeTainian/free-media-download";

export function SiteFooter({
  locale,
  dictionary,
}: {
  locale: Locale;
  dictionary: BubbleDictionary;
}) {
  return (
    <footer className="site-footer">
      <div className="footer-lead">
        <BrandLogo locale={locale} />
        <p>{dictionary.footer.tagline}</p>
      </div>
      <div className="footer-columns">
        <div>
          <strong>{dictionary.footer.product}</strong>
          <a href="#product">{dictionary.nav.product}</a>
          <a href="#use-cases">{dictionary.nav.useCases}</a>
          <a href="#pricing">{dictionary.nav.pricing}</a>
        </div>
        <div>
          <strong>{dictionary.footer.resources}</strong>
          <a
            href={`${repository}/blob/main/docs/platform-compatibility.md`}
            target="_blank"
            rel="noreferrer"
          >
            {dictionary.footer.platforms}
          </a>
          <a href={`${repository}#readme`} target="_blank" rel="noreferrer">
            {dictionary.footer.documentation}
          </a>
          <a href={`${repository}/issues`} target="_blank" rel="noreferrer">
            {dictionary.footer.contact}
          </a>
          <a
            href="https://www.bubbleai.cloud/"
            target="_blank"
            rel="noreferrer noopener"
          >
            {dictionary.footer.bubbleCloud} ↗
          </a>
        </div>
        <div>
          <strong>{dictionary.footer.legal}</strong>
          <Link href={`/${locale}/privacy`}>{dictionary.footer.privacy}</Link>
          <Link href={`/${locale}/terms`}>{dictionary.footer.terms}</Link>
          <a href={repository} target="_blank" rel="noreferrer">
            GitHub
          </a>
        </div>
      </div>
      <div className="footer-bottom">
        <span>{dictionary.footer.copyright}</span>
        <span>{dictionary.footer.permission}</span>
      </div>
    </footer>
  );
}
