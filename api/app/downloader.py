from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import signal
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

import aiohttp

from .config import Settings
from .models import MediaItem, OutputKind, Preset, ProbeResponse
from .security import (
    UnsafeUrlError,
    classify_url,
    parse_public_http_url,
    resolve_public_host,
    safe_filename,
)


class DownloadError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


ProgressCallback = Callable[[float, str | None, int | None], Awaitable[None]]


class PublicResolver(aiohttp.abc.AbstractResolver):
    def __init__(self) -> None:
        self._pinned: dict[tuple[str, int], list[dict[str, object]]] = {}

    async def pin(self, host: str, port: int) -> None:
        key = (host, port)
        if key not in self._pinned:
            self._pinned[key] = await resolve_public_host(host, port)

    async def resolve(self, host: str, port: int = 0, family: int = 0):  # type: ignore[override]
        await self.pin(host, port)
        return self._pinned[(host, port)]

    async def close(self) -> None:
        return None


def _format_duration(seconds: int | None) -> str:
    if not seconds:
        return "Unknown length"
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _build_presets(info: dict[str, object], direct: bool = False) -> list[Preset]:
    if direct:
        suffix = Path(urlsplit(str(info.get("webpage_url") or "")).path).suffix.lower().lstrip(".") or "file"
        return [
            Preset(
                id="original",
                label="Original file",
                detail="No conversion · fastest",
                kind=OutputKind.ORIGINAL,
                extension=suffix,
            )
        ]

    formats = info.get("formats") if isinstance(info.get("formats"), list) else []
    heights = {
        int(item["height"])
        for item in formats
        if isinstance(item, dict)
        and isinstance(item.get("height"), (int, float))
        and item.get("vcodec") not in {None, "none"}
    }
    choices = [value for value in (2160, 1440, 1080, 720, 480, 360) if any(height >= value for height in heights)]
    presets: list[Preset] = [
        Preset(
            id="best",
            label="Best available",
            detail="Highest source quality",
            kind=OutputKind.VIDEO,
            extension="mp4",
        )
    ]
    presets.extend(
        Preset(
            id=f"mp4-{height}",
            label=f"{height}p MP4",
            detail="Mobile-compatible video",
            kind=OutputKind.VIDEO,
            extension="mp4",
            height=height,
        )
        for height in choices[:5]
    )
    presets.append(
        Preset(
            id="mp3",
            label="MP3 audio",
            detail="High-quality audio only",
            kind=OutputKind.AUDIO,
            extension="mp3",
        )
    )
    return presets


def _normalize_info(info: dict[str, object], source_url: str, playlist_item: bool = False) -> MediaItem:
    duration = int(info["duration"]) if isinstance(info.get("duration"), (int, float)) else None
    return MediaItem(
        source_url=str(info.get("webpage_url") or info.get("url") or source_url),
        title=str(info.get("title") or "Untitled media")[:240],
        platform=str(info.get("extractor_key") or info.get("extractor") or "Media"),
        duration=duration,
        thumbnail=str(info["thumbnail"]) if isinstance(info.get("thumbnail"), str) else None,
        uploader=str(info["uploader"])[:160] if isinstance(info.get("uploader"), str) else None,
        is_playlist_item=playlist_item,
        presets=_build_presets(info),
    )


