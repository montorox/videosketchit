import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the whiteboard video application", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<html lang="en">/i);
  assert.match(html, /<title>VideoSketchIt \| Animated Sketch Video Studio<\/title>/i);
  assert.match(html, /Turn your ideas into a whiteboard video that speaks/);
  assert.match(html, /Upload Finished Narration/);
  assert.match(html, /Generate Video/);
  assert.match(html, /Connections/);
  assert.match(html, /VideoSketchIt/);
  assert.match(html, /by AIDB/);
  assert.doesNotMatch(html, /Your site is taking shape|Building your site/);
});

test("keeps public defaults portable and free of local configuration", async () => {
  const [page, layout, packageJson] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
  ]);

  assert.match(page, /tts_url:"http:\/\/127\.0\.0\.1:7860"/);
  assert.match(page, /NEXT_PUBLIC_API_BASE\|\|"http:\/\/127\.0\.0\.1:18775"/);
  assert.doesNotMatch(page, /api_key|api\.openlux\.ai/i);
  assert.doesNotMatch(page, /192\.168\.|10\.\d+\.\d+\.\d+/);
  assert.match(layout, /title:\s*"VideoSketchIt \| Animated Sketch Video Studio"/);
  assert.match(packageJson, /"build": "vinext build"/);
  assert.match(packageJson, /"test": "npm run build/);
});
