import asyncio
from unittest.mock import AsyncMock

import pytest

from app.downloader import DownloadError, YtDlpService, _build_presets, map_process_error
from app.config import Settings
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
    assert map_process_error("Unsupported URL").code == "UNSUPPORTED_URL"


def test_direct_probe_requires_original_preset(tmp_path):
    service = YtDlpService(Settings(data_dir=tmp_path))
    assert service.config.max_batch_items == 10


def test_browser_session_is_only_added_to_youtube_commands(tmp_path):
    service = YtDlpService(Settings(data_dir=tmp_path, cookies_from_browser="chrome"))
    assert service._youtube_auth_args("youtube") == ["--cookies-from-browser", "chrome"]
    assert service._youtube_auth_args("bilibili") == []


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


@pytest.mark.asyncio
async def test_direct_probe_rejects_declared_oversize_file(tmp_path, monkeypatch):
    service = YtDlpService(Settings(data_dir=tmp_path, max_file_bytes=10))

    async def fake_headers(url):
        return url, {"Content-Type": "video/mp4", "Content-Length": "11"}

    monkeypatch.setattr(service, "_direct_headers", fake_headers)
    with pytest.raises(DownloadError, match="2 GB") as caught:
        await service.probe("https://media.example.org/sample.mp4")
    assert caught.value.code == "FILE_TOO_LARGE"
