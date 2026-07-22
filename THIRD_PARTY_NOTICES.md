# Third-party notices

SaveBolt wraps upstream tools without modifying or copying their source code.

- **yt-dlp 2026.7.4** — installed from the pinned Python package and invoked through its documented machine-facing CLI. yt-dlp is dedicated to the public domain under the Unlicense. Source and license: <https://github.com/yt-dlp/yt-dlp>.
- **Node.js 24.14.0** — copied from the pinned official container image into the API image as the JavaScript runtime required by current yt-dlp extraction. Source and license: <https://github.com/nodejs/node>.
- **FFmpeg** — installed from the Debian Bookworm package repository in the API image and invoked by yt-dlp for media merging and conversion. Source and licensing details: <https://ffmpeg.org/legal.html>.
- **Chromium** — installed from the Debian Bookworm package repository and used only for isolated anonymous sessions required by strict public platforms. Source and licensing details: <https://www.chromium.org/Home/chromium-security/oss/>.
- **curl_cffi** — installed through yt-dlp's `curl-cffi` extra and used to match browser TLS/request fingerprints for strict public platforms. Licensed under MIT. Source and license: <https://github.com/lexiforest/curl_cffi>.
- **imageio-ffmpeg 0.6.0** — an optional, development-only Python package that supplies a pinned FFmpeg executable when no system binary is installed. Source and licensing details: <https://github.com/imageio/imageio-ffmpeg>.

Cobalt code, branding, and API code are not included in this project.
