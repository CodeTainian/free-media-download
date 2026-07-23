import asyncio
from pathlib import Path

import pytest

from app.audio_processor import AudioChunk
from app.config import Settings
from app.downloader import DownloadError, TranscriptSource
from app.transcript_acquisition import TranscriptAcquisitionService
from app.transcription_provider import (
    TranscriptionError,
    TranscriptionResult,
    TranscriptionSegment,
)
from app.transcripts import CaptionTrack, TranscriptDocument, TranscriptSegment


def source_info(*, manual=False, automatic=False, audio=True):
    info: dict[str, object] = {
        "title": "Public lesson",
        "duration": 12,
        "webpage_url": "https://www.youtube.com/watch?v=public",
        "formats": [{"acodec": "aac"}] if audio else [],
    }
    if manual:
        info["subtitles"] = {"en": [{"ext": "vtt"}]}
    if automatic:
        info["automatic_captions"] = {"en": [{"ext": "vtt"}]}
    return info


class FakeDownloader:
    def __init__(self, info):
        self.source = TranscriptSource(
            platform="youtube",
            normalized_url="https://www.youtube.com/watch?v=public",
            source_url="https://www.youtube.com/watch?v=public",
            title="Public lesson",
            duration=12,
            info=info,
        )
        self.caption_track = None
        self.extract_calls = 0

    async def prepare_transcript_source(self, _raw_url):
        return self.source

    async def fetch_caption_transcript_from_source(
        self, source, _output_dir, track, **kwargs
    ):
        self.caption_track = track
        await kwargs["on_stage"]("parsing")
        return TranscriptDocument(
            source_url=source.source_url,
            title=source.title,
            platform=source.platform,
            duration=source.duration,
            language=track.language,
            source_kind=track.source_kind,
            segments=(
                TranscriptSegment(
                    id="seg-00001", start=0, end=2, text="Caption evidence"
                ),
            ),
        )

    async def extract_transcription_audio(
        self, _source, output_dir, cancel_event, on_progress
    ):
        self.extract_calls += 1
        if cancel_event.is_set():
            raise DownloadError("CANCELLED", "Cancelled.")
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "source.m4a"
        path.write_bytes(b"audio")
        await on_progress(1)
        return path


class FakeAudioProcessor:
    def __init__(self):
        self.calls = 0

    async def prepare_chunks(
        self, _source_path, output_dir, _cancel_event, on_progress
    ):
        self.calls += 1
        output_dir.mkdir(parents=True, exist_ok=True)
        first = output_dir / "chunk-00001.wav"
        second = output_dir / "chunk-00002.wav"
        first.write_bytes(b"RIFFfirst")
        second.write_bytes(b"RIFFsecond")
        await on_progress(1)
        return 12.0, (
            AudioChunk(first, 0, 10),
            AudioChunk(second, 8, 4),
        )


class FakeProvider:
    def __init__(self, results=None, ready=True):
        self.results = list(results or [])
        self.is_ready = ready
        self.calls = 0
        self.prompts: list[str | None] = []
        self.closed = False

    def ready(self):
        return self.is_ready

    async def transcribe(
        self,
        _audio_path,
        *,
        requested_language,
        prompt,
        cancel_event,
        on_progress,
    ):
        assert requested_language is None
        if cancel_event.is_set():
            raise TranscriptionError("CANCELLED", "Cancelled.")
        self.prompts.append(prompt)
        result = self.results[self.calls]
        self.calls += 1
        await on_progress(1)
        return result

    async def close(self):
        self.closed = True


def asr_result(*segments):
    return TranscriptionResult(
        language="en",
        segments=tuple(
            TranscriptionSegment(start=start, end=end, text=text)
            for start, end, text in segments
        ),
        provider="mock",
        model="mock-1",
    )


async def run_acquisition(service, tmp_path):
    stages: list[str] = []
    progress: list[tuple[str, float]] = []
    transcript = await service.acquire(
        "https://www.youtube.com/watch?v=public",
        tmp_path / "summaries" / "job",
        preferred_languages=("en",),
        cancel_event=asyncio.Event(),
        on_stage=lambda stage: _append(stages, stage),
        on_progress=lambda stage, value: _append(progress, (stage, value)),
    )
    return transcript, stages, progress


async def _append(values, value):
    values.append(value)


@pytest.mark.asyncio
async def test_manual_caption_skips_audio_and_provider(tmp_path):
    downloader = FakeDownloader(source_info(manual=True))
    processor = FakeAudioProcessor()
    provider = FakeProvider()
    service = TranscriptAcquisitionService(
        Settings(data_dir=tmp_path), downloader, processor, provider
    )

    transcript, stages, _ = await run_acquisition(service, tmp_path)

    assert transcript.source_kind == "manual_caption"
    assert downloader.caption_track == CaptionTrack(language="en", automatic=False)
    assert downloader.extract_calls == 0
    assert processor.calls == 0
    assert provider.calls == 0
    assert stages == ["probing", "fetching_captions", "parsing_transcript"]


