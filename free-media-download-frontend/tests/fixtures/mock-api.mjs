import http from "node:http";

const summaryResult = {
  source_url: "https://www.youtube.com/watch?v=bubble-demo",
  title: "How retrieval systems find the right context",
  platform: "YouTube",
  duration: 1122,
  caption_language: "en",
  caption_source: "manual_caption",
  output_language: "en",
  overview:
    "The video explains how a retrieval pipeline turns a question into relevant context, then shows how chunking, embeddings, ranking, and evaluation shape the final answer.",
  outline: [
    {
      timestamp_seconds: 48,
      title: "Why retrieval quality matters",
      summary:
        "A model can only use the context it receives, so retrieval quality becomes a measurable part of answer quality.",
      evidence: [
        {
          id: "segment-01",
          start_seconds: 48,
          end_seconds: 67,
          text: "Retrieval is not a hidden plumbing detail. It decides which evidence the model can actually see.",
        },
      ],
    },
    {
      timestamp_seconds: 306,
      title: "Chunking and embeddings",
      summary:
        "Chunk boundaries affect meaning. Embeddings make those chunks searchable, but they do not remove the need for careful document structure.",
      evidence: [
        {
          id: "segment-12",
          start_seconds: 306,
          end_seconds: 331,
          text: "A chunk should be large enough to carry meaning and small enough to match a focused question.",
        },
      ],
    },
    {
      timestamp_seconds: 714,
      title: "Ranking useful context",
      summary:
        "The final ranking stage balances semantic relevance with diversity, recency, and source quality.",
      evidence: [
        {
          id: "segment-28",
          start_seconds: 714,
          end_seconds: 741,
          text: "The nearest vector is not automatically the most useful passage for the answer.",
        },
      ],
    },
  ],
  key_points: [
    {
      title: "Retrieval quality is measurable",
      explanation:
        "Evaluate whether the system finds the passages a good answer actually needs, not only whether an embedding score is high.",
      evidence: [
        {
          id: "segment-03",
          start_seconds: 82,
          end_seconds: 102,
          text: "Measure retrieval against the evidence required by the question.",
        },
      ],
    },
    {
      title: "Chunk boundaries change results",
      explanation:
        "Chunks that split definitions from their conditions produce weaker matches and less trustworthy generated answers.",
      evidence: [
        {
          id: "segment-14",
          start_seconds: 350,
          end_seconds: 376,
          text: "When a condition is separated from the rule it qualifies, both chunks become less useful.",
        },
      ],
    },
  ],
};

const summary = {
  id: "bubble-summary-demo",
  status: "completed",
  stage: "completed",
  progress: 100,
  created_at: new Date().toISOString(),
  expires_at: new Date(Date.now() + 30 * 60 * 1000).toISOString(),
  result: summaryResult,
  error: null,
};

const mediaItem = {
  source_url: summaryResult.source_url,
  title: summaryResult.title,
  platform: "YouTube",
  duration: summaryResult.duration,
  thumbnail: null,
  uploader: "Bubble AI Demo",
  is_playlist_item: false,
  summary_supported: true,
  caption_languages: ["en"],
  transcript_strategy_hint: "captions",
  presets: [
    {
      id: "mp4-1080",
      label: "MP4 · 1080p",
      detail: "Demo format",
      kind: "video",
      extension: "mp4",
      height: 1080,
    },
    {
      id: "mp3",
      label: "MP3 · audio",
      detail: "Demo format",
      kind: "audio",
      extension: "mp3",
      height: null,
    },
  ],
};

const port = Number(process.env.MOCK_API_PORT ?? 8000);

const server = http.createServer((request, response) => {
  response.setHeader("Access-Control-Allow-Origin", "*");

  if (request.method === "GET" && request.url === "/api/v1/health") {
    response.setHeader("Content-Type", "application/json");
    response.end(JSON.stringify({ status: "ok", api: true }));
    return;
  }

  if (request.method === "POST" && request.url === "/api/v1/media/probe") {
    response.setHeader("Content-Type", "application/json");
    response.end(JSON.stringify({ items: [mediaItem], truncated: false }));
    return;
  }

  if (request.method === "POST" && request.url === "/api/v1/summaries") {
    response.statusCode = 201;
    response.setHeader("Content-Type", "application/json");
    response.end(
      JSON.stringify({
        summary: { ...summary, status: "queued", stage: "queued", progress: 0, result: null },
        events_url: "/api/v1/summaries/bubble-summary-demo/events",
      }),
    );
    return;
  }

  if (
    request.method === "GET" &&
    request.url === "/api/v1/summaries/bubble-summary-demo"
  ) {
    response.setHeader("Content-Type", "application/json");
    response.end(JSON.stringify(summary));
    return;
  }

  if (
    request.method === "GET" &&
    request.url === "/api/v1/summaries/bubble-summary-demo/events"
  ) {
    response.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    });
    response.write(
      `id: 1\nevent: completed\ndata: ${JSON.stringify({
        sequence: 1,
        type: "completed",
        summary,
      })}\n\n`,
    );
    response.end();
    return;
  }

  response.statusCode = 404;
  response.setHeader("Content-Type", "application/json");
  response.end(
    JSON.stringify({ code: "NOT_FOUND", message: "Mock route not found", retryable: false }),
  );
});

server.listen(port, "127.0.0.1", () => {
  process.stdout.write(`Bubble Video AI mock API listening on http://127.0.0.1:${port}\n`);
});

process.on("SIGINT", () => server.close(() => process.exit(0)));
