from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    configured = os.getenv(name)
    if configured is None:
        return default
    return configured.strip().lower() in {"1", "true", "yes", "on"}


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
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


def _optional_path(name: str) -> Path | None:
    configured = os.getenv(name, "").strip()
    return Path(configured).expanduser() if configured else None


def _cookie_platforms() -> frozenset[str]:
    configured = os.getenv("SAVEBOLT_COOKIE_PLATFORMS", "youtube,bilibili")
    platforms = frozenset(value.strip().lower() for value in configured.split(",") if value.strip())
    if any(not re.fullmatch(r"[a-z0-9-]+", platform) for platform in platforms):
        raise ValueError("SAVEBOLT_COOKIE_PLATFORMS must contain comma-separated platform keys")
    return platforms


def _optional_text(name: str) -> str | None:
    return os.getenv(name, "").strip() or None


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


def _ffprobe_binary() -> str:
    configured = os.getenv("SAVEBOLT_FFPROBE_BINARY")
    if configured:
        return configured
    return shutil.which("ffprobe") or "ffprobe"


def _yt_dlp_binary() -> str:
    configured = os.getenv("SAVEBOLT_YTDLP_BINARY", "").strip()
    if configured:
        return configured
    environment_binary = Path(sys.executable).with_name("yt-dlp")
    if environment_binary.is_file() and os.access(environment_binary, os.X_OK):
        return str(environment_binary)
    return shutil.which("yt-dlp") or "yt-dlp"


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
    summary_max_duration_seconds: int = _int("SAVEBOLT_SUMMARY_MAX_DURATION_SECONDS", 2 * 60 * 60)
    summary_caption_timeout_seconds: int = _int("SAVEBOLT_SUMMARY_CAPTION_TIMEOUT_SECONDS", 2 * 60)
    summary_daily_limit: int = _int("SAVEBOLT_SUMMARY_DAILY_LIMIT", 5)
    summary_worker_concurrency: int = _int("SAVEBOLT_SUMMARY_WORKER_CONCURRENCY", 2)
    summary_job_ttl_seconds: int = _int("SAVEBOLT_SUMMARY_JOB_TTL_SECONDS", 30 * 60)
    summary_request_timeout_seconds: int = _int("SAVEBOLT_SUMMARY_REQUEST_TIMEOUT_SECONDS", 60)
    summary_chunk_characters: int = _int("SAVEBOLT_SUMMARY_CHUNK_CHARACTERS", 12_000)
    analysis_worker_concurrency: int = _int("SAVEBOLT_ANALYSIS_WORKER_CONCURRENCY", 2)
    analysis_job_ttl_seconds: int = _int("SAVEBOLT_ANALYSIS_JOB_TTL_SECONDS", 30 * 60)
    analysis_semantic_unit_characters: int = _int(
        "SAVEBOLT_ANALYSIS_SEMANTIC_UNIT_CHARACTERS", 4_000
    )
    analysis_provider_chunk_characters: int = _int(
        "SAVEBOLT_ANALYSIS_PROVIDER_CHUNK_CHARACTERS", 24_000
    )
    analysis_max_mind_map_nodes: int = _int("SAVEBOLT_ANALYSIS_MAX_MIND_MAP_NODES", 80)
    analysis_max_mind_map_depth: int = _int("SAVEBOLT_ANALYSIS_MAX_MIND_MAP_DEPTH", 5)
    analysis_visual_story_frames: int = _int("SAVEBOLT_ANALYSIS_VISUAL_STORY_FRAMES", 8)
    deepseek_api_key: str | None = field(
        default=_optional_text("DEEPSEEK_API_KEY"), repr=False
    )
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash").strip()
    transcription_provider: str = os.getenv("TRANSCRIPTION_PROVIDER", "none").strip().lower()
    transcription_api_key: str | None = field(
        default=_optional_text("TRANSCRIPTION_API_KEY"), repr=False
    )
    transcription_model: str = os.getenv("TRANSCRIPTION_MODEL", "whisper-1").strip()
    transcription_base_url: str = os.getenv(
        "TRANSCRIPTION_BASE_URL", "https://api.openai.com/v1"
    ).rstrip("/")
    transcription_timeout_seconds: float = _float("TRANSCRIPTION_TIMEOUT_SECONDS", 900)
    transcription_max_duration_seconds: int = _int(
        "TRANSCRIPTION_MAX_DURATION_SECONDS", 2 * 60 * 60
    )
    transcription_max_file_bytes: int = _int(
        "TRANSCRIPTION_MAX_FILE_BYTES", 24 * 1024**2
    )
    transcription_chunk_seconds: int = _int("TRANSCRIPTION_CHUNK_SECONDS", 600)
    transcription_chunk_overlap_seconds: float = _float(
        "TRANSCRIPTION_CHUNK_OVERLAP_SECONDS", 2
    )
    yt_dlp_binary: str = _yt_dlp_binary()
    ffmpeg_binary: str = _ffmpeg_binary()
    ffprobe_binary: str = _ffprobe_binary()
    yt_dlp_js_runtime: str = os.getenv("SAVEBOLT_YTDLP_JS_RUNTIME", "node")
    cookies_from_browser: str | None = _cookies_from_browser()
    cookies_file: Path | None = _optional_path("SAVEBOLT_COOKIES_FILE")
    cookie_platforms: frozenset[str] = _cookie_platforms()
    yt_dlp_user_agent: str | None = _optional_text("SAVEBOLT_YTDLP_USER_AGENT")
    yt_dlp_proxy: str | None = _optional_text("SAVEBOLT_YTDLP_PROXY")
    anonymous_browser_cookies: bool = _bool("SAVEBOLT_ANONYMOUS_BROWSER_COOKIES", True)
    browser_binary: str | None = _optional_text("SAVEBOLT_BROWSER_BINARY")
    browser_no_sandbox: bool = _bool("SAVEBOLT_BROWSER_NO_SANDBOX", False)
    browser_impersonate: str | None = (
        os.getenv("SAVEBOLT_BROWSER_IMPERSONATE", "chrome").strip() or None
    )
    browser_session_ttl_seconds: int = _int("SAVEBOLT_BROWSER_SESSION_TTL_SECONDS", 20 * 60)
    browser_cookie_wait_seconds: int = _int("SAVEBOLT_BROWSER_COOKIE_WAIT_SECONDS", 20)
    browser_start_timeout_seconds: int = _int("SAVEBOLT_BROWSER_START_TIMEOUT_SECONDS", 20)
    cors_origins: tuple[str, ...] = tuple(
        value.strip()
        for value in os.getenv(
            "SAVEBOLT_CORS_ORIGINS",
            "http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000,http://127.0.0.1:3001",
        ).split(",")
        if value.strip()
    )

    def __post_init__(self) -> None:
        if self.cookies_from_browser and self.cookies_file:
            raise ValueError(
                "Configure either SAVEBOLT_COOKIES_FROM_BROWSER or SAVEBOLT_COOKIES_FILE, not both"
            )
        if self.transcription_provider not in {"none", "openai_compatible"}:
            raise ValueError(
                "TRANSCRIPTION_PROVIDER must be 'none' or 'openai_compatible'"
            )
        parsed_base_url = urlsplit(self.transcription_base_url)
        if (
            parsed_base_url.scheme not in {"http", "https"}
            or not parsed_base_url.hostname
            or parsed_base_url.username
            or parsed_base_url.password
        ):
            raise ValueError(
                "TRANSCRIPTION_BASE_URL must be an HTTP(S) URL without credentials"
            )
        if (
            self.transcription_timeout_seconds <= 0
            or self.transcription_max_duration_seconds <= 0
            or self.transcription_max_file_bytes <= 0
            or self.transcription_chunk_seconds <= 0
            or self.transcription_chunk_overlap_seconds < 0
            or self.transcription_chunk_overlap_seconds
            >= self.transcription_chunk_seconds
        ):
            raise ValueError("Transcription limits must be positive and overlap must be smaller than a chunk")
        if (
            self.analysis_worker_concurrency <= 0
            or self.analysis_job_ttl_seconds <= 0
            or self.analysis_semantic_unit_characters < 500
            or self.analysis_provider_chunk_characters
            < self.analysis_semantic_unit_characters
            or not 10 <= self.analysis_max_mind_map_nodes <= 80
            or not 2 <= self.analysis_max_mind_map_depth <= 5
            or not 6 <= self.analysis_visual_story_frames <= 12
        ):
            raise ValueError("Analysis limits are invalid")

    @property
    def transcription_configured(self) -> bool:
        return bool(
            self.transcription_provider == "openai_compatible"
            and self.transcription_api_key
            and self.transcription_model
            and self.transcription_base_url
        )


settings = Settings()
