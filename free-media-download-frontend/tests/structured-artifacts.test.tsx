import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { DynamicWebsiteView } from "../app/components/workspace/views/dynamic-website-view";
import { InteractiveGuideView } from "../app/components/workspace/views/interactive-guide-view";
import { MindMapView } from "../app/components/workspace/views/mind-map-view";
import { enUS } from "../app/lib/i18n/messages/en-US";
import type {
  InteractiveGuide,
  MindMap,
  WebsiteManifest,
} from "../app/lib/api/types";

const evidence = {
  text: "Grounded explanation",
  evidence_segment_ids: ["seg-00001"],
  start_seconds: 0,
  end_seconds: 10,
};

const manifest: WebsiteManifest = {
  language: "en",
  title: '<script>alert("xss")</script>',
  subtitle: "Safe subtitle",
  theme: "editorial",
  hero: {
    eyebrow: "Bubble Video AI",
    title: '<img src=x onerror="alert(1)">',
    subtitle: "Safe subtitle",
    evidence_segment_ids: ["seg-00001"],
  },
  sections: [
    {
      id: "section-overview",
      kind: "overview",
      title: "Overview",
      item_ids: [],
    },
  ],
  chapters: [
    {
      id: "chapter-one",
      title: "Opening",
      start_seconds: 0,
      end_seconds: 10,
      summary: evidence,
      key_points: [evidence],
      evidence_segment_ids: ["seg-00001"],
    },
  ],
  quotes: [evidence],
  timeline: [],
  glossary: [],
  callouts: [evidence],
  sources: [{ label: "Source", url: "https://www.youtube.com/watch?v=test" }],
};

const guide: InteractiveGuide = {
  title: "Guided lesson",
  audience: "Curious learners",
  learning_objectives: [evidence],
  prerequisites: [],
  estimated_time_minutes: 10,
  steps: [
    {
      id: "step-01",
      title: "First",
      explanation: evidence,
      timestamp_seconds: 0,
      action: { kind: "review", instruction: "Review the concept." },
      checkpoint: {
        prompt: "Can you explain it?",
        success_criteria: "Use source evidence.",
      },
      evidence_segment_ids: ["seg-00001"],
    },
    {
      id: "step-02",
      title: "Second",
      explanation: { ...evidence, start_seconds: 10, end_seconds: 20 },
      timestamp_seconds: 10,
      action: { kind: "reflect", instruction: "Reflect on the idea." },
      checkpoint: {
        prompt: "What changed?",
        success_criteria: "Name one change.",
      },
      evidence_segment_ids: ["seg-00001"],
    },
  ],
  checkpoints: [],
  quiz: [
    {
      id: "quiz-01",
      question: "Which answer is grounded?",
      choices: ["Grounded", "Invented"],
      correct_index: 0,
      explanation: evidence,
    },
  ],
  glossary: [],
  next_actions: [],
};

const map: MindMap = {
  root_id: "node-root",
  nodes: [
    {
      id: "node-root",
      label: "Root",
      description: "The central idea",
      type: "root",
      timestamp_seconds: 0,
      evidence_segment_ids: ["seg-00001"],
      children: ["node-topic"],
    },
    {
      id: "node-topic",
      label: "Topic",
      description: "A supporting topic",
      type: "topic",
      timestamp_seconds: 5,
      evidence_segment_ids: ["seg-00001"],
      children: [],
    },
  ],
  edges: [
    {
      id: "edge-root-topic",
      source_id: "node-root",
      target_id: "node-topic",
      label: "theme",
    },
  ],
};

describe("structured artifact views", () => {
  it("renders WebsiteManifest as escaped React content and switches templates", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <DynamicWebsiteView
        analysisId="analysis-1"
        manifest={manifest}
        dictionary={enUS}
      />,
    );

    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText('<img src=x onerror="alert(1)">')).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Learning" }));
    expect(container.querySelector('[data-theme="learning"]')).not.toBeNull();
    await user.click(screen.getByRole("button", { name: "Mobile" }));
    expect(container.querySelector('[data-device="mobile"]')).not.toBeNull();
    expect(container.innerHTML).not.toContain("dangerouslySetInnerHTML");
  });

  it("offers an accessible mobile-safe mind map tree with collapse and recenter", async () => {
    const user = userEvent.setup();
    render(
      <MindMapView
        map={map}
        sourceUrl="https://www.youtube.com/watch?v=test"
        dictionary={enUS}
      />,
    );
    expect(screen.getByRole("tree")).toBeTruthy();
    expect(screen.getAllByRole("treeitem")).toHaveLength(2);
    await user.click(screen.getByRole("button", { name: /Root/ }));
    expect(screen.getAllByRole("treeitem")).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Recenter" }));
    expect(screen.getAllByRole("treeitem")).toHaveLength(2);
  });

  it("supports guide progress, quiz feedback, local restore, and keyboard paging", async () => {
    localStorage.clear();
    const user = userEvent.setup();
    render(
      <InteractiveGuideView
        analysisId="analysis-1"
        guide={guide}
        sourceUrl="https://www.youtube.com/watch?v=test"
        dictionary={enUS}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Mark complete" }));
    await waitFor(() =>
      expect(localStorage.getItem("bubble-guide:analysis-1")).toContain("step-01"),
    );
    fireEvent.keyDown(window, { key: "ArrowRight", altKey: true });
    expect(screen.getByRole("heading", { name: "Second" })).toBeTruthy();
    await user.click(screen.getByLabelText("Grounded"));
    expect(screen.getByText(/Correct/)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Restart" }));
    expect(screen.getByRole("heading", { name: "First" })).toBeTruthy();
  });
});
