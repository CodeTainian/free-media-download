import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useDownloadJob } from "../app/hooks/use-download-job";
import { enUS } from "../app/lib/i18n/messages/en-US";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useDownloadJob", () => {
  it("validates missing and multi-link single input", async () => {
    const { result } = renderHook(() => useDownloadJob(enUS));

    await act(async () => {
      await result.current.analyze();
    });
    expect(result.current.error?.code).toBe("MISSING_URL");

    act(() => result.current.setInput("https://youtu.be/a\nhttps://youtu.be/b"));
    await act(async () => {
      await result.current.analyze();
    });
    expect(result.current.error?.code).toBe("TOO_MANY_URLS");
  });

  it("preserves the probe-to-download workflow and request contract", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            items: [
              {
                source_url: "https://youtu.be/test",
                title: "Test",
                platform: "YouTube",
                is_playlist_item: false,
                summary_supported: true,
                caption_languages: ["en"],
                transcript_strategy_hint: "captions",
                presets: [
                  {
                    id: "mp4-1080",
                    label: "1080p",
                    detail: "",
                    kind: "video",
                    extension: "mp4",
                  },
                ],
              },
            ],
            truncated: false,
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            job: {
              id: "job",
              status: "completed",
              created_at: new Date(0).toISOString(),
              items: [
                {
                  id: "item",
                  title: "Test",
                  status: "ready",
                  progress: 100,
                  download_url: "/api/v1/jobs/job/files/item",
                },
              ],
              bundle_ready: false,
            },
            events_url: "/api/v1/jobs/job/events",
          }),
          { status: 201, headers: { "content-type": "application/json" } },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useDownloadJob(enUS));
    act(() => result.current.setInput("https://youtu.be/test"));
    await act(async () => {
      await result.current.analyze();
    });
    expect(result.current.items).toHaveLength(1);
    expect(result.current.items[0].presetId).toBe("mp4-1080");

    await act(async () => {
      await result.current.startDownload();
    });
    await waitFor(() => expect(result.current.job?.status).toBe("completed"));
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/v1/media/probe",
      expect.objectContaining({ method: "POST" }),
    );
    const secondInit = fetchMock.mock.calls[1][1] as RequestInit;
    expect(JSON.parse(String(secondInit.body))).toMatchObject({
      bundle: false,
      items: [{ url: "https://youtu.be/test", preset_id: "mp4-1080" }],
    });
  });
});
