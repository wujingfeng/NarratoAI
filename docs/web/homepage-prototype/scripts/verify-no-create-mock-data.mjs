import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = (file) => readFile(new URL(`../src/${file}`, import.meta.url), "utf8");

const page = await source("pages/CreatePage.jsx");
const createData = await source("data/createData.js");

assert.doesNotMatch(page, /initialCreateVideos/, "CreatePage must not initialize uploaded assets from mock data");
assert.match(page, /useState\(\[\]\)/, "CreatePage must start with no uploaded assets");
assert.match(page, /await uploadAsset/, "uploaded rows must come from the upload-complete API response");
assert.match(page, /assetId: asset\.id/, "uploaded rows must retain the real API asset ID");
assert.match(createData, /export const initialCreateVideos = \[\];/, "create data must not define placeholder upload assets");

console.log("PASS create page has no placeholder upload assets");
