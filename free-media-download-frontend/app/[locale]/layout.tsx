import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { headers } from "next/headers";
import { getDictionary, isLocale, locales } from "../lib/i18n/locales";
import "../globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export function generateStaticParams() {
  return locales.map((locale) => ({ locale }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  if (!isLocale(locale)) return {};
  const dictionary = getDictionary(locale);
  const requestHeaders = await headers();
  const host = requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host");
  const protocol =
    requestHeaders.get("x-forwarded-proto") ??
    (host?.startsWith("localhost") ? "http" : "https");
  const socialImage = host ? `${protocol}://${host}/og.png` : undefined;
  return {
    title: {
      default: dictionary.meta.title,
      template: `%s · Bubble Video AI`,
    },
    description: dictionary.meta.description,
    applicationName: "Bubble Video AI",
    keywords: [
      "AI video summary",
      "video knowledge workspace",
      "timestamped chapters",
      "public media download",
    ],
    robots: { index: true, follow: true },
    openGraph: {
      title: dictionary.meta.title,
      description: dictionary.meta.description,
      siteName: "Bubble Video AI",
      locale: locale.replace("-", "_"),
      type: "website",
      images: socialImage
        ? [{ url: socialImage, width: 1800, height: 942, alt: dictionary.meta.title }]
        : undefined,
    },
    twitter: {
      card: "summary_large_image",
      title: dictionary.meta.title,
      description: dictionary.meta.description,
      images: socialImage ? [socialImage] : undefined,
    },
  };
}

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#f7f7f4",
};

export default async function LocaleLayout({
  children,
  params,
}: Readonly<{
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}>) {
  const { locale } = await params;
  const documentLocale = isLocale(locale) ? locale : "en-US";

  return (
    <html lang={documentLocale}>
      <body className={`${geistSans.variable} ${geistMono.variable}`}>{children}</body>
    </html>
  );
}
