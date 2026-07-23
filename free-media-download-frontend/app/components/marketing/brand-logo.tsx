import Link from "next/link";
import type { Locale } from "../../lib/i18n/locales";

export function BrandLogo({ locale }: { locale: Locale }) {
  return (
    <Link className="brand-logo" href={`/${locale}`} aria-label="Bubble AI">
      <span className="brand-bubbles" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      <span>
        <strong>Bubble</strong>
        <small>AI</small>
      </span>
    </Link>
  );
}
