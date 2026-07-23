from __future__ import annotations

import asyncio
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path

from .analysis_models import StoryFrame
from .config import Settings
from .downloader import DownloadError, YtDlpService, terminate_process


ProgressCallback = Callable[[float], Awaitable[None]]


class FrameExtractionError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class FrameExtractor:
    def __init__(self, config: Settings, downloader: YtDlpService):
        self.config = config
        self.downloader = downloader

    async def extract(
        self,
        source_url: str,
        frames: list[StoryFrame],
        job_directory: Path,
        cancel_event: asyncio.Event,
        on_progress: ProgressCallback,
    ) -> dict[str, Path]:
        video_directory = job_directory / "visual-source"
        frame_directory = job_directory / "frames"
        video_directory.mkdir(parents=True, exist_ok=True)
        frame_directory.mkdir(parents=True, exist_ok=True)
        resolved_frames = frame_directory.resolve()
        try:
            try:
                video_path = await self.downloader.download(
                    source_url,
                    "mp4-720",
                    video_directory,
                    cancel_event,
                    lambda progress, _speed, _eta: on_progress(
                        min(0.35, progress / 100 * 0.35)
                    ),
                )
            except DownloadError as exc:
                if exc.code == "CANCELLED":
                    raise FrameExtractionError("CANCELLED", "The analysis was cancelled.") from exc
                raise FrameExtractionError(
                    "KEYFRAME_EXTRACTION_FAILED",
                    "Representative video frames could not be prepared.",
                    exc.retryable,
                ) from exc

            extracted: dict[str, Path] = {}
            for index, frame in enumerate(frames):
                if cancel_event.is_set():
                    raise FrameExtractionError(
                        "CANCELLED", "The analysis was cancelled."
                    )
                destination = frame_directory / f"{frame.id}.jpg"
                if not destination.resolve().is_relative_to(resolved_frames):
                    raise FrameExtractionError(
                        "KEYFRAME_EXTRACTION_FAILED",
                        "The frame workspace is invalid.",
                    )
                seek = max(0, frame.timestamp_seconds - 1.5)
                command = [
                    self.config.ffmpeg_binary,
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-ss",
                    f"{seek:.3f}",
                    "-i",
                    str(video_path),
                    "-t",
                    "3",
                    "-vf",
                    "thumbnail=30,scale='min(1280,iw)':-2",
                    "-frames:v",
                    "1",
                    "-q:v",
                    "3",
                    str(destination),
                ]
                try:
                    process = await asyncio.create_subprocess_exec(
                        *command,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.PIPE,
                        start_new_session=True,
                    )
                except FileNotFoundError:
                    break
                communicate_task = asyncio.create_task(process.communicate())
                cancel_task = asyncio.create_task(cancel_event.wait())
                try:
                    done, _ = await asyncio.wait(
                        {communicate_task, cancel_task},
                        timeout=45,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if cancel_task in done and cancel_event.is_set():
                        await terminate_process(process)
                        communicate_task.cancel()
                        await asyncio.gather(communicate_task, return_exceptions=True)
                        raise FrameExtractionError(
                            "CANCELLED", "The analysis was cancelled."
                        )
                    if communicate_task not in done:
                        await terminate_process(process)
                        communicate_task.cancel()
                        await asyncio.gather(communicate_task, return_exceptions=True)
                        destination.unlink(missing_ok=True)
                        continue
                    await communicate_task
                finally:
                    cancel_task.cancel()
                    await asyncio.gather(cancel_task, return_exceptions=True)
                if (
                    process.returncode == 0
                    and destination.is_file()
                    and destination.stat().st_size > 2_000
                ):
                    extracted[frame.id] = destination
                else:
                    destination.unlink(missing_ok=True)
                await on_progress(0.35 + 0.65 * (index + 1) / max(1, len(frames)))
            return extracted
        finally:
            shutil.rmtree(video_directory, ignore_errors=True)
