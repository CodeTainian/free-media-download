from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SUMMARY_PLATFORMS = frozenset({"youtube", "bilibili"})
_CAPTION_BUCKETS = (("subtitles", False), ("automatic_captions", True))
_IGNORED_LANGUAGES = frozenset({"danmaku", "live_chat", "comments"})
_SUPPORTED_CAPTION_EXTENSIONS = frozenset({"vtt", "srt"})
_LANGUAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_TIMING_RE = re.compile(
    r"^(?P<start>(?:\d{1,3}:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?)\s+-->\s+"
    r"(?P<end>(?:\d{1,3}:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?)(?:\s+.*)?$"
)
_TAG_RE = re.compile(r"<[^>]*>")
_SRT_STYLE_RE = re.compile(r"\{\\[^}]+}")
MAX_CAPTION_LANGUAGES = 64


@dataclass(frozen=True, slots=True)
class CaptionTrack:
    language: str
    automatic: bool

    @property
    def source_kind(self) -> Literal["manual_caption", "automatic_caption"]:
        return "automatic_caption" if self.automatic else "manual_caption"


class TranscriptSegment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    start: float
    end: float
    text: str
    speaker: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)

    @field_validator("id", "text")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped

    @field_validator("speaker")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @model_validator(mode="after")
    def validate_timing(self) -> "TranscriptSegment":
        if self.start < 0 or self.end <= self.start:
            raise ValueError("segment timing must be positive and increasing")
        return self


class TranscriptDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_url: str
    title: str
    platform: str
    duration: int | None
    language: str
    source_kind: Literal[
        "manual_caption", "automatic_caption", "audio_transcription"
    ]
    segments: tuple[TranscriptSegment, ...]
    detected_language: str | None = None
    requested_language: str | None = None
    provider: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    transcription_duration: float | None = Field(default=None, ge=0)
    audio_duration: float | None = Field(default=None, ge=0)

    @field_validator("source_url", "title", "platform", "language")
    @classmethod
    def strip_document_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped

    @field_validator("detected_language", "requested_language", "provider")
    @classmethod
    def strip_optional_document_text(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


def _valid_language(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    language = value.strip()
    if language.lower() in _IGNORED_LANGUAGES or not _LANGUAGE_RE.fullmatch(language):
        return None
    return language


def _has_caption_format(value: object) -> bool:
    if not isinstance(value, list):
        return False
    for candidate in value:
        if not isinstance(candidate, dict):
            continue
        extension = str(candidate.get("ext") or "").lower()
        if extension in _SUPPORTED_CAPTION_EXTENSIONS:
            return True
    return False


def discover_caption_tracks(info: dict[str, object]) -> tuple[CaptionTrack, ...]:
    """Return safe caption metadata without retaining signed subtitle URLs."""

    tracks: list[CaptionTrack] = []
    seen: set[tuple[str, bool]] = set()
    for bucket_name, automatic in _CAPTION_BUCKETS:
        bucket = info.get(bucket_name)
        if not isinstance(bucket, dict):
            continue
        for raw_language, formats in bucket.items():
            language = _valid_language(raw_language)
            key = (language.lower(), automatic) if language else None
            if not language or not _has_caption_format(formats) or key in seen:
                continue
            seen.add(key)
            tracks.append(CaptionTrack(language=language, automatic=automatic))
    return tuple(tracks)


def caption_languages(info: dict[str, object]) -> list[str]:
    original = _valid_language(info.get("language"))
    tracks = sorted(
        discover_caption_tracks(info),
        key=lambda track: (
            0
            if not track.automatic and _language_matches(track.language, "en")
            else 1
            if not track.automatic and original and _language_matches(track.language, original)
            else 2
            if not track.automatic
            else 3
            if _language_matches(track.language, "en")
            else 4
            if original and _language_matches(track.language, original)
            else 5,
            track.language.lower(),
        ),
    )
    languages: list[str] = []
    seen: set[str] = set()
    for track in tracks:
        normalized = track.language.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        languages.append(track.language)
        if len(languages) >= MAX_CAPTION_LANGUAGES:
            break
    return languages


def _language_matches(candidate: str, desired: str) -> bool:
    candidate_parts = candidate.lower().replace("_", "-").split("-")
    desired_parts = desired.lower().replace("_", "-").split("-")
    return candidate_parts == desired_parts or candidate_parts[0] == desired_parts[0]


def _first_matching(
    tracks: tuple[CaptionTrack, ...],
    languages: tuple[str, ...],
    *,
    automatic: bool,
    source_languages: tuple[str, ...] = (),
) -> CaptionTrack | None:
    for desired in languages:
        desired_normalized = desired.lower().replace("_", "-")
        desired_base = desired_normalized.split("-", 1)[0]
        ranked: list[tuple[int, int, CaptionTrack]] = []
        for index, track in enumerate(tracks):
            if track.automatic != automatic or not _language_matches(track.language, desired):
                continue
            candidate = track.language.lower().replace("_", "-")
            if candidate == desired_normalized:
                score = 0
            elif any(
                candidate
                in {
                    f"{desired_normalized}-{source.lower().replace('_', '-')}",
                    f"{desired_base}-{source.lower().replace('_', '-').split('-', 1)[0]}",
                }
                for source in source_languages
            ):
                score = 1
            elif candidate.startswith(f"{desired_normalized}-") or desired_normalized.startswith(
                f"{candidate}-"
            ):
                score = 2
            else:
                score = 3
            ranked.append((score, index, track))
        if ranked:
            return min(ranked, key=lambda item: (item[0], item[1]))[2]
    return None


def select_caption_track(
    info: dict[str, object], preferred_languages: tuple[str, ...] = ("en",)
) -> CaptionTrack | None:
    """Select English/manual first, then original/manual, then automatic equivalents."""

    tracks = discover_caption_tracks(info)
    if not tracks:
        return None

    preferred = tuple(
        language
        for raw_language in preferred_languages
        if (language := _valid_language(raw_language)) is not None
    )
    declared_original = _valid_language(info.get("language"))
    if declared_original:
        original = (declared_original,)
    else:
        first_manual = next((track.language for track in tracks if not track.automatic), None)
        original = (first_manual or tracks[0].language,)

    return (
        _first_matching(tracks, preferred, automatic=False)
        or _first_matching(tracks, original, automatic=False)
        or _first_matching(tracks, preferred, automatic=True, source_languages=original)
        or _first_matching(tracks, original, automatic=True, source_languages=original)
    )


def _parse_timestamp(value: str) -> float | None:
    parts = value.replace(",", ".").split(":")
    if len(parts) not in {2, 3}:
        return None
    try:
        if len(parts) == 2:
            hours = 0
            minutes, seconds = parts
        else:
            hours, minutes, seconds = parts
        result = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except ValueError:
        return None
    return result if result >= 0 else None


def _clean_cue(lines: list[str]) -> str:
    value = " ".join(lines)
    value = html.unescape(value)
    value = _TAG_RE.sub(" ", value)
    value = _SRT_STYLE_RE.sub(" ", value)
    return re.sub(r"\s+", " ", value.replace("\u200b", " ")).strip()


def normalize_transcript_segments(
    raw_segments: list[tuple[float, float, str]],
) -> tuple[TranscriptSegment, ...]:
    normalized: list[tuple[float, float, str]] = []
    for raw_start, raw_end, raw_text in sorted(raw_segments, key=lambda item: (item[0], item[1])):
        start = round(raw_start, 3)
        end = round(raw_end, 3)
        text = raw_text.strip()
        if not text or end <= start:
            continue

        if normalized:
            previous_start, previous_end, previous_text = normalized[-1]
            if text == previous_text and start <= previous_end + 0.1:
                normalized[-1] = (previous_start, max(previous_end, end), previous_text)
                continue
            if start < previous_end:
                if text.startswith(f"{previous_text} "):
                    text = text[len(previous_text) :].strip()
                elif previous_text.endswith(f" {text}") or previous_text == text:
                    continue
                start = previous_end
        if not text or end <= start:
            continue
        normalized.append((start, end, text))

    return tuple(
        TranscriptSegment(id=f"seg-{index:05d}", start=start, end=end, text=text)
        for index, (start, end, text) in enumerate(normalized, 1)
    )


def parse_subtitle_text(value: str) -> tuple[TranscriptSegment, ...]:
    """Parse VTT or SRT text into ordered, non-overlapping transcript segments."""

    lines = value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    raw_segments: list[tuple[float, float, str]] = []
    index = 0
    while index < len(lines):
        timing = _TIMING_RE.match(lines[index].strip().lstrip("\ufeff"))
        if not timing:
            index += 1
            continue
        start = _parse_timestamp(timing.group("start"))
        end = _parse_timestamp(timing.group("end"))
        index += 1
        cue_lines: list[str] = []
        while index < len(lines):
            line = lines[index].strip()
            if _TIMING_RE.match(line):
                break
            index += 1
            if not line:
                break
            cue_lines.append(line)
        text = _clean_cue(cue_lines)
        if start is not None and end is not None and text:
            raw_segments.append((start, end, text))
    return normalize_transcript_segments(raw_segments)


def parse_subtitle_file(path: Path) -> tuple[TranscriptSegment, ...]:
    if path.suffix.lower() not in {".vtt", ".srt"}:
        raise ValueError("Only VTT and SRT subtitle files are supported")
    return parse_subtitle_text(path.read_text(encoding="utf-8-sig", errors="replace"))
