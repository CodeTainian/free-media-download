import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Privacy" };

export default function PrivacyPage() {
  return (
    <main className="legal-page">
      <Link className="legal-back" href="/">← Back to SaveBolt</Link>
      <h1>Privacy, plainly.</h1>
      <p className="legal-intro">The launch MVP works without an account, permanent history, advertising trackers, or user cookies for source platforms.</p>
      <div className="legal-content">
        <section><h2>01 / What is processed</h2><p>SaveBolt processes the public URLs you submit, basic request information needed for rate limiting, media metadata, temporary job status, and the files produced for your download.</p></section>
        <section><h2>02 / What is not collected</h2><p>The MVP does not ask for your name, email, payment details, source-platform credentials, visitor browser cookies, or a SaveBolt account.</p></section>
        <section><h2>03 / Retention</h2><p>Job metadata is held in memory. Completed media and job files are scheduled for automatic deletion 30 minutes after processing finishes; restarting the service clears in-memory jobs.</p></section>
        <section><h2>04 / Source platforms</h2><p>To analyze and download a public link, the download service makes requests to the source platform and its media delivery hosts. Those services receive the server’s network address and normal request headers. A strict public platform may also receive an isolated anonymous browser session created by the server; it never contains visitor browser data.</p></section>
        <section><h2>05 / Public launch</h2><p>This document describes the local MVP. Before public deployment, the operator must add a real privacy contact, hosting details, jurisdiction-specific disclosures, and any analytics policy.</p></section>
      </div>
    </main>
  );
}
