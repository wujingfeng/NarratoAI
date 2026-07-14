import { ArrowRight, Sparkle } from "@phosphor-icons/react";

export function FinalCtaSection({ onStart }) {
  return (
    <section className="final-cta-panel" aria-labelledby="final-cta-title">
      <div className="final-cta-orbit" aria-hidden="true"><span /><span /><span /></div>
      <Sparkle className="final-cta-icon" size={42} weight="duotone" />
      <h2 id="final-cta-title">准备好完成你的第一条<span className="gradient-text">AI 成片</span>了吗？</h2>
      <button className="primary-button" type="button" onClick={onStart}>开始创作 <ArrowRight size={21} /></button>
      <p>真实生成前会透明展示预计消耗</p>
    </section>
  );
}
