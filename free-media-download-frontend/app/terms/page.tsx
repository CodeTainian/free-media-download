import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Terms of use" };

export default function TermsPage() {
  return (
    <main className="legal-page">
      <Link className="legal-back" href="/">← Back to SaveBolt</Link>
      <h1>Terms of use.</h1>
      <p className="legal-intro">SaveBolt is a tool for saving public media you own, created, or have permission to download. It is not a way around access controls.</p>
      <div className="legal-content">
        <section><h2>01 / Permitted use</h2><p>You may use SaveBolt only for lawful purposes and only for media that you are legally entitled to save. You remain responsible for copyright, privacy, contractual, and platform-policy compliance.</p></section>
        <section><h2>02 / Prohibited use</h2><p>Do not use SaveBolt to access private media, bypass DRM or paywalls, infringe copyrights, harass others, overload a source platform, probe internal networks, or distribute malicious content.</p></section>
        <section><h2>03 / Availability</h2><p>Source platforms change frequently and may limit automated access. SaveBolt does not guarantee that a particular link, format, resolution, or platform will remain available.</p></section>
        <section><h2>04 / Temporary files</h2><p>Completed files are designed to expire after 30 minutes. Do not treat SaveBolt as storage. You are responsible for saving your permitted files before they expire.</p></section>
        <section><h2>05 / Abuse</h2><p>For copyright or abuse concerns in this local MVP, contact <a href="mailto:abuse@savebolt.local">abuse@savebolt.local</a>. Replace this address with an operational contact before public deployment.</p></section>
      </div>
    </main>
  );
}
