import { useEffect, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowRight,
  CheckCircle,
  FilmSlate,
  Gauge,
  Lightning,
  MagnifyingGlass,
  Microphone,
  Play,
  Scissors,
  ShieldCheck,
  Translate,
  Waveform,
} from "@phosphor-icons/react";
import { ThreeHeroScene } from "./ThreeHeroScene";
import { getHeroPoseStyle, resolveHeroPose } from "./heroThreeScene";

const analysisSteps = [
  { icon: MagnifyingGlass, title: "识别剧情冲突", text: "分析剧情与节奏点" },
  { icon: Microphone, title: "提取高光片段", text: "定位高能情绪瞬间" },
  { icon: CheckCircle, title: "生成解说文案", text: "匹配风格与配音" },
  { icon: Waveform, title: "配音字幕合成", text: "声音与字幕自动对齐" },
];

const shortcuts = [
  { icon: FilmSlate, tone: "violet", title: "短剧解说", text: "加旁白讲剧情" },
  { icon: Translate, tone: "cyan", title: "视频翻译", text: "多语言翻译配音" },
  { icon: Scissors, tone: "orange", title: "短剧混剪", text: "智能提取高能片段" },
];

const benefits = [
  { icon: Lightning, title: "AI 智能提取", text: "高能片段" },
  { icon: Waveform, title: "自动配音字幕", text: "一键合成" },
  { icon: Gauge, title: "节奏快不拖沓", text: "适配平台算法" },
  { icon: ShieldCheck, title: "多格式导出", text: "高清无水印" },
];

function AnalysisList() {
  return (
    <div className="analysis-list">
      <div className="micro-heading">AI 处理流程</div>
      {analysisSteps.map(({ icon: Icon, title, text }, index) => (
        <div className="analysis-step" key={title}>
          <span className="analysis-step__icon"><Icon size={16} weight="bold" /></span>
          <span className="analysis-step__copy"><strong>{title}</strong><small>{text}</small></span>
          {index === analysisSteps.length - 1
            ? <span className="analysis-step__loader" aria-label="处理中" />
            : <CheckCircle className="analysis-step__check" size={17} weight="fill" />}
          {index < analysisSteps.length - 1 && <span className="analysis-step__line" />}
        </div>
      ))}
      <div className="analysis-progress"><span /></div>
      <small className="analysis-progress__label">预计还需 30 秒完成</small>
    </div>
  );
}

function VideoPreview() {
  return (
    <div className="video-preview">
      <span className="video-preview__ratio">9:16</span>
      <img src="/assets/hero-drama-vertical.webp" alt="都市短剧成片预览" fetchPriority="high" decoding="async" />
      <div className="video-preview__shade" />
      <div className="video-preview__title">命运的<br />反转</div>
      <div className="video-preview__subtitle">这一刻，他终于<br />发现自己爱上了她</div>
      <div className="video-preview__controls"><Play size={13} weight="fill" /><span>00:12 / 00:30</span><span className="control-line" /></div>
    </div>
  );
}

function ShortcutCards() {
  return (
    <div className="shortcut-stack">
      {shortcuts.map(({ icon: Icon, tone, title, text }) => (
        <div className={`shortcut-card shortcut-card--${tone}`} key={title}>
          <span className="shortcut-card__icon"><Icon size={27} weight="duotone" /></span>
          <span><strong>{title}</strong><small>{text}</small></span>
          <ArrowRight size={17} />
        </div>
      ))}
    </div>
  );
}

function Timeline() {
  const bars = [18, 38, 25, 52, 31, 47, 70, 43, 62, 28, 53, 76, 39, 56, 30, 68, 44, 58, 24, 50, 34, 64, 45, 30, 71, 42, 55, 26, 63, 39];
  return (
    <div className="timeline">
      <div className="timeline__ruler"><span>00:00</span><span>00:05</span><span>00:10</span><span>00:15</span><span>00:20</span><span>00:25</span><span>00:30</span></div>
      <div className="timeline__row timeline__row--clips">
        <span className="timeline__label">视频片段</span>
        <div className="timeline__clipstrip">
          {[0, 1, 2, 3, 4, 5].map((item) => <img key={item} src="/assets/d01/sample-urban.png" alt="" decoding="async" />)}
        </div>
      </div>
      <div className="timeline__row timeline__row--captions"><span className="timeline__label">解说文案</span><div className="caption-blocks"><span>这场相遇…</span><span>命运的反转</span><span>真相揭开</span><span>新的开始</span></div></div>
      <div className="timeline__row"><span className="timeline__label">配音音频</span><div className="wave-track wave-track--blue">{bars.map((height, i) => <i key={i} style={{ height: `${height}%` }} />)}</div></div>
      <div className="timeline__row"><span className="timeline__label">背景音乐</span><div className="wave-track wave-track--orange">{[...bars].reverse().map((height, i) => <i key={i} style={{ height: `${Math.max(14, height - 10)}%` }} />)}</div></div>
      <span className="timeline__playhead" />
    </div>
  );
}

