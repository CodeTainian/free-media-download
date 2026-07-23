import asyncio

import pytest

from app.audio_processor import AudioProcessingError, AudioProcessor
from app.config import Settings


@pytest.mark.asyncio
async def test_audio_processor_normalizes_and_chunks_with_stable_offsets(
    tmp_path, monkeypatch
):
    config = Settings(
        data_dir=tmp_path,
        transcription_chunk_seconds=600,
        transcription_chunk_overlap_seconds=2,
        transcription_max_file_bytes=25_165_824,
    )
    processor = AudioProcessor(config)
    source = tmp_path / "source.m4a"
    source.write_bytes(b"source")
    commands: list[list[str]] = []

    async def fake_run(command, **_kwargs):
        commands.append(command)
        if command[0] == config.ffprobe_binary:
            return b"605.0\n", b""
        output = command[-1]
        from pathlib import Path

        Path(output).write_bytes(b"R" * 100)
        return b"", b""

    monkeypatch.setattr(processor, "_run", fake_run)
    progress: list[float] = []
    duration, chunks = await processor.prepare_chunks(
        source,
        tmp_path / "chunks",
        asyncio.Event(),
        lambda value: _record(progress, value),
    )

    assert duration == 605
    assert [(chunk.offset_seconds, chunk.duration_seconds) for chunk in chunks] == [
        (0, 600),
        (598, 7),
    ]
    ffmpeg_commands = [command for command in commands if command[0] == config.ffmpeg_binary]
    assert all("-nostdin" in command for command in ffmpeg_commands)
    assert all(command[command.index("-ac") + 1] == "1" for command in ffmpeg_commands)
    assert all(command[command.index("-ar") + 1] == "16000" for command in ffmpeg_commands)
    assert progress[-1] == 1


async def _record(values, value):
    values.append(value)


def test_audio_processor_rejects_file_limit_too_small_for_safe_chunk(tmp_path):
    processor = AudioProcessor(
        Settings(
            data_dir=tmp_path,
            transcription_max_file_bytes=100_000,
            transcription_chunk_seconds=600,
        )
    )
    with pytest.raises(AudioProcessingError) as caught:
        processor._chunk_window_seconds()
    assert caught.value.code == "AUDIO_TOO_LARGE"


@pytest.mark.asyncio
async def test_audio_processor_cancellation_terminates_ffmpeg_process(
    tmp_path, monkeypatch
):
    processor = AudioProcessor(Settings(data_dir=tmp_path))
    cancel_event = asyncio.Event()
    terminated = asyncio.Event()

    class FakeProcess:
        returncode = None
        pid = 999_999

        async def communicate(self):
            await asyncio.Future()

    async def fake_create(*_args, **_kwargs):
        return FakeProcess()

    async def fake_terminate(_process):
        terminated.set()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    monkeypatch.setattr("app.audio_processor._terminate_process", fake_terminate)
    task = asyncio.create_task(
        processor._run(
            ["ffmpeg", "-version"],
            cancel_event=cancel_event,
            timeout=30,
            error_code="AUDIO_EXTRACTION_FAILED",
            error_message="failed",
        )
    )
    await asyncio.sleep(0)
    cancel_event.set()
    with pytest.raises(AudioProcessingError) as caught:
        await task
    assert caught.value.code == "CANCELLED"
    assert terminated.is_set()
