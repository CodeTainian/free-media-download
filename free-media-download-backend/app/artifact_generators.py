from __future__ import annotations

import re
from collections import defaultdict

from .analysis_models import (
    AnalysisDetail,
    AnalysisSource,
    CanonicalContentAnalysis,
    GuideAction,
    GuideActionKind,
    GuideCheckpoint,
    GuideQuizItem,
    GuideStep,
    InteractiveGuide,
    MindMap,
    MindMapEdge,
    MindMapNode,
    MindMapNodeType,
    StoryFrame,
    SummaryContent,
    VisualStory,
    WebsiteHero,
    WebsiteManifest,
    WebsiteSection,
    WebsiteSource,
    WebsiteTheme,
    WebsiteTimelineItem,
)


_HIGH_RISK = re.compile(
    r"(?i)\b(bomb|explosive|weapon|poison|overdose|self[- ]?harm|suicide|"
    r"malware|ransomware|credential theft|炸弹|爆炸物|武器|投毒|自残|自杀|勒索软件)\b"
)


def build_summary(
    canonical: CanonicalContentAnalysis,
    *,
    detail: AnalysisDetail,
    output_language: str,
) -> SummaryContent:
    limit = {
        AnalysisDetail.CONCISE: 5,
        AnalysisDetail.BALANCED: 12,
        AnalysisDetail.DETAILED: 30,
    }[detail]
    overview = (
        canonical.concise_summary
        if detail == AnalysisDetail.CONCISE
        else canonical.detailed_summary
    )
    return SummaryContent(
        detail=detail,
        output_language=output_language,
        tldr=canonical.concise_summary,
        overview=overview,
        key_takeaways=canonical.key_points[:limit],
        important_facts=canonical.claims[:limit],
        conclusions=canonical.conclusions[:limit],
        suggested_questions=canonical.suggested_questions[:limit],
    )


def build_mind_map(
    source: AnalysisSource,
    canonical: CanonicalContentAnalysis,
    *,
    max_nodes: int,
) -> MindMap:
    max_nodes = max(10, min(80, max_nodes))
    root_id = "node-root"
    root_evidence = canonical.concise_summary.evidence_segment_ids
    nodes: list[MindMapNode] = [
        MindMapNode(
            id=root_id,
            label=source.title,
            description=canonical.concise_summary.text,
            type=MindMapNodeType.ROOT,
            timestamp_seconds=canonical.concise_summary.start_seconds,
            evidence_segment_ids=root_evidence,
            children=[],
        )
    ]
    edges: list[MindMapEdge] = []
    topic_children: dict[str, list[str]] = defaultdict(list)
    topic_nodes: list[MindMapNode] = []
    for topic in canonical.topics:
        if len(nodes) + len(topic_nodes) >= max_nodes:
            break
        node_id = f"node-{topic.id}"
        topic_nodes.append(
            MindMapNode(
                id=node_id,
                label=topic.label,
                description=topic.summary.text,
                type=MindMapNodeType.TOPIC,
                timestamp_seconds=topic.summary.start_seconds,
                evidence_segment_ids=topic.summary.evidence_segment_ids,
                children=[],
            )
        )
        edges.append(
            MindMapEdge(
                id=f"edge-root-{len(topic_nodes):02d}",
                source_id=root_id,
                target_id=node_id,
                label="theme",
            )
        )
    nodes.extend(topic_nodes)
    root_children = [node.id for node in topic_nodes]
    nodes[0] = nodes[0].model_copy(update={"children": root_children})

    candidates: list[tuple[MindMapNodeType, str, str, object]] = []
    candidates.extend(
        (MindMapNodeType.CLAIM, claim.id, claim.statement.text, claim.statement)
        for claim in canonical.claims
    )
    candidates.extend(
        (
            MindMapNodeType.ENTITY,
            entity.id,
            f"{entity.name} · {entity.category}",
            entity.description,
        )
        for entity in canonical.entities
    )
    candidates.extend(
        (
            MindMapNodeType.TERM,
            item.id,
            item.term,
            item.definition,
        )
        for item in canonical.glossary
    )
    for kind, original_id, label, grounded in candidates:
        if len(nodes) >= max_nodes or not topic_nodes:
            break
        evidence_ids = set(grounded.evidence_segment_ids)
        parent = max(
            topic_nodes,
            key=lambda topic: len(
                evidence_ids.intersection(topic.evidence_segment_ids)
            ),
        )
        node_id = f"node-{original_id}"
        nodes.append(
            MindMapNode(
                id=node_id,
                label=label[:120],
                description=grounded.text,
                type=kind,
                timestamp_seconds=grounded.start_seconds,
                evidence_segment_ids=grounded.evidence_segment_ids,
                children=[],
            )
        )
        topic_children[parent.id].append(node_id)
        edges.append(
            MindMapEdge(
                id=f"edge-detail-{len(nodes):03d}",
                source_id=parent.id,
                target_id=node_id,
                label="supports",
            )
        )
    nodes = [
        node.model_copy(update={"children": topic_children.get(node.id, node.children)})
        for node in nodes
    ]
    return MindMap(root_id=root_id, nodes=nodes, edges=edges)


