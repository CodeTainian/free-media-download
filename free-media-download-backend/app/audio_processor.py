from __future__ import annotations

import asyncio
import os
import signal
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from .config import Settings


ProgressCallback = Callable[[float], Awaitable[None]]


class AudioProcessingError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class AudioChunk:
    path: Path
    offset_seconds: float
    duration_seconds: float


async def _terminate_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(process.wait(), timeout=3)
    except TimeoutError:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


class AudioProcessor:
    def __init__(self, config: Settings):
        self.config = config

    async def _run(
        self,
        command: list[str],
        *,
        cancel_event: asyncio.Event,
        timeout: float,
        error_code: str,
        error_message: str,
    ) -> tuple[bytes, bytes]:
        if cancel_event.is_set():
            raise AudioProcessingError("CANCELLED", "The summary job was cancelled.")
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            raise AudioProcessingError(
                error_code,
                error_message,
                True,
            ) from exc

        communicate_task = asyncio.create_task(process.communicate())
        cancel_task = asyncio.create_task(cancel_event.wait())
        try:
            done, _ = await asyncio.wait(
                {communicate_task, cancel_task},
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if cancel_task in done and cancel_event.is_set():
                await _terminate_process(process)
                communicate_task.cancel()
                await asyncio.gather(communicate_task, return_exceptions=True)
                raise AudioProcessingError(
                    "CANCELLED", "The summary job was cancelled."
                )
            if communicate_task not in done:
                await _terminate_process(process)
                communicate_task.cancel()
                await asyncio.gather(communicate_task, return_exceptions=True)
                raise AudioProcessingError(
                    error_code,
                    "Audio processing took too long.",
                    True,
                )
            stdout, stderr = communicate_task.result()
        except asyncio.CancelledError:
            await _terminate_process(process)
            communicate_task.cancel()
            await asyncio.gather(communicate_task, return_exceptions=True)
            raise
        finally:
            cancel_task.cancel()
            await asyncio.gather(cancel_task, return_exceptions=True)
        if process.returncode:
            raise AudioProcessingError(error_code, error_message, True)
        return stdout, stderr

    async def probe_duration(
        self, audio_path: Path, cancel_event: asyncio.Event
    ) -> float:
        stdout, _ = await self._run(
            [
                self.config.ffprobe_binary,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            cancel_event=cancel_event,
            timeout=min(30, self.config.transcription_timeout_seconds),
            error_code="AUDIO_EXTRACTION_FAILED",
            error_message="The extracted audio could not be inspected.",
        )
        try:
            duration = float(stdout.decode("utf-8", "replace").strip())
        except ValueError as exc:
            raise AudioProcessingError(
                "AUDIO_EXTRACTION_FAILED",
                "The extracted audio has an invalid duration.",
            ) from exc
        if duration <= 0:
            raise AudioProcessingError(
                "AUDIO_EXTRACTION_FAILED",
                "The extracted audio is empty.",
            )
        if duration > self.config.transcription_max_duration_seconds:
            raise AudioProcessingError(
                "AUDIO_TOO_LONG",
                "Audio transcription is limited to videos up to two hours long.",
            )
        return duration

    def _chunk_window_seconds(self) -> int:
        # mono, 16 kHz, 16-bit PCM is 32,000 bytes/second. Leave room for WAV headers.
        byte_limited = int(
            max(0, self.config.transcription_max_file_bytes - 4096) / 32_000
        )
        window = min(self.config.transcription_chunk_seconds, byte_limited)
        if window < 30:
            raise AudioProcessingError(
                "AUDIO_TOO_LARGE",
                "The configured transcription file limit is too small for safe audio chunks.",
            )
        return window

    async def prepare_chunks(
        self,
        source_path: Path,
        output_dir: Path,
        cancel_event: asyncio.Event,
        on_progress: ProgressCallback,
    ) -> tuple[float, tuple[AudioChunk, ...]]:
        duration = await self.probe_duration(source_path, cancel_event)
        output_dir.mkdir(parents=True, exist_ok=True)
        resolved_output = output_dir.resolve()
        window = self._chunk_window_seconds()
        step = window - self.config.transcription_chunk_overlap_seconds
        chunks: list[AudioChunk] = []
        offset = 0.0
        while offset < duration:
            chunk_duration = min(float(window), duration - offset)
            chunk_path = output_dir / f"chunk-{len(chunks) + 1:05d}.wav"
            if not chunk_path.resolve().is_relative_to(resolved_output):
                raise AudioProcessingError(
                    "AUDIO_EXTRACTION_FAILED",
                    "The audio workspace is invalid.",
                )
            await self._run(
                [
                    self.config.ffmpeg_binary,
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-ss",
                    f"{offset:.3f}",
                    "-i",
                    str(source_path),
                    "-t",
                    f"{chunk_duration:.3f}",
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-c:a",
                    "pcm_s16le",
                    str(chunk_path),
                ],
                cancel_event=cancel_event,
                timeout=max(60, chunk_duration * 2),
                error_code="AUDIO_EXTRACTION_FAILED",
                error_message="FFmpeg could not prepare audio for transcription.",
            )
            if (
                not chunk_path.is_file()
                or chunk_path.stat().st_size <= 44
                or chunk_path.stat().st_size
                >= self.config.transcription_max_file_bytes
            ):
                chunk_path.unlink(missing_ok=True)
                raise AudioProcessingError(
                    "AUDIO_TOO_LARGE",
                    "A normalized audio chunk exceeds the transcription provider limit.",
                )
            chunks.append(
                AudioChunk(
                    path=chunk_path,
                    offset_seconds=round(offset, 3),
                    duration_seconds=round(chunk_duration, 3),
                )
            )
            await on_progress(min(1, (offset + chunk_duration) / duration))
            if offset + chunk_duration >= duration:
                break
            offset += step
        return duration, tuple(chunks)
