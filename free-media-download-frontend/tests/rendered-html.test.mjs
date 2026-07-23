import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

async function render(path = "/") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}-${path}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request(`http://localhost${path}`, { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the SaveBolt product shell", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
  const html = await response.text();
  assert.match(html, /SaveBolt/);
  assert.match(html, /Public media, saved cleanly/);
  assert.match(html, /Keep the videos/);
  assert.match(html, /Free while we launch/i);
  assert.match(html, /Coming soon/i);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape|react-loading-skeleton/i);
});

test("renders legal routes", async () => {
  const [terms, privacy] = await Promise.all([render("/terms"), render("/privacy")]);
  assert.equal(terms.status, 200);
  assert.equal(privacy.status, 200);
  assert.match(await terms.text(), /Terms of use/);
  const privacyHtml = await privacy.text();
  assert.match(privacyHtml, /Privacy, plainly/);
  assert.match(privacyHtml, /DeepSeek API/);
  assert.match(privacyHtml, /does not send the video file or audio/i);
});

test("keeps the launch implementation honest and accessible", async () => {
  const [client, layout, packageJson, css, apiProxy, envExample] = await Promise.all([
    readFile(new URL("../app/components/download-studio.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
    readFile(new URL("../app/api/v1/[...path]/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../.env.example", import.meta.url), "utf8"),
  ]);
  assert.match(client, /aria-label="Public video URL"/);
  assert.match(client, /role="alert"/);
  assert.match(client, /Pro is not accepting payments yet/);
  assert.match(client, /EventSource/);
  assert.match(client, /Batch · up to 10/);
  assert.match(client, /\/api\/v1\/summaries/);
  assert.match(client, /summary_supported/);
  assert.match(client, /No usable captions/);
  assert.match(client, /role="progressbar"/);
  assert.match(client, /aria-busy=/);
  assert.match(client, /Cancel summary/);
  assert.match(client, /SUMMARY_CANCEL_FAILED/);
  assert.match(client, /Copy summary/);
  assert.match(client, /Source evidence/);
  assert.match(client, /language=\{summaryJob\.result/);
  assert.match(client, /No audio or full video is sent/);
  assert.match(client, /aria-describedby=\{summaryNoteId\}/);
  assert.match(client, /NEXT_PUBLIC_API_BASE_URL \?\? ""/);
  assert.match(apiProxy, /SAVEBOLT_API_ORIGIN/);
  assert.match(apiProxy, /SAFE_PATH_SEGMENT/);
  assert.match(apiProxy, /last-event-id/);
  assert.match(apiProxy, /return new Response\(upstream\.body/);
  assert.match(envExample, /SAVEBOLT_API_ORIGIN=http:\/\/127\.0\.0\.1:8000/);
  assert.match(layout, /SaveBolt — Public media, saved cleanly/);
  assert.doesNotMatch(layout, /codex-preview|Starter Project/);
  assert.doesNotMatch(packageJson, /react-loading-skeleton/);
  assert.match(css, /prefers-reduced-motion/);
  await assert.rejects(access(new URL("../app/_sites-preview/SkeletonPreview.tsx", import.meta.url)));
});
