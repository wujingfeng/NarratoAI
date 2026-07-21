import { useId, useRef, useState } from "react";
import "../styles/demo-workbenches.css";
import {
  AnchorSimple,
  ArrowsHorizontal,
  ArrowsOut,
  ArrowRight,
  Check,
  CheckCircle,
  FileText,
  FilmSlate,
  Microphone,
  Play,
  Scissors,
  Star,
  Translate,
  Waveform,
} from "@phosphor-icons/react";
import { useI18n } from "../i18n/useI18n.js";

export const TOOL_DATA = {
  narration: {
    icon: FilmSlate,
    tone: "violet",
    duration: "01:25",
    elapsed: "00:12",
    stepCount: 5,
  },
  translation: {
    icon: Translate,
    tone: "cyan",
    duration: "01:08",
    elapsed: "00:18",
    stepCount: 4,
  },
  remix: {
    icon: Scissors,
    tone: "orange",
    duration: "00:45",
    elapsed: "00:09",
    stepCount: 3,
  },
};

const CASE_SETS = {
  narration: [
    { id: "reversal", image: "/assets/short-drama-thumb.webp", duration: "01:25", playingElapsed: "00:18", progress: 34 },
    { id: "suspense", image: "/assets/documentary-thumb.webp", duration: "01:10", playingElapsed: "00:16", progress: 29 },
    { id: "counterattack", image: "/assets/film-action-thumb.webp", duration: "01:18", playingElapsed: "00:17", progress: 31 },
  ],
  translation: [
    { id: "global", image: "/assets/documentary-thumb.webp", duration: "01:08", playingElapsed: "00:18", progress: 36 },
    { id: "dramaEn", image: "/assets/short-drama-thumb.webp", duration: "00:58", playingElapsed: "00:14", progress: 30 },
    { id: "urbanJp", image: "/assets/film-action-thumb.webp", duration: "01:12", playingElapsed: "00:19", progress: 33 },
  ],
  remix: [
    { id: "urban", image: "/assets/film-action-thumb.webp", duration: "00:45", playingElapsed: "00:09", progress: 24 },
    { id: "romanceRemix", image: "/assets/short-drama-thumb.webp", duration: "00:45", playingElapsed: "00:11", progress: 28 },
    { id: "cinemaRemix", image: "/assets/documentary-thumb.webp", duration: "00:45", playingElapsed: "00:10", progress: 26 },
  ],
};

function localizeToolData(t) {
  return Object.fromEntries(Object.entries(TOOL_DATA).map(([id, tool]) => [id, {
    ...tool,
    label: t(`home.demo.tools.${id}.label`),
    summaryBadge: t(`home.demo.tools.${id}.summaryBadge`),
    preview: {
      beforeLabel: t(`home.demo.tools.${id}.preview.beforeLabel`),
      afterLabel: t(`home.demo.tools.${id}.preview.afterLabel`),
      beforeAlt: t(`home.demo.tools.${id}.preview.beforeAlt`),
      afterAlt: t(`home.demo.tools.${id}.preview.afterAlt`),
      titleLines: [t(`home.demo.tools.${id}.preview.titleLine1`), t(`home.demo.tools.${id}.preview.titleLine2`)],
      detailLines: [t(`home.demo.tools.${id}.preview.detailLine1`), t(`home.demo.tools.${id}.preview.detailLine2`)],
    },
    steps: Array.from({ length: tool.stepCount }, (_, index) => ({
      title: t(`home.demo.tools.${id}.steps.step${index + 1}.title`),
      text: t(`home.demo.tools.${id}.steps.step${index + 1}.text`),
    })),
    cta: t(`home.demo.tools.${id}.cta`),
  }]));
}