def map_process_error(stderr: str) -> DownloadError:
    text = stderr.lower()
    bot_check_markers = (
        "confirm you're not a bot",
        "confirm you’re not a bot",
        "sign in to confirm that you're not a bot",
        "sign in to confirm that you’re not a bot",
    )
    if any(marker in text for marker in bot_check_markers):
        return DownloadError(
            "YOUTUBE_BOT_CHECK",
            "YouTube is temporarily requiring bot verification. Please wait a while and try again.",
            True,
        )
    if "video unavailable" in text:
        return DownloadError(
            "MEDIA_UNAVAILABLE",
            "YouTube reports that this video is unavailable.",
        )
    if "private video" in text or "login required" in text or "sign in" in text:
        return DownloadError("AUTH_REQUIRED", "This media requires an account or is not public.")
    if "drm" in text:
        return DownloadError("DRM_PROTECTED", "DRM-protected media cannot be downloaded.")
    if "geo" in text or "not available in your country" in text:
        return DownloadError("REGION_BLOCKED", "This media is not available from the downloader's region.")
    if "429" in text or "too many requests" in text:
        return DownloadError("RATE_LIMITED", "The source platform is temporarily rate limiting requests.", True)
    if "max-filesize" in text or "larger than max-filesize" in text:
        return DownloadError("FILE_TOO_LARGE", "This media exceeds the 2 GB file limit.")
    if "unsupported url" in text:
        return DownloadError("UNSUPPORTED_URL", "This link is not supported by the selected platform extractor.")
    return DownloadError("DOWNLOAD_FAILED", "The source platform could not prepare this media right now.", True)


async def terminate_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(process.wait(), timeout=3)
    except TimeoutError:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


