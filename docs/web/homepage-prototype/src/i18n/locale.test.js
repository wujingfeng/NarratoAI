import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  normalizeLocale,
  resolveInitialLocale,
  translate,
  formatDateForLocale,
  formatNumberForLocale,
} from "./locale.js";
import { zhCN } from "./locales/zh-CN.js";
import { en } from "./locales/en.js";
import { ja } from "./locales/ja.js";

const currentDirectory = path.dirname(fileURLToPath(import.meta.url));
const sourceRoot = path.resolve(currentDirectory, "..");

function collectLeafKeys(value, prefix = "", keys = []) {
  for (const [key, child] of Object.entries(value)) {
    const leafKey = prefix ? `${prefix}.${key}` : key;
    if (typeof child === "string") keys.push(leafKey);
    else if (child && typeof child === "object") collectLeafKeys(child, leafKey, keys);
  }
  return keys.sort();
}

function walkFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) return walkFiles(target);
    return statSync(target).isFile() && (/\.jsx$/.test(entry.name) || /Data\.js$/.test(entry.name)) ? [target] : [];
  });
}

function findHanLiterals(file) {
  return readFileSync(file, "utf8").split("\n").flatMap((line, index) => {
    const sourceLine = line.replace(/\{\/\*.*?\*\/\}/g, "");
    const matches = [];
    for (const match of sourceLine.matchAll(/(?:^|[(:,=\[\s])(?:"([^"\n]*\p{Script=Han}[^"\n]*)"|'([^'\n]*\p{Script=Han}[^'\n]*)'|`([^`\n]*\p{Script=Han}[^`\n]*)`)/gu)) {
      matches.push({ literal: match[1] ?? match[2] ?? match[3], line: index + 1 });
    }
    for (const match of sourceLine.matchAll(/>([^<>{}]*\p{Script=Han}[^<>{}]*)</gu)) {
      matches.push({ literal: match[1].trim(), line: index + 1 });
    }
    return matches;
  });
}

const allowedHanContent = new Set([
  // Project and media file names are user content and must remain verbatim across locales.
  "霸总短剧解说 01", "都市逆袭 · 混剪", "悬疑短剧翻译", "第 1 集.mp4", "第1集.srt", "第 2 集.mp4", "第 3 集.mp4", "/media/narration-editor/古墓迷宫震全球3.srt",
  "命运的反转 · 英文翻译", "都市逆袭高光混剪", "悬疑短剧解说", "甜宠短剧翻译", "豪门恩怨混剪",
  // Script, subtitle, character-name, and source-dialogue content is intentionally not UI chrome.
  "婚礼当天，她亲手撕碎了所有人的谎言。谁也没想到，那个被赶出家门的女孩，才是真正掌控全局的人……", "林夏", "顾言", "我不会再替任何人承担错误。", "你早就知道真相，对吗？", "从你签下那份协议开始。",
  // Language self-names stay in their native script in every locale.
  "简中", "简体中文", "日本語",
  // Persisted editor preset content is compared as data before rendering its localized resource label.
  "沉稳男声·顾言",
]);

test("normalizes supported language tags", () => {
  assert.equal(normalizeLocale("zh-Hans-SG"), "zh-CN");
  assert.equal(normalizeLocale("en-US"), "en");
  assert.equal(normalizeLocale("ja-JP"), "ja");
  assert.equal(normalizeLocale("fr-FR"), null);
});

test("stored locale wins, then ordered browser locales, then zh-CN", () => {
  assert.equal(resolveInitialLocale({ storedLocale: "ja", browserLocales: ["en-US"] }), "ja");
  assert.equal(resolveInitialLocale({ storedLocale: "bad", browserLocales: ["fr-FR", "en-GB"] }), "en");
  assert.equal(resolveInitialLocale({ storedLocale: null, browserLocales: ["fr-FR"] }), "zh-CN");
});

test("translation falls back to zh-CN and preserves missing placeholders", () => {
  const resources = { "zh-CN": { hello: "你好 {name}", fallback: "中文" }, en: { hello: "Hi {name}" }, ja: {} };
  assert.equal(translate(resources, "en", "hello", { name: "Narrato" }), "Hi Narrato");
  assert.equal(translate(resources, "ja", "fallback"), "中文");
  assert.equal(translate(resources, "ja", "hello"), "你好 {name}");
  const originalWarn = console.warn;
  console.warn = () => {};
  try { assert.equal(translate(resources, "ja", "missing.key"), "missing.key"); }
  finally { console.warn = originalWarn; }
});

test("number formatting uses the active locale", () => {
  assert.equal(formatNumberForLocale("en", 1280), "1,280");
  assert.match(formatNumberForLocale("zh-CN", 1280), /1,280|1280/);
});

test("brand name remains 影创工坊 in every locale", () => {
  for (const resource of [zhCN, en, ja]) assert.equal(resource.common.brand, "影创工坊");
});

test("date formatting localizes valid ISO timestamps for all three locales", () => {
  const value = "2024-05-30T14:30:00+08:00";
  const options = { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Shanghai" };
  const formatted = ["zh-CN", "en", "ja"].map((locale) => formatDateForLocale(locale, value, options));
  assert.deepEqual(formatted, [
    new Intl.DateTimeFormat("zh-CN", options).format(new Date(value)),
    new Intl.DateTimeFormat("en", options).format(new Date(value)),
    new Intl.DateTimeFormat("ja", options).format(new Date(value)),
  ]);
  assert.equal(new Set(formatted).size, 3);
});

test("number and date formatters preserve invalid input", () => {
  assert.equal(formatNumberForLocale("en", "not-a-number"), "not-a-number");
  assert.equal(formatDateForLocale("en", "not-a-date"), "not-a-date");
});

test("a doubly missing translation warns once per key in development", () => {
  const warnings = [];
  const originalWarn = console.warn;
  console.warn = (...values) => warnings.push(values.join(" "));
  try {
    const resources = { "zh-CN": {}, en: {}, ja: {} };
    assert.equal(translate(resources, "en", "test.once.missing"), "test.once.missing");
    assert.equal(translate(resources, "ja", "test.once.missing"), "test.once.missing");
    assert.equal(warnings.length, 1);
    assert.match(warnings[0], /test\.once\.missing/);
  } finally {
    console.warn = originalWarn;
  }
});

test("English and Japanese resource leaf keys exactly match Chinese", () => {
  const expected = collectLeafKeys(zhCN);
  assert.deepEqual(collectLeafKeys(en), expected, "English resource keys must match zh-CN exactly");
  assert.deepEqual(collectLeafKeys(ja), expected, "Japanese resource keys must match zh-CN exactly");
});

test("JSX and data modules contain no non-allowlisted Han UI literals", () => {
  const findings = walkFiles(sourceRoot).flatMap((file) => findHanLiterals(file)
    .filter(({ literal }) => !allowedHanContent.has(literal))
    .map(({ literal, line }) => `${path.relative(sourceRoot, file)}:${line}: ${JSON.stringify(literal)}`));
  assert.deepEqual(findings, [], `Untranslated Han UI literals:\n${findings.join("\n")}`);
});
