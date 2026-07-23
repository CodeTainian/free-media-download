from __future__ import annotations

import asyncio
import json
import secrets
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .audio_processor import AudioProcessingError
from .config import Settings
from .downloader import DownloadError
from .models import (
    CreateSummaryRequest,
    ErrorBody,
    JobStatus,
    SummaryJobView,
    SummaryResult,
    SummaryStage,
)
from .summary_provider import SummaryError, SummaryService
from .transcript_acquisition import TranscriptAcquisitionService
from .transcription_provider import TranscriptionError


def now_utc() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class SummaryJobState:
    id: str
    request: CreateSummaryRequest
    directory: Path
    created_at: datetime = field(default_factory=now_utc)
    completed_at: datetime | None = None
    status: JobStatus = JobStatus.QUEUED
    stage: SummaryStage = SummaryStage.QUEUED
    progress: float = 0
    result: SummaryResult | None = None
    error: ErrorBody | None = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    events: list[dict[str, object]] = field(default_factory=list)
    event_condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    task: asyncio.Task[None] | None = None


class SummaryJobManager:
    def __init__(
        self,
        config: Settings,
        transcript_acquisition: TranscriptAcquisitionService,
        summarizer: SummaryService,
    ):
        self.config = config
        self.transcript_acquisition = transcript_acquisition
        self.summarizer = summarizer
        self.jobs: dict[str, SummaryJobState] = {}
        self.semaphore = asyncio.Semaphore(config.summary_worker_concurrency)
        self.cleanup_task: asyncio.Task[None] | None = None

    @property
    def root_directory(self) -> Path:
        return self.config.data_dir / "summaries"

    def ready(self) -> bool:
        return self.summarizer.ready()

    def start(self) -> None:
        self.root_directory.mkdir(parents=True, exist_ok=True)
        if not self.cleanup_task or self.cleanup_task.done():
            self.cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self) -> None:
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
            self.cleanup_task = None
        for job in list(self.jobs.values()):
            await self.cancel(job.id, remove_files=False)
        await self.transcript_acquisition.close()
        await self.summarizer.close()

    async def create(self, request: CreateSummaryRequest) -> SummaryJobState:
        job_id = secrets.token_urlsafe(24)
        directory = self.root_directory / job_id
        directory.mkdir(parents=True, exist_ok=False)
        job = SummaryJobState(id=job_id, request=request, directory=directory)
        self.jobs[job.id] = job
        await self._publish(job, "queued")
        job.task = asyncio.create_task(self._run(job))
        return job

    def get(self, job_id: str) -> SummaryJobState | None:
        return self.jobs.get(job_id)

    def view(self, job: SummaryJobState) -> SummaryJobView:
        expires_at = (
            job.completed_at + timedelta(seconds=self.config.summary_job_ttl_seconds)
            if job.completed_at
            else None
        )
        return SummaryJobView(
            id=job.id,
            status=job.status,
            stage=job.stage,
            progress=round(job.progress, 1),
            created_at=job.created_at.isoformat(),
            expires_at=expires_at.isoformat() if expires_at else None,
            result=job.result,
            error=job.error,
        )

    async def _run(self, job: SummaryJobState) -> None:
        try:
            async with self.semaphore:
                if job.cancel_event.is_set():
                    return
                job.status = JobStatus.RUNNING
                await self._publish(job, "started")

                stage_progress = {
                    "probing": (SummaryStage.PROBING, 2),
                    "fetching_captions": (SummaryStage.FETCHING_CAPTIONS, 5),
                    "extracting_audio": (SummaryStage.EXTRACTING_AUDIO, 10),
                    "preparing_audio": (SummaryStage.PREPARING_AUDIO, 30),
                    "transcribing": (SummaryStage.TRANSCRIBING, 40),
                }

                async def on_transcript_stage(stage: str) -> None:
                    if stage == "parsing_transcript":
                        progress = (
                            72
                            if job.stage == SummaryStage.TRANSCRIBING
                            or job.progress >= 40
                            else 20
                        )
                        await self._advance(
                            job, SummaryStage.PARSING_TRANSCRIPT, progress
                        )
                        return
                    summary_stage, progress = stage_progress[stage]
                    await self._advance(job, summary_stage, progress)

                async def on_transcript_progress(stage: str, value: float) -> None:
                    value = max(0, min(1, value))
                    if stage == "extracting_audio":
                        progress = 10 + 15 * value
                    elif stage == "preparing_audio":
                        progress = 30 + 8 * value
                    elif stage == "transcribing":
                        progress = 40 + 30 * value
                    else:
                        return
                    await self._set_progress(job, progress)

                transcript = await self.transcript_acquisition.acquire(
                    job.request.url,
                    job.directory,
                    preferred_languages=(job.request.output_language,),
                    cancel_event=job.cancel_event,
                    on_stage=on_transcript_stage,
                    on_progress=on_transcript_progress,
                )
                if job.cancel_event.is_set():
                    raise DownloadError("CANCELLED", "The summary job was cancelled.")
                await self._advance(job, SummaryStage.SUMMARIZING, 30)

                async def on_progress(progress: float) -> None:
                    await self._set_progress(job, 30 + 60 * max(0, min(1, progress)))

                async def on_generating_chapters() -> None:
                    await self._advance(job, SummaryStage.GENERATING_CHAPTERS, 92)

                async def on_finalizing() -> None:
                    await self._advance(job, SummaryStage.FINALIZING, 97)

                job.result = await self.summarizer.generate(
                    transcript,
                    title=job.request.title,
                    output_language=job.request.output_language,
                    on_progress=on_progress,
                    on_generating_chapters=on_generating_chapters,
                    on_finalizing=on_finalizing,
                )
                if job.cancel_event.is_set():
                    raise DownloadError("CANCELLED", "The summary job was cancelled.")
                job.status = JobStatus.COMPLETED
                job.stage = SummaryStage.COMPLETED
                job.progress = 100
                job.completed_at = now_utc()
                await self._publish(job, "completed")
        except asyncio.CancelledError:
            if job.status != JobStatus.CANCELLED:
                job.status = JobStatus.CANCELLED
                job.completed_at = now_utc()
            raise
        except DownloadError as exc:
            if job.status == JobStatus.CANCELLED:
                return
            if exc.code == "CANCELLED":
                job.status = JobStatus.CANCELLED
                job.completed_at = now_utc()
                await self._publish(job, "cancelled")
                return
            await self._fail(job, exc.code, exc.message, exc.retryable)
        except SummaryError as exc:
            if job.status != JobStatus.CANCELLED:
                await self._fail(job, exc.code, exc.message, exc.retryable)
        except (AudioProcessingError, TranscriptionError) as exc:
            if job.status == JobStatus.CANCELLED:
                return
            if exc.code == "CANCELLED":
                job.status = JobStatus.CANCELLED
                job.completed_at = now_utc()
                await self._publish(job, "cancelled")
                return
            await self._fail(job, exc.code, exc.message, exc.retryable)
        except Exception:
            if job.status != JobStatus.CANCELLED:
                await self._fail(
                    job,
                    "SUMMARY_FAILED",
                    "Bubble Video AI could not finish this summary.",
                    True,
                )

    async def _advance(
        self, job: SummaryJobState, stage: SummaryStage, progress: float
    ) -> None:
        job.stage = stage
        job.progress = max(job.progress, progress)
        await self._publish(job, "stage_changed")
        await self._publish(job, "progress")

    async def _set_progress(self, job: SummaryJobState, progress: float) -> None:
        job.progress = max(job.progress, min(99, progress))
        await self._publish(job, "progress")

    async def _fail(
        self,
        job: SummaryJobState,
        code: str,
        message: str,
        retryable: bool,
    ) -> None:
        job.status = JobStatus.FAILED
        job.completed_at = now_utc()
        job.error = ErrorBody(code=code, message=message, retryable=retryable)
        await self._publish(job, "failed")

    async def cancel(self, job_id: str, remove_files: bool = True) -> bool:
        job = self.jobs.get(job_id)
        if not job:
            return False
        job.cancel_event.set()
        if job.status not in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
            job.status = JobStatus.CANCELLED
            job.completed_at = now_utc()
            await self._publish(job, "cancelled")

        if job.task and job.task is not asyncio.current_task() and not job.task.done():
            done, pending = await asyncio.wait({job.task}, timeout=5)
            if pending:
                job.task.cancel()
                await asyncio.gather(job.task, return_exceptions=True)
            for task in done:
                if not task.cancelled():
                    task.exception()

        if remove_files:
            shutil.rmtree(job.directory, ignore_errors=True)
        return True

    async def _publish(self, job: SummaryJobState, event_type: str) -> None:
        payload = {
            "sequence": len(job.events) + 1,
            "type": event_type,
            "summary": self.view(job).model_dump(mode="json"),
        }
        async with job.event_condition:
            job.events.append(payload)
            job.event_condition.notify_all()

    async def stream(self, job: SummaryJobState, after: int = 0):
        cursor = max(0, after)
        while True:
            keep_alive = False
            async with job.event_condition:
                if cursor >= len(job.events):
                    if job.status in {
                        JobStatus.COMPLETED,
                        JobStatus.FAILED,
                        JobStatus.CANCELLED,
                    }:
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
        cutoff = now_utc() - timedelta(seconds=self.config.summary_job_ttl_seconds)
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
