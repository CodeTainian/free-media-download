import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import ValidationError

from app.analysis_exports import export_json, export_markdown, export_website_zip
from app.analysis_jobs import AnalysisJobManager
from app.analysis_models import (
    AnalysisDetail,
    AnalysisSource,
    ArtifactKind,
    ArtifactStatus,
    CanonicalAnalysisDraft,
    CreateAnalysisRequest,
    MindMap,
    MindMapEdge,
    MindMapNode,
    MindMapNodeType,
    WebsiteSource,
)
from app.analysis_provider import AnalysisError, DeepSeekAnalysisProvider
from app.artifact_generators import (
    build_interactive_guide,
    build_mind_map,
    build_summary,
    build_visual_story,
    build_website_manifest,
)
from app.config import Settings
from app.content_analysis import hydrate_canonical_analysis
from app.frame_extractor import FrameExtractionError
from app.semantic_segmentation import segment_transcript
from app.transcripts import TranscriptDocument, TranscriptSegment
from app.website_renderer import render_website_html


def sample_transcript(language: str = "en") -> TranscriptDocument:
    return TranscriptDocument(
        source_url="https://www.youtube.com/watch?v=public",
        title="Evidence-based lesson",
        platform="youtube",
        duration=60,
        language=language,
        source_kind="manual_caption",
        segments=tuple(
            TranscriptSegment(
                id=f"seg-{index:05d}",
                start=(index - 1) * 10,
                end=index * 10,
                text=f"Evidence statement {index}",
            )
            for index in range(1, 7)
        ),
    )


def grounded(text: str, *ids: str) -> dict[str, object]:
    return {"text": text, "evidence_segment_ids": list(ids)}


def sample_draft(*, language: str = "en") -> CanonicalAnalysisDraft:
    chinese = language == "zh-CN"
    return CanonicalAnalysisDraft.model_validate(
        {
            "concise_summary": grounded(
                "核心总结" if chinese else "Core summary", "seg-00001", "seg-00006"
            ),
            "detailed_summary": grounded(
                "详细概览" if chinese else "Detailed overview",
                "seg-00001",
                "seg-00003",
                "seg-00006",
            ),
            "topics": [
                {
                    "id": "topic-foundations",
                    "label": "基础" if chinese else "Foundations",
                    "summary": grounded("基础主题" if chinese else "Foundation theme", "seg-00001"),
                },
                {
                    "id": "topic-outcomes",
                    "label": "结果" if chinese else "Outcomes",
                    "summary": grounded("结果主题" if chinese else "Outcome theme", "seg-00005"),
                },
            ],
            "entities": [
                {
                    "id": "entity-system",
                    "name": "Bubble",
                    "category": "product",
                    "description": grounded("产品实体" if chinese else "Product entity", "seg-00002"),
                }
            ],
            "claims": [
                {
                    "id": "claim-grounded",
                    "statement": grounded("事实结论" if chinese else "Grounded fact", "seg-00003"),
                    "importance": "high",
                }
            ],
            "chapters": [
                {
                    "id": "chapter-opening",
                    "title": "开篇" if chinese else "Opening",
                    "start_seconds": 0,
                    "end_seconds": 30,
                    "summary": grounded("开篇总结" if chinese else "Opening summary", "seg-00001", "seg-00002"),
                    "key_points": [grounded("第一个要点" if chinese else "First point", "seg-00002")],
                    "evidence_segment_ids": ["seg-00001", "seg-00002"],
                },
                {
                    "id": "chapter-conclusion",
                    "title": "结论" if chinese else "Conclusion",
                    "start_seconds": 30,
                    "end_seconds": 60,
                    "summary": grounded("结论总结" if chinese else "Conclusion summary", "seg-00004", "seg-00006"),
                    "key_points": [grounded("最后要点" if chinese else "Final point", "seg-00005")],
                    "evidence_segment_ids": ["seg-00004", "seg-00005", "seg-00006"],
                },
            ],
            "key_points": [
                grounded("第一要点" if chinese else "First takeaway", "seg-00002"),
                grounded("第二要点" if chinese else "Second takeaway", "seg-00005"),
            ],
            "conclusions": [
                grounded("最终结论" if chinese else "Final conclusion", "seg-00006")
            ],
            "glossary": [
                {
                    "id": "term-evidence",
                    "term": "证据" if chinese else "Evidence",
                    "definition": grounded("可核验的依据" if chinese else "A verifiable basis", "seg-00003"),
                }
            ],
            "suggested_questions": [
                {
                    "id": "question-next",
                    "question": "下一步是什么？" if chinese else "What should we examine next?",
                    "reason": grounded("继续探索" if chinese else "Continue exploring", "seg-00006"),
                }
            ],
            "evidence_segment_ids": [f"seg-{index:05d}" for index in range(1, 7)],
        }
    )


