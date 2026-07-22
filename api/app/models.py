from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


class OutputKind(StrEnum):
    VIDEO = "video"
    AUDIO = "audio"
    ORIGINAL = "original"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ItemStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ErrorBody(BaseModel):
    code: str
    message: str
    retryable: bool = False
    itemIndex: int | None = None


class Preset(BaseModel):
    id: str
    label: str
    detail: str
    kind: OutputKind
    extension: str
    height: int | None = None


class MediaItem(BaseModel):
    source_url: str
    title: str
    platform: str
    duration: int | None = None
    thumbnail: str | None = None
    uploader: str | None = None
    is_playlist_item: bool = False
    presets: list[Preset]


class ProbeRequest(BaseModel):
    url: str = Field(min_length=8, max_length=4096)

    @field_validator("url")
    @classmethod
    def strip_url(cls, value: str) -> str:
        return value.strip()


class ProbeResponse(BaseModel):
    items: list[MediaItem]
    truncated: bool = False


class CreateJobItem(BaseModel):
    url: str = Field(min_length=8, max_length=4096)
    preset_id: str = Field(pattern=r"^(best|mp3|original|mp4-(360|480|720|1080|1440|2160))$")
    title: str | None = Field(default=None, max_length=240)

    @field_validator("url")
    @classmethod
    def strip_url(cls, value: str) -> str:
        return value.strip()


class CreateJobRequest(BaseModel):
    items: list[CreateJobItem] = Field(min_length=1, max_length=10)
    bundle: bool = True


class JobItemView(BaseModel):
    id: str
    title: str
    status: ItemStatus
    progress: float = 0
    speed: str | None = None
    eta: int | None = None
    filename: str | None = None
    download_url: str | None = None
    error: ErrorBody | None = None


class JobView(BaseModel):
    id: str
    status: JobStatus
    created_at: str
    expires_at: str | None = None
    items: list[JobItemView]
    bundle_url: str | None = None
    bundle_ready: bool = False


class CreateJobResponse(BaseModel):
    job: JobView
    events_url: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    api: bool
    yt_dlp: bool
    ffmpeg: bool
    javascript_runtime: bool
    yt_dlp_version: str | None = None
