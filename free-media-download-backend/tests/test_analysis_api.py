from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.analysis_models import (
    AnalysisDetail,
    AnalysisSnapshot,
    AnalysisStage,
    AnalysisStatus,
    ArtifactKind,
    ArtifactStatus,
    ArtifactView,
)
from app.main import analyses, app, limiter


def queued_snapshot(analysis_id: str) -> AnalysisSnapshot:
    return AnalysisSnapshot(
        id=analysis_id,
        status=AnalysisStatus.QUEUED,
        stage=AnalysisStage.QUEUED,
        progress=0,
        output_language="auto",
        detail=AnalysisDetail.BALANCED,
        artifacts={
            kind: ArtifactView(
                kind=kind,
                status=(
                    ArtifactStatus.QUEUED
                    if kind
                    in {
                        ArtifactKind.SUMMARY,
                        ArtifactKind.CHAPTERS,
                        ArtifactKind.TRANSCRIPT,
                    }
                    else ArtifactStatus.NOT_STARTED
                ),
            )
            for kind in ArtifactKind
        },
        created_at=datetime.now(UTC),
    )


def test_analysis_requires_rights_confirmation():
    limiter.events.clear()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/analyses",
            json={
                "url": "https://www.youtube.com/watch?v=public",
                "rights_confirmed": False,
            },
        )
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"


def test_analysis_rejects_platform_before_provider_check(monkeypatch):
    monkeypatch.setattr(analyses, "ready", lambda: False)
    limiter.events.clear()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/analyses",
            json={"url": "https://vimeo.com/123", "rights_confirmed": True},
        )
    assert response.status_code == 422
    assert response.json()["code"] == "ANALYSIS_UNSUPPORTED_PLATFORM"


def test_analysis_reports_missing_provider(monkeypatch):
    monkeypatch.setattr(analyses, "ready", lambda: False)
    limiter.events.clear()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/analyses",
            json={
                "url": "https://www.youtube.com/watch?v=public",
                "rights_confirmed": True,
            },
        )
    assert response.status_code == 503
    assert response.json()["code"] == "ANALYSIS_PROVIDER_UNAVAILABLE"


def test_analysis_create_supports_language_depth_and_stable_artifact_states(
    monkeypatch,
):
    async def fake_create(_payload):
        return SimpleNamespace(id="analysis-1")

    monkeypatch.setattr(analyses, "ready", lambda: True)
    monkeypatch.setattr(analyses, "create", fake_create)
    monkeypatch.setattr(
        analyses,
        "view",
        lambda job: queued_snapshot(job.id).model_copy(
            update={
                "output_language": "zh-CN",
                "detail": AnalysisDetail.DETAILED,
            }
        ),
    )
    limiter.events.clear()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/analyses",
            json={
                "url": "https://www.bilibili.com/video/BV1public",
                "output_language": "zh-CN",
                "detail": "detailed",
                "rights_confirmed": True,
            },
        )
    assert response.status_code == 201
    payload = response.json()
    assert payload["analysis"]["output_language"] == "zh-CN"
    assert payload["analysis"]["detail"] == "detailed"
    assert payload["analysis"]["artifacts"]["summary"]["status"] == "queued"
    assert payload["analysis"]["artifacts"]["mind_map"]["status"] == "not_started"
    assert payload["events_url"] == "/api/v1/analyses/analysis-1/events"


def test_analysis_snapshot_missing_uses_public_error():
    with TestClient(app) as client:
        response = client.get("/api/v1/analyses/not-an-analysis")
    assert response.status_code == 404
    assert response.json() == {
        "code": "NOT_FOUND",
        "message": "Analysis not found",
        "retryable": False,
    }