@pytest.mark.asyncio
async def test_automatic_caption_is_used_before_audio(tmp_path):
    downloader = FakeDownloader(source_info(automatic=True))
    processor = FakeAudioProcessor()
    provider = FakeProvider()
    service = TranscriptAcquisitionService(
        Settings(data_dir=tmp_path), downloader, processor, provider
    )

    transcript, _, _ = await run_acquisition(service, tmp_path)

    assert transcript.source_kind == "automatic_caption"
    assert downloader.caption_track == CaptionTrack(language="en", automatic=True)
    assert downloader.extract_calls == 0
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_no_captions_runs_asr_and_merges_global_timestamps(tmp_path):
    downloader = FakeDownloader(source_info())
    processor = FakeAudioProcessor()
    provider = FakeProvider(
        [
            asr_result((8, 10, "Boundary sentence")),
            asr_result(
                (0, 2, "Boundary sentence"),
                (2, 4, "Next topic"),
            ),
        ]
    )
    config = Settings(
        data_dir=tmp_path,
        transcription_provider="openai_compatible",
        transcription_api_key="test-key",
    )
    service = TranscriptAcquisitionService(config, downloader, processor, provider)

    transcript, stages, progress = await run_acquisition(service, tmp_path)

    assert transcript.source_kind == "audio_transcription"
    assert transcript.detected_language == "en"
    assert transcript.provider == "mock"
    assert transcript.audio_duration == 12
    assert [(item.id, item.start, item.end, item.text) for item in transcript.segments] == [
        ("seg-00001", 8, 10, "Boundary sentence"),
        ("seg-00002", 10, 12, "Next topic"),
    ]
    assert provider.prompts == [None, "Boundary sentence"]
    assert stages == [
        "probing",
        "fetching_captions",
        "extracting_audio",
        "preparing_audio",
        "transcribing",
        "parsing_transcript",
    ]
    assert progress[-1] == ("transcribing", 1)
    assert not (tmp_path / "summaries" / "job" / "audio").exists()


@pytest.mark.asyncio
async def test_asr_empty_result_is_safe_and_audio_is_cleaned(tmp_path):
    downloader = FakeDownloader(source_info())
    provider = FakeProvider(
        [
            TranscriptionResult(
                language="en",
                segments=(),
                provider="mock",
                model="mock-1",
            ),
            TranscriptionResult(
                language="en",
                segments=(),
                provider="mock",
                model="mock-1",
            ),
        ]
    )
    service = TranscriptAcquisitionService(
        Settings(
            data_dir=tmp_path,
            transcription_provider="openai_compatible",
            transcription_api_key="test-key",
        ),
        downloader,
        FakeAudioProcessor(),
        provider,
    )

    with pytest.raises(TranscriptionError) as caught:
        await run_acquisition(service, tmp_path)
    assert caught.value.code == "TRANSCRIPT_EMPTY"
    assert not (tmp_path / "summaries" / "job" / "audio").exists()


@pytest.mark.asyncio
async def test_asr_total_timeout_is_safe_and_audio_is_cleaned(tmp_path):
    class SlowProvider(FakeProvider):
        async def transcribe(self, *_args, **_kwargs):
            await asyncio.sleep(60)

    service = TranscriptAcquisitionService(
        Settings(
            data_dir=tmp_path,
            transcription_provider="openai_compatible",
            transcription_api_key="test-key",
            transcription_timeout_seconds=0.01,
        ),
        FakeDownloader(source_info()),
        FakeAudioProcessor(),
        SlowProvider(),
    )

    with pytest.raises(TranscriptionError) as caught:
        await run_acquisition(service, tmp_path)
    assert caught.value.code == "TRANSCRIPTION_TIMEOUT"
    assert caught.value.retryable is True
    assert not (tmp_path / "summaries" / "job" / "audio").exists()


@pytest.mark.asyncio
async def test_no_caption_source_reports_missing_provider_without_extracting(tmp_path):
    downloader = FakeDownloader(source_info())
    service = TranscriptAcquisitionService(
        Settings(data_dir=tmp_path),
        downloader,
        FakeAudioProcessor(),
        FakeProvider(ready=False),
    )

    with pytest.raises(TranscriptionError) as caught:
        await run_acquisition(service, tmp_path)
    assert caught.value.code == "TRANSCRIPTION_NOT_CONFIGURED"
    assert downloader.extract_calls == 0


@pytest.mark.asyncio
async def test_cancelled_audio_extraction_removes_isolated_audio_directory(tmp_path):
    started = asyncio.Event()

    class BlockingDownloader(FakeDownloader):
        async def extract_transcription_audio(
            self, _source, output_dir, cancel_event, _on_progress
        ):
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "partial.part").write_bytes(b"partial")
            started.set()
            await cancel_event.wait()
            raise DownloadError("CANCELLED", "Cancelled.")

    cancel_event = asyncio.Event()
    service = TranscriptAcquisitionService(
        Settings(
            data_dir=tmp_path,
            transcription_provider="openai_compatible",
            transcription_api_key="test-key",
        ),
        BlockingDownloader(source_info()),
        FakeAudioProcessor(),
        FakeProvider(),
    )
    job_directory = tmp_path / "summaries" / "job"
    task = asyncio.create_task(
        service.acquire(
            "https://www.youtube.com/watch?v=public",
            job_directory,
            preferred_languages=("en",),
            cancel_event=cancel_event,
            on_stage=lambda _stage: asyncio.sleep(0),
            on_progress=lambda _stage, _value: asyncio.sleep(0),
        )
    )
    await started.wait()
    cancel_event.set()
    with pytest.raises(DownloadError) as caught:
        await task
    assert caught.value.code == "CANCELLED"
    assert not (job_directory / "audio").exists()
