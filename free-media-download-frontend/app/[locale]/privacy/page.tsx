import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { LegalDocument } from "../../components/legal/legal-document";
import { getDictionary, isLocale } from "../../lib/i18n/locales";

export const metadata: Metadata = { title: "Privacy" };

export default async function PrivacyPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  const dictionary = getDictionary(locale);
  return (
    <LegalDocument
      locale={locale}
      back={dictionary.legal.back}
      title={dictionary.legal.privacyTitle}
      intro={dictionary.legal.privacyIntro}
      sections={dictionary.legal.privacySections}
    />
  );
}
