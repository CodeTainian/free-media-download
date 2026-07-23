import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.downloader import (
    DownloadError,
    TranscriptSource,
    YtDlpService,
    _build_presets,
    map_process_error,
)
from app.config import Settings, _yt_dlp_binary
from app.models import ProbeResponse


def test_builds_honest_error_messages():
    bot_check = map_process_error("Sign in to confirm you're not a bot. Use --cookies-from-browser")
    assert bot_check.code == "YOUTUBE_BOT_CHECK"
    assert bot_check.retryable is True
    unavailable = map_process_error("ERROR: [youtube] abc: Video unavailable")
    assert unavailable.code == "MEDIA_UNAVAILABLE"
    assert unavailable.retryable is False
    assert map_process_error("ERROR: Private video").code == "AUTH_REQUIRED"
    assert map_process_error("This video is DRM protected").code == "DRM_PROTECTED"
    assert map_process_error("HTTP Error 429: Too Many Requests").retryable is True
    assert map_process_error("Fresh cookies (not necessarily logged in) are needed").code == "COOKIE_REQUIRED"
    assert map_process_error("Your IP address is blocked from accessing this post").code == "PLATFORM_ACCESS_BLOCKED"
    assert map_process_error("PhantomJS not found").code == "RUNTIME_UNAVAILABLE"
    assert map_process_error("No video formats found!").code == "NO_MEDIA"
    assert map_process_error("Unsupported URL").code == "UNSUPPORTED_URL"
    assert map_process_error("No suitable extractor found for URL").code == "UNSUPPORTED_URL"
    assert map_process_error("Requested format is not available").code == "FORMAT_UNAVAILABLE"
    assert (
        map_process_error('Impersonate target "chrome" is not available. Missing dependencies.').code
        == "IMPERSONATION_UNAVAILABLE"
    )


def test_direct_probe_requires_original_preset(tmp_path):
    service = YtDlpService(Settings(data_dir=tmp_path))
    assert service.config.max_batch_items == 10


def test_yt_dlp_auto_discovers_current_virtual_environment(tmp_path, monkeypatch):
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    python = binary_dir / "python"
    yt_dlp = binary_dir / "yt-dlp"
    python.touch()
    yt_dlp.touch(mode=0o755)
    monkeypatch.delenv("SAVEBOLT_YTDLP_BINARY", raising=False)
    monkeypatch.setattr("app.config.sys.executable", str(python))
    monkeypatch.setattr("app.config.shutil.which", lambda _name: None)

    assert _yt_dlp_binary() == str(yt_dlp)


def test_explicit_yt_dlp_binary_takes_precedence(monkeypatch):
    monkeypatch.setenv("SAVEBOLT_YTDLP_BINARY", "/opt/savebolt/yt-dlp")
    assert _yt_dlp_binary() == "/opt/savebolt/yt-dlp"


def test_browser_session_is_only_added_to_configured_platform_commands(tmp_path):
    service = YtDlpService(Settings(data_dir=tmp_path, cookies_from_browser="chrome"))
    assert service._platform_args("youtube") == ["--cookies-from-browser", "chrome"]
    assert service._platform_args("bilibili") == ["--cookies-from-browser", "chrome"]
    assert service._platform_args("vimeo") == []


def test_browser_session_can_be_enabled_for_douyin(tmp_path):
    service = YtDlpService(
        Settings(
            data_dir=tmp_path,
            cookies_from_browser="firefox",
            cookie_platforms=frozenset({"douyin", "ixigua"}),
            yt_dlp_user_agent="Mozilla/5.0 test",
        )
    )
    assert service._platform_args("douyin") == [
        "--user-agent",
        "Mozilla/5.0 test",
        "--cookies-from-browser",
        "firefox",
    ]
    assert service._platform_args("youtube") == ["--user-agent", "Mozilla/5.0 test"]


