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

export const TOOL_DATA = {
  narration: {
    label: "短剧解说",
    icon: FilmSlate,
    tone: "violet",
    duration: "01:25",
    elapsed: "00:12",
    summaryBadge: "00:00–00:03",
    preview: {
      beforeLabel: "原始素材",
      afterLabel: "最终成片",
      beforeAlt: "原始剧情素材",
      afterAlt: "AI 生成的短剧解说成片",
      titleLines: ["命运的", "反转"],
      detailLines: ["这一刻，他终于", "发现自己爱上了她"],
    },
    steps: [
      { title: "上传剧集", text: "3 集素材已进入队列" },
      { title: "ASR/剧情拆解", text: "识别人物、对白与剧情冲突" },
      { title: "筛选高光", text: "按反转与情绪强度选出 8 段" },
      { title: "生成/润色解说词", text: "口语化重写并校准叙事节奏" },
      { title: "配音字幕合成", text: "配音、字幕与画面自动对齐" },
    ],
    stats: [
      [AnchorSimple, "前 3 秒强钩子", "抓人开场，提升完播率"],
      [Star, "8 个高光片段", "反转 / 冲突 / 情绪高点全覆盖"],
      [FileText, "解说文案 312 字", "这一刻，他终于发现自己爱上了她…"],
      [Microphone, "配音字幕已同步", "自然配音 + 精准字幕对齐"],
    ],
    cta: "播放完整案例",
  },
  translation: {
    label: "视频翻译",
    icon: Translate,
    tone: "cyan",
    duration: "01:08",
    elapsed: "00:18",
    summaryBadge: "中文 → EN",
    preview: {
      beforeLabel: "中文原片",
      afterLabel: "英文成片",
      beforeAlt: "待翻译的中文原片",
      afterAlt: "完成英语本地化的视频成片",
      titleLines: ["跨越语言", "自然表达"],
      detailLines: ["保留人物语气", "英文对白自然流畅"],
    },
    steps: [
      { title: "识别中文对白", text: "区分角色并还原对白时间轴" },
      { title: "翻译与本地化", text: "优化称谓、语气与文化表达" },
      { title: "角色声线映射", text: "为每位角色匹配目标语音色" },
      { title: "英文配音+双语字幕", text: "配音与双语字幕自动对齐" },
    ],
    stats: [
      [Translate, "6 种目标语言", "英语 / 日语 / 韩语等常用语种"],
      [Waveform, "3 位角色声线", "角色音色与情绪保持一致"],
      [FileText, "双语字幕 86 条", "时间轴已自动校准"],
      [CheckCircle, "本地化检查完成", "专有名词与文化表达已优化"],
    ],
    cta: "播放翻译案例",
  },
  remix: {
    label: "短剧混剪",
    icon: Scissors,
    tone: "orange",
    duration: "00:45",
    elapsed: "00:09",
    summaryBadge: "12 个片段",
    preview: {
      beforeLabel: "原始剧集",
      afterLabel: "高光混剪",
      beforeAlt: "待处理的原始短剧片段",
      afterAlt: "保留原声并完成节奏转场的高光混剪",
      titleLines: ["高能", "混剪"],
      detailLines: ["保留原声 · 卡点转场", "节奏与 BGM 自动匹配"],
    },
    steps: [
      { title: "导入多集", text: "12 集素材已建立镜头索引" },
      { title: "选择高光", text: "按冲突、反转与情绪强度排序" },
      { title: "卡点拼接与混音", text: "保留原声并匹配节拍与 BGM" },
    ],
    stats: [
      [Star, "12 个高光片段", "高能剧情自动筛选"],
      [Waveform, "原声完整保留", "关键对白不被音乐遮盖"],
      [Scissors, "节奏点 18 处", "卡点转场与情绪峰值匹配"],
      [CheckCircle, "BGM 已完成混音", "动态音量平衡已应用"],
    ],
    cta: "播放混剪案例",
  },
};

