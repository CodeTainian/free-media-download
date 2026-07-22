from __future__ import annotations

import asyncio
import json
import secrets
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile

from .config import Settings
from .downloader import DownloadError, YtDlpService
from .models import (
    CreateJobItem,
    ErrorBody,
    ItemStatus,
    JobItemView,
    JobStatus,
    JobView,
)
from .security import safe_filename


def now_utc() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class JobItemState:
    id: str
    request: CreateJobItem
    title: str
    status: ItemStatus = ItemStatus.QUEUED
    progress: float = 0
    speed: str | None = None
    eta: int | None = None
    path: Path | None = None
    error: ErrorBody | None = None


@dataclass(slots=True)
class JobState:
    id: str
    items: list[JobItemState]
    bundle_requested: bool
    directory: Path
    created_at: datetime = field(default_factory=now_utc)
    completed_at: datetime | None = None
    status: JobStatus = JobStatus.QUEUED
    bundle_path: Path | None = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    events: list[dict[str, object]] = field(default_factory=list)
    event_condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    tasks: list[asyncio.Task[None]] = field(default_factory=list)


class JobManager:
    def __init__(self, config: Settings, downloader: YtDlpService):
        self.config = config
        self.downloader = downloader
        self.jobs: dict[str, JobState] = {}
        self.semaphore = asyncio.Semaphore(config.worker_concurrency)
        self.cleanup_task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self.config.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.cleanup_task or self.cleanup_task.done():
            self.cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self) -> None:
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        for job in list(self.jobs.values()):
            await self.cancel(job.id, remove_files=False)

    async def create(self, requests: list[CreateJobItem], bundle: bool) -> JobState:
        job_id = secrets.token_urlsafe(24)
        directory = self.config.data_dir / job_id
        directory.mkdir(parents=True, exist_ok=False)
        items = [
            JobItemState(
                id=secrets.token_urlsafe(12),
                request=request,
                title=safe_filename(request.title or f"Media {index + 1}"),
            )
            for index, request in enumerate(requests)
        ]
        job = JobState(id=job_id, items=items, bundle_requested=bundle, directory=directory)
        self.jobs[job_id] = job
        await self._publish(job, "queued")
        task = asyncio.create_task(self._run(job))
        job.tasks.append(task)
        return job

    def get(self, job_id: str) -> JobState | None:
        return self.jobs.get(job_id)

    def view(self, job: JobState) -> JobView:
        expires_at = (
            job.completed_at + timedelta(seconds=self.config.job_ttl_seconds)
            if job.completed_at
            else None
        )
        return JobView(
            id=job.id,
            status=job.status,
            created_at=job.created_at.isoformat(),
            expires_at=expires_at.isoformat() if expires_at else None,
            items=[
                JobItemView(
                    id=item.id,
                    title=item.title,
                    status=item.status,
                    progress=round(item.progress, 1),
                    speed=item.speed,
                    eta=item.eta,
                    filename=item.path.name if item.path else None,
                    download_url=f"/api/v1/jobs/{job.id}/files/{item.id}" if item.path else None,
                    error=item.error,
                )
                for item in job.items
            ],
            bundle_url=f"/api/v1/jobs/{job.id}/bundle" if job.bundle_path else None,
            bundle_ready=job.bundle_path is not None,
        )

    async def _run(self, job: JobState) -> None:
        job.status = JobStatus.RUNNING
        await self._publish(job, "started")
        item_tasks = [asyncio.create_task(self._run_item(job, item)) for item in job.items]
        job.tasks.extend(item_tasks)
        await asyncio.gather(*item_tasks, return_exceptions=True)
        if job.cancel_event.is_set():
            job.status = JobStatus.CANCELLED
        elif any(item.status == ItemStatus.READY for item in job.items):
            if job.bundle_requested:
                await self._build_bundle(job)
            job.status = JobStatus.COMPLETED
        else:
            job.status = JobStatus.FAILED
        job.completed_at = now_utc()
        await self._publish(job, "completed")

    async def _run_item(self, job: JobState, item: JobItemState) -> None:
        async with self.semaphore:
            if job.cancel_event.is_set():
                item.status = ItemStatus.CANCELLED
                return
            item.status = ItemStatus.RUNNING
            await self._publish(job, "item_started", item.id)

            async def on_progress(percent: float, speed: str | None, eta: int | None) -> None:
                item.progress = max(0, min(100, percent))
                item.speed = speed
                item.eta = eta
                await self._publish(job, "item_progress", item.id)

            try:
                item_dir = job.directory / item.id
                item.path = await asyncio.wait_for(
                    self.downloader.download(
                        item.request.url,
                        item.request.preset_id,
                        item_dir,
                        job.cancel_event,
                        on_progress,
                    ),
                    timeout=self.config.item_timeout_seconds,
                )
                item.title = safe_filename(item.path.stem)
                item.progress = 100
                item.status = ItemStatus.READY
                await self._publish(job, "item_ready", item.id)
            except TimeoutError:
                item.status = ItemStatus.FAILED
                item.error = ErrorBody(
                    code="DOWNLOAD_TIMEOUT",
                    message="This download exceeded the one-hour processing limit.",
                    retryable=True,
                )
                await self._publish(job, "item_failed", item.id)
            except DownloadError as exc:
                item.status = ItemStatus.CANCELLED if exc.code == "CANCELLED" else ItemStatus.FAILED
                item.error = ErrorBody(code=exc.code, message=exc.message, retryable=exc.retryable)
                await self._publish(job, "item_failed", item.id)
            except Exception:
                item.status = ItemStatus.FAILED
                item.error = ErrorBody(
                    code="INTERNAL_ERROR",
                    message="SaveBolt could not finish this item.",
                    retryable=True,
                )
                await self._publish(job, "item_failed", item.id)

    async def _build_bundle(self, job: JobState) -> None:
        ready = [item for item in job.items if item.path and item.status == ItemStatus.READY]
        if not ready:
            return
        total = sum(item.path.stat().st_size for item in ready if item.path)
        if total > self.config.max_bundle_bytes:
            return
        bundle = job.directory / "savebolt-downloads.zip"
        used: set[str] = set()
        with ZipFile(bundle, "w", compression=ZIP_STORED, allowZip64=True) as archive:
            for index, item in enumerate(ready, 1):
                assert item.path
                name = safe_filename(item.path.name)
                if name in used:
                    name = f"{index}-{name}"
                used.add(name)
                archive.write(item.path, arcname=name)
        job.bundle_path = bundle
        await self._publish(job, "bundle_ready")

    async def cancel(self, job_id: str, remove_files: bool = True) -> bool:
        job = self.jobs.get(job_id)
        if not job:
            return False
        job.cancel_event.set()
        for item in job.items:
            if item.status in {ItemStatus.QUEUED, ItemStatus.RUNNING}:
                item.status = ItemStatus.CANCELLED
        job.status = JobStatus.CANCELLED
        job.completed_at = now_utc()
        await self._publish(job, "cancelled")

        current_task = asyncio.current_task()
        active = [
            task for task in job.tasks if task is not current_task and not task.done()
        ]
        if active:
            done, pending = await asyncio.wait(active, timeout=5)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                if not task.cancelled():
                    task.exception()

        if remove_files:
            shutil.rmtree(job.directory, ignore_errors=True)
            for item in job.items:
                item.path = None
            job.bundle_path = None
        return True

    async def _publish(self, job: JobState, event_type: str, item_id: str | None = None) -> None:
        payload = {
            "sequence": len(job.events) + 1,
            "type": event_type,
            "item_id": item_id,
            "job": self.view(job).model_dump(mode="json"),
        }
        async with job.event_condition:
            job.events.append(payload)
            job.event_condition.notify_all()

    async def stream(self, job: JobState, after: int = 0):
        cursor = max(0, after)
        while True:
            keep_alive = False
            async with job.event_condition:
                if cursor >= len(job.events):
                    if job.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
                        return
                    try:
                        await asyncio.wait_for(job.event_condition.wait(), timeout=15)
                    except TimeoutError:
                        keep_alive = True
                pending = job.events[cursor:]
            if keep_alive:
                yield ": keep-alive\n\n"
                continue
            for event in pending:
                cursor += 1
                yield (
                    f"id: {event['sequence']}\n"
                    f"event: {event['type']}\n"
                    f"data: {json.dumps(event, separators=(',', ':'))}\n\n"
                )

    async def cleanup_expired(self) -> int:
        cutoff = now_utc() - timedelta(seconds=self.config.job_ttl_seconds)
        expired = [
            job_id
            for job_id, job in self.jobs.items()
            if job.completed_at and job.completed_at <= cutoff
        ]
        for job_id in expired:
            job = self.jobs.pop(job_id)
            shutil.rmtree(job.directory, ignore_errors=True)
        return len(expired)

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(self.config.cleanup_interval_seconds)
            await self.cleanup_expired()
