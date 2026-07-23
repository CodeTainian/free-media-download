from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, ClassVar, Literal

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from .models import ErrorBody


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class AnalysisStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AnalysisStage(StrEnum):
    QUEUED = "queued"
    PROBING = "probing"
    ACQUIRING_TRANSCRIPT = "acquiring_transcript"
    SEMANTIC_SEGMENTATION = "semantic_segmentation"
    CANONICAL_ANALYSIS = "canonical_analysis"
    GENERATING_ARTIFACTS = "generating_artifacts"
    VALIDATING = "validating"
    FINALIZING = "finalizing"
    COMPLETED = "completed"


class ArtifactKind(StrEnum):
    SUMMARY = "summary"
    CHAPTERS = "chapters"
    MIND_MAP = "mind_map"
    VISUAL_STORY = "visual_story"
    DYNAMIC_WEBSITE = "dynamic_website"
    INTERACTIVE_GUIDE = "interactive_guide"
    TRANSCRIPT = "transcript"


class ArtifactStatus(StrEnum):
    NOT_STARTED = "not_started"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AnalysisDetail(StrEnum):
    CONCISE = "concise"
    BALANCED = "balanced"
    DETAILED = "detailed"


class AnalysisLanguage(StrEnum):
    AUTO = "auto"
    ENGLISH = "en"
    SIMPLIFIED_CHINESE = "zh-CN"


