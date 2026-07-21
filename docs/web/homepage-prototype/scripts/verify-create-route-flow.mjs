import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = (file) => readFile(new URL(`../src/${file}`, import.meta.url), "utf8");

const app = await source("App.jsx");
const page = await source("pages/CreatePage.jsx");
const summary = await source("components/create/CreationSummary.jsx");
const createData = await source("data/createData.js");

assert.match(app, /import\s+\{\s*CreatePage\s*\}/, "CreatePage must be imported by App");
assert.match(app, /path="\/create"\s+element=\{<RequireAuth><CreatePage \/><\/RequireAuth>\}/, "CreatePage must be exposed as protected /create route");
assert.match(createData, /export const creationTypes/, "create data must provide creation types");
assert.match(createData, /export const initialCreateVideos/, "create data must provide initial videos");
assert.match(page, /estimateProjectCost/, "CreatePage must read the API cost estimate");
assert.match(page, /canStartProject/, "CreatePage must gate start on asset readiness");
assert.match(summary, /disabled=\{disabled\}/, "start control must receive disabled state");
assert.match(summary, /estimatedCredits/, "start control must render API fee data");
console.log("PASS create route and project-start flow");
