import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const root = new URL("..", import.meta.url);
const uploader = await readFile(new URL("src/features/uploads/ossPostUpload.js", root), "utf8");
const createPage = await readFile(new URL("src/pages/CreatePage.jsx", root), "utf8");

assert.match(uploader, /MAX_SUBTITLE_SIZE_BYTES = 5 \* 1024 \* 1024/);
assert.match(uploader, /"\.srt": "application\/x-subrip"/);
assert.match(uploader, /content_type: contentType/);
assert.match(uploader, /assetType === "subtitle" \? MAX_SUBTITLE_SIZE_BYTES/);
assert.match(createPage, /SUBTITLE_SIZE_LIMIT = 5 \* 1024 \* 1024/);
assert.match(createPage, /仅支持 5 MiB 以内的 SRT 字幕文件/);

console.log("upload declaration checks passed");