function localizeCaseSets(t, tools) {
  return Object.fromEntries(Object.entries(CASE_SETS).map(([toolId, cases]) => [toolId, cases.map((item) => ({
    ...item,
    title: t(`home.demo.cases.${item.id}.title`),
    toolName: tools[toolId].label,
    tags: [1, 2, 3].map((index) => t(`home.demo.cases.${item.id}.tag${index}`)),
  }))]));
}

function ToolTabs({ activeTool, onToolChange, tools, t }) {
  const tabRefs = useRef(new Map());
  const toolIds = Object.keys(tools);

  const activateAndFocus = (nextIndex) => {
    const nextId = toolIds[(nextIndex + toolIds.length) % toolIds.length];
    onToolChange(nextId);
    requestAnimationFrame(() => tabRefs.current.get(nextId)?.focus());
  };

  const handleKeyDown = (event, index) => {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      activateAndFocus(index + 1);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      activateAndFocus(index - 1);
    } else if (event.key === "Home") {
      event.preventDefault();
      activateAndFocus(0);
    } else if (event.key === "End") {
      event.preventDefault();
      activateAndFocus(toolIds.length - 1);
    }
  };

  return (
    <div className="tool-tabs" role="tablist" aria-label={t("home.demo.toolTabsLabel")}>
      {Object.entries(tools).map(([id, tool], index) => {
        const Icon = tool.icon;
        return (
          <button
            key={id}
            ref={(node) => {
              if (node) tabRefs.current.set(id, node);
              else tabRefs.current.delete(id);
            }}
            id={`tool-tab-${id}`}
            type="button"
            role="tab"
            aria-selected={activeTool === id}
            aria-controls="tool-demo-panel"
            tabIndex={activeTool === id ? 0 : -1}
            className={`tool-tab tool-tab--${tool.tone} ${activeTool === id ? "is-active" : ""}`}
            onClick={() => onToolChange(id)}
            onKeyDown={(event) => handleKeyDown(event, index)}
          >
            <Icon size={24} weight="duotone" />{tool.label}
          </button>
        );
      })}
    </div>
  );
}

function NarrationComparePreview({ tool, value, onChange }) {
  const { t } = useI18n();
  const rangeId = useId();
  const { preview } = tool;
  return (
    <div className="narration-compare">
      <div className="narration-compare__stage">
        <img className="compare-image compare-image--before" src="/assets/short-drama-thumb.webp" alt={preview.beforeAlt} loading="lazy" decoding="async" />
        <div className="compare-after" style={{ width: `${value}%` }}>
          <img className="compare-image compare-image--after" style={{ width: `${10000 / value}%` }} src="/assets/film-action-thumb.webp" alt={preview.afterAlt} loading="lazy" decoding="async" />
        </div>
        <span className="compare-badge compare-badge--left">{preview.beforeLabel}</span>
        <span className="compare-badge compare-badge--right">{preview.afterLabel}</span>
        <div className="compare-divider" style={{ left: `${value}%` }}><span><ArrowsHorizontal size={19} weight="bold" /></span></div>
        <div className="compare-copy">
          <strong>{preview.titleLines.map((line, index) => <span key={line}>{line}{index < preview.titleLines.length - 1 && <br />}</span>)}</strong>
          <small>{preview.detailLines.map((line, index) => <span key={line}>{line}{index < preview.detailLines.length - 1 && <br />}</span>)}</small>
        </div>
        <div className="compare-player"><Play size={15} weight="fill" /><span>{tool.elapsed} / {tool.duration}</span><i /><ArrowsOut size={15} /></div>
      </div>
      <label className="sr-only" htmlFor={rangeId}>{t("home.demo.compareLabel", { before: preview.beforeLabel, after: preview.afterLabel })}</label>
      <input id={rangeId} className="compare-range" type="range" min="18" max="82" value={value} onChange={(event) => onChange(Number(event.target.value))} />
    </div>
  );
}

