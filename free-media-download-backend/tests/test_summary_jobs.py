import asyncio

import pytest

from app.config import Settings
from app.downloader import DownloadError
from app.models import (
    CreateSummaryRequest,
    JobStatus,
    SummaryEvidence,
    SummaryKeyPoint,
    SummaryOutlineItem,
    SummaryResult,
    SummaryStage,
)
from app.summary_jobs import SummaryJobManager
from app.transcription_provider import TranscriptionError
from app.transcripts import TranscriptDocument, TranscriptSegment


def sample_transcript() -> TranscriptDocument:
    return TranscriptDocument(
        source_url="https://www.youtube.com/watch?v=public",
        title="Public lesson",
        platform="youtube",
        duration=60,
        language="en",
        source_kind="manual_caption",
        segments=(
            TranscriptSegment(
                id="seg-00001", start=0, end=2, text="Original evidence"
            ),
        ),
    )


def sample_result() -> SummaryResult:
    evidence = SummaryEvidence(
        id="seg-00001", start_seconds=0, end_seconds=2, text="Original evidence"
    )
    return SummaryResult(
        source_url="https://www.youtube.com/watch?v=public",
        title="Public lesson",
        platform="youtube",
        duration=60,
        caption_language="en",
        caption_source="manual_caption",
        overview="Overview",
        outline=[
            SummaryOutlineItem(
                timestamp_seconds=0,
                title="Opening",
                summary="Summary",
                evidence=[evidence],
            )
        ],
        key_points=[
            SummaryKeyPoint(
                title="Point", explanation="Explanation", evidence=[evidence]
            )
        ],
    )


class FakeAcquisition:
    async def acquire(
        self,
        raw_url,
        job_directory,
        preferred_languages,
        cancel_event,
        on_stage,
        on_progress,
    ):
        job_directory.mkdir(parents=True, exist_ok=True)
        await on_stage("probing")
        await on_stage("fetching_captions")
        await on_stage("parsing_transcript")
        return sample_transcript()

    async def close(self):
        return None


class MissingCaptionAcquisition(FakeAcquisition):
    async def acquire(self, *args, **kwargs):
        raise DownloadError("NO_CAPTIONS", "No usable captions.")


class SlowAcquisition(FakeAcquisition):
    async def acquire(self, *args, **kwargs):
        cancel_event = kwargs["cancel_event"]
        await cancel_event.wait()
        raise DownloadError("CANCELLED", "Cancelled.")


class AsrAcquisition(FakeAcquisition):
    async def acquire(self, *args, **kwargs):
        for stage in (
            "probing",
            "fetching_captions",
            "extracting_audio",
            "preparing_audio",
            "transcribing",
            "parsing_transcript",
        ):
            await kwargs["on_stage"](stage)
            if stage in {"extracting_audio", "preparing_audio", "transcribing"}:
                await kwargs["on_progress"](stage, 1)
        transcript = sample_transcript()
        return transcript.model_copy(
            update={
                "source_kind": "audio_transcription",
                "provider": "mock",
                "audio_duration": 60,
            }
        )


class SecretFailureAcquisition(FakeAcquisition):
    async def acquire(self, *args, **kwargs):
        raise TranscriptionError(
            "TRANSCRIPTION_PROVIDER_UNAVAILABLE",
            "The transcription provider configuration was rejected.",
        )


class FakeSummaryService:
    def __init__(self):
        self.closed = False

    def ready(self):
        return True

    async def close(self):
        self.closed = True

    async def generate(
        self,
        transcript,
        *,
        title,
        output_language,
        on_progress,
        on_generating_chapters,
        on_finalizing,
    ):
        await on_progress(0.5)
        await on_generating_chapters()
        await on_finalizing()
        result = sample_result()
        result.caption_source = transcript.source_kind
        if title:
            result.title = title
        return result