class YtDlpService:
    def __init__(self, config: Settings):
        self.config = config
        self._probe_cache: dict[str, tuple[float, ProbeResponse]] = {}
        self._probe_inflight: dict[str, asyncio.Task[ProbeResponse]] = {}
        self._probe_cache_lock = asyncio.Lock()

    async def probe(self, raw_url: str) -> ProbeResponse:
        platform, normalized = classify_url(raw_url)
        cache_key = f"{platform}:{normalized}"
        now = time.monotonic()
        async with self._probe_cache_lock:
            cached = self._probe_cache.get(cache_key)
            if cached and cached[0] > now:
                return cached[1].model_copy(deep=True)
            if cached:
                self._probe_cache.pop(cache_key, None)
            task = self._probe_inflight.get(cache_key)
            if task is None:
                task = asyncio.create_task(self._probe_and_cache(cache_key, platform, normalized))
                self._probe_inflight[cache_key] = task
        result = await asyncio.shield(task)
        return result.model_copy(deep=True)

    async def _probe_and_cache(self, cache_key: str, platform: str, normalized: str) -> ProbeResponse:
        try:
            result = await self._probe_uncached(platform, normalized)
            if self.config.probe_cache_ttl_seconds > 0 and self.config.probe_cache_max_entries > 0:
                async with self._probe_cache_lock:
                    now = time.monotonic()
                    expired = [key for key, entry in self._probe_cache.items() if entry[0] <= now]
                    for key in expired:
                        self._probe_cache.pop(key, None)
                    while len(self._probe_cache) >= self.config.probe_cache_max_entries:
                        oldest = min(self._probe_cache, key=lambda key: self._probe_cache[key][0])
                        self._probe_cache.pop(oldest, None)
                    self._probe_cache[cache_key] = (
                        now + self.config.probe_cache_ttl_seconds,
                        result.model_copy(deep=True),
                    )
            return result
        finally:
            async with self._probe_cache_lock:
                if self._probe_inflight.get(cache_key) is asyncio.current_task():
                    self._probe_inflight.pop(cache_key, None)

    async def _probe_uncached(self, platform: str, normalized: str) -> ProbeResponse:
        if platform == "direct":
            try:
                return await self._probe_direct(normalized)
            except (UnsafeUrlError, DownloadError):
                raise
            except TimeoutError as exc:
                raise DownloadError("PROBE_TIMEOUT", "The public media host took too long to respond.", True) from exc
            except aiohttp.ClientError as exc:
                raise DownloadError("SOURCE_ERROR", "The public media host could not be reached.", True) from exc

        command = [
            self.config.yt_dlp_binary,
            "--dump-single-json",
            "--skip-download",
            "--no-warnings",
            "--no-colors",
            "--ignore-config",
            "--playlist-end",
            str(self.config.max_batch_items),
            "--use-extractors",
            "default,-generic",
            "--js-runtimes",
            self.config.yt_dlp_js_runtime,
        ]
        command.extend(self._youtube_auth_args(platform))
        command.append(normalized)
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            raise DownloadError("SERVICE_UNAVAILABLE", "The media engine is not installed.", True) from exc

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self.config.probe_timeout_seconds
            )
        except TimeoutError as exc:
            await terminate_process(process)
            raise DownloadError("PROBE_TIMEOUT", "The source platform took too long to respond.", True) from exc
        if process.returncode:
            raise map_process_error(stderr.decode("utf-8", "replace"))

        try:
            payload = json.loads(stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DownloadError("INVALID_RESPONSE", "The source returned an unreadable response.", True) from exc

        entries = payload.get("entries") if isinstance(payload, dict) else None
        if isinstance(entries, list):
            valid_entries = [entry for entry in entries if isinstance(entry, dict)][: self.config.max_batch_items]
            items = [_normalize_info(entry, normalized, True) for entry in valid_entries]
            truncated = len(entries) > self.config.max_batch_items
        elif isinstance(payload, dict):
            items = [_normalize_info(payload, normalized)]
            truncated = False
        else:
            items = []

        if not items:
            raise DownloadError("NO_MEDIA", "No downloadable public media was found at this link.")
        for item in items:
            if item.duration and item.duration > self.config.max_duration_seconds:
                raise DownloadError("MEDIA_TOO_LONG", "This media exceeds the six-hour duration limit.")
        return ProbeResponse(items=items, truncated=truncated)

    async def _probe_direct(self, normalized: str) -> ProbeResponse:
        final_url, headers = await self._direct_headers(normalized)
        content_type = headers.get("Content-Type", "").split(";", 1)[0].lower()
        if not (content_type.startswith("video/") or content_type.startswith("audio/") or content_type == "application/octet-stream"):
            raise DownloadError("UNSUPPORTED_MEDIA", "The public link did not return an audio or video file.")
        length = headers.get("Content-Length")
        if length and length.isdigit() and int(length) > self.config.max_file_bytes:
            raise DownloadError("FILE_TOO_LARGE", "This media exceeds the 2 GB file limit.")
        filename = safe_filename(unquote(Path(urlsplit(final_url).path).name) or "public-media")
        info: dict[str, object] = {"webpage_url": final_url, "title": filename}
        return ProbeResponse(
            items=[
                MediaItem(
                    source_url=final_url,
                    title=filename,
                    platform="Direct file",
                    presets=_build_presets(info, direct=True),
                )
            ]
        )

    async def _direct_headers(self, raw_url: str) -> tuple[str, aiohttp.typedefs.LooseHeaders]:
        resolver = PublicResolver()
        connector = aiohttp.TCPConnector(resolver=resolver, ttl_dns_cache=0)
        timeout = aiohttp.ClientTimeout(total=self.config.probe_timeout_seconds)
        current = raw_url
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            for _ in range(4):
                current, host, port = parse_public_http_url(current)
                await resolver.pin(host, port)
                async with session.get(
                    current,
                    headers={"Range": "bytes=0-0", "User-Agent": "SaveBolt/0.1"},
                    allow_redirects=False,
                ) as response:
                    if response.status in {301, 302, 303, 307, 308}:
                        location = response.headers.get("Location")
                        if not location:
                            raise DownloadError("INVALID_REDIRECT", "The media host returned an invalid redirect.")
                        current = urljoin(current, location)
                        continue
                    if response.status not in {200, 206}:
                        raise DownloadError("SOURCE_ERROR", "The public media host rejected this request.", True)
                    return str(response.url), response.headers
        raise DownloadError("TOO_MANY_REDIRECTS", "The media link redirected too many times.")

    async def download(
        self,
        raw_url: str,
        preset_id: str,
        output_dir: Path,
        cancel_event: asyncio.Event,
        progress: ProgressCallback,
    ) -> Path:
        platform, normalized = classify_url(raw_url)
        output_dir.mkdir(parents=True, exist_ok=True)
        if platform == "direct":
            if preset_id != "original":
                raise DownloadError("INVALID_PRESET", "Direct media links use the original file preset.")
            try:
                return await self._download_direct(normalized, output_dir, cancel_event, progress)
            except (UnsafeUrlError, DownloadError):
                raise
            except TimeoutError as exc:
                raise DownloadError("DOWNLOAD_TIMEOUT", "The public media host took too long to respond.", True) from exc
            except aiohttp.ClientError as exc:
                raise DownloadError("SOURCE_ERROR", "The public media host could not be reached.", True) from exc
        if not binary_available(self.config.ffmpeg_binary):
            raise DownloadError(
                "SERVICE_UNAVAILABLE",
                "FFmpeg is not available, so this platform download cannot be merged safely.",
                True,
            )
        return await self._download_platform(platform, normalized, preset_id, output_dir, cancel_event, progress)

    def _youtube_auth_args(self, platform: str) -> list[str]:
        if platform == "youtube" and self.config.cookies_from_browser:
            return ["--cookies-from-browser", self.config.cookies_from_browser]
        return []

    async def _download_platform(
        self,
        platform: str,
        normalized: str,
        preset_id: str,
        output_dir: Path,
        cancel_event: asyncio.Event,
        progress: ProgressCallback,
    ) -> Path:
        template = str(output_dir / "%(title).120B [%(id)s].%(ext)s")
        command = [
            self.config.yt_dlp_binary,
            "--newline",
            "--no-warnings",
            "--no-colors",
            "--ignore-config",
            "--no-playlist",
            "--use-extractors",
            "default,-generic",
            "--js-runtimes",
            self.config.yt_dlp_js_runtime,
            "--ffmpeg-location",
            self.config.ffmpeg_binary,
            "--max-filesize",
            str(self.config.max_file_bytes),
            "--match-filter",
            f"duration <= {self.config.max_duration_seconds} & !is_live",
            "--progress-template",
            "download:SBPROGRESS|%(progress._percent_str)s|%(progress._speed_str)s|%(progress.eta)s",
            "-o",
            template,
        ]
        command.extend(self._youtube_auth_args(platform))
        if preset_id == "mp3":
            command.extend(["-x", "--audio-format", "mp3", "--audio-quality", "0"])
        elif preset_id == "best":
            command.extend(["-f", "bv*+ba/b", "--merge-output-format", "mp4", "--remux-video", "mp4"])
        elif preset_id.startswith("mp4-"):
            height = int(preset_id.removeprefix("mp4-"))
            selector = (
                f"bv*[height<={height}][ext=mp4]+ba[ext=m4a]/"
                f"b[height<={height}][ext=mp4]/bv*[height<={height}]+ba/b[height<={height}]"
            )
            command.extend(["-f", selector, "--merge-output-format", "mp4", "--remux-video", "mp4"])
        else:
            raise DownloadError("INVALID_PRESET", "The selected output preset is not supported.")
        command.append(normalized)

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            raise DownloadError("SERVICE_UNAVAILABLE", "The media engine is not installed.", True) from exc

        stderr_chunks: list[bytes] = []

        async def read_stderr() -> None:
            assert process.stderr
            while chunk := await process.stderr.readline():
                stderr_chunks.append(chunk)
                if sum(map(len, stderr_chunks)) > 24_000:
                    stderr_chunks.pop(0)

        stderr_task = asyncio.create_task(read_stderr())
        try:
            assert process.stdout
            while process.returncode is None:
                if cancel_event.is_set():
                    await terminate_process(process)
                    raise DownloadError("CANCELLED", "Download cancelled.")
                try:
                    line = await asyncio.wait_for(process.stdout.readline(), timeout=0.5)
                except TimeoutError:
                    continue
                if not line:
                    if process.returncode is None:
                        await process.wait()
                    break
                decoded = line.decode("utf-8", "replace").strip()
                if decoded.startswith("SBPROGRESS|"):
                    parts = decoded.split("|", 3)
                    percent_match = re.search(r"([0-9.]+)%", parts[1]) if len(parts) > 1 else None
                    percent = float(percent_match.group(1)) if percent_match else 0
                    speed = parts[2].strip() if len(parts) > 2 and parts[2].strip() not in {"NA", "Unknown"} else None
                    eta = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else None
                    await progress(percent, speed, eta)
            await process.wait()
        except asyncio.CancelledError:
            await terminate_process(process)
            raise
        finally:
            await stderr_task

        if process.returncode:
            raise map_process_error(b"".join(stderr_chunks).decode("utf-8", "replace"))
        candidates = [
            path
            for path in output_dir.iterdir()
            if path.is_file() and path.suffix not in {".part", ".ytdl", ".json"}
        ]
        if not candidates:
            raise DownloadError("OUTPUT_MISSING", "The media engine completed without producing a file.", True)
        result = max(candidates, key=lambda path: path.stat().st_mtime)
        if result.stat().st_size > self.config.max_file_bytes:
            result.unlink(missing_ok=True)
            raise DownloadError("FILE_TOO_LARGE", "This media exceeds the 2 GB file limit.")
        await progress(100, None, 0)
        return result

    async def _download_direct(
        self,
        normalized: str,
        output_dir: Path,
        cancel_event: asyncio.Event,
        progress: ProgressCallback,
    ) -> Path:
        resolver = PublicResolver()
        connector = aiohttp.TCPConnector(resolver=resolver, ttl_dns_cache=0)
        timeout = aiohttp.ClientTimeout(total=self.config.item_timeout_seconds)
        current = normalized
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            for _ in range(4):
                current, host, port = parse_public_http_url(current)
                await resolver.pin(host, port)
                async with session.get(current, allow_redirects=False, headers={"User-Agent": "SaveBolt/0.1"}) as response:
                    if response.status in {301, 302, 303, 307, 308}:
                        location = response.headers.get("Location")
                        if not location:
                            raise DownloadError("INVALID_REDIRECT", "The media host returned an invalid redirect.")
                        current = urljoin(current, location)
                        continue
                    if response.status != 200:
                        raise DownloadError("SOURCE_ERROR", "The public media host rejected this request.", True)
                    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                    if not (
                        content_type.startswith("video/")
                        or content_type.startswith("audio/")
                        or content_type == "application/octet-stream"
                    ):
                        raise DownloadError("UNSUPPORTED_MEDIA", "The public link did not return an audio or video file.")
                    total = int(response.headers.get("Content-Length", "0") or 0)
                    if total > self.config.max_file_bytes:
                        raise DownloadError("FILE_TOO_LARGE", "This media exceeds the 2 GB file limit.")
                    name = safe_filename(unquote(Path(urlsplit(str(response.url)).path).name) or "public-media")
                    destination = output_dir / name
                    written = 0
                    with destination.open("wb") as handle:
                        async for chunk in response.content.iter_chunked(256 * 1024):
                            if cancel_event.is_set():
                                raise DownloadError("CANCELLED", "Download cancelled.")
                            written += len(chunk)
                            if written > self.config.max_file_bytes:
                                raise DownloadError("FILE_TOO_LARGE", "This media exceeds the 2 GB file limit.")
                            handle.write(chunk)
                            percent = written / total * 100 if total else 0
                            await progress(percent, None, None)
                    await progress(100, None, 0)
                    return destination
        raise DownloadError("TOO_MANY_REDIRECTS", "The media link redirected too many times.")


def binary_available(binary: str) -> bool:
    return shutil.which(binary) is not None