class FakeAcquisition:
    def __init__(self, transcript: TranscriptDocument | None = None):
        self.transcript = transcript or sample_transcript()
        self.calls = 0

    async def acquire(self, _url, job_directory, **kwargs):
        self.calls += 1
        job_directory.mkdir(parents=True, exist_ok=True)
        await kwargs["on_stage"]("fetching_captions")
        await kwargs["on_stage"]("parsing_transcript")
        return self.transcript


class FakeAnalysisProvider:
    provider_name = "mock"
    model_name = "mock-structured-v1"

    def __init__(self, draft: CanonicalAnalysisDraft | None = None):
        self.draft = draft or sample_draft()
        self.calls = 0

    def ready(self):
        return True

    async def analyze(self, _transcript, _units, **kwargs):
        self.calls += 1
        await kwargs["on_progress"](1)
        return self.draft

    async def close(self):
        return None


class FakeFrames:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.calls = 0

    async def extract(self, _url, _frames, _directory, _cancel_event, _progress):
        self.calls += 1
        if self.fail:
            raise RuntimeError("private ffmpeg path and diagnostics")
        return {}


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_canonical_analysis_and_all_artifacts_validate(language):
    transcript = sample_transcript("zh-CN" if language == "zh-CN" else "en")
    canonical = hydrate_canonical_analysis(sample_draft(language=language), transcript)
    source = AnalysisSource(
        source_url=transcript.source_url,
        title=transcript.title,
        platform=transcript.platform,
        duration_seconds=transcript.duration,
        transcript_source=transcript.source_kind,
        transcript_language=transcript.language,
    )

    summary = build_summary(
        canonical,
        detail=AnalysisDetail.BALANCED,
        output_language=language,
    )
    mind_map = build_mind_map(source, canonical, max_nodes=80)
    story = build_visual_story(source, canonical, frame_limit=8)
    website = build_website_manifest(
        source, canonical, output_language=language
    )
    guide = build_interactive_guide(
        source, canonical, output_language=language
    )

    assert summary.tldr.evidence_segment_ids
    assert mind_map.root_id == "node-root"
    assert story.frames == sorted(
        story.frames, key=lambda frame: frame.timestamp_seconds
    )
    assert website.language == language
    assert guide.steps[0].evidence_segment_ids


def test_structured_output_rejects_extra_fields_invalid_evidence_and_overlap():
    raw = sample_draft().model_dump(mode="json")
    raw["arbitrary_html"] = "<script>alert(1)</script>"
    with pytest.raises(ValidationError):
        CanonicalAnalysisDraft.model_validate(raw)

    bad_evidence = sample_draft().model_copy(deep=True)
    bad_evidence.concise_summary.evidence_segment_ids = ["seg-99999"]
    with pytest.raises(AnalysisError, match="evidence"):
        hydrate_canonical_analysis(bad_evidence, sample_transcript())

    overlap = sample_draft().model_copy(deep=True)
    overlap.chapters[1].start_seconds = 20
    with pytest.raises(AnalysisError) as caught:
        hydrate_canonical_analysis(overlap, sample_transcript())
    assert caught.value.code == "CHAPTERS_OVERLAP"


