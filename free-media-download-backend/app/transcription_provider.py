from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .config import Settings


ProgressCallback = Callable[[float], Awaitable[None]]


class TranscriptionError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class TranscriptionSegment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    speaker: str | None = None

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("segment text must not be empty")
        return stripped

    @model_validator(mode="after")
    def validate_timing(self) -> "TranscriptionSegment":
        if self.end <= self.start:
            raise ValueError("segment end must be after start")
        return self


class TranscriptionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    language: str | None = None
    duration: float | None = Field(default=None, ge=0)
    segments: tuple[TranscriptionSegment, ...]
    provider: str
    model: str


class _ProviderSegment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    start: float
    end: float
    text: str


class _ProviderResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    language: str | None = None
    duration: float | None = Field(default=None, ge=0)
    segments: list[_ProviderSegment]


class TranscriptionProvider(Protocol):
    def ready(self) -> bool: ...

    async def transcribe(
        self,
        audio_path: Path,
        *,
        requested_language: str | None,
        prompt: str | None,
        cancel_event: asyncio.Event,
        on_progress: ProgressCallback,
    ) -> TranscriptionResult: ...

    async def close(self) -> None: ...


class OpenAICompatibleTranscriptionProvider:
    def __init__(
        self,
        config: Settings,
        client: httpx.AsyncClient | None = None,
    ):
        self.config = config
        self._client = client
        self._owns_client = client is None

    def ready(self) -> bool:
        return self.config.transcription_configured

    def _request_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.transcription_timeout_seconds)
            )
        return self._client

    async def transcribe(
        self,
        audio_path: Path,
        *,
        requested_language: str | None,
        prompt: str | None,
        cancel_event: asyncio.Event,
        on_progress: ProgressCallback,
    ) -> TranscriptionResult:
        if not self.ready():
            raise TranscriptionError(
                "TRANSCRIPTION_NOT_CONFIGURED",
                "Audio transcription is not configured on this server.",
            )
        if cancel_event.is_set():
            raise TranscriptionError("CANCELLED", "The summary job was cancelled.")

        data = {
            "model": self.config.transcription_model,
            "response_format": "verbose_json",
            "timestamp_granularities[]": "segment",
        }
        if requested_language:
            data["language"] = requested_language
        if prompt:
            data["prompt"] = prompt[-1_000:]

        try:
            with audio_path.open("rb") as audio:
                request_task = asyncio.create_task(
                    self._request_client().post(
                        f"{self.config.transcription_base_url}/audio/transcriptions",
                        headers={
                            "Authorization": f"Bearer {self.config.transcription_api_key}"
                        },
                        data=data,
                        files={"file": (audio_path.name, audio, "audio/wav")},
                    )
                )
                cancel_task = asyncio.create_task(cancel_event.wait())
                try:
                    done, _ = await asyncio.wait(
                        {request_task, cancel_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if cancel_task in done and cancel_event.is_set():
                        request_task.cancel()
                        await asyncio.gather(request_task, return_exceptions=True)
                        raise TranscriptionError(
                            "CANCELLED", "The summary job was cancelled."
                        )
                    response = await request_task
                finally:
                    cancel_task.cancel()
                    await asyncio.gather(cancel_task, return_exceptions=True)
        except TranscriptionError:
            raise
        except httpx.TimeoutException as exc:
            raise TranscriptionError(
                "TRANSCRIPTION_TIMEOUT",
                "Audio transcription took too long.",
                True,
            ) from exc
        except httpx.TransportError as exc:
            raise TranscriptionError(
                "TRANSCRIPTION_PROVIDER_UNAVAILABLE",
                "The transcription provider could not be reached.",
                True,
            ) from exc
        except OSError as exc:
            raise TranscriptionError(
                "TRANSCRIPTION_FAILED",
                "The temporary audio could not be prepared for transcription.",
            ) from exc

        if response.status_code == 429:
            raise TranscriptionError(
                "TRANSCRIPTION_RATE_LIMITED",
                "The transcription provider is temporarily rate limiting requests.",
                True,
            )
        if response.status_code in {401, 403}:
            raise TranscriptionError(
                "TRANSCRIPTION_PROVIDER_UNAVAILABLE",
                "The transcription provider configuration was rejected.",
            )
        if response.status_code >= 500:
            raise TranscriptionError(
                "TRANSCRIPTION_PROVIDER_UNAVAILABLE",
                "The transcription provider is temporarily unavailable.",
                True,
            )
        if response.status_code >= 400:
            raise TranscriptionError(
                "TRANSCRIPTION_FAILED",
                "The transcription provider rejected the audio request.",
            )

        try:
            payload = _ProviderResponse.model_validate(response.json())
            segments = tuple(
                TranscriptionSegment(start=item.start, end=item.end, text=item.text)
                for item in payload.segments
                if item.text.strip() and item.end > item.start >= 0
            )
        except (ValueError, ValidationError, TypeError) as exc:
            raise TranscriptionError(
                "TRANSCRIPTION_FAILED",
                "The transcription provider returned an unreadable response.",
                True,
            ) from exc
        if not segments:
            raise TranscriptionError(
                "TRANSCRIPT_EMPTY",
                "The transcription provider did not detect any speech.",
            )
        await on_progress(1)
        return TranscriptionResult(
            language=payload.language,
            duration=payload.duration,
            segments=segments,
            provider="openai_compatible",
            model=self.config.transcription_model,
        )

    async def close(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None


def build_transcription_provider(
    config: Settings,
    *,
    client: httpx.AsyncClient | None = None,
) -> TranscriptionProvider:
    return OpenAICompatibleTranscriptionProvider(config, client=client)
