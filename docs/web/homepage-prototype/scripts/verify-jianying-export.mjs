import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

async function test(name, run) {
  try {
    await run();
    console.log(`PASS ${name}`);
  } catch (error) {
    console.error(`FAIL ${name}: ${error.message}`);
    process.exitCode = 1;
  }
}

await test("only desktop Chrome or Edge with File System Access can export", async () => {
  const { supportsJianyingExport } = await import("../src/features/exports/jianyingZip.js");
  assert.equal(supportsJianyingExport({ showSaveFilePicker() {}, navigator: { userAgent: "Mozilla/5.0 Chrome/130.0" } }), true);
  assert.equal(supportsJianyingExport({ showSaveFilePicker() {}, navigator: { userAgent: "Mozilla/5.0 Edg/130.0" } }), true);
  assert.equal(supportsJianyingExport({ showSaveFilePicker() {}, navigator: { userAgent: "Mozilla/5.0 Chrome/130.0 Mobile" } }), false);
  assert.equal(supportsJianyingExport({ navigator: { userAgent: "Mozilla/5.0 Chrome/130.0" } }), false);
});

await test("streams each CDN file into a ZIP entry with a Range GET and no Blob", async () => {
  const { writeManifestAsZipStream } = await import("../src/features/exports/jianyingZip.js");
  const calls = [];
  const entries = [];
  const consume = async (reader) => {
    if (reader instanceof ReadableStream) return new Response(reader).text();
    await reader.init?.();
    return new TextDecoder().decode(await reader.readUint8Array(0, reader.size));
  };
  const zipWriter = {
    add: async (path, reader) => entries.push([path, await consume(reader)]),
    close: async () => calls.push("zip.close"),
  };
  const writable = {
    write: async () => {},
    close: async () => calls.push("writable.close"),
    abort: async () => calls.push("writable.abort"),
  };
  await writeManifestAsZipStream({
    files: [
      { zip_path: "draft/content.json", content: "{\"draft\":true}" },
      { zip_path: "materials/video.mp4", url: "https://cdn.example.test/video.mp4" },
    ],
  }, writable, {
    createZipWriter: () => zipWriter,
    fetch: async (url, options) => {
      calls.push([url, options]);
      return new Response(new ReadableStream({ start(controller) { controller.enqueue(new TextEncoder().encode("streamed")); controller.close(); } }), { status: 206 });
    },
  });
  assert.deepEqual(entries, [["draft/content.json", "{\"draft\":true}"], ["materials/video.mp4", "streamed"]]);
  assert.equal(calls[0][1].headers.Range, "bytes=0-");
  assert.deepEqual(calls.at(-2), "zip.close");
  assert.deepEqual(calls.at(-1), "writable.close");
});

await test("failed stream aborts the writable so the action can be retried", async () => {
  const { writeManifestAsZipStream } = await import("../src/features/exports/jianyingZip.js");
  const calls = [];
  await assert.rejects(() => writeManifestAsZipStream({ files: [{ zip_path: "bad.mp4", url: "https://cdn.example.test/bad.mp4" }] }, {
    close: async () => calls.push("close"), abort: async () => calls.push("abort"),
  }, {
    createZipWriter: () => ({ add: async () => { throw new Error("network failed"); }, close: async () => calls.push("zip.close") }),
    fetch: async () => new Response("no", { status: 500 }),
  }), /CDN 500/);
  assert.deepEqual(calls, ["abort"]);
});

await test("result page requests a server manifest only after real Artifacts load", async () => {
  const source = await readFile(new URL("../src/pages/NarrationStagePage.jsx", import.meta.url), "utf8");
  assert.match(source, /if \(!result \|\| exportingDraft\) return/);
  assert.match(source, /apiRequest\(`\/projects\/\$\{projectId\}\/exports\/jianying-manifest`/);
  assert.match(source, /exportJianyingZip\(manifest\)/);
  assert.match(source, /result && <button/);
  assert.doesNotMatch(source, /exports\/zip|jianying.*artifact/i);
});

if (process.exitCode) process.exit(process.exitCode);
