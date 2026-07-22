import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "SaveBolt — Public media, saved cleanly",
    template: "%s · SaveBolt",
  },
  description: "Save public videos and audio in the quality you need. Single links, batches, MP4, MP3, and mobile-ready downloads.",
  applicationName: "SaveBolt",
  keywords: ["video downloader", "batch video downloader", "save video", "MP4", "MP3"],
  robots: { index: true, follow: true },
  openGraph: {
    title: "SaveBolt — Public media, saved cleanly",
    description: "Paste a public link, pick the quality, and keep it offline.",
    siteName: "SaveBolt",
    type: "website",
  },
  twitter: {
    card: "summary",
    title: "SaveBolt — Public media, saved cleanly",
    description: "Paste a public link, pick the quality, and keep it offline.",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0c0c0f",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable}`}>{children}</body>
    </html>
  );
}
