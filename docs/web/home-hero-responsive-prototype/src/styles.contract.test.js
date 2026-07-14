import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const css = readFileSync(`${process.cwd()}/src/styles.css`, "utf8");

describe("hero visual effect contracts", () => {
  it("defines animated title and mirror sweeps with reduced-motion fallbacks", () => {
    expect(css).toMatch(/\.hero-title-shine\s*\{[^}]*animation:\s*hero-title-shine/s);
    expect(css).toMatch(/animation:\s*hero-title-shine\s+9\.6s/);
    expect(css).toMatch(/@keyframes\s+hero-title-shine/);
    expect(css).toMatch(/\.workbench-top-reflection\s+span\s*\{[^}]*animation:\s*mirror-sweep/s);
    expect(css).toMatch(/@keyframes\s+mirror-sweep/);

    const reducedMotion = css.match(/@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{([\s\S]*)\}\s*$/)?.[1] ?? "";
    expect(reducedMotion).toMatch(/\.hero-title-shine/);
    expect(reducedMotion).toMatch(/\.workbench-top-reflection\s+span/);
    expect(reducedMotion).toMatch(/animation:\s*none/);
  });

  it("sweeps the title highlight from left to right", () => {
    const keyframes = css.match(/@keyframes\s+hero-title-shine\s*\{([\s\S]*?)\n\}\n\n@keyframes\s+mirror-sweep/)?.[1] ?? "";
    const leftStart = keyframes.indexOf("background-position: -85% 0");
    const rightEnd = keyframes.indexOf("background-position: 190% 0");

    expect(leftStart).toBeGreaterThanOrEqual(0);
    expect(rightEnd).toBeGreaterThan(leftStart);
  });

  it("keeps the workbench in a preserved 3D scene with a transparent air gap", () => {
    expect(css).toMatch(/\.workbench-placement\s*\{[^}]*perspective\([^)]*\)[^}]*rotateX\([^)]*\)[^}]*rotateY\([^)]*\)[^}]*transform-style:\s*preserve-3d/s);
    expect(css).toMatch(/\.workbench-shell\s*\{[^}]*transform-style:\s*preserve-3d/s);
    expect(css).toMatch(/\.workbench-void-rail\s*\{[^}]*background:\s*transparent/s);
    expect(css).toMatch(/\.workbench-top-reflection\s*\{[^}]*linear-gradient[^}]*blur/s);
  });

  it("keeps the 1201–1279 desktop depth layers inside their available right gutter", () => {
    expect(css).toMatch(/width:\s*clamp\(640px,\s*56vw,\s*710px\)/);
    expect(css).toMatch(/\.workbench-depth-frame--far\s*\{[^}]*inset:\s*-7px\s+-8px\s+-13px\s+9px/s);
    expect(css).toMatch(/\.workbench-side-face\s*\{[^}]*right:\s*-10px/s);
  });
});
