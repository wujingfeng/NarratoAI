import {
  ArrowRight,
  CloudArrowUp,
  Cpu,
  DownloadSimple,
  FilmSlate,
  MagicWand,
  Scissors,
  Sparkle,
  Translate,
  UserFocus,
  VideoCamera,
} from "@phosphor-icons/react";

const capabilities = [
  {
    id: "narration",
    tone: "violet",
    icon: FilmSlate,
    title: "短剧解说",
    subtitle: "小白也能做短剧号",
    features: "高光片段 · 解说文案 · AI 配音 · 字幕 · BGM",
  },
  {
    id: "translation",
    tone: "cyan",
    icon: Translate,
    title: "视频翻译",
    subtitle: "让内容跨越语言",
    features: "字幕翻译 · 重新配音 · 双语字幕",
  },
  {
    id: "remix",
    tone: "orange",
    icon: Scissors,
    title: "短剧混剪",
    subtitle: "不用懂剪辑",
    features: "高光片段 · 保留原声 · BGM",
  },
];

const processSteps = [
  { icon: CloudArrowUp, label: "上传素材" },
  { icon: Cpu, label: "AI 分析" },
  { icon: UserFocus, label: "用户审核" },
  { icon: VideoCamera, label: "自动合成" },
  { icon: DownloadSimple, label: "导出发布" },
];

function CapabilityCard({ item, selected, onChoose }) {
  const Icon = item.icon;
  return (
    <article className={`capability-card capability-card--${item.tone} ${selected ? "is-selected" : ""}`}>
      <div className="capability-card__copy">
        <span className="capability-card__icon"><Icon size={35} weight="duotone" /></span>
        <h3>{item.title}</h3>
        <p>{item.subtitle}</p>
        <small>{item.features}</small>
        <button type="button" onClick={() => onChoose(item.id)}>立即体验 <ArrowRight size={17} /></button>
      </div>
      <div className="capability-orbit" aria-hidden="true">
        <span className="capability-orbit__halo" />
        <span className="capability-orbit__core"><Icon size={76} weight="duotone" /></span>
        <i /><i /><i />
      </div>
    </article>
  );
}

function ProcessStepper() {
  return (
    <div className="process-panel">
      <div className="process-steps">
        {processSteps.map(({ icon: Icon, label }, index) => (
          <div className="process-step" key={label}>
            <div className="process-step__node"><Icon size={28} weight="duotone" /></div>
            <span><b>{index + 1}</b>{label}</span>
            {index < processSteps.length - 1 && <i className="process-step__connector" />}
          </div>
        ))}
      </div>
      <div className="process-note"><Sparkle size={30} weight="duotone" /><p>小白可以沿用 AI 推荐，<br />有经验也能逐步调整</p></div>
    </div>
  );
}

export function CapabilitySection({ activeTool, onChooseTool }) {
  return (
    <section id="capabilities" className="capability-section section-anchor page-container">
      <div className="capability-heading">
        <span className="section-kicker">ALL-IN-ONE WORKSPACE</span>
        <h2>一个工作台，搞定<span className="gradient-text">三种视频创作</span></h2>
        <p><MagicWand size={18} weight="duotone" /> 选择目标，剩下的交给 AI 流程</p>
      </div>
      <div className="capability-grid">
        {capabilities.map((item) => (
          <CapabilityCard key={item.id} item={item} selected={activeTool === item.id} onChoose={onChooseTool} />
        ))}
      </div>
      <ProcessStepper />
    </section>
  );
}