const CASE_SETS = {
  narration: [
    { id: "reversal", title: "霸总反转", toolName: "短剧解说", image: "/assets/short-drama-thumb.webp", duration: "01:25", playingElapsed: "00:18", progress: 34, tags: ["反转密集", "情绪拉满", "高完播"] },
    { id: "suspense", title: "悬疑真相局", toolName: "短剧解说", image: "/assets/documentary-thumb.webp", duration: "01:10", playingElapsed: "00:16", progress: 29, tags: ["强钩子", "层层递进", "沉浸旁白"] },
    { id: "counterattack", title: "都市逆袭录", toolName: "短剧解说", image: "/assets/film-action-thumb.webp", duration: "01:18", playingElapsed: "00:17", progress: 31, tags: ["冲突前置", "节奏紧凑", "反转收尾"] },
  ],
  translation: [
    { id: "global", title: "多语言出海", toolName: "视频翻译", image: "/assets/documentary-thumb.webp", duration: "01:08", playingElapsed: "00:18", progress: 36, tags: ["多语翻译", "本地配音", "全球发行"] },
    { id: "drama-en", title: "短剧英语版", toolName: "视频翻译", image: "/assets/short-drama-thumb.webp", duration: "00:58", playingElapsed: "00:14", progress: 30, tags: ["英语配音", "双语字幕", "角色声线"] },
    { id: "urban-jp", title: "都市剧日语版", toolName: "视频翻译", image: "/assets/film-action-thumb.webp", duration: "01:12", playingElapsed: "00:19", progress: 33, tags: ["日语本地化", "口型节奏", "字幕校准"] },
  ],
  remix: [
    { id: "urban", title: "都市逆袭混剪", toolName: "短剧混剪", image: "/assets/film-action-thumb.webp", duration: "00:45", playingElapsed: "00:09", progress: 24, tags: ["节奏紧凑", "燃点爆发", "高能混剪"] },
    { id: "romance-remix", title: "心动名场面", toolName: "短剧混剪", image: "/assets/short-drama-thumb.webp", duration: "00:45", playingElapsed: "00:11", progress: 28, tags: ["情绪峰值", "保留原声", "氛围 BGM"] },
    { id: "cinema-remix", title: "电影感卡点", toolName: "短剧混剪", image: "/assets/documentary-thumb.webp", duration: "00:45", playingElapsed: "00:10", progress: 26, tags: ["镜头卡点", "节奏转场", "高光合集"] },
  ],
};

