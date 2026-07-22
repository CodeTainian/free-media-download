# Platform compatibility

Last live check: **2026-07-22** with pinned **yt-dlp 2026.7.4** from the same network as the development API.

These are representative public-link probes, not platform-wide guarantees.

| Platform sample | Result | Notes |
| --- | --- | --- |
| Bilibili | Pass | Dedicated `BiliBili` extractor returned formats. |
| Weibo | Pass | Dedicated `Weibo` extractor returned formats. |
| Tencent Video | Pass | Dedicated `VQQVideo` extractor returned formats. |
| Youku | Pass | A current public sample returned formats; an older sample was blocked by Youku. |
| Mango TV | Pass | Dedicated `MGTV` extractor returned formats. |
| Huya video | Pass | Dedicated `HuyaVideo` extractor returned formats. |
| YouTube | Pass | Public sample returned formats without cookies from this network. |
| Instagram | Pass | Public sample returned formats without cookies from this network. |
| Vimeo | Pass | Current public sample passed; an obsolete sample returned an upstream 401. |
| Douyin | Probe and 1080p download pass automatically | Without cookies the detail API returned an empty body; SaveBolt now creates and caches an isolated anonymous Chromium session and matches its browser request fingerprint. No login is required. |
| Xigua | Cookie required | yt-dlp explicitly requested cookies, though they need not be logged in. |
| TikTok | Network blocked | TikTok rejected the downloader's current public IP. |
| Xiaohongshu | Upstream extractor gap | Two upstream test pages returned no video formats. |
| iQIYI | Inconclusive | The old upstream sample no longer returned a video. |
| Douyu VOD | Runtime gap | The extractor requested PhantomJS, an obsolete runtime not shipped by SaveBolt. |

## Douyin diagnosis and operating solution

The wrapper reaches the dedicated Douyin extractor correctly. Without cookies, Douyin's web-detail response does not contain the expected JSON, and the current yt-dlp extractor reports `Fresh cookies (not necessarily logged in) are needed`. The extractor source also notes that generating Douyin's signature cookies is not implemented upstream.

An isolated follow-up used a temporary, unsigned Chrome profile and exported only that profile's anonymous Douyin cookies. yt-dlp then completed both the public-video probe and a 1080p MP4 download with the same user agent, network address, and a Chrome request fingerprint. This confirms that a fresh anonymous browser session is sufficient for the tested link and no account login is required.

SaveBolt also normalizes Douyin Selected/`jingxuan` links such as `?modal_id=...` into the `/video/<id>` form required by the dedicated yt-dlp extractor. Without this normalization, yt-dlp reports that no suitable extractor exists.

SaveBolt now performs this anonymous refresh automatically when no explicit Douyin cookie source is configured. It waits for the full anonymous cookie set required by the tested extractor flow, exports only `douyin.com` cookies, writes them with `0600` permissions, and uses yt-dlp's recommended `curl_cffi` transport to match Chrome's TLS/request fingerprint. The session is cached briefly and removed on clean shutdown.

For an explicit local operator session instead:

1. Open the target public Douyin page in a browser from the same machine/IP shortly before starting the API.
2. Configure `SAVEBOLT_COOKIES_FROM_BROWSER`, add `douyin` to `SAVEBOLT_COOKIE_PLATFORMS`, and use the browser's exact user agent in `SAVEBOLT_YTDLP_USER_AGENT`.
3. Retry promptly; anti-bot cookies may be short-lived.

The API Docker image now includes Chromium for the automatic path. As an alternative, export a fresh Netscape-format cookie file, mount it read-only outside the repository, and set `SAVEBOLT_COOKIES_FILE`. Never accept cookie data through the public API. Even fresh cookies are not a permanent guarantee because Douyin can change the verification flow independently of this project.

## Other strict-platform guidance

- **TikTok/IP blocks:** use a stable, policy-compliant egress address in a supported region, optionally through an HTTP(S) `SAVEBOLT_YTDLP_PROXY`; keep request rates low. Do not build automatic proxy rotation or CAPTCHA bypass into the public API.
- **Cloudflare/403 responses:** refresh cookies in a browser using the same public IP and configure the matching user agent.
- **Xiaohongshu:** this is currently an upstream extraction problem rather than an allowlist problem. Keep the URL catalog entry, return `NO_MEDIA`, and retest after yt-dlp updates.
- **Douyu VOD:** do not add abandoned PhantomJS merely to make the sample pass. Leave the clear `RUNTIME_UNAVAILABLE` result until the upstream extractor no longer needs it.
- **Kuaishou:** the pinned yt-dlp release has no Kuaishou extractor, so it remains outside the catalog rather than making a false support claim.
