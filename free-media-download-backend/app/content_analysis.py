from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable

from .analysis_models import (
    CanonicalAnalysisDraft,
    CanonicalContentAnalysis,
    Chapter,
    Claim,
    DraftGroundedText,
    Entity,
    GlossaryEntry,
    GroundedText,
    SuggestedQuestion,
    Topic,
)
from .analysis_provider import AnalysisError
from .transcripts import TranscriptDocument, TranscriptSegment


_UNSAFE_GENERATED_TEXT = re.compile(
    r"(?is)<\s*(script|iframe|style|object|embed)\b|javascript\s*:|on(?:error|load|click)\s*="
)


def resolve_output_language(requested: str, transcript: TranscriptDocument) -> str:
    if requested != "auto":
        return requested
    detected = (
        transcript.detected_language or transcript.language or ""
    ).lower()
    return "zh-CN" if detected.startswith("zh") else "en"


def transcript_sha256(transcript: TranscriptDocument) -> str:
    serialized = json.dumps(
        [
            [segment.id, segment.start, segment.end, segment.text]
            for segment in transcript.segments
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _unique_ids(items: Iterable[object], label: str) -> None:
    ids = [str(getattr(item, "id")) for item in items]
    if len(ids) != len(set(ids)):
        raise AnalysisError(
            "ANALYSIS_RESPONSE_INVALID",
            f"The structured analysis contains duplicate {label} IDs.",
            True,
        )


def _hydrate_text(
    value: DraftGroundedText,
    segment_map: dict[str, TranscriptSegment],
) -> GroundedText:
    ids = list(dict.fromkeys(value.evidence_segment_ids))
    if not ids or any(segment_id not in segment_map for segment_id in ids):
        raise AnalysisError(
            "INVALID_EVIDENCE",
            "The structured analysis referenced transcript evidence that does not exist.",
            True,
        )
    evidence = [segment_map[segment_id] for segment_id in ids]
    return GroundedText(
        text=value.text,
        evidence_segment_ids=ids,
        start_seconds=min(segment.start for segment in evidence),
        end_seconds=max(segment.end for segment in evidence),
    )


def _assert_safe_generated_text(value: object) -> None:
    if isinstance(value, str):
        if _UNSAFE_GENERATED_TEXT.search(value):
            raise AnalysisError(
                "UNSAFE_GENERATED_CONTENT",
                "The provider returned content that cannot be rendered safely.",
            )
        return
    if isinstance(value, dict):
        for item in value.values():
            _assert_safe_generated_text(item)
    elif isinstance(value, list):
        for item in value:
            _assert_safe_generated_text(item)


def hydrate_canonical_analysis(
    draft: CanonicalAnalysisDraft,
    transcript: TranscriptDocument,
) -> CanonicalContentAnalysis:
    segment_map = {segment.id: segment for segment in transcript.segments}
    _unique_ids(draft.topics, "topic")
    _unique_ids(draft.entities, "entity")
    _unique_ids(draft.claims, "claim")
    _unique_ids(draft.chapters, "chapter")
    _unique_ids(draft.glossary, "glossary")
    _unique_ids(draft.suggested_questions, "question")

    chapters: list[Chapter] = []
    ordered_drafts = sorted(draft.chapters, key=lambda chapter: chapter.start_seconds)
    for index, chapter in enumerate(ordered_drafts):
        if index and chapter.start_seconds < ordered_drafts[index - 1].end_seconds:
            raise AnalysisError(
                "CHAPTERS_OVERLAP",
                "The generated chapter timeline contains overlapping chapters.",
                True,
            )
        if transcript.duration and chapter.end_seconds > transcript.duration + 1:
            raise AnalysisError(
                "CHAPTER_RANGE_INVALID",
                "A generated chapter extends beyond the source duration.",
                True,
            )
        summary = _hydrate_text(chapter.summary, segment_map)
        key_points = [
            _hydrate_text(key_point, segment_map)
            for key_point in chapter.key_points
        ]
        ids = list(
            dict.fromkeys(
                [
                    *chapter.evidence_segment_ids,
                    *summary.evidence_segment_ids,
                    *(
                        evidence_id
                        for key_point in key_points
                        for evidence_id in key_point.evidence_segment_ids
                    ),
                ]
            )
        )
        if any(segment_id not in segment_map for segment_id in ids):
            raise AnalysisError(
                "INVALID_EVIDENCE",
                "A chapter referenced transcript evidence that does not exist.",
                True,
            )
        evidence_start = min(segment_map[item].start for item in ids)
        evidence_end = max(segment_map[item].end for item in ids)
        if (
            evidence_start < chapter.start_seconds - 0.5
            or evidence_end > chapter.end_seconds + 0.5
        ):
            raise AnalysisError(
                "CHAPTER_RANGE_INVALID",
                "A chapter does not contain its cited transcript evidence.",
                True,
            )
        chapters.append(
            Chapter(
                id=chapter.id,
                title=chapter.title,
                start_seconds=chapter.start_seconds,
                end_seconds=chapter.end_seconds,
                summary=summary,
                key_points=key_points,
                evidence_segment_ids=ids,
            )
        )
    if chapters:
        near_zero_limit = min(
            30.0,
            max(5.0, float(transcript.duration or chapters[-1].end_seconds) * 0.05),
        )
        if chapters[0].start_seconds > near_zero_limit:
            raise AnalysisError(
                "CHAPTER_RANGE_INVALID",
                "The first generated chapter does not begin near the start of the source.",
                True,
            )

    result = CanonicalContentAnalysis(
        concise_summary=_hydrate_text(draft.concise_summary, segment_map),
        detailed_summary=_hydrate_text(draft.detailed_summary, segment_map),
        topics=[
            Topic(
                id=item.id,
                label=item.label,
                summary=_hydrate_text(item.summary, segment_map),
            )
            for item in draft.topics
        ],
        entities=[
            Entity(
                id=item.id,
                name=item.name,
                category=item.category,
                description=_hydrate_text(item.description, segment_map),
            )
            for item in draft.entities
        ],
        claims=[
            Claim(
                id=item.id,
                statement=_hydrate_text(item.statement, segment_map),
                importance=item.importance,
            )
            for item in draft.claims
        ],
        chapters=chapters,
        key_points=[_hydrate_text(item, segment_map) for item in draft.key_points],
        conclusions=[
            _hydrate_text(item, segment_map) for item in draft.conclusions
        ],
        glossary=[
            GlossaryEntry(
                id=item.id,
                term=item.term,
                definition=_hydrate_text(item.definition, segment_map),
            )
            for item in draft.glossary
        ],
        suggested_questions=[
            SuggestedQuestion(
                id=item.id,
                question=item.question,
                reason=_hydrate_text(item.reason, segment_map),
            )
            for item in draft.suggested_questions
        ],
        evidence_segment_ids=list(dict.fromkeys(draft.evidence_segment_ids)),
    )
    if any(
        segment_id not in segment_map
        for segment_id in result.evidence_segment_ids
    ):
        raise AnalysisError(
            "INVALID_EVIDENCE",
            "The canonical analysis referenced transcript evidence that does not exist.",
            True,
        )
    _assert_safe_generated_text(result.model_dump(mode="json"))
    return result
