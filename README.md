# SaveBolt

SaveBolt is a local-first MVP for saving public media that the user owns or is authorized to download. It supports single links, batches of up to ten items, mobile-compatible MP4, source-quality video, MP3 audio, per-file downloads, and ZIP bundles. Its URL catalog covers 60+ platform families across mainland China and the rest of the world.

It does **not** accept cookies from API clients or bypass DRM, paywalls, private media, or access controls. For public Douyin links, the API can create an isolated anonymous Chromium session automatically; an operator may also opt in to yt-dlp's official browser-cookie or cookie-file integration for selected platforms. Neither path passes cookie data through the public API.

## Platform catalog

- Mainland: Bilibili, Douyin, Xiaohongshu, Weibo, Xigua, Toutiao, AcFun, Youku/Tudou, iQIYI, Tencent Video, Mango TV, Douyu, Huya, CCTV, Sohu Video, Sina Video, Ximalaya, NetEase Music, QQ Music, and Zhihu.
- Global: YouTube, TikTok, Instagram, X, Facebook, Reddit, Vimeo, Dailymotion, Twitch, SoundCloud, Bandcamp, Mixcloud, Pinterest, Tumblr, LinkedIn, Snapchat, Streamable, Rumble, Odysee, VK, Rutube, OK, Niconico, Naver, Kakao TV, TED, major public broadcasters, and several public file/video hosts.

Catalog inclusion means SaveBolt safely accepts the URL and delegates it to the pinned dedicated yt-dlp extractor. It is not a guarantee that every link works: login, DRM, region, IP reputation, extractor regressions, and site changes still apply. The current live-test matrix and known gaps are in [`docs/platform-compatibility.md`](docs/platform-compatibility.md).

The completed video-download MVP, its engineering decisions, validation evidence, known limits, and recommended next-stage plan are summarized in [`docs/mvp-video-download-handoff.md`](docs/mvp-video-download-handoff.md).

## Architecture

- `free-media-download-frontend/` — anonymous React/TypeScript product site built with vinext
- `free-media-download-backend/` — FastAPI service that wraps pinned upstream `yt-dlp` and FFmpeg binaries without shell execution
- `docker-compose.yml` — local web, API, health checks, and temporary job volume

The API accepts only server-defined presets. Platform URLs are passed to pinned `yt-dlp==2026.7.4` without a shell and with the generic extractor disabled. The API image also carries the pinned Node 24 runtime required by current yt-dlp YouTube extraction and Chromium for isolated anonymous Douyin sessions. Public direct-media links use a separate downloader that validates and pins public DNS results for every redirect, blocking loopback, private, link-local, reserved, and cloud-metadata destinations.

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
cd free-media-download-frontend
npm install
npm run dev
```

For the API, use Python 3.12 with `yt-dlp` and FFmpeg available:

```bash
cd free-media-download-backend
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. .venv/bin/uvicorn app.main:app --reload --port 8000
```

### Automatic Douyin session

When no explicit Douyin cookie source is configured, the first public Douyin request starts a temporary Chromium profile, waits for Douyin to issue its anonymous anti-bot cookies, and passes only `douyin.com` cookies plus the matching user agent to yt-dlp. yt-dlp uses its recommended `curl_cffi` transport to impersonate Chrome's TLS/browser request fingerprint for this managed session. The temporary browser profile is discarded immediately. The restricted cookie file is cached for 20 minutes, shared by concurrent requests, and removed during a clean API shutdown.

Chrome is auto-detected on macOS; the Docker API image includes Chromium. Set `SAVEBOLT_BROWSER_BINARY` only for a nonstandard installation. Disable this behavior with `SAVEBOLT_ANONYMOUS_BROWSER_COOKIES=false`. `SAVEBOLT_BROWSER_IMPERSONATE` defaults to `chrome`; set it to an empty value only when diagnosing a transport compatibility problem.

### Explicit operator session

If another selected platform asks for a fresh browser session, or if an operator prefers to override the automatic Douyin session, stop the API and restart it as the same OS user that owns the browser profile:

```bash
cd free-media-download-backend
SAVEBOLT_COOKIES_FROM_BROWSER=firefox \
SAVEBOLT_COOKIE_PLATFORMS=youtube,douyin,ixigua \
SAVEBOLT_YTDLP_USER_AGENT='Mozilla/5.0 ...' \
PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. .venv/bin/uvicorn app.main:app --reload --port 8000
```

`firefox` can be replaced with another browser supported by yt-dlp, such as `chrome` or `safari`. Keep `SAVEBOLT_COOKIE_PLATFORMS` to the smallest necessary set. For a container, export a fresh Netscape-format file, mount it read-only, and set `SAVEBOLT_COOKIES_FILE`; never configure both cookie sources. Do not mount a personal browser profile into a public/shared container or commit cookie files. Some anti-bot systems require cookies, the matching browser user agent, and the downloader to use the same public IP.

An explicit cookie source configured for `douyin` takes priority over automatic anonymous sessions. The API returns explicit retryable errors for browser startup failures, missing/expired cookies, rejected network addresses, rate limits, and YouTube bot checks. Successful probes are cached in memory for five minutes by default, and concurrent probes for the exact same URL share one upstream request.

When using the project-local virtual environment, ensure `free-media-download-backend/.venv/bin` is on `PATH` so the API health check and subprocess runner can find the pinned `yt-dlp` executable. The development requirements include a pinned FFmpeg binary fallback for machines without a system installation; the Docker image continues to use Debian's FFmpeg package.

Frontend and backend configuration examples live in their respective project directories. Copy `free-media-download-frontend/.env.example` to `.env.local` for frontend overrides; load backend values from `free-media-download-backend/.env.example` into the API process environment only when needed.

## Validation

```bash
npm --prefix free-media-download-frontend test
PYTHONPATH=free-media-download-backend free-media-download-backend/.venv/bin/pytest free-media-download-backend/tests
docker compose config
```

The automated suites cover URL allowlisting and SSRF protection, similar-domain attacks, format mapping, file-size limits, cancellation, timeouts, SSE ordering, partial failure, ZIP creation, TTL cleanup, rate limiting, legal pages, launch claims, and SSR output.

## Runtime limits

All limits can be adjusted through environment variables; defaults are 10 items per batch, 2 GB per file, 4 GB per ZIP, six hours per media item, a 30-second probe timeout, a five-minute successful-probe cache, a one-hour processing timeout, two concurrent items, and 30-minute retention. See the [backend environment example](free-media-download-backend/.env.example) for the deployment-facing values.

Third-party licensing is documented in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

Before a public deployment, replace the working abuse contact, complete legal review, add production egress controls and observability, and choose a persistent job/entitlement design if accounts or billing are introduced.
