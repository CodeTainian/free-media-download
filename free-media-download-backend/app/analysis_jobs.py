from __future__ import annotations

import asyncio
import json
import secrets
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel

from .analysis_models import (
    AnalysisEvent,
    AnalysisResult,
    AnalysisSnapshot,
    AnalysisSource,
    AnalysisStage,
    AnalysisStatus,
    ArtifactKind,
    ArtifactStatus,
    ArtifactView,
    CanonicalContentAnalysis,
    CreateAnalysisRequest,
    GenerationMetadata,
    VisualStory,
)
from .analysis_provider import AnalysisError, AnalysisProvider
from .artifact_generators import (
    build_interactive_guide,
    build_mind_map,
    build_summary,
    build_visual_story,
    build_website_manifest,
)
from .audio_processor import AudioProcessingError
from .config import Settings
from .content_analysis import (
    hydrate_canonical_analysis,
    resolve_output_language,
    transcript_sha256,
)
from .downloader import DownloadError
from .frame_extractor import FrameExtractionError, FrameExtractor
from .models import ErrorBody
from .semantic_segmentation import SemanticUnit, segment_transcript
from .transcript_acquisition import TranscriptAcquisitionService
from .transcription_provider import TranscriptionError
from .transcripts import TranscriptDocument


def now_utc() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class AnalysisArtifactState:
    kind: ArtifactKind
    status: ArtifactStatus = ArtifactStatus.NOT_STARTED
    progress: float = 0
    payload: BaseModel | list[BaseModel] | None = None
    error: ErrorBody | None = None
    generated_at: datetime | None = None
    task: asyncio.Task[None] | None = None


@dataclass(slots=True)
class AnalysisJobState:
    id: str
    request: CreateAnalysisRequest
    directory: Path
    created_at: datetime = field(default_factory=now_utc)
    completed_at: datetime | None = None
    status: AnalysisStatus = AnalysisStatus.QUEUED
    stage: AnalysisStage = AnalysisStage.QUEUED
    progress: float = 0
    source: AnalysisSource | None = None
    transcript: TranscriptDocument | None = None
    semantic_units: tuple[SemanticUnit, ...] = ()
    canonical_analysis: CanonicalContentAnalysis | None = None
    generation_metadata: GenerationMetadata | None = None
    output_language: str = "auto"
    artifacts: dict[ArtifactKind, AnalysisArtifactState] = field(default_factory=dict)
    frame_paths: dict[str, Path] = field(default_factory=dict)
    error: ErrorBody | None = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    events: list[dict[str, object]] = field(default_factory=list)
    event_condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    task: asyncio.Task[None] | None = None
    sequence: int = 0