def test_cookie_file_and_proxy_are_passed_without_a_shell(tmp_path):
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("# Netscape HTTP Cookie File\n")
    service = YtDlpService(
        Settings(
            data_dir=tmp_path,
            cookies_file=cookie_file,
            cookie_platforms=frozenset({"douyin"}),
            yt_dlp_proxy="http://127.0.0.1:8080",
        )
    )
    assert service._platform_args("douyin") == [
        "--proxy",
        "http://127.0.0.1:8080",
        "--cookies",
        str(cookie_file),
    ]


def test_rejects_two_cookie_sources(tmp_path):
    with pytest.raises(ValueError, match="either"):
        Settings(
            data_dir=tmp_path,
            cookies_from_browser="chrome",
            cookies_file=tmp_path / "cookies.txt",
        )


def test_missing_cookie_file_returns_configuration_error(tmp_path):
    service = YtDlpService(
        Settings(
            data_dir=tmp_path,
            cookies_file=tmp_path / "missing.cookies.txt",
            cookie_platforms=frozenset({"douyin"}),
        )
    )
    with pytest.raises(DownloadError) as caught:
        service._platform_args("douyin")
    assert caught.value.code == "COOKIE_SOURCE_ERROR"


@pytest.mark.asyncio
async def test_successful_probe_is_cached(tmp_path, monkeypatch):
    service = YtDlpService(Settings(data_dir=tmp_path, probe_cache_ttl_seconds=300))
    uncached = AsyncMock(return_value=ProbeResponse(items=[]))
    monkeypatch.setattr(service, "_probe_uncached", uncached)

    first = await service.probe("https://www.youtube.com/watch?v=public")
    second = await service.probe("https://www.youtube.com/watch?v=public")

    assert first == second
    assert first is not second
    uncached.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_probe_is_not_cached(tmp_path, monkeypatch):
    service = YtDlpService(Settings(data_dir=tmp_path, probe_cache_ttl_seconds=300))
    uncached = AsyncMock(side_effect=DownloadError("YOUTUBE_BOT_CHECK", "Wait and retry.", True))
    monkeypatch.setattr(service, "_probe_uncached", uncached)

    for _ in range(2):
        with pytest.raises(DownloadError, match="Wait and retry"):
            await service.probe("https://www.youtube.com/watch?v=public")

    assert uncached.await_count == 2


@pytest.mark.asyncio
async def test_platform_download_requires_ffmpeg(tmp_path, monkeypatch):
    service = YtDlpService(Settings(data_dir=tmp_path, ffmpeg_binary="missing-ffmpeg"))
    monkeypatch.setattr("app.downloader.binary_available", lambda _: False)
    with pytest.raises(DownloadError) as caught:
        await service.download(
            "https://www.youtube.com/watch?v=public",
            "best",
            tmp_path / "out",
            asyncio.Event(),
            lambda *_: asyncio.sleep(0),
        )
    assert caught.value.code == "SERVICE_UNAVAILABLE"


def test_format_mapping_only_exposes_available_resolutions():
    presets = _build_presets(
        {
            "formats": [
                {"height": 360, "vcodec": "h264"},
                {"height": 720, "vcodec": "h264"},
                {"height": 1080, "vcodec": "av01"},
                {"height": None, "vcodec": "none"},
            ]
        }
    )
    assert [preset.id for preset in presets] == ["best", "mp4-1080", "mp4-720", "mp4-480", "mp4-360", "mp3"]


def test_format_mapping_does_not_offer_tiers_below_lowest_source():
    presets = _build_presets(
        {
            "formats": [
                {"height": 576, "vcodec": "h264"},
                {"height": 720, "vcodec": "h264"},
                {"height": 1080, "vcodec": "h264"},
            ]
        }
    )
    assert [preset.id for preset in presets] == ["best", "mp4-1080", "mp4-720", "mp3"]


