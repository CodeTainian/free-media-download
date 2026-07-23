import Link from "next/link";
import type { Locale } from "../../lib/i18n/locales";

export function LegalDocument({
  locale,
  back,
  title,
  intro,
  sections,
}: {
  locale: Locale;
  back: string;
  title: string;
  intro: string;
  sections: string[][];
}) {
  return (
    <main className="legal-page">
      <Link className="legal-back" href={`/${locale}`}>
        ← {back}
      </Link>
      <h1>{title}</h1>
      <p className="legal-intro">{intro}</p>
      <div className="legal-content">
        {sections.map(([heading, content]) => (
          <section key={heading}>
            <h2>{heading}</h2>
            <p>{content}</p>
          </section>
        ))}
      </div>
    </main>
  );
}