function NarrationStudio({ tool, onPlay }) {
  const { t } = useI18n();
  const [compareValue, setCompareValue] = useState(52);

  return (
    <div className="narration-studio">
      <div className="narration-studio__pipeline">
        <div className="narration-studio__pipeline-heading">
          <span>{t("home.demo.narration.pipelineTitle")}</span>
          <small>{t("home.demo.narration.pipelineStatus")}</small>
        </div>
        <ol>
          {tool.steps.map((step, index) => {
            const isComplete = index < 3;
            const isActive = index === 3;
            return (
              <li
                className={`${isComplete ? "is-complete" : ""} ${isActive ? "is-active" : ""}`}
                data-flow-step={index + 1}
                key={step.title}
              >
                <span>{isComplete ? <Check size={13} weight="bold" /> : index + 1}</span>
                <div><strong>{step.title}</strong><small>{step.text}</small></div>
              </li>
            );
          })}
        </ol>
      </div>

      <div className="narration-studio__workspace">
        <aside className="narration-assets" aria-label={t("home.demo.narration.assetQueueAria")}>
          <header><span>{t("home.demo.narration.assetQueue")}</span><small>{t("home.demo.narration.assetSummary")}</small></header>
          <div className="narration-assets__list">
            {[
              [1, "03:02", "/assets/d01/sample-urban.png"],
              [2, "02:51", "/assets/d06/romance.png"],
              [3, "02:53", "/assets/short-drama-thumb.webp"],
            ].map(([episode, duration, image], index) => (
              (() => {
                const name = t("home.demo.narration.episode", { number: String(episode).padStart(2, "0") });
                return (
              <article className={index === 1 ? "is-selected" : ""} key={name}>
                <img src={image} alt="" loading="lazy" decoding="async" />
                <span><strong>{name}</strong><small>{duration} · {t("home.demo.narration.analyzed")}</small></span>
                <CheckCircle size={17} weight="fill" />
              </article>
                );
              })()
            ))}
          </div>
          <div className="narration-assets__insight">
            <Star size={18} weight="duotone" />
            <span><strong>{t("home.demo.narration.insightTitle")}</strong><small>{t("home.demo.narration.insightSummary")}</small></span>
          </div>
        </aside>

        <main className="narration-editor">
          <NarrationComparePreview tool={tool} value={compareValue} onChange={setCompareValue} />
          <section className="narration-script" aria-label={t("home.demo.narration.scriptEditorAria")}>
            <div className="narration-script__tabs"><button type="button">{t("home.demo.narration.storyUnderstanding")}</button><button className="is-active" type="button">{t("home.demo.narration.script")}</button></div>
            <div className="narration-script__hook"><span>{t("home.demo.narration.strongHook")}</span><em>{t("home.demo.narration.recommended")}</em></div>
            <textarea aria-label={t("home.demo.narration.script")} defaultValue="婚礼当天，她亲手撕碎了所有人的谎言。谁也没想到，那个被赶出家门的女孩，才是真正掌控全局的人……" />
            <footer><span>{t("home.demo.narration.scriptMeta")}</span><button type="button"><FileText size={15} />{t("home.demo.narration.polish")}</button></footer>
          </section>
        </main>

        <aside className="narration-output" aria-label={t("home.demo.narration.outputAria")}>
          <header><span>{t("home.demo.narration.output")}</span><em>{t("home.demo.narration.almostDone")}</em></header>
          <div className="narration-output__score"><strong>92</strong><span>{t("home.demo.narration.scoreLabel")}<small>{t("home.demo.narration.scoreDetail")}</small></span></div>
          <ul>
            {[AnchorSimple, Microphone, FileText, Waveform].map((Icon, index) => <li key={index}><Icon size={18} weight="duotone" /><span><strong>{t(`home.demo.narration.outputItems.item${index + 1}.title`)}</strong><small>{t(`home.demo.narration.outputItems.item${index + 1}.detail`)}</small></span><Check size={15} /></li>)}
          </ul>
          <button className="narration-output__play" type="button" onClick={onPlay}><Play size={17} weight="fill" />{tool.cta}</button>
        </aside>
      </div>
    </div>
  );
}

