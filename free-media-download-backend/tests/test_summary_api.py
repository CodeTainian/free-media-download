from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app, limiter, summaries
from app.models import JobStatus, SummaryJobView, SummaryStage


def queued_view(job_id: str) -> SummaryJobView:
    return SummaryJobView(
        id=job_id,
        status=JobStatus.QUEUED,
        stage=SummaryStage.QUEUED,
        created_at="2026-07-22T00:00:00+00:00",
    )


def test_summary_rejects_unsupported_platform_before_provider_check():
    limiter.events.clear()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/summaries", json={"url": "https://vimeo.com/123"}
        )
    assert response.status_code == 422
    assert response.json()["code"] == "SUMMARY_UNSUPPORTED_PLATFORM"


def test_summary_reports_missing_server_provider_configuration(monkeypatch):
    monkeypatch.setattr(summaries, "ready", lambda: False)
    limiter.events.clear()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/summaries",
            json={"url": "https://www.youtube.com/watch?v=public"},
        )
    assert response.status_code == 503
    assert response.json() == {
        "code": "SUMMARY_PROVIDER_UNAVAILABLE",
        "message": "AI summaries are not configured on this server.",
        "retryable": True,
    }


def test_summary_create_has_stable_shape_and_enforces_daily_limit(monkeypatch):
    created = 0

    async def fake_create(_payload):
        nonlocal created
        created += 1
        return SimpleNamespace(id=f"summary-{created}")

    monkeypatch.setattr(summaries, "ready", lambda: True)
    monkeypatch.setattr(summaries, "create", fake_create)
    monkeypatch.setattr(summaries, "view", lambda job: queued_view(job.id))
    limiter.events.clear()
    with TestClient(app) as client:
        responses = [
            client.post(
                "/api/v1/summaries",
                json={"url": "https://www.youtube.com/watch?v=public"},
            )
            for _ in range(6)
        ]

    assert [response.status_code for response in responses] == [201, 201, 201, 201, 201, 429]
    first = responses[0].json()
    assert first["summary"]["status"] == "queued"
    assert first["events_url"] == "/api/v1/summaries/summary-1/events"
    assert responses[-1].json()["code"] == "SUMMARY_RATE_LIMITED"
    assert created == 5


def test_summary_output_language_is_fixed_to_english():
    limiter.events.clear()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/summaries",
            json={
                "url": "https://www.youtube.com/watch?v=public",
                "output_language": "zh-CN",
            },
        )
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"


def test_missing_summary_uses_public_not_found_error():
    with TestClient(app) as client:
        response = client.get("/api/v1/summaries/not-a-summary")
    assert response.status_code == 404
    assert response.json() == {
        "code": "NOT_FOUND",
        "message": "Summary not found",
        "retryable": False,
    }