function HeroWorkbench({ workbenchRef }) {
  return (
    <div ref={workbenchRef} className="hero-workbench-wrap" aria-label="AI 视频出片工作台预览">
      <div className="hero-workbench neon-frame">
        <div className="hero-workbench__topline"><span>创作点 <strong>1,280</strong></span><button type="button">充值</button></div>
        <div className="hero-workbench__columns">
          <AnalysisList />
          <VideoPreview />
          <ShortcutCards />
        </div>
        <Timeline />
      </div>
      <div className="hero-workbench__reflection" aria-hidden="true" />
    </div>
  );
}

export function HeroSection({ onStart, onViewDemo }) {
  const heroRef = useRef(null);
  const workbenchRef = useRef(null);
  const [poseName, setPoseName] = useState(() => (
    resolveHeroPose(typeof window === "undefined" ? 1261 : window.innerWidth)
  ));

  useEffect(() => {
    const updateHeroPose = () => {
      const nextPoseName = resolveHeroPose(window.innerWidth);
      setPoseName((currentPoseName) => (
        currentPoseName === nextPoseName ? currentPoseName : nextPoseName
      ));
    };

    updateHeroPose();
    window.addEventListener("resize", updateHeroPose);

    return () => window.removeEventListener("resize", updateHeroPose);
  }, []);

  return (
    <section
      id="hero"
      ref={heroRef}
      className="hero-section"
      data-hero-pose={poseName}
      style={getHeroPoseStyle(poseName)}
    >
      <div className="hero-atmosphere" aria-hidden="true"><span /><span /><span /></div>
      <div className="hero-grid-floor" aria-hidden="true" />
      <div className="hero-mirror-floor" aria-hidden="true">
        <span className="hero-mirror-floor__horizon" />
        <div className="hero-mirror-floor__copy-reflection">
          <i />
          <i />
          <i />
          <i />
        </div>
        <div className="hero-mirror-floor__workbench-reflection">
          <i />
          <i />
          <i />
        </div>
      </div>
      <ThreeHeroScene heroRef={heroRef} workbenchRef={workbenchRef} poseName={poseName} />
      <div className="hero-main page-container">
        <div className="hero-copy">
          <div className="eyebrow">AI 视频创作 · 小白也能做专业视频</div>
          <h1 data-route-heading tabIndex="-1"><span>专为自媒体小白打造的</span><strong>AI 出片工作台</strong></h1>
          <p>
            <span className="hero-description--desktop">上传素材，AI 自动完成剪辑、文案、配音、字幕与合成。短剧解说、视频翻译、智能混剪，一个工作台搞定。</span>
            <span className="hero-description--mobile">上传素材，AI 自动完成剪辑、文案、配音、字幕与合成。</span>
          </p>
          <div className="hero-actions">
            <button className="primary-button" type="button" onClick={onStart}>开始创作 <ArrowRight size={22} /></button>
            <button className="secondary-button" type="button" onClick={onViewDemo}><Play size={18} weight="fill" /> 查看案例</button>
          </div>
        </div>
        <HeroWorkbench workbenchRef={workbenchRef} />
      </div>
      <div className="benefit-row page-container">
        {benefits.map(({ icon: Icon, title, text }, index) => (
          <div className={`benefit-item benefit-item--${index + 1}`} key={title}>
            <Icon size={39} weight="duotone" />
            <span><strong>{title}</strong><small>{text}</small></span>
          </div>
        ))}
      </div>
      <button className="hero-scroll-cue" type="button" aria-label="查看案例" onClick={onViewDemo}><ArrowDown size={26} /></button>
    </section>
  );
}
