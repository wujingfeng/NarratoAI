import {
  Gauge,
  Lightning,
  ShieldCheck,
  Waveform,
} from "@phosphor-icons/react";

const benefits = [
  { icon: Lightning, title: "AI 智能提取", text: "高能片段", tone: "cyan" },
  { icon: Waveform, title: "自动配音字幕", text: "一键合成", tone: "violet" },
  { icon: Gauge, title: "节奏快不拖沓", text: "适配平台算法", tone: "purple" },
  { icon: ShieldCheck, title: "多格式导出", text: "高清无水印", tone: "blue" },
];

export function BenefitStrip() {
  return (
    <section className="benefit-strip" aria-label="产品核心能力">
      {benefits.map((benefit) => {
        const Icon = benefit.icon;
        return (
          <article className={`benefit benefit--${benefit.tone}`} key={benefit.title}>
            <Icon weight="duotone" aria-hidden="true" />
            <p><strong>{benefit.title}</strong><span>{benefit.text}</span></p>
          </article>
        );
      })}
    </section>
  );
}