@pytest.mark.asyncio
async def test_summary_job_completes_with_ordered_sse_and_result(tmp_path):
    manager = SummaryJobManager(
        Settings(data_dir=tmp_path, summary_job_ttl_seconds=60),
        FakeAcquisition(),
        FakeSummaryService(),
    )
    manager.start()
    try:
        job = await manager.create(
            CreateSummaryRequest(
                url="https://www.youtube.com/watch?v=public", title="Requested title"
            )
        )
        assert job.task
        await job.task
        view = manager.view(job)
        frames = [frame async for frame in manager.stream(job)]

        assert view.status == JobStatus.COMPLETED
        assert view.stage == SummaryStage.COMPLETED
        assert view.progress == 100
        assert view.result and view.result.title == "Requested title"
        event_types = [event["type"] for event in job.events]
        assert event_types[:2] == ["queued", "started"]
        assert "stage_changed" in event_types
        assert "progress" in event_types
        assert event_types[-1] == "completed"
        assert [event["sequence"] for event in job.events] == list(
            range(1, len(job.events) + 1)
        )
        progresses = [
            event["summary"]["progress"]
            for event in job.events
            if isinstance(event.get("summary"), dict)
        ]
        assert progresses == sorted(progresses)
        assert "event: queued" in frames[0]
        assert "event: completed" in frames[-1]
    finally:
        await manager.stop()


@pytest.mark.asyncio
async def test_summary_job_exposes_no_captions_failure(tmp_path):
    manager = SummaryJobManager(
        Settings(data_dir=tmp_path), MissingCaptionAcquisition(), FakeSummaryService()
    )
    job = await manager.create(
        CreateSummaryRequest(url="https://www.bilibili.com/video/BV1public")
    )
    assert job.task
    await job.task

    view = manager.view(job)
    assert view.status == JobStatus.FAILED
    assert view.error and view.error.code == "NO_CAPTIONS"
    assert view.result is None


@pytest.mark.asyncio
async def test_summary_cancel_stops_work_and_removes_temporary_files(tmp_path):
    manager = SummaryJobManager(
        Settings(data_dir=tmp_path), SlowAcquisition(), FakeSummaryService()
    )
    job = await manager.create(
        CreateSummaryRequest(url="https://www.youtube.com/watch?v=public")
    )
    await asyncio.sleep(0)
    assert job.directory.exists()

    assert await manager.cancel(job.id)
    assert manager.view(job).status == JobStatus.CANCELLED
    assert not job.directory.exists()


@pytest.mark.asyncio
async def test_summary_cleanup_removes_expired_state_and_files(tmp_path):
    manager = SummaryJobManager(
        Settings(data_dir=tmp_path, summary_job_ttl_seconds=0),
        FakeAcquisition(),
        FakeSummaryService(),
    )
    job = await manager.create(
        CreateSummaryRequest(url="https://www.youtube.com/watch?v=public")
    )
    assert job.task
    await job.task
    assert job.directory.exists()

    assert await manager.cleanup_expired() == 1
    assert manager.get(job.id) is None
    assert not job.directory.exists()


@pytest.mark.asyncio
async def test_asr_summary_sse_has_ordered_stages_monotonic_progress_and_one_terminal(
    tmp_path,
):
    manager = SummaryJobManager(
        Settings(data_dir=tmp_path), AsrAcquisition(), FakeSummaryService()
    )
    job = await manager.create(
        CreateSummaryRequest(url="https://www.youtube.com/watch?v=public")
    )
    assert job.task
    await job.task

    stages = [
        event["summary"]["stage"]
        for event in job.events
        if event["type"] == "stage_changed"
    ]
    assert stages == [
        "probing",
        "fetching_captions",
        "extracting_audio",
        "preparing_audio",
        "transcribing",
        "parsing_transcript",
        "summarizing",
        "generating_chapters",
        "finalizing",
    ]
    progresses = [event["summary"]["progress"] for event in job.events]
    assert progresses == sorted(progresses)
    assert [event["type"] for event in job.events].count("completed") == 1
    assert not {
        event["type"] for event in job.events
    }.intersection({"failed", "cancelled"})
    assert job.result and job.result.caption_source == "audio_transcription"


@pytest.mark.asyncio
async def test_transcription_secret_never_appears_in_summary_state_or_sse(tmp_path):
    secret = "sk-summary-state-must-never-contain-this"
    manager = SummaryJobManager(
        Settings(
            data_dir=tmp_path,
            transcription_provider="openai_compatible",
            transcription_api_key=secret,
        ),
        SecretFailureAcquisition(),
        FakeSummaryService(),
    )
    job = await manager.create(
        CreateSummaryRequest(url="https://www.youtube.com/watch?v=public")
    )
    assert job.task
    await job.task

    serialized = str(
        [
            manager.view(job).model_dump(mode="json"),
            *job.events,
        ]
    )
    assert secret not in serialized
    assert job.error
    assert job.error.code == "TRANSCRIPTION_PROVIDER_UNAVAILABLE"