class CreateAnalysisRequest(StrictModel):
    url: str = Field(min_length=8, max_length=4096)
    title: str | None = Field(default=None, max_length=240)
    output_language: AnalysisLanguage = AnalysisLanguage.AUTO
    detail: AnalysisDetail = AnalysisDetail.BALANCED
    rights_confirmed: bool

    @field_validator("url")
    @classmethod
    def strip_url(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_rights(self) -> "CreateAnalysisRequest":
        if not self.rights_confirmed:
            raise ValueError("rights confirmation is required")
        return self


class RequestArtifactRequest(StrictModel):
    kind: Literal[
        ArtifactKind.MIND_MAP,
        ArtifactKind.VISUAL_STORY,
        ArtifactKind.DYNAMIC_WEBSITE,
        ArtifactKind.INTERACTIVE_GUIDE,
    ]


class AnalysisSource(StrictModel):
    source_url: AnyHttpUrl
    title: str = Field(min_length=1, max_length=240)
    platform: str = Field(min_length=1, max_length=80)
    duration_seconds: float | None = Field(default=None, gt=0)
    transcript_source: Literal[
        "manual_caption", "automatic_caption", "audio_transcription"
    ] | None = None
    transcript_language: str | None = None


class DraftGroundedText(StrictModel):
    text: str = Field(min_length=1, max_length=12_000)
    evidence_segment_ids: list[str] = Field(min_length=1, max_length=24)


class GroundedText(DraftGroundedText):
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> "GroundedText":
        if self.end_seconds <= self.start_seconds:
            raise ValueError("end_seconds must be greater than start_seconds")
        return self


class DraftTopic(StrictModel):
    id: str = Field(pattern=r"^topic-[a-z0-9-]{1,48}$")
    label: str = Field(min_length=1, max_length=120)
    summary: DraftGroundedText


class Topic(StrictModel):
    id: str
    label: str
    summary: GroundedText


class DraftEntity(StrictModel):
    id: str = Field(pattern=r"^entity-[a-z0-9-]{1,48}$")
    name: str = Field(min_length=1, max_length=160)
    category: str = Field(min_length=1, max_length=80)
    description: DraftGroundedText


class Entity(StrictModel):
    id: str
    name: str
    category: str
    description: GroundedText


class DraftClaim(StrictModel):
    id: str = Field(pattern=r"^claim-[a-z0-9-]{1,48}$")
    statement: DraftGroundedText
    importance: Literal["low", "medium", "high"] = "medium"


class Claim(StrictModel):
    id: str
    statement: GroundedText
    importance: Literal["low", "medium", "high"]


class DraftChapter(StrictModel):
    id: str = Field(pattern=r"^chapter-[a-z0-9-]{1,48}$")
    title: str = Field(min_length=1, max_length=120)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    summary: DraftGroundedText
    key_points: list[DraftGroundedText] = Field(min_length=1, max_length=12)
    evidence_segment_ids: list[str] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def validate_range(self) -> "DraftChapter":
        if self.end_seconds <= self.start_seconds:
            raise ValueError("chapter end must be after start")
        return self


class Chapter(StrictModel):
    id: str
    title: str
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    summary: GroundedText
    key_points: list[GroundedText]
    evidence_segment_ids: list[str]


class DraftGlossaryEntry(StrictModel):
    id: str = Field(pattern=r"^term-[a-z0-9-]{1,48}$")
    term: str = Field(min_length=1, max_length=160)
    definition: DraftGroundedText


class GlossaryEntry(StrictModel):
    id: str
    term: str
    definition: GroundedText


class DraftSuggestedQuestion(StrictModel):
    id: str = Field(pattern=r"^question-[a-z0-9-]{1,48}$")
    question: str = Field(min_length=1, max_length=500)
    reason: DraftGroundedText


class SuggestedQuestion(StrictModel):
    id: str
    question: str
    reason: GroundedText


class CanonicalAnalysisDraft(StrictModel):
    concise_summary: DraftGroundedText
    detailed_summary: DraftGroundedText
    topics: list[DraftTopic] = Field(min_length=1, max_length=30)
    entities: list[DraftEntity] = Field(default_factory=list, max_length=40)
    claims: list[DraftClaim] = Field(default_factory=list, max_length=40)
    chapters: list[DraftChapter] = Field(min_length=1, max_length=40)
    key_points: list[DraftGroundedText] = Field(min_length=1, max_length=40)
    conclusions: list[DraftGroundedText] = Field(default_factory=list, max_length=20)
    glossary: list[DraftGlossaryEntry] = Field(default_factory=list, max_length=40)
    suggested_questions: list[DraftSuggestedQuestion] = Field(
        default_factory=list, max_length=30
    )
    evidence_segment_ids: list[str] = Field(min_length=1, max_length=512)


class CanonicalContentAnalysis(StrictModel):
    concise_summary: GroundedText
    detailed_summary: GroundedText
    topics: list[Topic]
    entities: list[Entity]
    claims: list[Claim]
    chapters: list[Chapter]
    key_points: list[GroundedText]
    conclusions: list[GroundedText]
    glossary: list[GlossaryEntry]
    suggested_questions: list[SuggestedQuestion]
    evidence_segment_ids: list[str]


class SummaryContent(StrictModel):
    detail: AnalysisDetail
    output_language: str
    tldr: GroundedText
    overview: GroundedText
    key_takeaways: list[GroundedText]
    important_facts: list[Claim]
    conclusions: list[GroundedText]
    suggested_questions: list[SuggestedQuestion]


class MindMapNodeType(StrEnum):
    ROOT = "root"
    TOPIC = "topic"
    ENTITY = "entity"
    CLAIM = "claim"
    TERM = "term"


class MindMapNode(StrictModel):
    id: str = Field(pattern=r"^node-[a-z0-9-]{1,64}$")
    label: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=2_000)
    type: MindMapNodeType
    timestamp_seconds: float = Field(ge=0)
    evidence_segment_ids: list[str] = Field(min_length=1, max_length=24)
    children: list[str] = Field(default_factory=list, max_length=30)


class MindMapEdge(StrictModel):
    id: str = Field(pattern=r"^edge-[a-z0-9-]{1,64}$")
    source_id: str
    target_id: str
    label: str = Field(default="contains", min_length=1, max_length=80)


