import asyncio

import httpx
import pytest

from app.config import Settings
from app.transcription_provider import (
    OpenAICompatibleTranscriptionProvider,
    TranscriptionError,
)


def configured_settings(tmp_path, secret: str = "sk-transcription-super-secret") -> Settings:
    return Settings(
        data_dir=tmp_path,
        transcription_provider="openai_compatible",
        transcription_api_key=secret,
        transcription_model="whisper-1",
        transcription_base_url="https://speech.example/v1",
        transcription_timeout_seconds=3,
    )


async def transcribe(provider, audio_path, cancel_event=None):
    return await provider.transcribe(
        audio_path,
        requested_language=None,
        prompt=None,
        cancel_event=cancel_event or asyncio.Event(),
        on_progress=lambda _value: asyncio.sleep(0),
    )


@pytest.mark.asyncio
async def test_openai_compatible_provider_sends_fixed_verbose_segment_request(tmp_path):
    audio = tmp_path / "chunk.wav"
    audio.write_bytes(b"RIFFtest")

    async def handler(request: httpx.Request):
        assert request.url == "https://speech.example/v1/audio/transcriptions"
        assert request.headers["authorization"].startswith("Bearer ")
        body = await request.aread()
        assert b'name="model"' in body
        assert b"whisper-1" in body
        assert b"verbose_json" in body
        assert b"timestamp_granularities[]" in body
        return httpx.Response(
            200,
            json={
                "language": "en",
                "duration": 4.5,
                "segments": [
                    {"start": 0, "end": 2, "text": "First sentence."},
                    {"start": 2, "end": 4.5, "text": "Second sentence."},
                ],
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleTranscriptionProvider(
        configured_settings(tmp_path), client=client
    )
    try:
        result = await transcribe(provider, audio)
    finally:
        await client.aclose()

    assert result.language == "en"
    assert [segment.text for segment in result.segments] == [
        "First sentence.",
        "Second sentence.",
    ]
    assert result.provider == "openai_compatible"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (429, "TRANSCRIPTION_RATE_LIMITED", True),
        (401, "TRANSCRIPTION_PROVIDER_UNAVAILABLE", False),
        (503, "TRANSCRIPTION_PROVIDER_UNAVAILABLE", True),
        (400, "TRANSCRIPTION_FAILED", False),
    ],
)
async def test_provider_maps_http_errors_without_exposing_response(
    tmp_path, status, code, retryable, caplog
):
    audio = tmp_path / "chunk.wav"
    audio.write_bytes(b"RIFFtest")
    secret_body = "provider-internal-secret-response"
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(status, text=secret_body)
        )
    )
    provider = OpenAICompatibleTranscriptionProvider(
        configured_settings(tmp_path), client=client
    )
    try:
        with pytest.raises(TranscriptionError) as caught:
            await transcribe(provider, audio)
    finally:
        await client.aclose()

    assert caught.value.code == code
    assert caught.value.retryable is retryable
    assert secret_body not in str(caught.value)
    assert secret_body not in caplog.text
    assert "sk-transcription-super-secret" not in caplog.text


@pytest.mark.asyncio
async def test_provider_maps_timeout_and_invalid_payload_safely(tmp_path):
    audio = tmp_path / "chunk.wav"
    audio.write_bytes(b"RIFFtest")

    async def timeout_handler(request):
        raise httpx.ReadTimeout("upstream timeout with internal details", request=request)

    timeout_client = httpx.AsyncClient(
        transport=httpx.MockTransport(timeout_handler)
    )
    timeout_provider = OpenAICompatibleTranscriptionProvider(
        configured_settings(tmp_path), client=timeout_client
    )
    with pytest.raises(TranscriptionError) as timeout:
        await transcribe(timeout_provider, audio)
    assert timeout.value.code == "TRANSCRIPTION_TIMEOUT"
    assert "internal details" not in str(timeout.value)
    await timeout_client.aclose()

    invalid_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, content=b"not-json")
        )
    )
    invalid_provider = OpenAICompatibleTranscriptionProvider(
        configured_settings(tmp_path), client=invalid_client
    )
    with pytest.raises(TranscriptionError) as invalid:
        await transcribe(invalid_provider, audio)
    assert invalid.value.code == "TRANSCRIPTION_FAILED"
    await invalid_client.aclose()


@pytest.mark.asyncio
async def test_provider_rejects_empty_segments(tmp_path):
    audio = tmp_path / "chunk.wav"
    audio.write_bytes(b"RIFFtest")
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200, json={"language": "en", "segments": []}
            )
        )
    )
    provider = OpenAICompatibleTranscriptionProvider(
        configured_settings(tmp_path), client=client
    )
    with pytest.raises(TranscriptionError) as caught:
        await transcribe(provider, audio)
    assert caught.value.code == "TRANSCRIPT_EMPTY"
    await client.aclose()


@pytest.mark.asyncio
async def test_provider_cancellation_stops_inflight_http_request(tmp_path):
    audio = tmp_path / "chunk.wav"
    audio.write_bytes(b"RIFFtest")
    started = asyncio.Event()

    async def handler(_request):
        started.set()
        await asyncio.Future()

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleTranscriptionProvider(
        configured_settings(tmp_path), client=client
    )
    cancel_event = asyncio.Event()
    task = asyncio.create_task(transcribe(provider, audio, cancel_event))
    await started.wait()
    cancel_event.set()
    with pytest.raises(TranscriptionError) as caught:
        await task
    assert caught.value.code == "CANCELLED"
    await client.aclose()


def test_transcription_secret_is_hidden_from_repr_and_configuration_errors(tmp_path):
    secret = "sk-never-print-this-value"
    config = configured_settings(tmp_path, secret)
    provider = OpenAICompatibleTranscriptionProvider(config)

    assert secret not in repr(config)
    assert secret not in repr(provider)

    unconfigured = Settings(
        data_dir=tmp_path,
        transcription_provider="openai_compatible",
        transcription_api_key=None,
    )
    unconfigured_provider = OpenAICompatibleTranscriptionProvider(unconfigured)
    assert unconfigured_provider.ready() is False
