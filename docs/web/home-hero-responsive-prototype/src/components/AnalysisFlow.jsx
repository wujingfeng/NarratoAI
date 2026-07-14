import {
  Check,
  MagicWand,
  SpinnerGap,
  TextAa,
  UploadSimple,
  Waveform,
} from "@phosphor-icons/react";

const steps = [
  {
    title: "识别剧情冲突",
    description: "分析剧情 5 个冲突点",
    icon: UploadSimple,
    state: "done",
  },
  {
    title: "提取高光片段",
    description: "定位高能片段与情绪爆点",
    icon: MagicWand,
    state: "done",
  },
  {
    title: "生成解说文案",
    description: "结合剧情生成爆款文案",
    icon: TextAa,
    state: "done",
  },
  {
    title: "配音字幕合成",
    description: "AI 配音与字幕自动对齐",
    icon: Waveform,
    state: "active",
  },
];

export function AnalysisFlow() {
  return (
    <section className="analysis-flow" aria-labelledby="analysis-title">
      <div className="panel-section-heading">
        <span className="section-dot" aria-hidden="true" />
        <h2 id="analysis-title">AI 处理流程</h2>
      </div>

      <ol className="analysis-list">
        {steps.map((step, index) => {
          const Icon = step.icon;
          return (
            <li className={`analysis-step analysis-step--${step.state}`} key={step.title}>
              <span className="step-marker" aria-hidden="true">
                <Icon weight="duotone" />
              </span>
              <span className="step-copy">
                <strong>{step.title}</strong>
                <small>{step.description}</small>
              </span>
              <span className="step-state" aria-label={step.state === "done" ? "已完成" : "处理中"}>
                {step.state === "done" ? (
                  <Check weight="bold" />
                ) : (
                  <SpinnerGap className="spin" weight="bold" />
                )}
              </span>
              {index < steps.length - 1 ? <span className="flow-link" aria-hidden="true" /> : null}
            </li>
          );
        })}
      </ol>

      <div className="analysis-progress">
        <span>素材还原 30 秒完成</span>
        <div className="progress-track" aria-label="处理进度 72%">
          <span style={{ width: "72%" }} />
        </div>
      </div>
    </section>
  );
}
