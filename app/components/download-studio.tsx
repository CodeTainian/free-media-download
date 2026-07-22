"use client";

/* eslint-disable @next/next/no-img-element -- source thumbnails come from arbitrary supported hosts and are deliberately not proxied. */

import { useEffect, useMemo, useRef, useState } from "react";

type Mode = "single" | "batch";
type OutputKind = "video" | "audio" | "original";
type ItemStatus = "queued" | "running" | "ready" | "failed" | "cancelled";
type JobStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

type ApiError = {
  code: string;
  message: string;
  retryable?: boolean;
  itemIndex?: number;
};

type Preset = {
  id: string;
  label: string;
  detail: string;
  kind: OutputKind;
  extension: string;
  height?: number | null;
};

type MediaItem = {
  source_url: string;
  title: string;
  platform: string;
  duration?: number | null;
  thumbnail?: string | null;
  uploader?: string | null;
  is_playlist_item: boolean;
  presets: Preset[];
};

type Selection = MediaItem & { selectionId: string; presetId: string };

type JobItem = {
  id: string;
  title: string;
  status: ItemStatus;
  progress: number;
  speed?: string | null;
  eta?: number | null;
  filename?: string | null;
  download_url?: string | null;
  error?: ApiError | null;
};

type Job = {
  id: string;
  status: JobStatus;
  created_at: string;
  expires_at?: string | null;
  items: JobItem[];
  bundle_url?: string | null;
  bundle_ready: boolean;
};

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const platforms = ["YouTube", "TikTok", "Instagram", "X", "Facebook", "Reddit", "Vimeo", "Bilibili"];
const eventNames = [
  "queued",
  "started",
  "item_started",
  "item_progress",
  "item_ready",
  "item_failed",
  "bundle_ready",
  "completed",
  "cancelled",
];