function TranslationLocalizer({ tool, onPlay }) {
  const { t } = useI18n();
  const dialogueRows = [
    ["林夏", "我不会再替任何人承担错误。", "I won't take the blame for anyone again.", `Ava · ${t("home.demo.translation.calmFemaleVoice")}`],
    ["顾言", "你早就知道真相，对吗？", "You knew the truth all along, didn't you?", `Ethan · ${t("home.demo.translation.deepMaleVoice")}`],
    ["林夏", "从你签下那份协议开始。", "Since the moment you signed that agreement.", `Ava · ${t("home.demo.translation.calmFemaleVoice")}`],
  ];

  return (
    <div className="translation-localizer">
      <header className="translation-localizer__header">
        <div><strong>{t("home.demo.translation.title")}</strong><small>{t("home.demo.translation.summary")}</small></div>
        <div className="translation-language-pair" aria-label={t("home.demo.translation.languageSettingsAria")}>
          <label>{t("home.demo.translation.sourceLanguage")}<select aria-label={t("home.demo.translation.sourceLanguage")} defaultValue="zh"><option value="zh">简体中文</option></select></label>
          <ArrowsHorizontal size={20} weight="bold" />
          <label>{t("home.demo.translation.targetLanguage")}<select aria-label={t("home.demo.translation.targetLanguage")} defaultValue="en"><option value="en">English</option><option value="ja">日本語</option></select></label>
        </div>
      </header>

      <ol className="translation-localizer__flow" aria-label={t("home.demo.translation.flowAria")}>
        {tool.steps.map((step, index) => (
          <li className={index < 2 ? "is-complete" : index === 2 ? "is-active" : ""} data-flow-step={index + 1} key={step.title}>
            <span>{index < 2 ? <Check size={13} weight="bold" /> : index + 1}</span>
            <div><strong>{step.title}</strong><small>{step.text}</small></div>
          </li>
        ))}
      </ol>

      <div className="translation-localizer__workspace">
        <section className="translation-preview" aria-label={t("home.demo.translation.previewAria")}>
          <div className="translation-preview__screen">
            <img src="/assets/short-drama-thumb.webp" alt={t("home.demo.translation.previewAlt")} loading="lazy" decoding="async" />
            <span className="translation-preview__badge">{tool.summaryBadge}</span>
            <div className="bilingual-subtitles">
              <p className="bilingual-subtitles__source" lang="zh-CN">你早就知道真相，对吗？</p>
              <p className="bilingual-subtitles__target" lang="en">You knew the truth all along, didn't you?</p>
            </div>
            <div className="translation-preview__player"><Play size={14} weight="fill" /><span>{tool.elapsed} / {tool.duration}</span><i /></div>
          </div>
          <div className="translation-dialogues" aria-label={t("home.demo.translation.dialogueEditorAria")}>
            {dialogueRows.map(([role, source, target]) => (
              <article key={`${role}-${source}`}>
                <span>{role}</span>
                <div><p lang="zh-CN">{source}</p><p lang="en">{target}</p></div>
                <button type="button" aria-label={t("home.demo.translation.editTranslation", { role })}><FileText size={16} /></button>
              </article>
            ))}
          </div>
        </section>

        <aside className="voice-mapping" aria-label={t("home.demo.translation.voiceMappingAria")}>
          <header><span>{t("home.demo.translation.voiceMapping")}</span><em>{t("home.demo.translation.matched")}</em></header>
          <div className="voice-mapping__list">
            {dialogueRows.map(([role, , , voice], index) => (
              <article key={`${role}-${index}`}>
                <span className="voice-mapping__avatar">{role.slice(0, 1)}</span>
                <div><strong>{role}</strong><small>{voice}</small></div>
                <button type="button" aria-label={t("home.demo.translation.previewVoice", { role })}><Play size={13} weight="fill" /></button>
              </article>
            ))}
          </div>
          <div className="voice-mapping__check"><CheckCircle size={20} weight="fill" /><span><strong>{t("home.demo.translation.checkComplete")}</strong><small>{t("home.demo.translation.checkDetail")}</small></span></div>
          <button className="voice-mapping__play" type="button" onClick={onPlay}><Play size={17} weight="fill" />{tool.cta}</button>
        </aside>
      </div>
    </div>
  );
}