@pytest.mark.asyncio
async def test_transcription_audio_extraction_uses_fixed_safe_command(
    tmp_path, monkeypatch
):
    service = YtDlpService(
        Settings(data_dir=tmp_path, yt_dlp_binary="yt-dlp-test")
    )
    output_dir = tmp_path / "summaries" / "job" / "audio" / "source"
    captured: list[str] = []

    class Stream:
        def __init__(self, lines):
            self.lines = list(lines)

        async def readline(self):
            return self.lines.pop(0) if self.lines else b""

    class Process:
        def __init__(self):
            self.returncode = None
            self.stdout = Stream([b"SBPROGRESS|50.0%\n", b""])
            self.stderr = Stream([])

        async def wait(self):
            self.returncode = 0
            return 0

    async def fake_create(*command, **kwargs):
        captured.extend(command)
        assert kwargs["start_new_session"] is True
        template = Path(command[command.index("-o") + 1])
        template.with_name(template.name.replace("%(ext)s", "m4a")).write_bytes(
            b"audio"
        )
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    source = TranscriptSource(
        platform="youtube",
        normalized_url="https://www.youtube.com/watch?v=public",
        source_url="https://www.youtube.com/watch?v=public",
        title="Public lesson",
        duration=60,
        info={"formats": [{"acodec": "aac"}]},
    )
    progress: list[float] = []
    result = await service.extract_transcription_audio(
        source,
        output_dir,
        asyncio.Event(),
        lambda value: _capture_progress(progress, value),
    )

    assert result.is_file()
    assert progress == [0.5, 1]
    assert "--ignore-config" in captured
    assert "--no-playlist" in captured
    assert captured[captured.index("--use-extractors") + 1] == "default,-generic"
    assert captured[captured.index("-f") + 1] == "ba/b"
    assert "--cookies-from-browser" not in captured


async def _capture_progress(values, value):
    values.append(value)


@pytest.mark.asyncio
async def test_transcription_audio_extraction_cancels_yt_dlp(
    tmp_path, monkeypatch
):
    service = YtDlpService(
        Settings(data_dir=tmp_path, yt_dlp_binary="yt-dlp-test")
    )
    cancel_event = asyncio.Event()
    terminated = asyncio.Event()

    class BlockingStream:
        async def readline(self):
            await asyncio.sleep(60)

    class EmptyStream:
        async def readline(self):
            return b""

    class Process:
        returncode = None
        stdout = BlockingStream()
        stderr = EmptyStream()

        async def wait(self):
            return self.returncode

    async def fake_create(*_command, **_kwargs):
        return Process()

    async def fake_terminate(process):
        process.returncode = -15
        terminated.set()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    monkeypatch.setattr("app.downloader.terminate_process", fake_terminate)
    source = TranscriptSource(
        platform="youtube",
        normalized_url="https://www.youtube.com/watch?v=public",
        source_url="https://www.youtube.com/watch?v=public",
        title="Public lesson",
        duration=60,
        info={"formats": [{"acodec": "aac"}]},
    )
    task = asyncio.create_task(
        service.extract_transcription_audio(
            source,
            tmp_path / "summaries" / "job" / "audio" / "source",
            cancel_event,
            lambda _value: asyncio.sleep(0),
        )
    )
    await asyncio.sleep(0)
    cancel_event.set()
    with pytest.raises(DownloadError) as caught:
        await task
    assert caught.value.code == "CANCELLED"
    assert terminated.is_set()


@pytest.mark.asyncio
async def test_direct_probe_rejects_declared_oversize_file(tmp_path, monkeypatch):
    service = YtDlpService(Settings(data_dir=tmp_path, max_file_bytes=10))

    async def fake_headers(url):
        return url, {"Content-Type": "video/mp4", "Content-Length": "11"}

    monkeypatch.setattr(service, "_direct_headers", fake_headers)
    with pytest.raises(DownloadError, match="2 GB") as caught:
        await service.probe("https://media.example.org/sample.mp4")
    assert caught.value.code == "FILE_TOO_LARGE"
