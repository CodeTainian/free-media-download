from pathlib import Path

from fastapi.testclient import TestClient

from app.main import (
    MemoryRateLimiter,
    app,
    downloader,
    impersonation_target_available,
    jobs,
    limiter,
)
from app.downloader import DownloadError
from app.models import MediaItem, OutputKind, Preset, ProbeResponse


def sample_probe(url: str) -> ProbeResponse:
    return ProbeResponse(
        items=[
            MediaItem(
                source_url=url,
                title="Public sample",
                platform="Vimeo",
                duration=20,
                presets=[Preset(id="mp4-720", label="720p MP4", detail="Mobile-compatible video", kind=OutputKind.VIDEO, extension="mp4", height=720)],
            )
        ]
    )


def test_health_has_stable_shape():
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert set(response.json()) >= {
        "status",
        "api",
        "yt_dlp",
        "ffmpeg",
        "anonymous_browser",
        "request_impersonation",
        "transcription",
        "transcription_provider",
    }


def test_health_detects_missing_request_impersonation_dependency():
    unavailable = "Client OS Source\nChrome - curl_cffi (unavailable)\n"
    available = "Client OS Source\nChrome-136 Macos-15 curl_cffi\n"

    assert impersonation_target_available(unavailable, "chrome") is False
    assert impersonation_target_available(available, "chrome") is True
    assert impersonation_target_available(None, None) is True


def test_probe_endpoint(monkeypatch):
    async def fake_probe(url):
        return sample_probe(url)

    monkeypatch.setattr(downloader, "probe", fake_probe)
    limiter.events.clear()
    with TestClient(app) as client:
        response = client.post("/api/v1/media/probe", json={"url": "https://vimeo.com/123"})
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["title"] == "Public sample"
    assert item["summary_supported"] is False
    assert item["caption_languages"] == []
    assert item["transcript_strategy_hint"] == "unsupported"


def test_youtube_bot_check_has_retryable_public_error(monkeypatch):
    async def fake_probe(_url):
        raise DownloadError(
            "YOUTUBE_BOT_CHECK",
            "YouTube is temporarily requiring bot verification. Please wait a while and try again.",
            True,
        )

    monkeypatch.setattr(downloader, "probe", fake_probe)
    limiter.events.clear()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/media/probe",
            json={"url": "https://www.youtube.com/watch?v=public"},
        )
    assert response.status_code == 503
    assert response.json()["code"] == "YOUTUBE_BOT_CHECK"
    assert response.json()["retryable"] is True


def test_cookie_requirement_has_retryable_service_error(monkeypatch):
    async def fake_probe(_url):
        raise DownloadError("COOKIE_REQUIRED", "Refresh the configured cookies.", True)

    monkeypatch.setattr(downloader, "probe", fake_probe)
    limiter.events.clear()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/media/probe",
            json={"url": "https://www.douyin.com/video/public"},
        )
    assert response.status_code == 503
    assert response.json() == {
        "code": "COOKIE_REQUIRED",
        "message": "Refresh the configured cookies.",
        "retryable": True,
    }


def test_rejects_similar_domain_before_job_creation():
    limiter.events.clear()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/jobs",
            json={"items": [{"url": "https://youtube.com.attacker.example/video", "preset_id": "best"}], "bundle": False},
        )
    assert response.status_code == 400
    assert response.json()["code"] == "UNSAFE_URL"


def test_job_snapshot_and_cancel(monkeypatch, tmp_path):
    async def fake_download(raw_url, preset_id, output_dir, cancel_event, progress):
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "test.mp4"
        path.write_bytes(b"video")
        await progress(100, None, 0)
        return path

    monkeypatch.setattr(downloader, "download", fake_download)
    old_dir = jobs.config.data_dir
    object.__setattr__(jobs.config, "data_dir", tmp_path)
    limiter.events.clear()
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/v1/jobs",
                json={"items": [{"url": "https://vimeo.com/123", "preset_id": "best", "title": "Sample"}], "bundle": False},
            )
            assert created.status_code == 201
            job_id = created.json()["job"]["id"]
            snapshot = client.get(f"/api/v1/jobs/{job_id}")
            assert snapshot.status_code == 200
            cancelled = client.delete(f"/api/v1/jobs/{job_id}")
            assert cancelled.status_code == 204
    finally:
        object.__setattr__(jobs.config, "data_dir", old_dir)


def test_http_errors_use_public_error_envelope():
    with TestClient(app) as client:
        response = client.get("/api/v1/jobs/not-a-job")
    assert response.status_code == 404
    assert response.json() == {
        "code": "NOT_FOUND",
        "message": "Job not found",
        "retryable": False,
    }


def test_memory_rate_limiter_is_bounded():
    test_limiter = MemoryRateLimiter()
    assert test_limiter.check("127.0.0.1", "probe", 2, 60)
    assert test_limiter.check("127.0.0.1", "probe", 2, 60)
    assert not test_limiter.check("127.0.0.1", "probe", 2, 60)