class MindMap(StrictModel):
    MAX_NODES: ClassVar[int] = 80
    MAX_DEPTH: ClassVar[int] = 5

    root_id: str
    nodes: list[MindMapNode] = Field(min_length=1, max_length=MAX_NODES)
    edges: list[MindMapEdge] = Field(default_factory=list, max_length=160)

    @model_validator(mode="after")
    def validate_graph(self) -> "MindMap":
        node_ids = [node.id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("mind map node IDs must be unique")
        nodes = {node.id: node for node in self.nodes}
        if self.root_id not in nodes:
            raise ValueError("mind map root_id does not exist")
        adjacency: dict[str, set[str]] = {
            node.id: set(node.children) for node in self.nodes
        }
        for edge in self.edges:
            if edge.source_id not in nodes or edge.target_id not in nodes:
                raise ValueError("mind map edge references an unknown node")
            adjacency[edge.source_id].add(edge.target_id)
        if any(child not in nodes for children in adjacency.values() for child in children):
            raise ValueError("mind map child references an unknown node")

        visited: set[str] = set()
        active: set[str] = set()

        def visit(node_id: str, depth: int) -> None:
            if depth > self.MAX_DEPTH:
                raise ValueError("mind map exceeds maximum depth")
            if node_id in active:
                raise ValueError("mind map contains a cycle")
            if node_id in visited:
                return
            active.add(node_id)
            for child in adjacency[node_id]:
                visit(child, depth + 1)
            active.remove(node_id)
            visited.add(node_id)

        visit(self.root_id, 1)
        if visited != set(nodes):
            raise ValueError("mind map contains unreachable nodes")
        return self


class StoryFrame(StrictModel):
    id: str = Field(pattern=r"^frame-[0-9]{2}$")
    timestamp_seconds: float = Field(ge=0)
    image_url: str | None = None
    title: str = Field(min_length=1, max_length=160)
    caption: str = Field(min_length=1, max_length=600)
    narrative: str = Field(min_length=1, max_length=3_000)
    related_chapter_id: str
    evidence_segment_ids: list[str] = Field(min_length=1, max_length=24)

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("/api/v1/analyses/"):
            raise ValueError("story image URL must be an analysis-owned API path")
        return value


class VisualStory(StrictModel):
    title: str = Field(min_length=1, max_length=240)
    frames: list[StoryFrame] = Field(min_length=1, max_length=12)
    warnings: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validate_frames(self) -> "VisualStory":
        timestamps = [frame.timestamp_seconds for frame in self.frames]
        if timestamps != sorted(timestamps):
            raise ValueError("story frames must be time ordered")
        if len({frame.id for frame in self.frames}) != len(self.frames):
            raise ValueError("story frame IDs must be unique")
        return self


class WebsiteTheme(StrEnum):
    EDITORIAL = "editorial"
    LEARNING = "learning"
    DOCUMENTARY = "documentary"
    PRODUCT_BRIEF = "product_brief"


class WebsiteHero(StrictModel):
    eyebrow: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=240)
    subtitle: str = Field(min_length=1, max_length=1_000)
    evidence_segment_ids: list[str] = Field(min_length=1, max_length=24)


class WebsiteSection(StrictModel):
    id: str = Field(pattern=r"^section-[a-z0-9-]{1,48}$")
    kind: Literal[
        "overview",
        "key_points",
        "chapters",
        "timeline",
        "glossary",
        "questions",
    ]
    title: str = Field(min_length=1, max_length=160)
    item_ids: list[str] = Field(default_factory=list, max_length=80)


class WebsiteTimelineItem(StrictModel):
    id: str
    timestamp_seconds: float = Field(ge=0)
    title: str
    text: str
    evidence_segment_ids: list[str] = Field(min_length=1, max_length=24)


class WebsiteSource(StrictModel):
    label: str
    url: AnyHttpUrl


class WebsiteManifest(StrictModel):
    language: Literal["en", "zh-CN"]
    title: str = Field(min_length=1, max_length=240)
    subtitle: str = Field(min_length=1, max_length=1_000)
    theme: WebsiteTheme
    hero: WebsiteHero
    sections: list[WebsiteSection] = Field(min_length=1, max_length=12)
    chapters: list[Chapter]
    quotes: list[GroundedText] = Field(default_factory=list, max_length=12)
    timeline: list[WebsiteTimelineItem] = Field(default_factory=list, max_length=40)
    glossary: list[GlossaryEntry] = Field(default_factory=list, max_length=40)
    callouts: list[GroundedText] = Field(default_factory=list, max_length=20)
    sources: list[WebsiteSource] = Field(min_length=1, max_length=8)