def _story_candidates(canonical: CanonicalContentAnalysis):
    for chapter in canonical.chapters:
        yield (
            chapter.start_seconds,
            chapter.id,
            chapter.title,
            chapter.summary.text,
            chapter.summary,
        )
        for point in chapter.key_points:
            yield (
                point.start_seconds,
                chapter.id,
                chapter.title,
                point.text,
                point,
            )
    for topic in canonical.topics:
        chapter = min(
            canonical.chapters,
            key=lambda item: abs(item.start_seconds - topic.summary.start_seconds),
        )
        yield (
            topic.summary.start_seconds,
            chapter.id,
            topic.label,
            topic.summary.text,
            topic.summary,
        )
    for index, point in enumerate(canonical.key_points, 1):
        chapter = min(
            canonical.chapters,
            key=lambda item: abs(item.start_seconds - point.start_seconds),
        )
        yield (
            point.start_seconds,
            chapter.id,
            chapter.title,
            point.text,
            point,
        )
    for claim in canonical.claims:
        chapter = min(
            canonical.chapters,
            key=lambda item: abs(item.start_seconds - claim.statement.start_seconds),
        )
        yield (
            claim.statement.start_seconds,
            chapter.id,
            chapter.title,
            claim.statement.text,
            claim.statement,
        )


def build_visual_story(
    source: AnalysisSource,
    canonical: CanonicalContentAnalysis,
    *,
    frame_limit: int,
) -> VisualStory:
    candidates = sorted(_story_candidates(canonical), key=lambda item: item[0])
    deduplicated: list[tuple] = []
    seen: set[tuple[int, str]] = set()
    for candidate in candidates:
        key = (round(candidate[0]), re.sub(r"\s+", " ", candidate[3]).lower()[:120])
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(candidate)
    candidates = deduplicated
    selected: list[tuple] = []
    for candidate in candidates:
        if selected and candidate[0] - selected[-1][0] < 4:
            continue
        selected.append(candidate)
        if len(selected) >= frame_limit:
            break
    minimum = min(6, frame_limit, len(candidates))
    if len(selected) < minimum:
        selected_keys = {
            (candidate[0], candidate[3])
            for candidate in selected
        }
        remaining = [
            candidate
            for candidate in candidates
            if (candidate[0], candidate[3]) not in selected_keys
        ]
        for candidate in remaining:
            selected.append(candidate)
            if len(selected) >= minimum:
                break
        selected.sort(key=lambda item: item[0])
    if not selected and canonical.chapters:
        chapter = canonical.chapters[0]
        selected.append(
            (
                chapter.start_seconds,
                chapter.id,
                chapter.title,
                chapter.summary.text,
                chapter.summary,
            )
        )
    frames = [
        StoryFrame(
            id=f"frame-{index:02d}",
            timestamp_seconds=timestamp,
            image_url=None,
            title=title,
            caption=grounded.text[:600],
            narrative=narrative,
            related_chapter_id=chapter_id,
            evidence_segment_ids=grounded.evidence_segment_ids,
        )
        for index, (timestamp, chapter_id, title, narrative, grounded) in enumerate(
            selected, 1
        )
    ]
    return VisualStory(title=source.title, frames=frames)


def build_website_manifest(
    source: AnalysisSource,
    canonical: CanonicalContentAnalysis,
    *,
    output_language: str,
) -> WebsiteManifest:
    labels = (
        {
            "overview": "概览",
            "key_points": "关键要点",
            "chapters": "章节",
            "glossary": "术语表",
            "questions": "值得继续探索的问题",
        }
        if output_language == "zh-CN"
        else {
            "overview": "Overview",
            "key_points": "Key points",
            "chapters": "Chapters",
            "glossary": "Glossary",
            "questions": "Questions to explore",
        }
    )
    sections = [
        WebsiteSection(
            id="section-overview",
            kind="overview",
            title=labels["overview"],
            item_ids=["concise_summary", "detailed_summary"],
        ),
        WebsiteSection(
            id="section-key-points",
            kind="key_points",
            title=labels["key_points"],
            item_ids=[f"key-point-{index:02d}" for index, _ in enumerate(canonical.key_points, 1)],
        ),
        WebsiteSection(
            id="section-chapters",
            kind="chapters",
            title=labels["chapters"],
            item_ids=[chapter.id for chapter in canonical.chapters],
        ),
        WebsiteSection(
            id="section-glossary",
            kind="glossary",
            title=labels["glossary"],
            item_ids=[item.id for item in canonical.glossary],
        ),
        WebsiteSection(
            id="section-questions",
            kind="questions",
            title=labels["questions"],
            item_ids=[item.id for item in canonical.suggested_questions],
        ),
    ]
    return WebsiteManifest(
        language="zh-CN" if output_language == "zh-CN" else "en",
        title=source.title,
        subtitle=canonical.concise_summary.text,
        theme=WebsiteTheme.EDITORIAL,
        hero=WebsiteHero(
            eyebrow="Bubble Video AI",
            title=source.title,
            subtitle=canonical.concise_summary.text,
            evidence_segment_ids=canonical.concise_summary.evidence_segment_ids,
        ),
        sections=sections,
        chapters=canonical.chapters,
        quotes=canonical.key_points[:6],
        timeline=[
            WebsiteTimelineItem(
                id=chapter.id,
                timestamp_seconds=chapter.start_seconds,
                title=chapter.title,
                text=chapter.summary.text,
                evidence_segment_ids=chapter.evidence_segment_ids,
            )
            for chapter in canonical.chapters
        ],
        glossary=canonical.glossary,
        callouts=[claim.statement for claim in canonical.claims[:8]],
        sources=[WebsiteSource(label=source.title, url=source.source_url)],
    )


