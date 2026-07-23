import { notFound } from "next/navigation";
import { ExperienceProvider } from "../components/experience/experience-provider";
import { MarketingPage } from "../components/marketing/marketing-page";
import { getDictionary, isLocale } from "../lib/i18n/locales";

export default async function HomePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  const dictionary = getDictionary(locale);

  return (
    <ExperienceProvider locale={locale} dictionary={dictionary}>
      <MarketingPage locale={locale} dictionary={dictionary} />
    </ExperienceProvider>
  );
}