class AnalysisJobManager:
    def __init__(
        self,
        config: Settings,
        transcript_acquisition: TranscriptAcquisitionService,
        provider: AnalysisProvider,
        frame_extractor: FrameExtractor,
    ):
        self.config = config
        self.transcript_acquisition = transcript_acquisition
        self.provider = provider
        self.frame_extractor = frame_extractor
        self.jobs: dict[str, AnalysisJobState] = {}
        self.semaphore = asyncio.Semaphore(config.analysis_worker_concurrency)
        self.cleanup_task: asyncio.Task[None] | None = None
        self.create_lock = asyncio.Lock()
        self.shared_jobs: dict[tuple[str, str, str], str] = {}

    @property
    def root_directory(self) -> Path:
        return self.config.data_dir / "analyses"

    def ready(self) -> bool:
        return self.provider.ready()

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
        await self.provider.close()

    async def create(self, request: CreateAnalysisRequest) -> AnalysisJobState:
        cache_key = (
            request.url,
            request.output_language.value,
            request.detail.value,
        )
        async with self.create_lock:
            shared_id = self.shared_jobs.get(cache_key)
            shared = self.jobs.get(shared_id) if shared_id else None
            if shared and shared.status not in {
                AnalysisStatus.FAILED,
                AnalysisStatus.CANCELLED,
            }:
                return shared
            job_id = secrets.token_urlsafe(24)
            directory = self.root_directory / job_id
            directory.mkdir(parents=True, exist_ok=False)
            artifacts = {
                kind: AnalysisArtifactState(
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
            }
            job = AnalysisJobState(
                id=job_id,
                request=request,
                directory=directory,
                output_language=request.output_language.value,
                artifacts=artifacts,
            )
            self.jobs[job.id] = job
            self.shared_jobs[cache_key] = job.id
            await self._publish(job, "analysis.queued")
            job.task = asyncio.create_task(self._run_core(job))
            return job

    def get(self, analysis_id: str) -> AnalysisJobState | None:
        return self.jobs.get(analysis_id)

    def view(self, job: AnalysisJobState) -> AnalysisSnapshot:
        expires_at = (
            job.completed_at + timedelta(seconds=self.config.analysis_job_ttl_seconds)
            if job.completed_at
            else None
        )
        return AnalysisSnapshot(
            id=job.id,
            status=job.status,
            stage=job.stage,
            progress=round(job.progress, 1),
            source=job.source,
            output_language=job.output_language,
            detail=job.request.detail,
            artifacts={
                kind: self.artifact_view(artifact)
                for kind, artifact in job.artifacts.items()
            },
            error=job.error,
            created_at=job.created_at,
            expires_at=expires_at,
        )

    @staticmethod
    def artifact_view(artifact: AnalysisArtifactState) -> ArtifactView:
        return ArtifactView(
            kind=artifact.kind,
            status=artifact.status,
            progress=round(artifact.progress, 1),
            error=artifact.error,
            generated_at=artifact.generated_at,
        )

    def result(self, job: AnalysisJobState) -> AnalysisResult | None:
        if (
            not job.source
            or not job.canonical_analysis
            or not job.generation_metadata
        ):
            return None
        return AnalysisResult(
            id=job.id,
            source=job.source,
            canonical_analysis=job.canonical_analysis,
            generation_metadata=job.generation_metadata,
        )

    async def _run_core(self, job: AnalysisJobState) -> None:
        try:
            async with self.semaphore:
                if job.cancel_event.is_set():
                    return
                job.status = AnalysisStatus.RUNNING
                await self._publish(job, "analysis.started")
                await self._advance(job, AnalysisStage.PROBING, 2)
                transcript_artifact = job.artifacts[ArtifactKind.TRANSCRIPT]
                transcript_artifact.status = ArtifactStatus.RUNNING
                await self._publish(
                    job, "artifact.started", artifact=transcript_artifact
                )

                async def on_transcript_stage(stage: str) -> None:
                    stage_progress = {
                        "probing": 3,
                        "fetching_captions": 7,
                        "extracting_audio": 12,
                        "preparing_audio": 20,
                        "transcribing": 27,
                        "parsing_transcript": 36,
                    }
                    await self._advance(
                        job,
                        AnalysisStage.ACQUIRING_TRANSCRIPT,
                        stage_progress.get(stage, job.progress),
                    )

                async def on_transcript_progress(stage: str, value: float) -> None:
                    bases = {
                        "extracting_audio": (12, 7),
                        "preparing_audio": (20, 6),
                        "transcribing": (27, 8),
                    }
                    if stage in bases:
                        base, span = bases[stage]
                        await self._set_progress(job, base + span * value)

                transcript = await self.transcript_acquisition.acquire(
                    job.request.url,
                    job.directory,
                    preferred_languages=("zh", "en"),
                    cancel_event=job.cancel_event,
                    on_stage=on_transcript_stage,
                    on_progress=on_transcript_progress,
                )
                job.transcript = transcript
                job.output_language = resolve_output_language(
                    job.request.output_language.value, transcript
                )
                job.source = AnalysisSource(
                    source_url=transcript.source_url,
                    title=(job.request.title or transcript.title)[:240],
                    platform=transcript.platform,
                    duration_seconds=transcript.duration,
                    transcript_source=transcript.source_kind,
                    transcript_language=transcript.language,
                )
                await self._complete_artifact(
                    job, transcript_artifact, transcript, "transcript.completed"
                )

                await self._advance(
                    job, AnalysisStage.SEMANTIC_SEGMENTATION, 40
                )
                job.semantic_units = segment_transcript(
                    transcript,
                    target_characters=self.config.analysis_semantic_unit_characters,
                )

                await self._advance(job, AnalysisStage.CANONICAL_ANALYSIS, 45)

                async def provider_progress(value: float) -> None:
                    await self._set_progress(job, 45 + 35 * value)

                draft = await self.provider.analyze(
                    transcript,
                    job.semantic_units,
                    output_language=job.output_language,
                    detail=job.request.detail,
                    cancel_event=job.cancel_event,
                    on_progress=provider_progress,
                )
                await self._advance(job, AnalysisStage.VALIDATING, 82)
                canonical = hydrate_canonical_analysis(draft, transcript)
                job.canonical_analysis = canonical
                job.generation_metadata = GenerationMetadata(
                    output_language=job.output_language,
                    detail=job.request.detail,
                    transcript_sha256=transcript_sha256(transcript),
                    semantic_unit_count=len(job.semantic_units),
                    provider=self.provider.provider_name,
                    model=self.provider.model_name,
                    created_at=now_utc(),
                )

                await self._advance(
                    job, AnalysisStage.GENERATING_ARTIFACTS, 86
                )
                summary_artifact = job.artifacts[ArtifactKind.SUMMARY]
                chapters_artifact = job.artifacts[ArtifactKind.CHAPTERS]
                for artifact in (summary_artifact, chapters_artifact):
                    artifact.status = ArtifactStatus.RUNNING
                    await self._publish(job, "artifact.started", artifact=artifact)
                await self._complete_artifact(
                    job,
                    summary_artifact,
                    build_summary(
                        canonical,
                        detail=job.request.detail,
                        output_language=job.output_language,
                    ),
                    "artifact.completed",
                )
                await self._complete_artifact(
                    job,
                    chapters_artifact,
                    canonical.chapters,
                    "artifact.completed",
                )

                await self._advance(job, AnalysisStage.FINALIZING, 97)
                job.status = AnalysisStatus.COMPLETED
                job.stage = AnalysisStage.COMPLETED
                job.progress = 100
                job.completed_at = now_utc()
                await self._publish(job, "analysis.completed")
        except asyncio.CancelledError:
            if job.status != AnalysisStatus.CANCELLED:
                job.status = AnalysisStatus.CANCELLED
                job.completed_at = now_utc()
            raise
        except (
            DownloadError,
            AudioProcessingError,
            TranscriptionError,
            AnalysisError,
        ) as exc:
            if job.status == AnalysisStatus.CANCELLED:
                return
            if exc.code == "CANCELLED":
                await self._mark_cancelled(job)
                return
            await self._fail_core(job, exc.code, exc.message, exc.retryable)
        except Exception:
            if job.status != AnalysisStatus.CANCELLED:
                await self._fail_core(
                    job,
                    "ANALYSIS_FAILED",
                    "Bubble Video AI could not complete this analysis.",
                    True,
                )

    async def request_artifact(
        self, job: AnalysisJobState, kind: ArtifactKind
    ) -> AnalysisArtifactState:
        if kind in {
            ArtifactKind.SUMMARY,
            ArtifactKind.CHAPTERS,
            ArtifactKind.TRANSCRIPT,
        }:
            return job.artifacts[kind]
        async with job.lock:
            artifact = job.artifacts[kind]
            if artifact.status in {
                ArtifactStatus.QUEUED,
                ArtifactStatus.RUNNING,
                ArtifactStatus.COMPLETED,
            }:
                return artifact
            if not job.canonical_analysis or not job.source:
                raise AnalysisError(
                    "ANALYSIS_NOT_READY",
                    "The canonical analysis is not ready yet.",
                    True,
                )
            if job.status in {AnalysisStatus.FAILED, AnalysisStatus.CANCELLED}:
                raise AnalysisError(
                    "ANALYSIS_NOT_READY",
                    "This analysis is no longer available for artifact generation.",
                )
            artifact.status = ArtifactStatus.QUEUED
            artifact.progress = 0
            artifact.error = None
            artifact.payload = None
            await self._publish(job, "artifact.queued", artifact=artifact)
            artifact.task = asyncio.create_task(self._run_artifact(job, artifact))
            return artifact

    async def _run_artifact(
        self, job: AnalysisJobState, artifact: AnalysisArtifactState
    ) -> None:
        try:
            async with self.semaphore:
                if job.cancel_event.is_set():
                    raise AnalysisError("CANCELLED", "The analysis was cancelled.")
                artifact.status = ArtifactStatus.RUNNING
                artifact.progress = 5
                job.status = AnalysisStatus.RUNNING
                job.completed_at = None
                await self._publish(job, "artifact.started", artifact=artifact)
                canonical = job.canonical_analysis
                source = job.source
                assert canonical is not None and source is not None
                if artifact.kind == ArtifactKind.MIND_MAP:
                    payload = build_mind_map(
                        source,
                        canonical,
                        max_nodes=self.config.analysis_max_mind_map_nodes,
                    )
                elif artifact.kind == ArtifactKind.DYNAMIC_WEBSITE:
                    payload = build_website_manifest(
                        source,
                        canonical,
                        output_language=job.output_language,
                    )
                elif artifact.kind == ArtifactKind.INTERACTIVE_GUIDE:
                    payload = build_interactive_guide(
                        source,
                        canonical,
                        output_language=job.output_language,
                    )
                elif artifact.kind == ArtifactKind.VISUAL_STORY:
                    story = build_visual_story(
                        source,
                        canonical,
                        frame_limit=self.config.analysis_visual_story_frames,
                    )

                    async def frame_progress(value: float) -> None:
                        artifact.progress = max(
                            artifact.progress, min(95, 10 + 85 * value)
                        )
                        await self._publish(
                            job, "artifact.progress", artifact=artifact
                        )

                    try:
                        paths = await self.frame_extractor.extract(
                            str(source.source_url),
                            story.frames,
                            job.directory,
                            job.cancel_event,
                            frame_progress,
                        )
                        job.frame_paths.update(paths)
                        story = story.model_copy(
                            update={
                                "frames": [
                                    frame.model_copy(
                                        update={
                                            "image_url": (
                                                f"/api/v1/analyses/{job.id}/frames/{frame.id}"
                                                if frame.id in paths
                                                else None
                                            )
                                        }
                                    )
                                    for frame in story.frames
                                ]
                            }
                        )
                    except FrameExtractionError as exc:
                        if exc.code == "CANCELLED":
                            raise
                        story = story.model_copy(
                            update={
                                "warnings": [
                                    "Representative frames were unavailable; the story remains usable as a text timeline."
                                ]
                            }
                        )
                    payload = story
                else:
                    raise AnalysisError(
                        "UNSUPPORTED_ARTIFACT",
                        "This knowledge artifact is not supported.",
                    )
                await self._complete_artifact(
                    job, artifact, payload, "artifact.completed"
                )
            job.status = (
                AnalysisStatus.PARTIAL
                if any(
                    item.status == ArtifactStatus.FAILED
                    for item in job.artifacts.values()
                )
                else AnalysisStatus.COMPLETED
            )
            job.completed_at = now_utc()
            await self._publish(
                job,
                "analysis.partial"
                if job.status == AnalysisStatus.PARTIAL
                else "analysis.completed",
            )
        except (AnalysisError, FrameExtractionError) as exc:
            if exc.code == "CANCELLED":
                artifact.status = ArtifactStatus.CANCELLED
                artifact.error = ErrorBody(
                    code="CANCELLED",
                    message="The artifact generation was cancelled.",
                )
                await self._publish(job, "artifact.cancelled", artifact=artifact)
                return
            artifact.status = ArtifactStatus.FAILED
            artifact.error = ErrorBody(
                code=exc.code,
                message=exc.message,
                retryable=exc.retryable,
            )
            job.status = AnalysisStatus.PARTIAL
            job.completed_at = now_utc()
            await self._publish(job, "artifact.failed", artifact=artifact)
            await self._publish(job, "analysis.partial", artifact=artifact)
        except Exception:
            artifact.status = ArtifactStatus.FAILED
            artifact.error = ErrorBody(
                code="ARTIFACT_FAILED",
                message="This knowledge artifact could not be generated.",
                retryable=True,
            )
            job.status = AnalysisStatus.PARTIAL
            job.completed_at = now_utc()
            await self._publish(job, "artifact.failed", artifact=artifact)
            await self._publish(job, "analysis.partial", artifact=artifact)
        finally:
            artifact.task = None

    async def _complete_artifact(
        self,
        job: AnalysisJobState,
        artifact: AnalysisArtifactState,
        payload: BaseModel | list[BaseModel],
        event_type: str,
    ) -> None:
        artifact.payload = payload
        artifact.status = ArtifactStatus.COMPLETED
        artifact.progress = 100
        artifact.generated_at = now_utc()
        artifact.error = None
        await self._publish(job, event_type, artifact=artifact)

    async def _advance(
        self, job: AnalysisJobState, stage: AnalysisStage, progress: float
    ) -> None:
        job.stage = stage
        job.progress = max(job.progress, min(99, progress))
        await self._publish(job, "analysis.stage_changed")

    async def _set_progress(self, job: AnalysisJobState, progress: float) -> None:
        job.progress = max(job.progress, min(99, progress))
        await self._publish(job, "analysis.progress")

    async def _fail_core(
        self,
        job: AnalysisJobState,
        code: str,
        message: str,
        retryable: bool,
    ) -> None:
        job.status = AnalysisStatus.FAILED
        job.completed_at = now_utc()
        job.error = ErrorBody(code=code, message=message, retryable=retryable)
        for artifact in job.artifacts.values():
            if artifact.status in {ArtifactStatus.QUEUED, ArtifactStatus.RUNNING}:
                artifact.status = ArtifactStatus.FAILED
                artifact.error = job.error
        await self._publish(job, "analysis.failed", error=job.error)

    async def _mark_cancelled(self, job: AnalysisJobState) -> None:
        if job.status == AnalysisStatus.CANCELLED:
            return
        job.status = AnalysisStatus.CANCELLED
        job.completed_at = now_utc()
        for artifact in job.artifacts.values():
            if artifact.status in {ArtifactStatus.QUEUED, ArtifactStatus.RUNNING}:
                artifact.status = ArtifactStatus.CANCELLED
        await self._publish(job, "analysis.cancelled")

    async def cancel(self, analysis_id: str, remove_files: bool = False) -> bool:
        job = self.jobs.get(analysis_id)
        if not job:
            return False
        tasks = [
            task
            for task in [
                job.task,
                *(artifact.task for artifact in job.artifacts.values()),
            ]
            if task and task is not asyncio.current_task() and not task.done()
        ]
        if tasks or job.status in {AnalysisStatus.QUEUED, AnalysisStatus.RUNNING}:
            job.cancel_event.set()
            await self._mark_cancelled(job)
        if tasks:
            done, pending = await asyncio.wait(tasks, timeout=5)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                if not task.cancelled():
                    task.exception()
        if remove_files:
            shutil.rmtree(job.directory, ignore_errors=True)
        return True

    async def delete(self, analysis_id: str) -> bool:
        job = self.jobs.get(analysis_id)
        if not job:
            return False
        await self.cancel(analysis_id, remove_files=True)
        self.jobs.pop(analysis_id, None)
        return True

    async def _publish(
        self,
        job: AnalysisJobState,
        event_type: str,
        *,
        artifact: AnalysisArtifactState | None = None,
        error: ErrorBody | None = None,
    ) -> None:
        job.sequence += 1
        envelope = AnalysisEvent(
            sequence=job.sequence,
            event=event_type,
            analysis_id=job.id,
            emitted_at=now_utc(),
            stage=job.stage,
            overall_progress=round(job.progress, 1),
            artifact=self.artifact_view(artifact) if artifact else None,
            error=error,
        ).model_dump(mode="json", exclude_none=True)
        async with job.event_condition:
            job.events.append(envelope)
            job.event_condition.notify_all()

    async def stream(self, job: AnalysisJobState, after: int = 0):
        cursor = max(0, after)
        while True:
            keep_alive = False
            async with job.event_condition:
                pending = [
                    event
                    for event in job.events
                    if int(event["sequence"]) > cursor
                ]
                if not pending:
                    if job.status in {
                        AnalysisStatus.FAILED,
                        AnalysisStatus.CANCELLED,
                    }:
                        return
                    try:
                        await asyncio.wait_for(
                            job.event_condition.wait(), timeout=15
                        )
                    except TimeoutError:
                        keep_alive = True
                    pending = [
                        event
                        for event in job.events
                        if int(event["sequence"]) > cursor
                    ]
            if keep_alive and not pending:
                yield ": keep-alive\n\n"
                continue
            for event in pending:
                cursor = int(event["sequence"])
                yield (
                    f"id: {cursor}\n"
                    f"event: {event['event']}\n"
                    f"data: {json.dumps(event, separators=(',', ':'))}\n\n"
                )

    async def cleanup_expired(self) -> int:
        cutoff = now_utc() - timedelta(seconds=self.config.analysis_job_ttl_seconds)
        expired = [
            analysis_id
            for analysis_id, job in self.jobs.items()
            if job.completed_at and job.completed_at <= cutoff
        ]
        for analysis_id in expired:
            job = self.jobs.pop(analysis_id)
            shutil.rmtree(job.directory, ignore_errors=True)
            key = (
                job.request.url,
                job.request.output_language.value,
                job.request.detail.value,
            )
            if self.shared_jobs.get(key) == analysis_id:
                self.shared_jobs.pop(key, None)
        return len(expired)

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(self.config.cleanup_interval_seconds)
            await self.cleanup_expired()
