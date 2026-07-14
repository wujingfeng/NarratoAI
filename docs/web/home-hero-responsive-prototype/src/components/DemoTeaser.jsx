import { forwardRef } from "react";
import { ArrowRight, CaretDown, Play } from "@phosphor-icons/react";

export const DemoTeaser = forwardRef(function DemoTeaser({ onCreate }, ref) {
  return (
    <section className="demo-teaser" ref={ref} aria-labelledby="demo-heading">
      <div className="demo-heading-wrap">
        <span className="demo-rule" aria-hidden="true" />
        <h2 id="demo-heading">案例 <em>Demo</em></h2>
        <span className="demo-rule" aria-hidden="true" />
      </div>
      <p>看 AI 如何把一段普通素材，变成节奏紧凑的高能成片。</p>
      <button type="button" onClick={onCreate}>
        <Play weight="fill" aria-hidden="true" />
        用这个案例开始创作
        <ArrowRight weight="bold" aria-hidden="true" />
      </button>
      <CaretDown className="demo-caret" weight="bold" aria-hidden="true" />
    </section>
  );
});
