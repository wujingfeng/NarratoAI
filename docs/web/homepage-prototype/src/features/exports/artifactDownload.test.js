import test from "node:test";
import assert from "node:assert/strict";
import { downloadArtifact } from "./artifactDownload.js";

function makeAnchorSpy() {
  const calls = [];
  class FakeAnchor {
    constructor() {
      this.href = "";
      this.download = "";
      this.rel = "";
      this.clicked = false;
    }
    click() {
      this.clicked = true;
      calls.push({ href: this.href, download: this.download });
    }
  }
  return { FakeAnchor, calls };
}

test("downloadArtifact fetches then triggers a blob URL download", async () => {
  const { FakeAnchor, calls } = makeAnchorSpy();
  const originalCreateElement = globalThis.document;
  const blobs = [];
  const revokeCalls = [];
  globalThis.URL = {
    createObjectURL: (blob) => {
      blobs.push(blob);
      return "blob:mock";
    },
    revokeObjectURL: (url) => revokeCalls.push(url),
  };
  globalThis.document = {
    createElement: (tag) => {
      if (tag !== "a") throw new Error(`Unexpected tag ${tag}`);
      return new FakeAnchor();
    },
    body: { appendChild: () => {}, removeChild: () => {} },
  };
  try {
    const fetcher = async () => new Response(new Blob(["hello"], { type: "video/mp4" }), { status: 200 });
    const result = await downloadArtifact({ id: "art_1", cdn_url: "https://example.com/x", content_type: "video/mp4" }, { fetcher });
    assert.equal(result.method, "blob");
    assert.equal(result.filename, "art_1.mp4");
    assert.equal(calls.length, 1);
    assert.equal(calls[0].href, "blob:mock");
    assert.equal(calls[0].download, "art_1.mp4");
    assert.equal(blobs.length, 1);
    // revokeObjectURL 通过 setTimeout(..., 0) 异步触发,等待一帧再断言
    await new Promise((resolve) => setTimeout(resolve, 5));
    assert.equal(revokeCalls.length, 1);
  } finally {
    globalThis.document = originalCreateElement;
  }
});

test("downloadArtifact falls back to anchor download when fetch fails", async () => {
  const { FakeAnchor, calls } = makeAnchorSpy();
  const originalCreateElement = globalThis.document;
  globalThis.URL = { createObjectURL: () => "blob:mock", revokeObjectURL: () => {} };
  globalThis.document = {
    createElement: (tag) => {
      if (tag !== "a") throw new Error(`Unexpected tag ${tag}`);
      return new FakeAnchor();
    },
    body: { appendChild: () => {}, removeChild: () => {} },
  };
  try {
    const fetcher = async () => { throw new TypeError("NetworkError"); };
    const result = await downloadArtifact({ id: "art_2", cdn_url: "https://example.com/y", filename: "captions.vtt" }, { fetcher });
    assert.equal(result.method, "anchor");
    assert.equal(result.filename, "captions.vtt");
    assert.equal(calls.length, 1);
    assert.equal(calls[0].href, "https://example.com/y");
    assert.equal(calls[0].download, "captions.vtt");
  } finally {
    globalThis.document = originalCreateElement;
  }
});

test("downloadArtifact never navigates the current page (no window.open)", async () => {
  const originalWindowOpen = globalThis.window?.open;
  let opened = 0;
  globalThis.window = { ...(globalThis.window || {}), open: () => { opened += 1; return null; } };
  try {
    const fetcher = async () => new Response(new Blob(["x"], { type: "audio/mpeg" }), { status: 200 });
    const { FakeAnchor } = makeAnchorSpy();
    const originalCreateElement = globalThis.document;
    globalThis.URL = { createObjectURL: () => "blob:mock", revokeObjectURL: () => {} };
    globalThis.document = {
      createElement: () => new FakeAnchor(),
      body: { appendChild: () => {}, removeChild: () => {} },
    };
    try {
      await downloadArtifact({ id: "art_3", cdn_url: "https://example.com/z" }, { fetcher });
    } finally {
      globalThis.document = originalCreateElement;
    }
  } finally {
    if (originalWindowOpen) globalThis.window.open = originalWindowOpen;
  }
  assert.equal(opened, 0);
});
