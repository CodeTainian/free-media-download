from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import shutil
import signal
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import getproxies

import aiohttp

from .browser_session import (
    AnonymousBrowserSessionManager,
    BrowserSessionError,
    BrowserUnavailableError,
)
from .config import Settings
from .models import MediaItem, OutputKind, Preset, ProbeResponse
from .security import (
    UnsafeUrlError,
    classify_url,
    is_short_platform_url,
    parse_public_http_url,
    resolve_public_host,
    safe_filename,
)
from .transcripts import (
    SUMMARY_PLATFORMS,
    CaptionTrack,
    TranscriptDocument,
    caption_languages,
    parse_subtitle_file,
    select_caption_track,
)


class DownloadError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


ProgressCallback = Callable[[float, str | None, int | None], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class TranscriptSource:
    platform: str
    normalized_url: str
    source_url: str
    title: str
    duration: int | None
    info: dict[str, object]


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
    choices = [
        value
        for value in (2160, 1440, 1080, 720, 480, 360)
        if heights and min(heights) <= value <= max(heights)
    ]
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
            label=f"Up to {height}p MP4",
            detail=f"Best source at or below {height}p",
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


def _normalize_info(
    info: dict[str, object],
    source_url: str,
    playlist_item: bool = False,
    platform_key: str | None = None,
    transcription_ready: bool = False,
) -> MediaItem:
    duration = int(info["duration"]) if isinstance(info.get("duration"), (int, float)) else None
    languages = caption_languages(info) if platform_key in SUMMARY_PLATFORMS else []
    if platform_key not in SUMMARY_PLATFORMS:
        transcript_strategy = "unsupported"
    elif languages:
        transcript_strategy = "captions"
    elif has_usable_audio(info):
        transcript_strategy = "audio_transcription"
    else:
        transcript_strategy = "unavailable"
    return MediaItem(
        source_url=str(info.get("webpage_url") or info.get("url") or source_url),
        title=str(info.get("title") or "Untitled media")[:240],
        platform=str(info.get("extractor_key") or info.get("extractor") or "Media"),
        duration=duration,
        thumbnail=str(info["thumbnail"]) if isinstance(info.get("thumbnail"), str) else None,
        uploader=str(info["uploader"])[:160] if isinstance(info.get("uploader"), str) else None,
        is_playlist_item=playlist_item,
        summary_supported=bool(languages)
        or (transcript_strategy == "audio_transcription" and transcription_ready),
        caption_languages=languages,
        transcript_strategy_hint=transcript_strategy,
        presets=_build_presets(info),
    )


def has_usable_audio(info: dict[str, object]) -> bool:
    if info.get("is_live") is True or info.get("live_status") in {
        "is_live",
        "is_upcoming",
        "post_live",
    }:
        return False
    formats = info.get("formats")
    if isinstance(formats, list):
        return any(
            isinstance(item, dict)
            and str(item.get("acodec") or "none").lower() != "none"
            for item in formats
        )
    return str(info.get("acodec") or "none").lower() != "none"


def map_process_error(stderr: str) -> DownloadError:
    text = stderr.lower()
    if "impersonate target" in text and (
        "not available" in text or "missing dependencies" in text
    ):
        return DownloadError(
            "IMPERSONATION_UNAVAILABLE",
            "Browser request impersonation is unavailable. Install the pinned API dependencies and restart the service.",
            True,
        )
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
    cookie_markers = (
        "fresh cookies",
        "cookies (not necessarily logged in) are needed",
        "cookies are needed",
    )
    if any(marker in text for marker in cookie_markers):
        return DownloadError(
            "COOKIE_REQUIRED",
            "This platform requires a fresh server-side browser session. Refresh the configured cookies and try again.",
            True,
        )
    if "your ip address is blocked" in text or "ip address has been blocked" in text:
        return DownloadError(
            "PLATFORM_ACCESS_BLOCKED",
            "The source platform is blocking the downloader's current network address.",
            True,
        )
    if "phantomjs not found" in text:
        return DownloadError(
            "RUNTIME_UNAVAILABLE",
            "This extractor requires the unsupported PhantomJS runtime and is not available in this deployment.",
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
    if "http error 403" in text or "forbidden" in text:
        return DownloadError(
            "PLATFORM_ACCESS_BLOCKED",
            "The source platform rejected this server session. Refresh server-side cookies or try again later.",
            True,
        )
    if "max-filesize" in text or "larger than max-filesize" in text:
        return DownloadError("FILE_TOO_LARGE", "This media exceeds the 2 GB file limit.")
    if "unsupported url" in text or "no suitable extractor found" in text:
        return DownloadError("UNSUPPORTED_URL", "This link is not supported by the selected platform extractor.")
    if "requested format is not available" in text:
        return DownloadError(
            "FORMAT_UNAVAILABLE",
            "The selected quality is no longer available for this media. Analyze the link again.",
            True,
        )
    if "no video formats found" in text or "can't find any video" in text:
        return DownloadError(
            "NO_MEDIA",
            "The platform page was found, but its extractor did not return downloadable media.",
            True,
        )
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
    def __init__(
        self,
        config: Settings,
        browser_sessions: AnonymousBrowserSessionManager | None = None,
        transcription_ready: Callable[[], bool] | None = None,
    ):
        self.config = config
        self._browser_sessions = browser_sessions or AnonymousBrowserSessionManager(config)
        self._probe_cache: dict[str, tuple[float, ProbeResponse]] = {}
        self._probe_inflight: dict[str, asyncio.Task[ProbeResponse]] = {}
        self._probe_cache_lock = asyncio.Lock()
        self._transcription_ready = transcription_ready or (lambda: False)

    async def close(self) -> None:
        await self._browser_sessions.close()

    def anonymous_browser_available(self) -> bool:
        return self._browser_sessions.available()

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

        normalized = await self._expand_short_url(platform, normalized)

        payload = await self._load_platform_payload(platform, normalized)

        entries = payload.get("entries") if isinstance(payload, dict) else None
        if isinstance(entries, list):
            valid_entries = [entry for entry in entries if isinstance(entry, dict)][: self.config.max_batch_items]
            items = [
                _normalize_info(
                    entry,
                    normalized,
                    True,
                    platform_key=platform,
                    transcription_ready=self._transcription_ready(),
                )
                for entry in valid_entries
            ]
            truncated = len(entries) > self.config.max_batch_items
        elif isinstance(payload, dict):
            items = [
                _normalize_info(
                    payload,
                    normalized,
                    platform_key=platform,
                    transcription_ready=self._transcription_ready(),
                )
            ]
            truncated = False
        else:
            items = []

        if not items:
            raise DownloadError("NO_MEDIA", "No downloadable public media was found at this link.")
        for item in items:
            if item.duration and item.duration > self.config.max_duration_seconds:
                raise DownloadError("MEDIA_TOO_LONG", "This media exceeds the six-hour duration limit.")
        return ProbeResponse(items=items, truncated=truncated)

    async def _load_platform_payload(self, platform: str, normalized: str) -> dict[str, object]:
        stdout, stderr, returncode = await self._run_probe_process(platform, normalized)
        if returncode:
            error = map_process_error(stderr.decode("utf-8", "replace"))
            if error.code == "COOKIE_REQUIRED" and self._uses_managed_session(platform):
                stdout, stderr, returncode = await self._run_probe_process(
                    platform, normalized, force_session=True
                )
                if returncode:
                    raise map_process_error(stderr.decode("utf-8", "replace"))
            else:
                raise error

        try:
            payload = json.loads(stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DownloadError(
                "INVALID_RESPONSE", "The source returned an unreadable response.", True
            ) from exc
        if not isinstance(payload, dict):
            raise DownloadError("INVALID_RESPONSE", "The source returned an unreadable response.", True)
        return payload

    async def _run_probe_process(
        self,
        platform: str,
        normalized: str,
        force_session: bool = False,
    ) -> tuple[bytes, bytes, int]:
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
        command.extend(
            await self._resolved_platform_args(platform, normalized, force_session=force_session)
        )
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
        return stdout, stderr, int(process.returncode or 0)

    def _caption_download_command(
        self,
        normalized: str,
        output_dir: Path,
        track: CaptionTrack,
        platform_args: list[str],
    ) -> list[str]:
        command = [
            self.config.yt_dlp_binary,
            "--skip-download",
            "--no-playlist",
            "--no-warnings",
            "--no-colors",
            "--ignore-config",
            "--use-extractors",
            "default,-generic",
            "--js-runtimes",
            self.config.yt_dlp_js_runtime,
            "--sub-langs",
            track.language,
            "--sub-format",
            "vtt/srt",
            "--output",
            str(output_dir / "savebolt-caption.%(ext)s"),
            "--write-auto-subs" if track.automatic else "--write-subs",
        ]
        command.extend(platform_args)
        command.append(normalized)
        return command

    async def _download_caption_file(
        self,
        platform: str,
        normalized: str,
        output_dir: Path,
        track: CaptionTrack,
        cancel_event: asyncio.Event | None,
    ) -> Path:
        if cancel_event and cancel_event.is_set():
            raise DownloadError("CANCELLED", "The summary job was cancelled.")
        output_dir.mkdir(parents=True, exist_ok=True)
        platform_args = await self._resolved_platform_args(platform, normalized)
        command = self._caption_download_command(normalized, output_dir, track, platform_args)
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            raise DownloadError("SERVICE_UNAVAILABLE", "The media engine is not installed.", True) from exc

        communicate_task = asyncio.create_task(process.communicate())
        cancel_task = asyncio.create_task(cancel_event.wait()) if cancel_event else None
        waiters: set[asyncio.Task[object]] = {communicate_task}  # type: ignore[arg-type]
        if cancel_task:
            waiters.add(cancel_task)  # type: ignore[arg-type]
        try:
            done, _ = await asyncio.wait(
                waiters,
                timeout=self.config.summary_caption_timeout_seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if communicate_task in done:
                _stdout, stderr = communicate_task.result()
            elif cancel_task and cancel_task in done and cancel_event and cancel_event.is_set():
                await terminate_process(process)
                communicate_task.cancel()
                await asyncio.gather(communicate_task, return_exceptions=True)
                raise DownloadError("CANCELLED", "The summary job was cancelled.")
            else:
                await terminate_process(process)
                communicate_task.cancel()
                await asyncio.gather(communicate_task, return_exceptions=True)
                raise DownloadError(
                    "CAPTION_TIMEOUT", "Caption retrieval took too long.", True
                )
        except asyncio.CancelledError:
            await terminate_process(process)
            communicate_task.cancel()
            await asyncio.gather(communicate_task, return_exceptions=True)
            raise
        finally:
            if cancel_task:
                cancel_task.cancel()
                await asyncio.gather(cancel_task, return_exceptions=True)

        if process.returncode:
            error = map_process_error(stderr.decode("utf-8", "replace"))
            if error.code == "DOWNLOAD_FAILED":
                raise DownloadError(
                    "CAPTION_DOWNLOAD_FAILED",
                    "The source platform could not provide this video's captions.",
                    True,
                )
            raise error

        resolved_output_dir = output_dir.resolve()
        candidates = sorted(
            (
                path
                for path in output_dir.glob("savebolt-caption*")
                if path.is_file()
                and path.suffix.lower() in {".vtt", ".srt"}
                and path.resolve().is_relative_to(resolved_output_dir)
            ),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        if not candidates:
            raise DownloadError("NO_CAPTIONS", "This video does not have usable captions.")
        return candidates[0]

    async def fetch_caption_transcript(
        self,
        raw_url: str,
        output_dir: Path,
        preferred_languages: tuple[str, ...] = ("en",),
        cancel_event: asyncio.Event | None = None,
        on_stage: Callable[[str], Awaitable[None]] | None = None,
    ) -> TranscriptDocument:
        source = await self.prepare_transcript_source(raw_url)
        if source.duration and source.duration > self.config.summary_max_duration_seconds:
            raise DownloadError(
                "MEDIA_TOO_LONG", "AI summaries are limited to videos up to two hours long."
            )
        track = select_caption_track(source.info, preferred_languages)
        if not track:
            raise DownloadError("NO_CAPTIONS", "This video does not have usable captions.")
        return await self.fetch_caption_transcript_from_source(
            source,
            output_dir,
            track,
            cancel_event=cancel_event,
            on_stage=on_stage,
        )

    async def prepare_transcript_source(self, raw_url: str) -> TranscriptSource:
        platform, normalized = classify_url(raw_url)
        if platform not in SUMMARY_PLATFORMS:
            raise DownloadError(
                "SUMMARY_UNSUPPORTED_PLATFORM",
                "AI summaries currently support YouTube and Bilibili videos.",
            )
        normalized = await self._expand_short_url(platform, normalized)
        payload = await self._load_platform_payload(platform, normalized)
        entries = payload.get("entries")
        if isinstance(entries, list):
            valid_entries = [entry for entry in entries if isinstance(entry, dict)]
            if len(valid_entries) != 1:
                raise DownloadError(
                    "SUMMARY_SINGLE_VIDEO_REQUIRED",
                    "AI summaries process one video at a time.",
                )
            info = valid_entries[0]
        else:
            info = payload

        duration = int(info["duration"]) if isinstance(info.get("duration"), (int, float)) else None
        return TranscriptSource(
            platform=platform,
            normalized_url=normalized,
            source_url=str(info.get("webpage_url") or info.get("url") or normalized),
            title=str(info.get("title") or "Untitled media")[:240],
            duration=duration,
            info=info,
        )

    async def fetch_caption_transcript_from_source(
        self,
        source: TranscriptSource,
        output_dir: Path,
        track: CaptionTrack,
        *,
        cancel_event: asyncio.Event | None = None,
        on_stage: Callable[[str], Awaitable[None]] | None = None,
    ) -> TranscriptDocument:
        caption_file = await self._download_caption_file(
            source.platform,
            source.normalized_url,
            output_dir,
            track,
            cancel_event,
        )
        if on_stage:
            await on_stage("parsing")
        segments = parse_subtitle_file(caption_file)
        if not segments:
            raise DownloadError("NO_CAPTIONS", "This video does not have usable captions.")
        return TranscriptDocument(
            source_url=source.source_url,
            title=source.title,
            platform=source.platform,
            duration=source.duration,
            language=track.language,
            source_kind=track.source_kind,
            segments=segments,
        )

    async def extract_transcription_audio(
        self,
        source: TranscriptSource,
        output_dir: Path,
        cancel_event: asyncio.Event,
        on_progress: Callable[[float], Awaitable[None]],
    ) -> Path:
        if source.platform not in SUMMARY_PLATFORMS or not has_usable_audio(source.info):
            raise DownloadError(
                "UNSUPPORTED_AUDIO_SOURCE",
                "This public source does not expose a supported audio track.",
            )
        if (
            source.duration
            and source.duration > self.config.transcription_max_duration_seconds
        ):
            raise DownloadError(
                "AUDIO_TOO_LONG",
                "Audio transcription is limited to videos up to two hours long.",
            )
        if cancel_event.is_set():
            raise DownloadError("CANCELLED", "The summary job was cancelled.")

        summary_root = (self.config.data_dir / "summaries").resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        resolved_output = output_dir.resolve()
        if not resolved_output.is_relative_to(summary_root):
            raise DownloadError(
                "AUDIO_EXTRACTION_FAILED",
                "The temporary audio workspace is invalid.",
            )
        token = secrets.token_urlsafe(18).replace("-", "").replace("_", "")
        template = str(output_dir / f"{token}.%(ext)s")
        platform_args = await self._resolved_platform_args(
            source.platform, source.normalized_url
        )
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
            "--max-filesize",
            str(self.config.max_file_bytes),
            "--match-filter",
            f"duration <= {self.config.transcription_max_duration_seconds} & !is_live",
            "--progress-template",
            "download:SBPROGRESS|%(progress._percent_str)s",
            "-f",
            "ba/b",
            "-o",
            template,
        ]
        command.extend(platform_args)
        command.append(source.normalized_url)
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            raise DownloadError(
                "AUDIO_EXTRACTION_FAILED",
                "The media engine is unavailable for audio extraction.",
                True,
            ) from exc

        stderr_chunks: list[bytes] = []

        async def read_stderr() -> None:
            assert process.stderr
            while chunk := await process.stderr.readline():
                stderr_chunks.append(chunk)
                if sum(map(len, stderr_chunks)) > 24_000:
                    stderr_chunks.pop(0)

        stderr_task = asyncio.create_task(read_stderr())
        deadline = time.monotonic() + min(
            self.config.item_timeout_seconds,
            self.config.transcription_timeout_seconds,
        )
        try:
            assert process.stdout
            while process.returncode is None:
                if cancel_event.is_set():
                    await terminate_process(process)
                    raise DownloadError("CANCELLED", "The summary job was cancelled.")
                if time.monotonic() >= deadline:
                    await terminate_process(process)
                    raise DownloadError(
                        "AUDIO_EXTRACTION_FAILED",
                        "Audio extraction took too long.",
                        True,
                    )
                try:
                    line = await asyncio.wait_for(process.stdout.readline(), timeout=0.5)
                except TimeoutError:
                    continue
                if not line:
                    await process.wait()
                    break
                decoded = line.decode("utf-8", "replace").strip()
                if decoded.startswith("SBPROGRESS|"):
                    match = re.search(r"([0-9.]+)%", decoded)
                    if match:
                        await on_progress(min(1, float(match.group(1)) / 100))
            await process.wait()
        except asyncio.CancelledError:
            await terminate_process(process)
            raise
        finally:
            await stderr_task

        if process.returncode:
            mapped = map_process_error(
                b"".join(stderr_chunks).decode("utf-8", "replace")
            )
            if mapped.code == "FILE_TOO_LARGE":
                raise DownloadError(
                    "AUDIO_TOO_LARGE",
                    "The extracted audio exceeds the temporary processing limit.",
                )
            if mapped.code != "DOWNLOAD_FAILED":
                raise mapped
            raise DownloadError(
                "AUDIO_EXTRACTION_FAILED",
                "The source platform could not provide a public audio track.",
                True,
            )
        candidates = [
            path
            for path in output_dir.glob(f"{token}.*")
            if path.is_file()
            and path.resolve().is_relative_to(resolved_output)
            and path.suffix not in {".part", ".ytdl", ".json"}
        ]
        if len(candidates) != 1:
            raise DownloadError(
                "AUDIO_EXTRACTION_FAILED",
                "The media engine did not produce a usable audio track.",
                True,
            )
        result = candidates[0]
        if result.stat().st_size > self.config.max_file_bytes:
            result.unlink(missing_ok=True)
            raise DownloadError(
                "AUDIO_TOO_LARGE",
                "The extracted audio exceeds the temporary processing limit.",
            )
        await on_progress(1)
        return result

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
        normalized = await self._expand_short_url(platform, normalized)
        if not binary_available(self.config.ffmpeg_binary):
            raise DownloadError(
                "SERVICE_UNAVAILABLE",
                "FFmpeg is not available, so this platform download cannot be merged safely.",
                True,
            )
        platform_args = await self._resolved_platform_args(platform, normalized)
        return await self._download_platform(
            platform,
            normalized,
            preset_id,
            output_dir,
            cancel_event,
            progress,
            platform_args,
        )

    def _platform_args(self, platform: str) -> list[str]:
        args: list[str] = []
        if self.config.yt_dlp_proxy:
            args.extend(["--proxy", self.config.yt_dlp_proxy])
        if self.config.yt_dlp_user_agent:
            args.extend(["--user-agent", self.config.yt_dlp_user_agent])
        if platform not in self.config.cookie_platforms:
            return args
        if self.config.cookies_from_browser:
            args.extend(["--cookies-from-browser", self.config.cookies_from_browser])
        elif self.config.cookies_file:
            if not self.config.cookies_file.is_file():
                raise DownloadError(
                    "COOKIE_SOURCE_ERROR",
                    "The configured server-side cookie file is unavailable.",
                    True,
                )
            args.extend(["--cookies", str(self.config.cookies_file)])
        return args

    def _uses_managed_session(self, platform: str) -> bool:
        if not self.config.anonymous_browser_cookies or platform != "douyin":
            return False
        has_configured_cookie = platform in self.config.cookie_platforms and bool(
            self.config.cookies_from_browser or self.config.cookies_file
        )
        return not has_configured_cookie

    async def _resolved_platform_args(
        self,
        platform: str,
        normalized: str,
        force_session: bool = False,
    ) -> list[str]:
        args = self._platform_args(platform)
        if not self._uses_managed_session(platform):
            return args
        try:
            session = await self._browser_sessions.ensure(platform, normalized, force=force_session)
        except BrowserUnavailableError as exc:
            raise DownloadError(
                "BROWSER_UNAVAILABLE",
                "Automatic anonymous session refresh requires Chromium on the API server.",
                True,
            ) from exc
        except BrowserSessionError as exc:
            raise DownloadError(
                "COOKIE_REFRESH_FAILED",
                "The API could not refresh the platform's anonymous browser session.",
                True,
            ) from exc
        if not session:
            return args
        if self.config.browser_impersonate:
            args.extend(["--impersonate", self.config.browser_impersonate])
        args.extend(["--user-agent", session.user_agent, "--cookies", str(session.cookies_file)])
        return args

    async def _expand_short_url(self, platform: str, normalized: str) -> str:
        if not is_short_platform_url(normalized):
            return normalized

        resolver = PublicResolver()
        configured_proxy = self.config.yt_dlp_proxy
        proxy_scheme = urlsplit(configured_proxy).scheme if configured_proxy else ""
        request_proxy = configured_proxy if proxy_scheme in {"http", "https"} else None
        environment_proxies = getproxies() if not configured_proxy else {}
        environment_proxy = environment_proxies.get(urlsplit(normalized).scheme)
        uses_http_proxy = bool(request_proxy or environment_proxy)
        connector = aiohttp.TCPConnector(
            resolver=None if uses_http_proxy else resolver,
            ttl_dns_cache=0,
        )
        timeout = aiohttp.ClientTimeout(total=self.config.probe_timeout_seconds)
        current = normalized
        headers = {
            "User-Agent": self.config.yt_dlp_user_agent
            or "Mozilla/5.0 (compatible; SaveBolt/0.1; +https://localhost)",
        }
        try:
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                trust_env=bool(environment_proxy),
            ) as session:
                for _ in range(5):
                    current, host, port = parse_public_http_url(current)
                    if uses_http_proxy:
                        await resolve_public_host(host, port)
                    else:
                        await resolver.pin(host, port)
                    async with session.get(
                        current,
                        headers=headers,
                        allow_redirects=False,
                        proxy=request_proxy,
                    ) as response:
                        if response.status not in {301, 302, 303, 307, 308}:
                            raise DownloadError(
                                "UNSUPPORTED_URL",
                                "The platform short link could not be expanded to a supported media page.",
                                True,
                            )
                        location = response.headers.get("Location")
                        if not location:
                            raise DownloadError(
                                "INVALID_REDIRECT",
                                "The platform short link returned an invalid redirect.",
                            )
                        candidate = urljoin(current, location)
                        candidate_platform, candidate = classify_url(candidate)
                        if candidate_platform != platform:
                            raise UnsafeUrlError(
                                "The platform short link redirected outside its supported platform."
                            )
                        if not is_short_platform_url(candidate):
                            return candidate
                        current = candidate
        except (UnsafeUrlError, DownloadError):
            raise
        except TimeoutError as exc:
            raise DownloadError(
                "PROBE_TIMEOUT", "The platform short link took too long to respond.", True
            ) from exc
        except aiohttp.ClientError as exc:
            raise DownloadError(
                "SOURCE_ERROR", "The platform short link could not be reached.", True
            ) from exc
        raise DownloadError("TOO_MANY_REDIRECTS", "The platform short link redirected too many times.")

    async def _download_platform(
        self,
        platform: str,
        normalized: str,
        preset_id: str,
        output_dir: Path,
        cancel_event: asyncio.Event,
        progress: ProgressCallback,
        platform_args: list[str],
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
        command.extend(platform_args)
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
