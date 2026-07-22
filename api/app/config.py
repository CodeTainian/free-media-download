from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


SUPPORTED_COOKIE_BROWSERS = frozenset(
    {"brave", "chrome", "chromium", "edge", "firefox", "opera", "safari", "vivaldi", "whale"}
)


def _cookies_from_browser() -> str | None:
    configured = os.getenv("SAVEBOLT_COOKIES_FROM_BROWSER", "").strip().lower()
    if not configured:
        return None
    if configured not in SUPPORTED_COOKIE_BROWSERS:
        supported = ", ".join(sorted(SUPPORTED_COOKIE_BROWSERS))
        raise ValueError(f"SAVEBOLT_COOKIES_FROM_BROWSER must be one of: {supported}")
    return configured


def _ffmpeg_binary() -> str:
    configured = os.getenv("SAVEBOLT_FFMPEG_BINARY")
    if configured:
        return configured
    system_binary = shutil.which("ffmpeg")
    if system_binary:
        return system_binary
    try:
        import imageio_ffmpeg  # type: ignore[import-not-found]

        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        return "ffmpeg"


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path = Path(
        os.getenv("SAVEBOLT_DATA_DIR", str(Path(tempfile.gettempdir()) / "savebolt-jobs"))
    )
    max_batch_items: int = _int("SAVEBOLT_MAX_BATCH_ITEMS", 10)
    max_file_bytes: int = _int("SAVEBOLT_MAX_FILE_BYTES", 2 * 1024**3)
    max_bundle_bytes: int = _int("SAVEBOLT_MAX_BUNDLE_BYTES", 4 * 1024**3)
    max_duration_seconds: int = _int("SAVEBOLT_MAX_DURATION_SECONDS", 6 * 60 * 60)
    probe_timeout_seconds: int = _int("SAVEBOLT_PROBE_TIMEOUT_SECONDS", 30)
    item_timeout_seconds: int = _int("SAVEBOLT_ITEM_TIMEOUT_SECONDS", 60 * 60)
    worker_concurrency: int = _int("SAVEBOLT_WORKER_CONCURRENCY", 2)
    job_ttl_seconds: int = _int("SAVEBOLT_JOB_TTL_SECONDS", 30 * 60)
    cleanup_interval_seconds: int = _int("SAVEBOLT_CLEANUP_INTERVAL_SECONDS", 5 * 60)
    probe_cache_ttl_seconds: int = _int("SAVEBOLT_PROBE_CACHE_TTL_SECONDS", 5 * 60)
    probe_cache_max_entries: int = _int("SAVEBOLT_PROBE_CACHE_MAX_ENTRIES", 256)
    yt_dlp_binary: str = os.getenv("SAVEBOLT_YTDLP_BINARY", "yt-dlp")
    ffmpeg_binary: str = _ffmpeg_binary()
    yt_dlp_js_runtime: str = os.getenv("SAVEBOLT_YTDLP_JS_RUNTIME", "node")
    cookies_from_browser: str | None = _cookies_from_browser()
    cors_origins: tuple[str, ...] = tuple(
        value.strip()
        for value in os.getenv(
            "SAVEBOLT_CORS_ORIGINS",
            "http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000,http://127.0.0.1:3001",
        ).split(",")
        if value.strip()
    )


settings = Settings()