def test_mind_map_rejects_cycles_and_node_limit():
    root = MindMapNode(
        id="node-root",
        label="Root",
        description="Root node",
        type=MindMapNodeType.ROOT,
        timestamp_seconds=0,
        evidence_segment_ids=["seg-00001"],
        children=["node-child"],
    )
    child = MindMapNode(
        id="node-child",
        label="Child",
        description="Child node",
        type=MindMapNodeType.TOPIC,
        timestamp_seconds=1,
        evidence_segment_ids=["seg-00001"],
        children=["node-root"],
    )
    with pytest.raises(ValidationError, match="cycle"):
        MindMap(
            root_id="node-root",
            nodes=[root, child],
            edges=[
                MindMapEdge(
                    id="edge-cycle",
                    source_id="node-child",
                    target_id="node-root",
                )
            ],
        )

    with pytest.raises(ValidationError):
        MindMap(
            root_id="node-root",
            nodes=[root.model_copy(update={"children": []})] * 81,
        )


@pytest.mark.asyncio
async def test_provider_rejects_invalid_json_without_exposing_secret():
    secret = "sk-analysis-never-leak"

    def handler(request: httpx.Request) -> httpx.Response:
        assert secret in request.headers["authorization"]
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "{not-json"}}]},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = DeepSeekAnalysisProvider(
        Settings(
            deepseek_api_key=secret,
            analysis_semantic_unit_characters=500,
            analysis_provider_chunk_characters=1_000,
        ),
        client=client,
    )
    transcript = sample_transcript()
    with pytest.raises(AnalysisError) as caught:
        await provider.analyze(
            transcript,
            segment_transcript(transcript, target_characters=500),
            output_language="en",
            detail=AnalysisDetail.BALANCED,
            cancel_event=asyncio.Event(),
            on_progress=lambda _value: asyncio.sleep(0),
        )
    assert caught.value.code == "ANALYSIS_RESPONSE_INVALID"
    assert secret not in repr(provider.config)
    assert secret not in str(caught.value)
    await client.aclose()


@pytest.mark.asyncio
async def test_jobs_reuse_core_and_lazy_artifact_tasks(tmp_path):
    acquisition = FakeAcquisition()
    provider = FakeAnalysisProvider()
    frames = FakeFrames()
    manager = AnalysisJobManager(
        Settings(data_dir=tmp_path),
        acquisition,
        provider,
        frames,
    )
    request = CreateAnalysisRequest(
        url="https://www.youtube.com/watch?v=public",
        output_language="en",
        detail="balanced",
        rights_confirmed=True,
    )
    first, second = await asyncio.gather(
        manager.create(request),
        manager.create(request),
    )
    assert first is second
    assert first.task
    await first.task
    assert acquisition.calls == 1
    assert provider.calls == 1
    assert first.artifacts[ArtifactKind.SUMMARY].status == ArtifactStatus.COMPLETED
    assert first.artifacts[ArtifactKind.MIND_MAP].status == ArtifactStatus.NOT_STARTED

    artifact_a, artifact_b = await asyncio.gather(
        manager.request_artifact(first, ArtifactKind.MIND_MAP),
        manager.request_artifact(first, ArtifactKind.MIND_MAP),
    )
    assert artifact_a is artifact_b
    if artifact_a.task:
        await artifact_a.task
    assert artifact_a.status == ArtifactStatus.COMPLETED
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_single_artifact_failure_preserves_other_results_and_sse_replay(tmp_path):
    manager = AnalysisJobManager(
        Settings(data_dir=tmp_path),
        FakeAcquisition(),
        FakeAnalysisProvider(),
        FakeFrames(fail=True),
    )
    job = await manager.create(
        CreateAnalysisRequest(
            url="https://www.youtube.com/watch?v=public",
            rights_confirmed=True,
        )
    )
    assert job.task
    await job.task
    story = await manager.request_artifact(job, ArtifactKind.VISUAL_STORY)
    assert story.task
    await story.task

    assert story.status == ArtifactStatus.FAILED
    assert story.error
    assert "private ffmpeg" not in story.error.message
    assert job.artifacts[ArtifactKind.SUMMARY].status == ArtifactStatus.COMPLETED
    assert job.artifacts[ArtifactKind.CHAPTERS].status == ArtifactStatus.COMPLETED
    sequences = [int(event["sequence"]) for event in job.events]
    assert sequences == list(range(1, len(sequences) + 1))
    progresses = [float(event["overall_progress"]) for event in job.events]
    assert progresses == sorted(progresses)
    replay = manager.stream(job, after=sequences[-3])
    first_replayed = await anext(replay)
    assert f"id: {sequences[-2]}" in first_replayed
    await replay.aclose()


