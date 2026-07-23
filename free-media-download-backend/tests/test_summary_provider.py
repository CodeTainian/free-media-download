import json

import httpx
import pytest

from app.config import Settings
from app.summary_provider import (
    DeepSeekSummaryProvider,
    DraftKeyPoint,
    DraftOutlineItem,
    SummaryDraft,
    SummaryError,
    SummaryService,
    TranscriptChunk,
    chunk_transcript,
    resolve_summary_draft,
)
from app.transcripts import TranscriptDocument, TranscriptSegment


def sample_transcript(segment_count: int = 4, text_size: int = 20) -> TranscriptDocument:
    return TranscriptDocument(
        source_url="https://www.youtube.com/watch?v=public",
        title="Public lesson",
        platform="youtube",
        duration=segment_count * 2,
        language="en",
        source_kind="manual_caption",
        segments=tuple(
            TranscriptSegment(
                id=f"seg-{index:05d}",
                start=float((index - 1) * 2),
                end=float(index * 2),
                text=(f"Lesson point {index} " + "x" * text_size),
            )
            for index in range(1, segment_count + 1)
        ),
    )


def valid_draft(evidence_id: str = "seg-00001") -> SummaryDraft:
    return SummaryDraft(
        overview="An evidence-backed overview.",
        outline=[
            DraftOutlineItem(
                title="Opening",
                summary="The lesson introduces its main idea.",
                evidence_ids=[evidence_id],
            )
        ],
        key_points=[
            DraftKeyPoint(
                title="Main idea",
                explanation="The central concept is explained.",
                evidence_ids=[evidence_id],
            )
        ],
    )


def response_payload(content: str) -> dict[str, object]:
    return {"choices": [{"message": {"content": content}}]}


def test_chunks_transcript_without_splitting_segments():
    transcript = sample_transcript(segment_count=8, text_size=420)
    chunks = chunk_transcript(transcript, max_characters=1_000)

    assert len(chunks) == 4
    assert [segment.id for chunk in chunks for segment in chunk.segments] == [
        segment.id for segment in transcript.segments
    ]
    assert all(len(chunk.content) <= 1_000 for chunk in chunks)


def test_settings_repr_never_contains_deepseek_secret(tmp_path):
    assert "test-secret" not in repr(
        Settings(data_dir=tmp_path, deepseek_api_key="test-secret")
    )


def test_resolves_only_real_evidence_ids_and_uses_original_caption_text():
    transcript = sample_transcript()
    draft = SummaryDraft(
        overview="Overview",
        outline=[
            DraftOutlineItem(
                title="Later section",
                summary="Later supported detail",
                evidence_ids=["seg-00004"],
            ),
            DraftOutlineItem(
                title="Verified section",
                summary="Supported detail",
                evidence_ids=["missing", "seg-00002", "seg-00002"],
            ),
            DraftOutlineItem(
                title="Invented section",
                summary="Unsupported detail",
                evidence_ids=["missing"],
            ),
        ],
        key_points=[
            DraftKeyPoint(
                title="Verified point",
                explanation="Supported explanation",
                evidence_ids=["seg-00003", "unknown"],
            )
        ],
    )

    result = resolve_summary_draft(transcript, draft, title="Requested title")

    assert result.title == "Requested title"
    assert len(result.outline) == 2
    assert result.outline[0].timestamp_seconds == 2.0
    assert [item.id for item in result.outline[0].evidence] == ["seg-00002"]
    assert result.outline[0].evidence[0].text == transcript.segments[1].text
    assert result.outline[1].timestamp_seconds == 6.0
    assert [item.id for item in result.key_points[0].evidence] == ["seg-00003"]


def test_rejects_summary_when_all_evidence_is_unknown():
    transcript = sample_transcript()
    with pytest.raises(SummaryError) as caught:
        resolve_summary_draft(transcript, valid_draft("invented"))
    assert caught.value.code == "AI_RESPONSE_INVALID"


def test_draft_accepts_common_summary_alias_for_key_point_explanation():
    draft = SummaryDraft.model_validate(
        {
            "overview": "Overview",
            "outline": [
                {
                    "title": "Section",
                    "summary": "Section summary",
                    "evidence_ids": ["seg-00001"],
                }
            ],
            "key_points": [
                {
                    "title": "Point",
                    "summary": "Provider used a common synonym",
                    "evidence_ids": ["seg-00001"],
                }
            ],
        }
    )
    assert draft.key_points[0].explanation == "Provider used a common synonym"


@pytest.mark.asyncio
async def test_deepseek_provider_retries_transient_failure(monkeypatch):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.headers["authorization"] == "Bearer test-key"
        if calls == 1:
            return httpx.Response(500, json={"error": "temporary"})
        return httpx.Response(200, json=response_payload(valid_draft().model_dump_json()))

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr("app.summary_provider.asyncio.sleep", no_sleep)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = DeepSeekSummaryProvider(
        Settings(deepseek_api_key="test-key", deepseek_base_url="https://deepseek.test"),
        client,
    )
    try:
        result = await provider.summarize_chunk(
            TranscriptChunk(1, sample_transcript().segments, "[seg-00001 0-2] lesson"),
            "en",
        )
    finally:
        await client.aclose()

    assert result.overview == "An evidence-backed overview."
    assert calls == 2


@pytest.mark.asyncio
async def test_deepseek_provider_repairs_invalid_or_empty_json_once():
    contents = ["", valid_draft().model_dump_json()]
    requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=response_payload(contents.pop(0)))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = DeepSeekSummaryProvider(
        Settings(deepseek_api_key="test-key", deepseek_base_url="https://deepseek.test"),
        client,
    )
    try:
        result = await provider.summarize_chunk(
            TranscriptChunk(1, sample_transcript().segments, "[seg-00001 0-2] lesson"),
            "en",
        )
    finally:
        await client.aclose()

    assert result.key_points[0].evidence_ids == ["seg-00001"]
    assert len(requests) == 2
    assert len(requests[1]["messages"]) == 4


@pytest.mark.asyncio
async def test_deepseek_provider_requires_server_side_key():
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(500)))
    provider = DeepSeekSummaryProvider(Settings(deepseek_api_key=None), client)
    try:
        with pytest.raises(SummaryError) as caught:
            await provider.summarize_chunk(
                TranscriptChunk(1, sample_transcript().segments, "caption"), "en"
            )
    finally:
        await client.aclose()
    assert caught.value.code == "SUMMARY_PROVIDER_UNAVAILABLE"


class FakeProvider:
    def __init__(self):
        self.chunk_calls = 0
        self.closed = False

    def ready(self):
        return True

    async def summarize_chunk(self, chunk, output_language):
        self.chunk_calls += 1
        return valid_draft(chunk.segments[0].id)

    async def synthesize(self, drafts, output_language):
        return valid_draft("seg-00002")

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_summary_service_reports_progress_and_resolves_final_result(tmp_path):
    provider = FakeProvider()
    service = SummaryService(
        Settings(data_dir=tmp_path, summary_chunk_characters=1_000), provider
    )
    progress: list[float] = []
    finalizing = 0

    async def on_progress(value):
        progress.append(value)

    async def on_finalizing():
        nonlocal finalizing
        finalizing += 1

    result = await service.generate(
        sample_transcript(segment_count=8, text_size=420),
        title=None,
        output_language="en",
        on_progress=on_progress,
        on_finalizing=on_finalizing,
    )

    assert provider.chunk_calls == 4
    assert progress[-1] == 95
    assert progress == sorted(progress)
    assert finalizing == 1
    assert result.outline[0].evidence[0].id == "seg-00002"
