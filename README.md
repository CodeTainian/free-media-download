# SaveBolt

SaveBolt is a local-first MVP for saving public media that the user owns or is authorized to download. It supports single links, batches of up to ten items, mobile-compatible MP4, source-quality video, MP3 audio, per-file downloads, and ZIP bundles.

It does **not** accept cookies from API clients or bypass DRM, paywalls, private media, or access controls. For local development, an operator may opt in to yt-dlp's official `--cookies-from-browser` integration for YouTube bot verification; the browser session never passes through the public API.

## Architecture

- `app/` — anonymous React/TypeScript product site built with vinext
- `api/` — FastAPI service that wraps pinned upstream `yt-dlp` and FFmpeg binaries without shell execution
- `docker-compose.yml` — local web, API, health checks, and temporary job volume

The API accepts only server-defined presets. Platform URLs are passed to pinned `yt-dlp==2026.7.4` without a shell and with the generic extractor disabled. The API image also carries the pinned Node 24 runtime required by current yt-dlp YouTube extraction. Public direct-media links use a separate downloader that validates and pins public DNS results for every redirect, blocking loopback, private, link-local, reserved, and cloud-metadata destinations.

Job state is held in memory. Completed files remain available for 30 minutes by default and are then removed. Restarting the API clears active job state.

## Run with Docker

Start Docker Desktop, then:

```bash
docker compose up --build
```

Open `http://localhost:3000`. The API health endpoint is available at `http://localhost:8000/api/v1/health`.

## Local development

The frontend requires Node.js 22.13 or newer:

```bash
npm install
npm run dev
```

For the API, use Python 3.12 with `yt-dlp` and FFmpeg available:

```bash
python3.12 -m venv api/.venv
api/.venv/bin/pip install -r api/requirements-dev.txt
PYTHONPATH=api api/.venv/bin/uvicorn app.main:app --reload --port 8000
```

If YouTube asks the server to confirm it is not a bot, stop the API and restart it as the same macOS user that owns an already signed-in browser profile:

```bash
SAVEBOLT_COOKIES_FROM_BROWSER=chrome PYTHONPATH=api api/.venv/bin/uvicorn app.main:app --reload --port 8000
```

`chrome` can be replaced with another browser supported by yt-dlp, such as `firefox` or `safari`. This setting is intentionally opt-in and local-only: do not mount a personal browser profile into a public/shared container. If YouTube still requires verification, the API returns the retryable `YOUTUBE_BOT_CHECK` error instead of claiming that a public video is private. Successful probes are cached in memory for five minutes by default, and concurrent probes for the exact same URL share one upstream request.

When using the project-local virtual environment, ensure `api/.venv/bin` is on `PATH` so the API health check and subprocess runner can find the pinned `yt-dlp` executable. The development requirements include a pinned FFmpeg binary fallback for machines without a system installation; the Docker image continues to use Debian's FFmpeg package.

Copy `.env.example` to `.env.local` only when overriding defaults.

## Validation

```bash
npm test
PYTHONPATH=api api/.venv/bin/pytest api/tests
docker compose config
```

The automated suites cover URL allowlisting and SSRF protection, similar-domain attacks, format mapping, file-size limits, cancellation, timeouts, SSE ordering, partial failure, ZIP creation, TTL cleanup, rate limiting, legal pages, launch claims, and SSR output.

## Runtime limits

All limits can be adjusted through environment variables; defaults are 10 items per batch, 2 GB per file, 4 GB per ZIP, six hours per media item, a 30-second probe timeout, a five-minute successful-probe cache, a one-hour processing timeout, two concurrent items, and 30-minute retention. See [`.env.example`](.env.example) for the deployment-facing values.

Third-party licensing is documented in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

Before a public deployment, replace the working abuse contact, complete legal review, add production egress controls and observability, and choose a persistent job/entitlement design if accounts or billing are introduced.