def test_website_renderer_escapes_xss_and_rejects_malicious_url():
    transcript = sample_transcript()
    draft = sample_draft().model_copy(deep=True)
    draft.chapters[0].title = '<img src=x onerror="alert(1)">'
    with pytest.raises(AnalysisError) as caught:
        hydrate_canonical_analysis(draft, transcript)
    assert caught.value.code == "UNSAFE_GENERATED_CONTENT"
    canonical = hydrate_canonical_analysis(sample_draft(), transcript)
    source = AnalysisSource(
        source_url=transcript.source_url,
        title="<script>alert(1)</script>",
        platform=transcript.platform,
        duration_seconds=transcript.duration,
    )
    manifest = build_website_manifest(
        source, canonical, output_language="en"
    )
    rendered = render_website_html(manifest)
    assert "<script>alert(1)</script>" not in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    assert "onerror=" not in rendered
    assert "<iframe" not in rendered

    with pytest.raises(ValidationError):
        WebsiteSource(label="bad", url="javascript:alert(1)")


def test_exports_are_structured_and_static_zip_contains_no_secrets():
    transcript = sample_transcript()
    canonical = hydrate_canonical_analysis(sample_draft(), transcript)
    source = AnalysisSource(
        source_url=transcript.source_url,
        title=transcript.title,
        platform=transcript.platform,
        duration_seconds=transcript.duration,
    )
    summary = build_summary(
        canonical,
        detail=AnalysisDetail.BALANCED,
        output_language="en",
    )
    website = build_website_manifest(source, canonical, output_language="en")

    assert json.loads(export_json(summary))["tldr"]["text"] == "Core summary"
    assert "# Summary" in export_markdown(ArtifactKind.SUMMARY, summary)
    archive = export_website_zip(website)
    assert b"DEEPSEEK_API_KEY" not in archive
    assert b"<script" not in archive


@pytest.mark.asyncio
async def test_cleanup_removes_frames_and_state(tmp_path):
    manager = AnalysisJobManager(
        Settings(data_dir=tmp_path, analysis_job_ttl_seconds=1),
        FakeAcquisition(),
        FakeAnalysisProvider(),
        FakeFrames(),
    )
    job = await manager.create(
        CreateAnalysisRequest(
            url="https://www.youtube.com/watch?v=public",
            rights_confirmed=True,
        )
    )
    assert job.task
    await job.task
    marker = job.directory / "frames" / "frame-01.jpg"
    marker.parent.mkdir(parents=True)
    marker.write_bytes(b"frame")
    job.completed_at = datetime.now(UTC) - timedelta(seconds=2)

    assert await manager.cleanup_expired() == 1
    assert manager.get(job.id) is None
    assert not job.directory.exists()


def test_create_request_requires_rights_confirmation():
    with pytest.raises(ValidationError):
        CreateAnalysisRequest(
            url="https://www.youtube.com/watch?v=public",
            rights_confirmed=False,
        )
