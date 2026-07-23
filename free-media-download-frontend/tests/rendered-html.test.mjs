import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

async function render(path, headers = {}) {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}-${path}-${Math.random()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request(`http://localhost${path}`, {
      headers: { accept: "text/html", ...headers },
      redirect: "manual",
    }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders English and Chinese Bubble Video AI pages", async () => {
  const [english, chinese] = await Promise.all([
    render("/en-US"),
    render("/zh-CN"),
  ]);
  assert.equal(english.status, 200);
  assert.equal(chinese.status, 200);
  const englishHtml = await english.text();
  const chineseHtml = await chinese.text();
  assert.match(englishHtml, /<html lang="en-US"/);
  assert.match(englishHtml, /Turn any video into knowledge you can use/);
  assert.match(englishHtml, /Bubble Workspace/);
  assert.match(englishHtml, /No account required/);
  assert.match(chineseHtml, /<html lang="zh-CN"/);
  assert.match(chineseHtml, /把任意视频，变成真正能用的知识/);
  assert.match(chineseHtml, /无需注册/);
  assert.doesNotMatch(
    `${englishHtml}${chineseHtml}`,
    /codex-preview|Your site is taking shape|react-loading-skeleton/i,
  );
});

test("redirects unprefixed routes from Accept-Language", async () => {
  const [chinese, english, privacy] = await Promise.all([
    render("/", { "accept-language": "zh-CN,zh;q=0.9,en;q=0.5" }),
    render("/", { "accept-language": "fr-FR,fr;q=0.9" }),
    render("/privacy", { "accept-language": "zh;q=1" }),
  ]);
  assert.ok([307, 308].includes(chinese.status));
  assert.match(chinese.headers.get("location") ?? "", /\/zh-CN$/);
  assert.match(english.headers.get("location") ?? "", /\/en-US$/);
  assert.match(privacy.headers.get("location") ?? "", /\/zh-CN\/privacy$/);
});

test("renders localized legal routes", async () => {
  const [terms, privacy] = await Promise.all([
    render("/en-US/terms"),
    render("/zh-CN/privacy"),
  ]);
  assert.equal(terms.status, 200);
  assert.equal(privacy.status, 200);
  assert.match(await terms.text(), /Terms of use/);
  const privacyHtml = await privacy.text();
  assert.match(privacyHtml, /把隐私说清楚/);
  assert.match(privacyHtml, /DeepSeek API/);
  assert.match(privacyHtml, /不会发送视频或音频文件/);
});

test("keeps the implementation honest, accessible, and split by responsibility", async () => {
  const [input, workspace, stream, layout, packageJson, css, apiProxy, envExample] =
    await Promise.all([
      readFile(new URL("../app/components/media-input/bubble-input.tsx", import.meta.url), "utf8"),
      readFile(new URL("../app/components/workspace/result-workspace.tsx", import.meta.url), "utf8"),
      readFile(new URL("../app/hooks/use-task-stream.ts", import.meta.url), "utf8"),
      readFile(new URL("../app/[locale]/layout.tsx", import.meta.url), "utf8"),
      readFile(new URL("../package.json", import.meta.url), "utf8"),
      readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
      readFile(new URL("../app/api/v1/[...path]/route.ts", import.meta.url), "utf8"),
      readFile(new URL("../.env.example", import.meta.url), "utf8"),
    ]);
  assert.match(input, /aria-label=\{dictionary\.input\.urlLabel\}/);
  assert.match(input, /NEXT_PUBLIC_ENABLE_UPLOAD/);
  assert.match(workspace, /role="tabpanel"/);
  assert.match(workspace, /aria-live="polite"/);
  assert.doesNotMatch(workspace, /dangerouslySetInnerHTML/);
  assert.match(stream, /reconnectDelays = \[1000, 2000, 4000, 8000, 10000\]/);
  assert.match(stream, /getSnapshot/);
  assert.match(apiProxy, /SAVEBOLT_API_ORIGIN/);
  assert.match(apiProxy, /last-event-id/);
  assert.match(envExample, /NEXT_PUBLIC_SHOW_PRICING_PREVIEW=true/);
  assert.match(envExample, /NEXT_PUBLIC_ENABLE_UPLOAD=false/);
  assert.match(layout, /<html lang=\{documentLocale\}>/);
  assert.doesNotMatch(packageJson, /react-loading-skeleton/);
  assert.match(css, /--background: #f7f7f4/);
  assert.match(css, /prefers-reduced-motion/);
  assert.match(css, /@media \(max-width: 520px\)/);
  assert.match(css, /overflow-x: clip/);
  await assert.rejects(
    access(new URL("../app/components/download-studio.tsx", import.meta.url)),
  );
});