function RemixConsole({ tool, onPlay }) {
  const { t } = useI18n();
  const clips = [
    [t("home.demo.remix.clips.clip1"), "00:03.2", "/assets/film-action-thumb.webp", "98"],
    [t("home.demo.remix.clips.clip2"), "00:04.8", "/assets/d06/romance.png", "94"],
    [t("home.demo.remix.clips.clip3"), "00:05.1", "/assets/short-drama-thumb.webp", "91"],
    [t("home.demo.remix.clips.clip4"), "00:03.9", "/assets/documentary-thumb.webp", "89"],
  ];

  return (
    <div className="remix-console">
      <header className="remix-console__header">
        <div><strong>{t("home.demo.remix.title")}</strong><small>{t("home.demo.remix.summary")}</small></div>
        <ol aria-label={t("home.demo.remix.flowAria")}>
          {tool.steps.map((step, index) => (
            <li className={index < 2 ? "is-complete" : "is-active"} data-flow-step={index + 1} key={step.title}>
              <span>{index < 2 ? <Check size={13} weight="bold" /> : index + 1}</span>
              <div><strong>{step.title}</strong><small>{step.text}</small></div>
            </li>
          ))}
        </ol>
      </header>

      <div className="remix-console__workspace">
        <aside className="clip-pool" aria-label={t("home.demo.remix.clipPoolAria")}>
          <header><span>{t("home.demo.remix.clipPool")}</span><small>{t("home.demo.remix.sortedByIntensity")}</small></header>
          <div className="clip-pool__list">
            {clips.map(([title, duration, image, score], index) => (
              <button className={index < 3 ? "is-selected" : ""} type="button" key={title}>
                <img src={image} alt="" loading="lazy" decoding="async" />
                <span><strong>{title}</strong><small>{duration}</small></span>
                <em>{score}</em>
              </button>
            ))}
          </div>
        </aside>

        <main className="remix-monitor">
          <div className="remix-monitor__screen">
            <img src="/assets/film-action-thumb.webp" alt={t("home.demo.remix.previewAlt")} loading="lazy" decoding="async" />
            <span>{t("home.demo.remix.previewBadge")}</span>
            <button type="button" aria-label={t("home.demo.remix.playPreview")}><Play size={22} weight="fill" /></button>
            <div><small>{tool.elapsed}</small><i /><small>{tool.duration}</small></div>
          </div>
          <section className="remix-timeline" aria-label={t("home.demo.remix.timelineAria")}>
            <div className="remix-timeline__ruler"><span>00:00</span><span>00:15</span><span>00:30</span><span>00:45</span></div>
            <div className="remix-track remix-track--video"><strong>{t("home.demo.remix.videoTrack")}</strong><div>{clips.map(([title], index) => <span className={`clip-${index + 1}`} key={title}>{title}</span>)}</div></div>
            <div className="remix-track remix-track--original"><strong>{t("home.demo.remix.originalAudio")}</strong><div><Waveform size={420} weight="fill" /></div></div>
            <div className="remix-track remix-track--bgm"><strong>BGM</strong><div><Waveform size={420} weight="fill" /></div></div>
            <span className="remix-timeline__playhead" />
          </section>
        </main>

        <aside className="beat-controls" aria-label={t("home.demo.remix.beatControlsAria")}>
          <header><span>{t("home.demo.remix.beatControls")}</span><em>{t("home.demo.remix.synced")}</em></header>
          <div className="beat-controls__track"><Waveform size={22} weight="duotone" /><span><strong>Neon Pulse</strong><small>{t("home.demo.remix.musicStyle")}</small></span><button type="button" aria-label={t("home.demo.remix.playMusic")}><Play size={13} weight="fill" /></button></div>
          <label><span>{t("home.demo.remix.beatIntensity")}<em>78%</em></span><input aria-label={t("home.demo.remix.beatIntensity")} type="range" min="0" max="100" defaultValue="78" /></label>
          <label><span>{t("home.demo.remix.originalVolume")}<em>82%</em></span><input aria-label={t("home.demo.remix.originalVolume")} type="range" min="0" max="100" defaultValue="82" /></label>
          <label><span>{t("home.demo.remix.bgmVolume")}<em>36%</em></span><input aria-label={t("home.demo.remix.bgmVolume")} type="range" min="0" max="100" defaultValue="36" /></label>
          <div className="beat-controls__markers"><span>{t("home.demo.remix.beatPoints")}</span><span>{t("home.demo.remix.transitions")}</span><span>{t("home.demo.remix.emptyBeats")}</span></div>
          <button className="beat-controls__play" type="button" onClick={onPlay}><Play size={17} weight="fill" />{tool.cta}</button>
        </aside>
      </div>
    </div>
  );
}

