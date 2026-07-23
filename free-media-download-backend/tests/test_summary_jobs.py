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


class FakeDownloader:
    async def fetch_caption_transcript(
        self,
        raw_url,
        output_dir,
        preferred_languages,
        cancel_event,
        on_stage,
    ):
        output_dir.mkdir(parents=True, exist_ok=True)
        await on_stage("parsing")
        return sample_transcript()


class MissingCaptionDownloader(FakeDownloader):
    async def fetch_caption_transcript(self, *args, **kwargs):
        raise DownloadError("NO_CAPTIONS", "No usable captions.")


class SlowDownloader(FakeDownloader):
    async def fetch_caption_transcript(self, *args, **kwargs):
        cancel_event = kwargs["cancel_event"]
        await cancel_event.wait()
        raise DownloadError("CANCELLED", "Cancelled.")


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
        on_finalizing,
    ):
        await on_progress(55)
        await on_finalizing()
        await on_progress(95)
        result = sample_result()
        if title:
            result.title = title
        return result


@pytest.mark.asyncio
async def test_summary_job_completes_with_ordered_sse_and_result(tmp_path):
    manager = SummaryJobManager(
        Settings(data_dir=tmp_path, summary_job_ttl_seconds=60),
        FakeDownloader(),
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
        assert [event["type"] for event in job.events] == [
            "queued",
            "started",
            "stage_changed",
            "stage_changed",
            "stage_changed",
            "progress",
            "stage_changed",
            "progress",
            "completed",
        ]
        assert "event: queued" in frames[0]
        assert "event: completed" in frames[-1]
    finally:
        await manager.stop()


@pytest.mark.asyncio
async def test_summary_job_exposes_no_captions_failure(tmp_path):
    manager = SummaryJobManager(
        Settings(data_dir=tmp_path), MissingCaptionDownloader(), FakeSummaryService()
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
        Settings(data_dir=tmp_path), SlowDownloader(), FakeSummaryService()
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
        FakeDownloader(),
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