class GuideActionKind(StrEnum):
    REVIEW = "review"
    REFLECT = "reflect"
    COMPARE = "compare"
    VERIFY = "verify"


class GuideAction(StrictModel):
    kind: GuideActionKind
    instruction: str = Field(min_length=1, max_length=500)


class GuideCheckpoint(StrictModel):
    prompt: str = Field(min_length=1, max_length=500)
    success_criteria: str = Field(min_length=1, max_length=800)


class GuideStep(StrictModel):
    id: str = Field(pattern=r"^step-[0-9]{2}$")
    title: str = Field(min_length=1, max_length=160)
    explanation: GroundedText
    timestamp_seconds: float = Field(ge=0)
    action: GuideAction
    checkpoint: GuideCheckpoint
    evidence_segment_ids: list[str] = Field(min_length=1, max_length=24)


class GuideQuizItem(StrictModel):
    id: str = Field(pattern=r"^quiz-[0-9]{2}$")
    question: str = Field(min_length=1, max_length=500)
    choices: list[str] = Field(min_length=2, max_length=6)
    correct_index: int = Field(ge=0)
    explanation: GroundedText

    @model_validator(mode="after")
    def validate_answer(self) -> "GuideQuizItem":
        if self.correct_index >= len(self.choices):
            raise ValueError("quiz answer is outside the choices")
        return self


class InteractiveGuide(StrictModel):
    title: str = Field(min_length=1, max_length=240)
    audience: str = Field(min_length=1, max_length=240)
    learning_objectives: list[GroundedText] = Field(min_length=1, max_length=12)
    prerequisites: list[str] = Field(default_factory=list, max_length=12)
    estimated_time_minutes: int = Field(ge=1, le=600)
    steps: list[GuideStep] = Field(min_length=1, max_length=30)
    checkpoints: list[GuideCheckpoint] = Field(default_factory=list, max_length=30)
    quiz: list[GuideQuizItem] = Field(default_factory=list, max_length=20)
    glossary: list[GlossaryEntry] = Field(default_factory=list, max_length=40)
    next_actions: list[str] = Field(default_factory=list, max_length=12)
    safety_notice: str | None = Field(default=None, max_length=1_000)


class GenerationMetadata(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    output_language: str
    detail: AnalysisDetail
    transcript_sha256: str
    semantic_unit_count: int = Field(ge=1)
    provider: str
    model: str
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime


class AnalysisResult(StrictModel):
    id: str
    source: AnalysisSource
    canonical_analysis: CanonicalContentAnalysis
    generation_metadata: GenerationMetadata


class ArtifactView(StrictModel):
    kind: ArtifactKind
    status: ArtifactStatus
    progress: float = Field(default=0, ge=0, le=100)
    error: ErrorBody | None = None
    generated_at: datetime | None = None


class AnalysisSnapshot(StrictModel):
    id: str
    status: AnalysisStatus
    stage: AnalysisStage
    progress: float = Field(ge=0, le=100)
    source: AnalysisSource | None = None
    output_language: str
    detail: AnalysisDetail
    artifacts: dict[ArtifactKind, ArtifactView]
    error: ErrorBody | None = None
    created_at: datetime
    expires_at: datetime | None = None


class CreateAnalysisResponse(StrictModel):
    analysis: AnalysisSnapshot
    events_url: str


class AnalysisEvent(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    sequence: int = Field(ge=1)
    event: str
    analysis_id: str
    emitted_at: datetime
    stage: AnalysisStage
    overall_progress: float = Field(ge=0, le=100)
    artifact: ArtifactView | None = None
    error: ErrorBody | None = None