function CaseCard({ item, onOpen, onTemplate }) {
  const { t } = useI18n();
  return (
    <article className="case-card">
      <button className="case-card__image" type="button" onClick={() => onOpen(item)} aria-label={t("home.demo.playCase", { title: item.title })}>
        <img src={item.image} alt={t("home.demo.caseCoverAlt", { title: item.title })} loading="lazy" decoding="async" />
        <span><Play size={17} weight="fill" /></span>
      </button>
      <div className="case-card__body">
        <h3>{item.title}</h3>
        <div className="case-card__tags">{item.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
        <button type="button" onClick={() => onTemplate(item)}>{t("home.demo.useTemplate")} <ArrowRight size={16} /></button>
      </div>
    </article>
  );
}

export function DemoSection({ activeTool, onToolChange, onOpenCase, onTemplate }) {
  const { t } = useI18n();
  const tools = localizeToolData(t);
  const caseSets = localizeCaseSets(t, tools);
  const tool = tools[activeTool];
  const cases = caseSets[activeTool];
  const defaultCase = cases[0];

  return (
    <section id="demo" className="demo-section section-anchor">
      <div className="section-heading page-container">
        <span className="section-kicker">{t("home.demo.kicker")}</span>
        <h2>{t("home.demo.headingPrefix")} <span className="gradient-text">AI</span> {t("home.demo.headingSuffix")}</h2>
        <p>{t("home.demo.description")}</p>
      </div>
      <div className={`demo-shell demo-shell--${tool.tone} page-container`}>
        <ToolTabs activeTool={activeTool} onToolChange={onToolChange} tools={tools} t={t} />
        <div
          id="tool-demo-panel"
          className={`demo-workbench demo-workbench--${activeTool}`}
          data-tool-layout={activeTool}
          role="tabpanel"
          aria-labelledby={`tool-tab-${activeTool}`}
        >
          {activeTool === "narration" && <NarrationStudio tool={tool} onPlay={() => onOpenCase(defaultCase)} />}
          {activeTool === "translation" && <TranslationLocalizer tool={tool} onPlay={() => onOpenCase(defaultCase)} />}
          {activeTool === "remix" && <RemixConsole tool={tool} onPlay={() => onOpenCase(defaultCase)} />}
        </div>
      </div>
      <div className="case-grid page-container">
        {cases.map((item) => <CaseCard item={item} key={item.id} onOpen={onOpenCase} onTemplate={onTemplate} />)}
      </div>
    </section>
  );
}
