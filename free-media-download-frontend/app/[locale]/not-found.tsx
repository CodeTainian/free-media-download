import Link from "next/link";

export default function NotFound() {
  return (
    <main className="workspace-empty-shell">
      <section className="empty-state">
        <p className="section-kicker">404</p>
        <h1>Page not found</h1>
        <p>The page you requested does not exist.</p>
        <Link className="download-link-button" href="/en-US">
          Bubble Video AI
        </Link>
      </section>
    </main>
  );
}
