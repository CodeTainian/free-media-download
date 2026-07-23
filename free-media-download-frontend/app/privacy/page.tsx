import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Privacy" };

export default function PrivacyPage() {
  return (
    <main className="legal-page">
      <Link className="legal-back" href="/">← Back to SaveBolt</Link>
      <h1>Privacy, plainly.</h1>
      <p className="legal-intro">The launch MVP works without an account, permanent history, advertising trackers, or visitor cookies for source platforms.</p>
      <div className="legal-content">
        <section><h2>01 / What is processed</h2><p>SaveBolt processes the public URLs you submit, basic request information needed for rate limiting, media metadata, temporary job status, and the files produced for your download. When you choose AI Summary, it also temporarily processes the selected caption track and the generated summary.</p></section>
        <section><h2>02 / What is not collected</h2><p>The MVP does not ask for your name, email, payment details, source-platform credentials, visitor browser cookies, or a SaveBolt account.</p></section>
        <section><h2>03 / AI summary provider</h2><p>AI Summary is optional. If you choose it, SaveBolt sends caption text, caption timestamps, and the video title to the configured DeepSeek API to generate an English summary. It does not send the video file or audio. DeepSeek processes that information under its own privacy terms. SaveBolt does not expose a full-transcript viewing or download endpoint.</p></section>
        <section><h2>04 / Retention</h2><p>Job metadata is held in memory. Completed media files, temporary captions, and AI summary results are scheduled for automatic deletion 30 minutes after processing finishes; restarting the service clears in-memory jobs and results.</p></section>
        <section><h2>05 / Rate limiting</h2><p>SaveBolt uses the source network address to apply abuse and usage limits, including the rolling 24-hour AI summary limit. In the MVP this state is kept only in the running API process and disappears when it restarts.</p></section>
        <section><h2>06 / Source platforms</h2><p>To analyze and download a public link, the download service makes requests to the source platform and its media delivery hosts. Those services receive the server’s network address and normal request headers. A strict public platform may also receive an isolated anonymous browser session created by the server; it never contains visitor browser data.</p></section>
        <section><h2>07 / Public launch</h2><p>This document describes the local MVP. Before public deployment, the operator must add a real privacy contact, hosting details, jurisdiction-specific disclosures, the AI provider’s production data terms, and any analytics policy.</p></section>
      </div>
    </main>
  );
}
