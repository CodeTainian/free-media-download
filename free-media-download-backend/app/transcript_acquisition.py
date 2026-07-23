from __future__ import annotations

import asyncio
import re
import shutil
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from .audio_processor import AudioProcessingError, AudioProcessor
from .config import Settings
from .downloader import DownloadError, YtDlpService, has_usable_audio
from .transcription_provider import (
    TranscriptionError,
    TranscriptionProvider,
    TranscriptionResult,
)
from .transcripts import (
    TranscriptDocument,
    TranscriptSegment,
    normalize_transcript_segments,
    select_caption_track,
)


StageCallback = Callable[[str], Awaitable[None]]
ProgressCallback = Callable[[str, float], Awaitable[None]]


def _normalized_words(value: str) -> list[str]:
    return re.findall(r"\w+", value.casefold(), flags=re.UNICODE)


def _trim_boundary_text(previous: str, current: str) -> str:
    previous_words = _normalized_words(previous)
    current_words = _normalized_words(current)
    if not previous_words or not current_words:
        return current.strip()
    if current_words == previous_words or (
        len(current_words) <= len(previous_words)
        and previous_words[-len(current_words) :] == current_words
    ):
        return ""
    max_common = min(len(previous_words), len(current_words), 20)
    common = 0
    for count in range(max_common, 1, -1):
        if previous_words[-count:] == current_words[:count]:
            common = count
            break
    if not common:
        return current.strip()
    tokens = current.split()
    return " ".join(tokens[common:]).strip() if len(tokens) >= common else ""


def merge_transcription_results(
    chunks: tuple[tuple[float, float, TranscriptionResult], ...],
    audio_duration: float,
) -> tuple[TranscriptSegment, ...]:
    raw: list[tuple[float, float, str]] = []
    previous_text = ""
    for offset, chunk_duration, result in chunks:
        for segment in result.segments:
            start = max(offset, offset + segment.start)
            end = min(audio_duration, offset + segment.end, offset + chunk_duration)
            text = _trim_boundary_text(previous_text, segment.text)
            if not text or end <= start:
                continue
            raw.append((start, end, text))
            previous_text = text
    return normalize_transcript_segments(raw)


class TranscriptAcquisitionService:
    def __init__(
        self,
        config: Settings,
        downloader: YtDlpService,
        audio_processor: AudioProcessor,
        transcription_provider: TranscriptionProvider,
    ):
        self.config = config
        self.downloader = downloader
        self.audio_processor = audio_processor
        self.transcription_provider = transcription_provider

    def transcription_ready(self) -> bool:
        return self.transcription_provider.ready()

    async def close(self) -> None:
        await self.transcription_provider.close()

    async def acquire(
        self,
        raw_url: str,
        job_directory: Path,
        *,
        preferred_languages: tuple[str, ...],
        cancel_event: asyncio.Event,
        on_stage: StageCallback,
        on_progress: ProgressCallback,
    ) -> TranscriptDocument:
        await on_stage("probing")
        source = await self.downloader.prepare_transcript_source(raw_url)
        if cancel_event.is_set():
            raise DownloadError("CANCELLED", "The summary job was cancelled.")
        if (
            source.duration
            and source.duration > self.config.summary_max_duration_seconds
        ):
            raise DownloadError(
                "MEDIA_TOO_LONG",
                "AI summaries are limited to videos up to two hours long.",
            )

        await on_stage("fetching_captions")
        track = select_caption_track(source.info, preferred_languages)
        if track:
            return await self.downloader.fetch_caption_transcript_from_source(
                source,
                job_directory / "captions",
                track,
                cancel_event=cancel_event,
                on_stage=lambda _stage: on_stage("parsing_transcript"),
            )

        if not has_usable_audio(source.info):
            raise DownloadError(
                "UNSUPPORTED_AUDIO_SOURCE",
                "This public source does not expose a supported audio track.",
            )
        if not self.transcription_provider.ready():
            raise TranscriptionError(
                "TRANSCRIPTION_NOT_CONFIGURED",
                "Audio transcription is not configured on this server.",
            )
        if (
            source.duration
            and source.duration > self.config.transcription_max_duration_seconds
        ):
            raise AudioProcessingError(
                "AUDIO_TOO_LONG",
                "Audio transcription is limited to videos up to two hours long.",
            )

        audio_directory = job_directory / "audio"
        try:
            await on_stage("extracting_audio")
            source_audio = await self.downloader.extract_transcription_audio(
                source,
                audio_directory / "source",
                cancel_event,
                lambda value: on_progress("extracting_audio", value),
            )
            await on_stage("preparing_audio")
            audio_duration, chunks = await self.audio_processor.prepare_chunks(
                source_audio,
                audio_directory / "chunks",
                cancel_event,
                lambda value: on_progress("preparing_audio", value),
            )
            if not chunks:
                raise AudioProcessingError(
                    "AUDIO_EXTRACTION_FAILED",
                    "The extracted audio is empty.",
                )

            await on_stage("transcribing")
            started = time.monotonic()
            transcribed: list[tuple[float, float, TranscriptionResult]] = []
            detected_language: str | None = None
            prompt: str | None = None
            try:
                async with asyncio.timeout(
                    self.config.transcription_timeout_seconds
                ):
                    for index, chunk in enumerate(chunks):
                        if cancel_event.is_set():
                            raise TranscriptionError(
                                "CANCELLED", "The summary job was cancelled."
                            )

                        async def provider_progress(value: float) -> None:
                            await on_progress(
                                "transcribing",
                                min(1, (index + max(0, min(1, value))) / len(chunks)),
                            )

                        result = await self.transcription_provider.transcribe(
                            chunk.path,
                            requested_language=None,
                            prompt=prompt,
                            cancel_event=cancel_event,
                            on_progress=provider_progress,
                        )
                        transcribed.append(
                            (chunk.offset_seconds, chunk.duration_seconds, result)
                        )
                        detected_language = detected_language or result.language
                        prompt = " ".join(
                            segment.text for segment in result.segments[-3:]
                        )[-1_000:]
                        await on_progress(
                            "transcribing", (index + 1) / len(chunks)
                        )
            except TimeoutError as exc:
                raise TranscriptionError(
                    "TRANSCRIPTION_TIMEOUT",
                    "Audio transcription took too long.",
                    True,
                ) from exc

            await on_stage("parsing_transcript")
            segments = merge_transcription_results(tuple(transcribed), audio_duration)
            if not segments:
                raise TranscriptionError(
                    "TRANSCRIPT_EMPTY",
                    "The transcription provider did not detect any speech.",
                )
            provider_name = (
                transcribed[0][2].provider
                if transcribed
                else self.config.transcription_provider
            )
            return TranscriptDocument(
                source_url=source.source_url,
                title=source.title,
                platform=source.platform,
                duration=source.duration,
                language=detected_language or "und",
                source_kind="audio_transcription",
                segments=segments,
                detected_language=detected_language,
                requested_language=None,
                provider=provider_name,
                transcription_duration=round(time.monotonic() - started, 3),
                audio_duration=round(audio_duration, 3),
            )
        finally:
            shutil.rmtree(audio_directory, ignore_errors=True)
