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
import { useI18n } from "../i18n/useI18n.js";

const analysisSteps = [
  { id: "identify", icon: MagnifyingGlass },
  { id: "highlights", icon: Microphone },
  { id: "script", icon: CheckCircle },
  { id: "synthesis", icon: Waveform },
];

const shortcuts = [
  { id: "narration", icon: FilmSlate, tone: "violet" },
  { id: "translation", icon: Translate, tone: "cyan" },
  { id: "remix", icon: Scissors, tone: "orange" },
];

const benefits = [
  { id: "extract", icon: Lightning },
  { id: "synthesis", icon: Waveform },
  { id: "pace", icon: Gauge },
  { id: "export", icon: ShieldCheck },
];

function AnalysisList() {
  const { t } = useI18n();
  return (
    <div className="analysis-list">
      <div className="micro-heading">{t("home.hero.analysis.heading")}</div>
      {analysisSteps.map(({ id, icon: Icon }, index) => (
        <div className="analysis-step" key={id}>
          <span className="analysis-step__icon"><Icon size={16} weight="bold" /></span>
          <span className="analysis-step__copy"><strong>{t(`home.hero.analysis.steps.${id}.title`)}</strong><small>{t(`home.hero.analysis.steps.${id}.text`)}</small></span>
          {index === analysisSteps.length - 1
            ? <span className="analysis-step__loader" aria-label={t("home.hero.analysis.processing")} />
            : <CheckCircle className="analysis-step__check" size={17} weight="fill" />}
          {index < analysisSteps.length - 1 && <span className="analysis-step__line" />}
        </div>
      ))}
      <div className="analysis-progress"><span /></div>
      <small className="analysis-progress__label">{t("home.hero.analysis.eta")}</small>
    </div>
  );
}

function VideoPreview() {
  const { t } = useI18n();
  return (
    <div className="video-preview">
      <span className="video-preview__ratio">9:16</span>
      <img src="/assets/hero-drama-vertical.webp" alt={t("home.hero.preview.alt")} fetchPriority="high" decoding="async" />
      <div className="video-preview__shade" />
      <div className="video-preview__title">{t("home.hero.preview.titleLine1")}<br />{t("home.hero.preview.titleLine2")}</div>
      <div className="video-preview__subtitle">{t("home.hero.preview.subtitleLine1")}<br />{t("home.hero.preview.subtitleLine2")}</div>
      <div className="video-preview__controls"><Play size={13} weight="fill" /><span>00:12 / 00:30</span><span className="control-line" /></div>
    </div>
  );
}

function ShortcutCards() {
  const { t } = useI18n();
  return (
    <div className="shortcut-stack">
      {shortcuts.map(({ id, icon: Icon, tone }) => (
        <div className={`shortcut-card shortcut-card--${tone}`} key={id}>
          <span className="shortcut-card__icon"><Icon size={27} weight="duotone" /></span>
          <span><strong>{t(`home.hero.shortcuts.${id}.title`)}</strong><small>{t(`home.hero.shortcuts.${id}.text`)}</small></span>
          <ArrowRight size={17} />
        </div>
      ))}
    </div>
  );
}

function Timeline() {
  const { t } = useI18n();
  const bars = [18, 38, 25, 52, 31, 47, 70, 43, 62, 28, 53, 76, 39, 56, 30, 68, 44, 58, 24, 50, 34, 64, 45, 30, 71, 42, 55, 26, 63, 39];
  return (
    <div className="timeline">
      <div className="timeline__ruler"><span>00:00</span><span>00:05</span><span>00:10</span><span>00:15</span><span>00:20</span><span>00:25</span><span>00:30</span></div>
      <div className="timeline__row timeline__row--clips">
        <span className="timeline__label">{t("home.hero.timeline.video")}</span>
        <div className="timeline__clipstrip">
          {[0, 1, 2, 3, 4, 5].map((item) => <img key={item} src="/assets/d01/sample-urban.png" alt="" decoding="async" />)}
        </div>
      </div>
      <div className="timeline__row timeline__row--captions"><span className="timeline__label">{t("home.hero.timeline.captions")}</span><div className="caption-blocks">{[1, 2, 3, 4].map((id) => <span key={id}>{t(`home.hero.timeline.caption${id}`)}</span>)}</div></div>
      <div className="timeline__row"><span className="timeline__label">{t("home.hero.timeline.voice")}</span><div className="wave-track wave-track--blue">{bars.map((height, i) => <i key={i} style={{ height: `${height}%` }} />)}</div></div>
      <div className="timeline__row"><span className="timeline__label">{t("home.hero.timeline.bgm")}</span><div className="wave-track wave-track--orange">{[...bars].reverse().map((height, i) => <i key={i} style={{ height: `${Math.max(14, height - 10)}%` }} />)}</div></div>
      <span className="timeline__playhead" />
    </div>
  );
}

function HeroWorkbench({ workbenchRef }) {
  const { t } = useI18n();
  return (
    <div ref={workbenchRef} className="hero-workbench-wrap" aria-label={t("home.hero.workbench.ariaLabel")}>
      <div className="hero-workbench neon-frame">
        <div className="hero-workbench__topline"><span>{t("home.hero.workbench.credits")} <strong>1,280</strong></span><button type="button">{t("home.hero.workbench.recharge")}</button></div>
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
  const { t } = useI18n();
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
          <div className="eyebrow">{t("home.hero.eyebrow")}</div>
          <h1><span>{t("home.hero.headingPrefix")}</span><strong>{t("home.hero.headingAccent")}</strong></h1>
          <p>
            <span className="hero-description--desktop">{t("home.hero.descriptionDesktop")}</span>
            <span className="hero-description--mobile">{t("home.hero.descriptionMobile")}</span>
          </p>
          <div className="hero-actions">
            <button className="primary-button" type="button" onClick={onStart}>{t("home.hero.start")} <ArrowRight size={22} /></button>
            <button className="secondary-button" type="button" onClick={onViewDemo}><Play size={18} weight="fill" /> {t("home.hero.viewDemo")}</button>
          </div>
        </div>
        <HeroWorkbench workbenchRef={workbenchRef} />
      </div>
      <div className="benefit-row page-container">
        {benefits.map(({ id, icon: Icon }, index) => (
          <div className={`benefit-item benefit-item--${index + 1}`} key={id}>
            <Icon size={39} weight="duotone" />
            <span><strong>{t(`home.hero.benefits.${id}.title`)}</strong><small>{t(`home.hero.benefits.${id}.text`)}</small></span>
          </div>
        ))}
      </div>
      <button className="hero-scroll-cue" type="button" aria-label={t("home.hero.viewDemo")} onClick={onViewDemo}><ArrowDown size={26} /></button>
    </section>
  );
}
