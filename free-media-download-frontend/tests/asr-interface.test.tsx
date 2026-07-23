import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MediaResults } from "../app/components/media/media-results";
import { SiteFooter } from "../app/components/marketing/site-footer";
import type { MediaSelection } from "../app/lib/api/types";
import { enUS } from "../app/lib/i18n/messages/en-US";
import { zhCN } from "../app/lib/i18n/messages/zh-CN";

function selection(
  overrides: Partial<MediaSelection> = {},
): MediaSelection {
  return {
    selectionId: "source-1",
    source_url: "https://www.youtube.com/watch?v=public",
    title: "Public lesson",
    platform: "YouTube",
    duration: 60,
    is_playlist_item: false,
    summary_supported: true,
    caption_languages: [],
    transcript_strategy_hint: "audio_transcription",
    presetId: "best",
    presets: [
      {
        id: "best",
        label: "Best available",
        detail: "",
        kind: "video",
        extension: "mp4",
      },
    ],
    ...overrides,
  };
}

describe("no-caption transcription interface", () => {
  it("shows an explicit Chinese ASR action and audio-transfer disclosure", () => {
    render(
      <MediaResults
        items={[selection()]}
        dictionary={zhCN}
        summaryStarting={false}
        onAnalyze={vi.fn()}
        onPresetChange={vi.fn()}
        onApply1080={vi.fn()}
      />,
    );

    const action = screen.getByRole("button", {
      name: "转写并生成总结",
    }) as HTMLButtonElement;
    expect(action.disabled).toBe(false);
    expect(
      screen.getByText(/可使用音频转写/).textContent,
    ).toContain("可使用音频转写");
    expect(
      screen.getByText(/把音频分块发送给服务器配置的语音转写服务/)
        .textContent,
    ).toContain("音频分块");
  });

  it("explains server configuration and disables unavailable ASR", () => {
    render(
      <MediaResults
        items={[selection({ summary_supported: false })]}
        dictionary={enUS}
        summaryStarting={false}
        onAnalyze={vi.fn()}
        onPresetChange={vi.fn()}
        onApply1080={vi.fn()}
      />,
    );

    const action = screen.getByRole("button", {
      name: "Transcribe & summarize",
    }) as HTMLButtonElement;
    expect(action.disabled).toBe(true);
    expect(
      screen.getByText(/Audio transcription available · Audio transcription is not configured/),
    ).toBeTruthy();
  });

  it("keeps caption summaries on the caption-only disclosure path", () => {
    render(
      <MediaResults
        items={[
          selection({
            caption_languages: ["en"],
            transcript_strategy_hint: "captions",
          }),
        ]}
        dictionary={enUS}
        summaryStarting={false}
        onAnalyze={vi.fn()}
        onPresetChange={vi.fn()}
        onApply1080={vi.fn()}
      />,
    );

    const action = screen.getByRole("button", {
      name: "Create knowledge",
    }) as HTMLButtonElement;
    expect(action.disabled).toBe(false);
    expect(
      screen.queryByText(/extract temporary audio/i),
    ).toBeNull();
    expect(screen.getByText(/1 caption tracks/)).toBeTruthy();
  });
});

describe("Bubble AI footer", () => {
  it("includes the secure Bubble AI Cloud friend link", () => {
    render(<SiteFooter locale="en-US" dictionary={enUS} />);
    const link = screen.getByRole("link", { name: /Bubble AI Cloud/ });
    expect(link.getAttribute("href")).toBe("https://www.bubbleai.cloud/");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });
});
