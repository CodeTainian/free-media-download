import asyncio
from pathlib import Path

import pytest

from app.config import Settings
from app.jobs import JobManager
from app.models import CreateJobItem, ItemStatus, JobStatus


class FakeDownloader:
    async def download(self, raw_url, preset_id, output_dir, cancel_event, progress):
        output_dir.mkdir(parents=True, exist_ok=True)
        await progress(38, "2.1MiB/s", 3)
        path = output_dir / "sample.mp4"
        path.write_bytes(b"media")
        await progress(100, None, 0)
        return path


class PartialDownloader(FakeDownloader):
    async def download(self, raw_url, preset_id, output_dir, cancel_event, progress):
        if raw_url.endswith("/bad"):
            from app.downloader import DownloadError

            raise DownloadError("SOURCE_ERROR", "Source failed.", True)
        return await super().download(raw_url, preset_id, output_dir, cancel_event, progress)


class SlowDownloader:
    async def download(self, raw_url, preset_id, output_dir, cancel_event, progress):
        await asyncio.sleep(1)
        return Path(output_dir) / "never.mp4"


@pytest.mark.asyncio
async def test_job_completes_and_builds_store_only_zip(tmp_path):
    settings = Settings(data_dir=tmp_path, worker_concurrency=2, job_ttl_seconds=1)
    manager = JobManager(settings, FakeDownloader())
    manager.start()
    try:
        job = await manager.create(
            [
                CreateJobItem(url="https://vimeo.com/1", preset_id="mp4-720", title="One"),
                CreateJobItem(url="https://vimeo.com/2", preset_id="mp4-720", title="Two"),
            ],
            bundle=True,
        )
        await job.tasks[0]
        view = manager.view(job)
        assert view.status == JobStatus.COMPLETED
        assert all(item.status == ItemStatus.READY for item in view.items)
        assert view.bundle_ready is True
        assert job.bundle_path and job.bundle_path.exists()
        assert any(event["type"] == "item_progress" for event in job.events)
    finally:
        await manager.stop()


@pytest.mark.asyncio
async def test_cancel_marks_pending_items(tmp_path):
    settings = Settings(data_dir=tmp_path)
    manager = JobManager(settings, FakeDownloader())
    job = await manager.create(
        [CreateJobItem(url="https://vimeo.com/1", preset_id="best", title="One")],
        bundle=False,
    )
    assert await manager.cancel(job.id)
    assert manager.view(job).status == JobStatus.CANCELLED


@pytest.mark.asyncio
async def test_cleanup_removes_expired_job(tmp_path):
    settings = Settings(data_dir=tmp_path, job_ttl_seconds=0)
    manager = JobManager(settings, FakeDownloader())
    job = await manager.create(
        [CreateJobItem(url="https://vimeo.com/1", preset_id="best", title="One")],
        bundle=False,
    )
    await job.tasks[0]
    assert await manager.cleanup_expired() == 1
    assert manager.get(job.id) is None


@pytest.mark.asyncio
async def test_partial_failure_still_completes_ready_files_and_sse_order(tmp_path):
    manager = JobManager(Settings(data_dir=tmp_path), PartialDownloader())
    job = await manager.create(
        [
            CreateJobItem(url="https://vimeo.com/good", preset_id="best", title="Good"),
            CreateJobItem(url="https://vimeo.com/bad", preset_id="best", title="Bad"),
        ],
        bundle=True,
    )
    await job.tasks[0]
    frames = [frame async for frame in manager.stream(job)]
    assert manager.view(job).status == JobStatus.COMPLETED
    assert [item.status for item in manager.view(job).items] == [ItemStatus.READY, ItemStatus.FAILED]
    assert "event: queued" in frames[0]
    assert "event: completed" in frames[-1]
    assert job.bundle_path and job.bundle_path.is_file()


@pytest.mark.asyncio
async def test_item_timeout_is_reported_and_task_is_reclaimed(tmp_path):
    manager = JobManager(Settings(data_dir=tmp_path, item_timeout_seconds=0), SlowDownloader())
    job = await manager.create(
        [CreateJobItem(url="https://vimeo.com/slow", preset_id="best", title="Slow")],
        bundle=False,
    )
    await job.tasks[0]
    view = manager.view(job)
    assert view.status == JobStatus.FAILED
    assert view.items[0].error and view.items[0].error.code == "DOWNLOAD_TIMEOUT"


def test_service_restart_has_no_persistent_jobs(tmp_path):
    first = JobManager(Settings(data_dir=tmp_path), FakeDownloader())
    restarted = JobManager(Settings(data_dir=tmp_path), FakeDownloader())
    first.jobs["memory-only"] = object()  # type: ignore[assignment]
    assert restarted.get("memory-only") is None