function durationLabel(seconds?: number | null) {
  if (!seconds) return "Length unknown";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = seconds % 60;
  return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}` : `${minutes}:${String(rest).padStart(2, "0")}`;
}

function defaultPreset(presets: Preset[]) {
  return (
    presets.find((preset) => preset.id === "mp4-1080") ??
    presets.find((preset) => preset.id === "mp4-720") ??
    presets.find((preset) => preset.id === "best") ??
    presets[0]
  )?.id;
}

function statusLabel(status: JobStatus | ItemStatus) {
  return status.replace("_", " ");
}

async function readError(response: Response): Promise<ApiError> {
  try {
    const data = (await response.json()) as Partial<ApiError>;
    return {
      code: data.code ?? "REQUEST_FAILED",
      message: data.message ?? "SaveBolt could not complete that request.",
      retryable: data.retryable,
      itemIndex: data.itemIndex,
    };
  } catch {
    return { code: "REQUEST_FAILED", message: "SaveBolt could not reach the download service.", retryable: true };
  }
}

export function DownloadStudio() {
  const [mode, setMode] = useState<Mode>("single");
  const [input, setInput] = useState("");
  const [items, setItems] = useState<Selection[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [proOpen, setProOpen] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);
  const proDialogRef = useRef<HTMLElement | null>(null);
  const proCloseRef = useRef<HTMLButtonElement | null>(null);

  const urls = useMemo(
    () => Array.from(new Set(input.split(/[\n\s]+/).map((value) => value.trim()).filter(Boolean))).slice(0, 10),
    [input],
  );

  useEffect(() => () => eventSourceRef.current?.close(), []);

  useEffect(() => {
    if (!proOpen) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setProOpen(false);
    };
    document.addEventListener("keydown", closeOnEscape);
    proCloseRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", closeOnEscape);
      previousFocus?.focus();
    };
  }, [proOpen]);

  function keepFocusInPro(event: React.KeyboardEvent<HTMLElement>) {
    if (event.key !== "Tab" || !proDialogRef.current) return;
    const controls = Array.from(
      proDialogRef.current.querySelectorAll<HTMLElement>("button, a[href], [tabindex]:not([tabindex='-1'])"),
    );
    const first = controls[0];
    const last = controls.at(-1);
    if (!first || !last) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function changeMode(nextMode: Mode) {
    setMode(nextMode);
    setInput("");
    setItems([]);
    setJob(null);
    setError(null);
  }

  async function pasteFromClipboard() {
    try {
      const value = await navigator.clipboard.readText();
      if (value) setInput(value);
    } catch {
      setError({ code: "CLIPBOARD_BLOCKED", message: "Clipboard access is blocked. Paste the link into the field instead." });
    }
  }

  async function analyze() {
    if (!urls.length) {
      setError({ code: "MISSING_URL", message: "Paste at least one public media link to continue." });
      return;
    }
    if (mode === "single" && urls.length > 1) {
      setError({ code: "TOO_MANY_URLS", message: "Switch to Batch mode to analyze more than one link." });
      return;
    }
    setBusy(true);
    setError(null);
    setJob(null);
    const nextItems: Selection[] = [];
    try {
      for (const url of urls) {
        const response = await fetch(`${API_BASE}/api/v1/media/probe`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url }),
        });
        if (!response.ok) throw await readError(response);
        const data = (await response.json()) as { items: MediaItem[] };
        for (const media of data.items) {
          if (nextItems.length >= 10) break;
          nextItems.push({
            ...media,
            selectionId: `${nextItems.length}-${media.source_url}`,
            presetId: defaultPreset(media.presets),
          });
        }
      }
      setItems(nextItems);
    } catch (caught) {
      setError(
        typeof caught === "object" && caught && "message" in caught
          ? (caught as ApiError)
          : { code: "SERVICE_OFFLINE", message: "The downloader service is offline. Start the API and try again.", retryable: true },
      );
    } finally {
      setBusy(false);
    }
  }

  function updatePreset(selectionId: string, presetId: string) {
    setItems((current) => current.map((item) => (item.selectionId === selectionId ? { ...item, presetId } : item)));
  }

  function applyPresetToAll(presetId: string) {
    setItems((current) =>
      current.map((item) => (item.presets.some((preset) => preset.id === presetId) ? { ...item, presetId } : item)),
    );
  }

  function watchJob(nextJob: Job, eventsUrl: string) {
    eventSourceRef.current?.close();
    setJob(nextJob);
    const source = new EventSource(`${API_BASE}${eventsUrl}`);
    eventSourceRef.current = source;
    const handler = (event: Event) => {
      const message = event as MessageEvent<string>;
      try {
        const payload = JSON.parse(message.data) as { job: Job };
        setJob(payload.job);
        if (["completed", "failed", "cancelled"].includes(payload.job.status)) source.close();
      } catch {
        // Ignore malformed progress frames while keeping the connection alive.
      }
    };
    eventNames.forEach((name) => source.addEventListener(name, handler));
    source.onerror = () => {
      if (source.readyState === EventSource.CLOSED) return;
      fetch(`${API_BASE}/api/v1/jobs/${nextJob.id}`)
        .then((response) => (response.ok ? response.json() : null))
        .then((snapshot: Job | null) => snapshot && setJob(snapshot))
        .catch(() => undefined);
    };
  }

  async function startDownload() {
    if (!items.length) return;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/v1/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          bundle: items.length > 1,
          items: items.map((item) => ({ url: item.source_url, preset_id: item.presetId, title: item.title })),
        }),
      });
      if (!response.ok) throw await readError(response);
      const data = (await response.json()) as { job: Job; events_url: string };
      watchJob(data.job, data.events_url);
    } catch (caught) {
      setError(
        typeof caught === "object" && caught && "message" in caught
          ? (caught as ApiError)
          : { code: "JOB_FAILED", message: "The download job could not be created.", retryable: true },
      );
    } finally {
      setBusy(false);
    }
  }

  async function cancelJob() {
    if (!job) return;
    await fetch(`${API_BASE}/api/v1/jobs/${job.id}`, { method: "DELETE" });
    eventSourceRef.current?.close();
    setJob({ ...job, status: "cancelled", items: job.items.map((item) => ({ ...item, status: item.status === "ready" ? item.status : "cancelled" })) });
  }

  return (
    <main>
      <header className="site-header">
        <a className="brand" href="#top" aria-label="SaveBolt home">
          <span className="brand-mark" aria-hidden="true">S</span>
          <span>SaveBolt</span>
        </a>
        <nav aria-label="Primary navigation">
          <a href="#how">How it works</a>
          <a href="#pricing">Pricing</a>
          <a href="#faq">FAQ</a>
        </nav>
        <a className="header-cta" href="#download">Start saving <span aria-hidden="true">↘</span></a>
      </header>

      <section className="hero" id="top">
        <div className="hero-copy">
          <div className="eyebrow"><span className="live-dot" /> Free while we launch</div>
          <h1>Keep the videos<br />you <em>need.</em></h1>
          <p className="hero-lede">Paste a public link. Pick the quality. Keep it offline—without an account, an app, or a maze of pop-ups.</p>
          <div className="hero-proof" aria-label="Product benefits">
            <span>No account</span><span>Files auto-delete</span><span>Works on mobile</span>
          </div>
        </div>

        <div className="studio-wrap" id="download">
          <div className="studio-shadow" aria-hidden="true" />
          <div className="studio-card">
            <div className="studio-head">
              <div>
                <span className="step-label">01 / ADD LINKS</span>
                <h2>What are we saving?</h2>
              </div>
              <span className="secure-note"><span aria-hidden="true">●</span> Public media only</span>
            </div>

            <div className="mode-switch" aria-label="Download mode">
              <button className={mode === "single" ? "active" : ""} onClick={() => changeMode("single")} type="button" aria-pressed={mode === "single"}>Single link</button>
              <button className={mode === "batch" ? "active" : ""} onClick={() => changeMode("batch")} type="button" aria-pressed={mode === "batch"}>Batch · up to 10</button>
            </div>

            <div className="input-shell">
              {mode === "single" ? (
                <input
                  type="url"
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={(event) => event.key === "Enter" && analyze()}
                  placeholder="https://youtube.com/watch?v=..."
                  aria-label="Public video URL"
                />
              ) : (
                <textarea
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  placeholder={"Paste one public link per line\nhttps://vimeo.com/...\nhttps://reddit.com/..."}
                  aria-label="Public video URLs, one per line"
                  rows={5}
                />
              )}
              <button className="paste-button" type="button" onClick={pasteFromClipboard}>Paste</button>
            </div>
            <div className="input-meta">
              <span>{mode === "batch" ? `${urls.length}/10 links detected` : "Videos, shorts, reels, clips & audio"}</span>
              <span>Max 2 GB each</span>
            </div>

            {error && (
              <div className="error-banner" role="alert">
                <span aria-hidden="true">!</span>
                <div><strong>{error.code.replaceAll("_", " ")}</strong><p>{error.message}</p></div>
                <button type="button" onClick={() => setError(null)} aria-label="Dismiss error">×</button>
              </div>
            )}

            {items.length > 0 && !job && (
              <div className="analysis-results" aria-live="polite">
                <div className="result-toolbar">
                  <span>{items.length} {items.length === 1 ? "item" : "items"} ready</span>
                  {items.length > 1 && (
                    <button type="button" onClick={() => applyPresetToAll("mp4-1080")}>Apply 1080p to all</button>
                  )}
                </div>
                {items.map((item, index) => (
                  <article className="media-row" key={item.selectionId}>
                    <div className="media-index">{String(index + 1).padStart(2, "0")}</div>
                    {item.thumbnail ? <img src={item.thumbnail} alt="" referrerPolicy="no-referrer" /> : <div className="media-placeholder" aria-hidden="true">▶</div>}
                    <div className="media-copy">
                      <span>{item.platform} · {durationLabel(item.duration)}</span>
                      <h3>{item.title}</h3>
                    </div>
                    <label className="preset-select">
                      <span className="sr-only">Output format for {item.title}</span>
                      <select value={item.presetId} onChange={(event) => updatePreset(item.selectionId, event.target.value)}>
                        {item.presets.map((preset) => <option value={preset.id} key={preset.id}>{preset.label}</option>)}
                      </select>
                    </label>
                  </article>
                ))}
              </div>
            )}

            {job && (
              <div className="job-panel" aria-live="polite">
                <div className="job-head">
                  <div><span className="step-label">02 / PROCESSING</span><h3>{job.status === "completed" ? "Your files are ready." : "Saving your media…"}</h3></div>
                  <span className={`status-pill status-${job.status}`}>{statusLabel(job.status)}</span>
                </div>
                <div className="job-list">
                  {job.items.map((item, index) => (
                    <div className="job-item" key={item.id}>
                      <div className="job-item-top">
                        <span>{String(index + 1).padStart(2, "0")}</span>
                        <strong>{item.title}</strong>
                        <span>{item.status === "running" ? `${Math.round(item.progress)}%` : statusLabel(item.status)}</span>
                      </div>
                      <div className="progress-track"><span style={{ width: `${item.status === "ready" ? 100 : item.progress}%` }} /></div>
                      <div className="job-item-bottom">
                        <span>{item.error?.message ?? (item.speed ? `${item.speed}${item.eta ? ` · ${item.eta}s left` : ""}` : "")}</span>
                        {item.download_url && <a href={`${API_BASE}${item.download_url}`} download>Download file ↘</a>}
                      </div>
                    </div>
                  ))}
                </div>
                <div className="job-actions">
                  {job.bundle_url && <a className="primary-button" href={`${API_BASE}${job.bundle_url}`} download>Download all as ZIP <span>↘</span></a>}
                  {!["completed", "failed", "cancelled"].includes(job.status) && <button className="text-button" type="button" onClick={cancelJob}>Cancel job</button>}
                  {["completed", "failed", "cancelled"].includes(job.status) && <button className="text-button" type="button" onClick={() => { setJob(null); setItems([]); setInput(""); }}>Start another</button>}
                </div>
              </div>
            )}

            {!job && (
              <button className="primary-button analyze-button" type="button" onClick={items.length ? startDownload : analyze} disabled={busy}>
                <span>{busy ? "Working…" : items.length ? `Save ${items.length === 1 ? "this file" : `${items.length} files`}` : "Analyze link"}</span>
                <span aria-hidden="true">↘</span>
              </button>
            )}
            <p className="legal-mini">By continuing, you confirm you own the content or have permission to save it.</p>
          </div>
        </div>
      </section>

      <div className="platform-strip" aria-label="Supported platforms">
        <span className="strip-title">WORKS WITH</span>
        <div>{platforms.map((platform) => <span key={platform}>{platform}</span>)}</div>
        <span className="strip-end">+ PUBLIC FILES</span>
      </div>

      <section className="how-section" id="how">
        <div className="section-heading">
          <span className="eyebrow dark">THE SHORT VERSION</span>
          <h2>From link to local<br />in three clean moves.</h2>
        </div>
        <div className="steps-grid">
          <article><span>01</span><div className="step-icon" aria-hidden="true">↗</div><h3>Drop the link</h3><p>Paste one public link, a playlist, or up to ten links at once.</p></article>
          <article><span>02</span><div className="step-icon" aria-hidden="true">≡</div><h3>Choose the output</h3><p>Pick mobile-ready MP4, best source quality, or high-quality MP3.</p></article>
          <article><span>03</span><div className="step-icon" aria-hidden="true">↓</div><h3>Keep it offline</h3><p>Download each file as it finishes—or grab the whole batch as a ZIP.</p></article>
        </div>
      </section>

      <section className="value-section">
        <div className="value-statement">
          <span className="eyebrow">BUILT FOR THE USEFUL STUFF</span>
          <h2>Your references.<br />Your edits.<br /><em>Your files.</em></h2>
        </div>
        <div className="value-list">
          <div><span>01</span><h3>Public media only</h3><p>No paywall or DRM bypasses. SaveBolt is for media you are allowed to keep.</p></div>
          <div><span>02</span><h3>Private by default</h3><p>No account and no permanent library. Completed files are deleted automatically.</p></div>
          <div><span>03</span><h3>Fewer dead ends</h3><p>Clear messages explain login requirements, regional blocks, and temporary platform limits.</p></div>
        </div>
      </section>

      <section className="pricing-section" id="pricing">
        <div className="section-heading pricing-heading">
          <span className="eyebrow dark">FAIR FROM DAY ONE</span>
          <h2>Free now.<br />Worth paying for later.</h2>
          <p>Use the complete launch version without an account. Pro arrives when it adds real value—not before.</p>
        </div>
        <div className="price-grid">
          <article className="price-card free-card">
            <div className="price-card-head"><span>FREE / LAUNCH</span><span className="current-badge">AVAILABLE NOW</span></div>
            <div className="price"><strong>$0</strong><span>while we launch</span></div>
            <ul><li>Single and batch downloads</li><li>Up to 10 links per batch</li><li>MP4, source quality, and MP3</li><li>Automatic file deletion</li></ul>
            <a href="#download" className="price-action">Start saving <span>↘</span></a>
          </article>
          <article className="price-card pro-card">
            <div className="pro-ribbon">COMING SOON</div>
            <div className="price-card-head"><span>PRO / AT LAUNCH</span><span>SaveBolt+</span></div>
            <div className="price"><strong>$9</strong><span>/ month at launch</span></div>
            <ul><li>Priority processing queue</li><li>Larger batches and saved presets</li><li>Private download history</li><li>Subtitle translation and AI summaries</li></ul>
            <button type="button" className="price-action pro-action" onClick={() => setProOpen(true)}>See what’s next <span>→</span></button>
          </article>
        </div>
      </section>

      <section className="faq-section" id="faq">
        <div className="section-heading"><span className="eyebrow dark">THE HONEST ANSWERS</span><h2>Before you paste.</h2></div>
        <div className="faq-list">
          <details><summary>Does SaveBolt work with every website?<span>+</span></summary><p>No tool can honestly promise every website. This launch supports major public platforms and direct media links; platform changes can temporarily affect availability.</p></details>
          <details><summary>Can it download private or paid videos?<span>+</span></summary><p>No. SaveBolt does not accept account cookies and does not bypass DRM, paywalls, regional rights, or private access controls.</p></details>
          <details><summary>Where do completed files go?<span>+</span></summary><p>Your browser saves them through its normal download flow. On iPhone and iPad, they typically appear in the Files app; Android uses the system Downloads folder.</p></details>
          <details><summary>How long are files kept?<span>+</span></summary><p>Completed files remain available for 30 minutes, then the download service removes them automatically.</p></details>
        </div>
      </section>

      <footer>
        <div className="footer-brand"><span className="brand-mark">S</span><strong>SaveBolt</strong><p>Public media, saved cleanly.</p></div>
        <div className="footer-links"><div><span>PRODUCT</span><a href="#download">Downloader</a><a href="#pricing">Pricing</a><a href="#faq">FAQ</a></div><div><span>LEGAL</span><a href="/terms">Terms</a><a href="/privacy">Privacy</a><a href="mailto:abuse@savebolt.local">Report abuse</a></div></div>
        <div className="footer-bottom"><span>© 2026 SaveBolt. Working product name.</span><span>For public media you own or may lawfully save.</span></div>
      </footer>

      {proOpen && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setProOpen(false)}>
          <section ref={proDialogRef} className="pro-modal" role="dialog" aria-modal="true" aria-labelledby="pro-title" onKeyDown={keepFocusInPro} onMouseDown={(event) => event.stopPropagation()}>
            <button ref={proCloseRef} className="modal-close" type="button" aria-label="Close Pro preview" onClick={() => setProOpen(false)}>×</button>
            <span className="eyebrow">SAVEBOLT PRO</span>
            <h2 id="pro-title">Pay for saved time,<br />not basic access.</h2>
            <p>Pro is not accepting payments yet. The next release will focus on priority processing, larger batches, useful history, and AI-assisted transcripts.</p>
            <button className="primary-button" type="button" onClick={() => setProOpen(false)}>Got it <span>✓</span></button>
          </section>
        </div>
      )}
    </main>
  );
}