def build_interactive_guide(
    source: AnalysisSource,
    canonical: CanonicalContentAnalysis,
    *,
    output_language: str,
) -> InteractiveGuide:
    corpus = " ".join(
        [
            canonical.concise_summary.text,
            *(chapter.summary.text for chapter in canonical.chapters),
        ]
    )
    high_risk = bool(_HIGH_RISK.search(corpus))
    is_chinese = output_language == "zh-CN"
    action_text = (
        "只回看并核对这一段的核心概念，不执行其中可能造成伤害的操作。"
        if high_risk and is_chinese
        else "Review and verify the concept only; do not perform potentially harmful actions."
        if high_risk
        else "回看对应片段，并用自己的话写下一句解释。"
        if is_chinese
        else "Review the linked moment and restate the idea in your own words."
    )
    checkpoint_prompt = (
        "你能否用一句话说明这一部分的核心观点？"
        if is_chinese
        else "Can you explain the central idea of this step in one sentence?"
    )
    criteria = (
        "回答应与原视频证据一致，并明确区分事实与推断。"
        if is_chinese
        else "The answer should match the source evidence and separate fact from inference."
    )
    steps = [
        GuideStep(
            id=f"step-{index:02d}",
            title=chapter.title,
            explanation=chapter.summary,
            timestamp_seconds=chapter.start_seconds,
            action=GuideAction(
                kind=GuideActionKind.REVIEW,
                instruction=action_text,
            ),
            checkpoint=GuideCheckpoint(
                prompt=checkpoint_prompt,
                success_criteria=criteria,
            ),
            evidence_segment_ids=chapter.evidence_segment_ids,
        )
        for index, chapter in enumerate(canonical.chapters, 1)
    ]
    quiz: list[GuideQuizItem] = []
    distractors = [topic.label for topic in canonical.topics]
    for index, question in enumerate(canonical.suggested_questions[:6], 1):
        correct = question.reason.text[:240]
        choices = [correct]
        choices.extend(
            label
            for label in distractors
            if label.casefold() not in correct.casefold()
        )
        while len(choices) < 2:
            choices.append(
                "需要回到原视频核对"
                if is_chinese
                else "Requires checking the original source"
            )
        quiz.append(
            GuideQuizItem(
                id=f"quiz-{index:02d}",
                question=question.question,
                choices=choices[:4],
                correct_index=0,
                explanation=question.reason,
            )
        )
    safety_notice = None
    if high_risk:
        safety_notice = (
            "检测到高风险主题。本指南只提供概念性理解和证据核对，不提供可执行的危险步骤。"
            if is_chinese
            else "High-risk subject matter was detected. This guide provides conceptual review and source verification only, not executable dangerous steps."
        )
    return InteractiveGuide(
        title=(
            f"{source.title} 学习指南"
            if is_chinese
            else f"Learning guide: {source.title}"
        ),
        audience="希望系统理解该视频的学习者" if is_chinese else "Learners reviewing this video",
        learning_objectives=[
            topic.summary for topic in canonical.topics[:6]
        ],
        prerequisites=[],
        estimated_time_minutes=max(5, len(steps) * 4),
        steps=steps,
        checkpoints=[step.checkpoint for step in steps],
        quiz=quiz,
        glossary=canonical.glossary,
        next_actions=(
            ["核对关键证据", "复习薄弱章节", "回答推荐问题"]
            if is_chinese
            else [
                "Verify the strongest evidence",
                "Revisit a weak chapter",
                "Answer the suggested questions",
            ]
        ),
        safety_notice=safety_notice,
    )
