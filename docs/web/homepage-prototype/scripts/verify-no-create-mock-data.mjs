import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = (file) => readFile(new URL(`../src/${file}`, import.meta.url), "utf8");

const page = await source("pages/CreatePage.jsx");
const createData = await source("data/createData.js");
const uploadPanel = await source("components/create/VideoUploadPanel.jsx");

assert.doesNotMatch(page, /initialCreateVideos/, "CreatePage must not initialize uploaded assets from mock data");
assert.match(page, /useState\(\[\]\)/, "CreatePage must start with no uploaded assets");
assert.match(page, /await uploadAsset/, "uploaded rows must come from the upload-complete API response");
assert.match(page, /assetId: asset\.id/, "uploaded rows must retain the real API asset ID");
assert.match(createData, /export const initialCreateVideos = \[\];/, "create data must not define placeholder upload assets");
assert.match(page, /const \[isUploading, setIsUploading\] = useState\(false\)/, "CreatePage must track upload state");
assert.match(page, /uploadInFlight\.current/, "CreatePage must reject overlapping upload requests");
assert.match(page, /finally \{[\s\S]*?setIsUploading\(false\);\s*\}/, "CreatePage must release the upload lock after completion");
assert.match(uploadPanel, /create-upload-loading/, "upload panel must render a loading indicator");
assert.match(uploadPanel, /disabled=\{isUploading\}/, "upload controls must be disabled while uploading");
assert.doesNotMatch(page, /素材已校验/, "video validation state must not replace the SRT upload prompt");
assert.match(page, /subtitleStatus: "上传 SRT 字幕文件"/, "every uploaded video must continue to offer SRT upload");
assert.match(page, /uploadAsset\(projectId, file, "subtitle"\)/, "SRT selection must use the real upload API");

console.log("PASS create page has no placeholder upload assets");