function ToolTabs({ activeTool, onToolChange }) {
  const tabRefs = useRef(new Map());
  const toolIds = Object.keys(TOOL_DATA);

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
    <div className="tool-tabs" role="tablist" aria-label="选择创作工具">
      {Object.entries(TOOL_DATA).map(([id, tool], index) => {
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
      <label className="sr-only" htmlFor={rangeId}>拖动查看{preview.beforeLabel}与{preview.afterLabel}</label>
      <input id={rangeId} className="compare-range" type="range" min="18" max="82" value={value} onChange={(event) => onChange(Number(event.target.value))} />
    </div>
  );
}

function NarrationStudio({ tool, onPlay }) {
  const [compareValue, setCompareValue] = useState(52);

  return (
    <div className="narration-studio">
      <div className="narration-studio__pipeline">
        <div className="narration-studio__pipeline-heading">
          <span>解说创作流程</span>
          <small>剧情理解完成 · 正在润色文案</small>
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
        <aside className="narration-assets" aria-label="已上传素材队列">
          <header><span>素材队列</span><small>3 集 · 08:46</small></header>
          <div className="narration-assets__list">
            {[
              ["第 01 集", "03:02", "/assets/d01/sample-urban.png", "已分析"],
              ["第 02 集", "02:51", "/assets/d06/romance.png", "已分析"],
              ["第 03 集", "02:53", "/assets/short-drama-thumb.webp", "已分析"],
            ].map(([name, duration, image, status], index) => (
              <article className={index === 1 ? "is-selected" : ""} key={name}>
                <img src={image} alt="" loading="lazy" decoding="async" />
                <span><strong>{name}</strong><small>{duration} · {status}</small></span>
                <CheckCircle size={17} weight="fill" />
              </article>
            ))}
          </div>
          <div className="narration-assets__insight">
            <Star size={18} weight="duotone" />
            <span><strong>剧情高点已定位</strong><small>反转 3 · 冲突 4 · 情绪峰值 5</small></span>
          </div>
        </aside>

        <main className="narration-editor">
          <NarrationComparePreview tool={tool} value={compareValue} onChange={setCompareValue} />
          <section className="narration-script" aria-label="剧情与解说文案编辑">
            <div className="narration-script__tabs"><button type="button">剧情理解</button><button className="is-active" type="button">解说文案</button></div>
            <div className="narration-script__hook"><span>强钩子 · 00:00–00:03</span><em>推荐</em></div>
            <textarea aria-label="解说文案" defaultValue="婚礼当天，她亲手撕碎了所有人的谎言。谁也没想到，那个被赶出家门的女孩，才是真正掌控全局的人……" />
            <footer><span>96 字 · 预计 23 秒</span><button type="button"><FileText size={15} />AI 润色</button></footer>
          </section>
        </main>

        <aside className="narration-output" aria-label="视频输出摘要">
          <header><span>视频输出</span><em>接近完成</em></header>
          <div className="narration-output__score"><strong>92</strong><span>专业度评分<small>节奏与钩子表现优秀</small></span></div>
          <ul>
            <li><AnchorSimple size={18} weight="duotone" /><span><strong>前 3 秒强钩子</strong><small>冲突信息已前置</small></span><Check size={15} /></li>
            <li><Microphone size={18} weight="duotone" /><span><strong>自然女声 · 1.05x</strong><small>情绪强度已匹配</small></span><Check size={15} /></li>
            <li><FileText size={18} weight="duotone" /><span><strong>动态高亮字幕</strong><small>安全区与断句已校准</small></span><Check size={15} /></li>
            <li><Waveform size={18} weight="duotone" /><span><strong>BGM 自动闪避</strong><small>对白区域降低 8dB</small></span><Check size={15} /></li>
          </ul>
          <button className="narration-output__play" type="button" onClick={onPlay}><Play size={17} weight="fill" />播放解说案例</button>
        </aside>
      </div>
    </div>
  );
}

function TranslationLocalizer({ tool, onPlay }) {
  const dialogueRows = [
    ["林夏", "我不会再替任何人承担错误。", "I won't take the blame for anyone again.", "Ava · 冷静女声"],
    ["顾言", "你早就知道真相，对吗？", "You knew the truth all along, didn't you?", "Ethan · 低沉男声"],
    ["林夏", "从你签下那份协议开始。", "Since the moment you signed that agreement.", "Ava · 冷静女声"],
  ];

  return (
    <div className="translation-localizer">
      <header className="translation-localizer__header">
        <div><strong>多语言本地化</strong><small>已识别 3 位角色 · 86 条对白</small></div>
        <div className="translation-language-pair" aria-label="翻译语言设置">
          <label>源语言<select aria-label="源语言" defaultValue="zh"><option value="zh">简体中文</option></select></label>
          <ArrowsHorizontal size={20} weight="bold" />
          <label>目标语言<select aria-label="目标语言" defaultValue="en"><option value="en">English</option><option value="ja">日本語</option></select></label>
        </div>
      </header>

      <ol className="translation-localizer__flow" aria-label="视频翻译流程">
        {tool.steps.map((step, index) => (
          <li className={index < 2 ? "is-complete" : index === 2 ? "is-active" : ""} data-flow-step={index + 1} key={step.title}>
            <span>{index < 2 ? <Check size={13} weight="bold" /> : index + 1}</span>
            <div><strong>{step.title}</strong><small>{step.text}</small></div>
          </li>
        ))}
      </ol>

      <div className="translation-localizer__workspace">
        <section className="translation-preview" aria-label="双语视频预览">
          <div className="translation-preview__screen">
            <img src="/assets/short-drama-thumb.webp" alt="中文短剧英文配音预览" loading="lazy" decoding="async" />
            <span className="translation-preview__badge">中文 → EN</span>
            <div className="bilingual-subtitles">
              <p className="bilingual-subtitles__source" lang="zh-CN">你早就知道真相，对吗？</p>
              <p className="bilingual-subtitles__target" lang="en">You knew the truth all along, didn't you?</p>
            </div>
            <div className="translation-preview__player"><Play size={14} weight="fill" /><span>{tool.elapsed} / {tool.duration}</span><i /></div>
          </div>
          <div className="translation-dialogues" aria-label="双语对白编辑">
            {dialogueRows.map(([role, source, target]) => (
              <article key={`${role}-${source}`}>
                <span>{role}</span>
                <div><p lang="zh-CN">{source}</p><p lang="en">{target}</p></div>
                <button type="button" aria-label={`编辑${role}的译文`}><FileText size={16} /></button>
              </article>
            ))}
          </div>
        </section>

        <aside className="voice-mapping" aria-label="角色声线映射">
          <header><span>角色声线映射</span><em>3 / 3 已匹配</em></header>
          <div className="voice-mapping__list">
            {dialogueRows.map(([role, , , voice], index) => (
              <article key={`${role}-${index}`}>
                <span className="voice-mapping__avatar">{role.slice(0, 1)}</span>
                <div><strong>{role}</strong><small>{voice}</small></div>
                <button type="button" aria-label={`试听${role}的英文声线`}><Play size={13} weight="fill" /></button>
              </article>
            ))}
          </div>
          <div className="voice-mapping__check"><CheckCircle size={20} weight="fill" /><span><strong>本地化检查完成</strong><small>专有名词、称谓和语气已优化</small></span></div>
          <button className="voice-mapping__play" type="button" onClick={onPlay}><Play size={17} weight="fill" />播放翻译案例</button>
        </aside>
      </div>
    </div>
  );
}

function RemixConsole({ tool, onPlay }) {
  const clips = [
    ["冲突爆发", "00:03.2", "/assets/film-action-thumb.webp", "98"],
    ["身份揭晓", "00:04.8", "/assets/d06/romance.png", "94"],
    ["绝地反击", "00:05.1", "/assets/short-drama-thumb.webp", "91"],
    ["情绪顶点", "00:03.9", "/assets/documentary-thumb.webp", "89"],
  ];

  return (
    <div className="remix-console">
      <header className="remix-console__header">
        <div><strong>高光混剪控制台</strong><small>12 集 · 36:40 · 已选 8 个高能镜头</small></div>
        <ol aria-label="短剧混剪流程">
          {tool.steps.map((step, index) => (
            <li className={index < 2 ? "is-complete" : "is-active"} data-flow-step={index + 1} key={step.title}>
              <span>{index < 2 ? <Check size={13} weight="bold" /> : index + 1}</span>
              <div><strong>{step.title}</strong><small>{step.text}</small></div>
            </li>
          ))}
        </ol>
      </header>

      <div className="remix-console__workspace">
        <aside className="clip-pool" aria-label="高光片段池">
          <header><span>高光片段池</span><small>按强度排序</small></header>
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
            <img src="/assets/film-action-thumb.webp" alt="高光混剪成片预览" loading="lazy" decoding="async" />
            <span>高光混剪 · 9:16</span>
            <button type="button" aria-label="播放高光混剪"><Play size={22} weight="fill" /></button>
            <div><small>{tool.elapsed}</small><i /><small>{tool.duration}</small></div>
          </div>
          <section className="remix-timeline" aria-label="多轨混剪时间线">
            <div className="remix-timeline__ruler"><span>00:00</span><span>00:15</span><span>00:30</span><span>00:45</span></div>
            <div className="remix-track remix-track--video"><strong>画面</strong><div>{clips.map(([title], index) => <span className={`clip-${index + 1}`} key={title}>{title}</span>)}</div></div>
            <div className="remix-track remix-track--original"><strong>原声</strong><div><Waveform size={420} weight="fill" /></div></div>
            <div className="remix-track remix-track--bgm"><strong>BGM</strong><div><Waveform size={420} weight="fill" /></div></div>
            <span className="remix-timeline__playhead" />
          </section>
        </main>

        <aside className="beat-controls" aria-label="BGM 与节拍控制">
          <header><span>BGM / 节拍</span><em>已同步</em></header>
          <div className="beat-controls__track"><Waveform size={22} weight="duotone" /><span><strong>Neon Pulse</strong><small>电子氛围 · 128 BPM</small></span><button type="button"><Play size={13} weight="fill" /></button></div>
          <label><span>卡点强度<em>78%</em></span><input aria-label="卡点强度" type="range" min="0" max="100" defaultValue="78" /></label>
          <label><span>原声音量<em>82%</em></span><input aria-label="原声音量" type="range" min="0" max="100" defaultValue="82" /></label>
          <label><span>BGM 音量<em>36%</em></span><input aria-label="BGM 音量" type="range" min="0" max="100" defaultValue="36" /></label>
          <div className="beat-controls__markers"><span>18 个节拍点</span><span>6 处转场</span><span>0 空拍</span></div>
          <button className="beat-controls__play" type="button" onClick={onPlay}><Play size={17} weight="fill" />播放混剪案例</button>
        </aside>
      </div>
    </div>
  );
}

function CaseCard({ item, onOpen, onTemplate }) {
  return (
    <article className="case-card">
      <button className="case-card__image" type="button" onClick={() => onOpen(item)} aria-label={`播放案例：${item.title}`}>
        <img src={item.image} alt={`${item.title}案例封面`} loading="lazy" decoding="async" />
        <span><Play size={17} weight="fill" /></span>
      </button>
      <div className="case-card__body">
        <h3>{item.title}</h3>
        <div className="case-card__tags">{item.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
        <button type="button" onClick={() => onTemplate(item)}>使用相同模板创作 <ArrowRight size={16} /></button>
      </div>
    </article>
  );
}

export function DemoSection({ activeTool, onToolChange, onOpenCase, onTemplate }) {
  const tool = TOOL_DATA[activeTool];
  const cases = CASE_SETS[activeTool];
  const defaultCase = cases[0];

  return (
    <section id="demo" className="demo-section section-anchor">
      <div className="section-heading page-container">
        <span className="section-kicker">CASE DEMO</span>
        <h2>看见 <span className="gradient-text">AI</span> 如何把素材变成成片</h2>
        <p>小白不用懂剪辑，跟着流程就能完成</p>
      </div>
      <div className={`demo-shell demo-shell--${tool.tone} page-container`}>
        <ToolTabs activeTool={activeTool} onToolChange={onToolChange} />
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
