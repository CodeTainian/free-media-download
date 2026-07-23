from __future__ import annotations

from pydantic import Field

from .analysis_models import StrictModel
from .transcripts import TranscriptDocument, TranscriptSegment


class SemanticUnit(StrictModel):
    id: str
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    segment_ids: list[str] = Field(min_length=1)
    content: str = Field(min_length=1)


def segment_transcript(
    transcript: TranscriptDocument,
    *,
    target_characters: int,
) -> tuple[SemanticUnit, ...]:
    """Create stable semantic windows at pauses without altering evidence IDs."""

    units: list[SemanticUnit] = []
    current: list[TranscriptSegment] = []
    characters = 0

    def flush() -> None:
        nonlocal current, characters
        if not current:
            return
        index = len(units) + 1
        units.append(
            SemanticUnit(
                id=f"unit-{index:04d}",
                start_seconds=current[0].start,
                end_seconds=current[-1].end,
                segment_ids=[segment.id for segment in current],
                content="\n".join(
                    f"[{segment.id} {segment.start:.3f}-{segment.end:.3f}] {segment.text}"
                    for segment in current
                ),
            )
        )
        current = []
        characters = 0

    previous: TranscriptSegment | None = None
    for segment in transcript.segments:
        gap = segment.start - previous.end if previous else 0
        projected = characters + len(segment.text) + 48
        if current and (
            projected > target_characters
            or (gap >= 8 and characters >= target_characters // 3)
        ):
            flush()
        current.append(segment)
        characters += len(segment.text) + 48
        previous = segment
    flush()
    if not units:
        raise ValueError("Transcript does not contain semantic units")
    return tuple(units)


def batch_semantic_units(
    units: tuple[SemanticUnit, ...],
    *,
    max_characters: int,
) -> tuple[tuple[SemanticUnit, ...], ...]:
    batches: list[tuple[SemanticUnit, ...]] = []
    current: list[SemanticUnit] = []
    characters = 0
    for unit in units:
        if current and characters + len(unit.content) > max_characters:
            batches.append(tuple(current))
            current = []
            characters = 0
        current.append(unit)
        characters += len(unit.content)
    if current:
        batches.append(tuple(current))
    return tuple(batches)
