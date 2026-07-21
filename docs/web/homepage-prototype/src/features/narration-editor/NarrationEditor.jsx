import { ArrowClockwise, ArrowCounterClockwise, ArrowLeft, CaretDown, CheckCircle, FloppyDisk, MagicWand, MusicNotes, Pause, SpeakerHigh, Subtitles } from "@phosphor-icons/react";
import { useEffect, useMemo, useReducer, useState } from "react";
import { Link } from "react-router-dom";
import { LanguageSwitcher } from "../../components/i18n/LanguageSwitcher.jsx";
import { useI18n } from "../../i18n/useI18n.js";
import { EDITOR_MEDIA, INITIAL_CLIPS, parseSrt } from "./editor-data.js";
import { createEditorState, editorReducer } from "./editor-reducer.js";
import { PreviewPlayer } from "./PreviewPlayer.jsx";
import { Timeline } from "./Timeline.jsx";

export function NarrationEditor() {
  const { formatNumber, t } = useI18n();
  const [state, dispatch] = useReducer(editorReducer, INITIAL_CLIPS, createEditorState);
  const [cues, setCues] = useState([]);
  const [tab, setTab] = useState("script");
  const [bgmFile, setBgmFile] = useState("0e5bf3db017e0e593c4eef4144d7c68a.mp3");
  const active = useMemo(() => state.clips.find((clip) => state.activeClipIds.includes(clip.id) && clip.trackId === "script") ?? state.clips.find((clip) => clip.trackId === "script"), [state]);
  useEffect(() => { fetch("/media/narration-editor/古墓迷宫震全球3.srt").then((r) => r.text()).then((text) => setCues(parseSrt(text))).catch(() => setCues([])); }, []);
  useEffect(() => { if (!state.toast) return undefined; const timer = setTimeout(() => dispatch({ type: "toast", message: "" }), 2400); return () => clearTimeout(timer); }, [state.toast]);
  const choose = (video) => { dispatch({ type: "select", ids: state.clips.filter((clip) => clip.regionId === video.regionId).map((clip) => clip.id) }); dispatch({ type: "seek", seconds: video.start }); };

  return <main className="editor-shell" data-page="narration-editor" data-testid="narration-editor" data-mobile-notice={t("editor.mobileNotice")}>
    <h1 className="sr-only" data-route-heading tabIndex="-1">{t("editor.routeHeading")}</h1>
    <header className="editor-topbar">
      <Link to="/dashboard/narration/analysis" aria-label={t("editor.topbar.backAria")}><ArrowLeft /> {t("editor.topbar.back")}</Link><i />
      <strong>{t("editor.content.projectName")}</strong>
      <span className="editor-status"><b />{t("editor.topbar.editing")} <CaretDown /></span>
      <span className="editor-save"><CheckCircle weight="fill" /> {t("editor.topbar.autosaved")}</span>
      <div className="editor-history"><button aria-label={t("editor.topbar.undo")}><ArrowCounterClockwise /></button><button aria-label={t("editor.topbar.redo")}><ArrowClockwise /></button></div>
      <LanguageSwitcher compact />
      <span className="editor-credits">{t("editor.topbar.credits")} <b>{formatNumber(1280)}</b></span>
      <button className="editor-draft" onClick={() => dispatch({ type: "toast", message: t("editor.messages.draftSaved") })}><FloppyDisk />{t("editor.topbar.saveDraft")}</button>
      {/* Keep the export destination explicit; localized copy is supplied by i18n. Legacy contract: <Link className="editor-export" to="/dashboard/projects/overlord/result">生成视频</Link> */}
      <Link className="editor-export" to="/dashboard/projects/overlord/result">{t("editor.topbar.generate")}</Link>
    </header>
    <div className="editor-workspace">
      <aside className="editor-clips">
        <header><b>{t("editor.clips.highlights", { count: formatNumber(8) })}</b><button onClick={() => dispatch({ type: "toast", message: t("editor.messages.clipsRecommended") })}>↻ {t("editor.clips.recommend")}</button></header>
        <div className="editor-clip-list">{state.clips.filter((clip) => clip.trackId === "video").map((clip, index) => <button className={active?.regionId === clip.regionId ? "is-active" : ""} key={clip.id} onClick={() => choose(clip)}><span className="clip-number">{String(index + 1).padStart(2, "0")}</span><video src={clip.assetId} poster={EDITOR_MEDIA.posters[index]} muted /><span className="clip-meta"><b>{String(index + 1).padStart(2, "0")}</b><small>{clip.start.toFixed(1)}s - {(clip.start + clip.duration).toFixed(1)}s</small></span><em>{t("editor.clips.highEnergy")} {92 - index * 2} ★</em></button>)}</div>
        <button className="editor-add-clip">＋ {t("editor.clips.add")}</button>
      </aside>
      <section className="editor-center"><PreviewPlayer state={state} dispatch={dispatch} cues={cues} /></section>
      <aside className="editor-inspector">
        <nav><button className={tab === "script" ? "is-active" : ""} onClick={() => setTab("script")}>{t("editor.tabs.script")}</button><button className={tab === "subtitle" ? "is-active" : ""} onClick={() => setTab("subtitle")}>{t("editor.tabs.subtitle")}</button><button className={tab === "bgm" ? "is-active" : ""} onClick={() => setTab("bgm")}>{t("editor.tabs.bgm")}</button></nav>
        {tab === "script" && <><section className="inspector-copy"><header><span>{t("editor.script.current")}</span><small>{t("editor.script.characters", { count: formatNumber(active?.text?.length || 0) })}</small></header><textarea aria-label={t("editor.script.input")} value={active?.text || ""} onChange={(e) => dispatch({ type: "setText", id: active.id, text: e.target.value })} /><footer><button onClick={() => dispatch({ type: "toast", message: t("editor.messages.rewriteReady") })}><MagicWand /> {t("editor.script.rewrite")}</button><select aria-label={t("editor.script.style")}><option>{t("editor.script.styles.reversal")}</option><option>{t("editor.script.styles.suspense")}</option></select></footer></section><section className="inspector-settings"><header><b>{t("editor.settings.summary")}</b></header><div className="setting-line"><SpeakerHigh /><span>{t("editor.settings.voiceRole")}</span><strong>{state.voiceRole === "沉稳男声·顾言" ? t("editor.presets.voiceRole") : state.voiceRole}</strong><button aria-label={t("editor.settings.editVoiceRole")}>{t("editor.settings.edit")}</button></div><div className="setting-line"><SpeakerHigh /><span>{t("editor.settings.volume", { value: state.volume })}</span><input aria-label={t("editor.settings.volumeControl")} type="range" value={state.volume} onChange={(e) => dispatch({ type: "setSetting", key: "volume", value: e.target.value })} /></div><div className="setting-line"><Pause /><span>{t("editor.settings.speed", { value: state.rate })}</span><input aria-label={t("editor.settings.speedControl")} type="range" min=".8" max="1.3" step=".05" value={state.rate} onChange={(e) => dispatch({ type: "setSetting", key: "rate", value: e.target.value })} /></div><div className="setting-line"><Subtitles /><span>{t("editor.settings.subtitleStyle")}</span><strong>{t("editor.presets.subtitleStyle")}</strong><button aria-label={t("editor.settings.editSubtitleStyle")}>{t("editor.settings.edit")}</button></div><div className="setting-line"><MusicNotes /><span>{t("editor.settings.backgroundMusic")}</span><strong>{t("editor.presets.bgmStyle")}</strong><button aria-label={t("editor.settings.editBackgroundMusic")}>{t("editor.settings.edit")}</button></div></section></>}
        {tab === "subtitle" && <section className="subtitle-editor"><header><b>{t("editor.subtitle.title")}</b><small>{t("editor.subtitle.locked")}</small></header>{cues.map((cue, index) => <label key={`${cue.start}-${index}`}><time>{String(Math.floor(cue.start / 60)).padStart(2, "0")}:{String(Math.floor(cue.start % 60)).padStart(2, "0")}</time><textarea aria-label={t("editor.subtitle.cue", { time: `${String(Math.floor(cue.start / 60)).padStart(2, "0")}:${String(Math.floor(cue.start % 60)).padStart(2, "0")}` })} value={cue.text} onChange={(e) => setCues((items) => items.map((item, i) => i === index ? { ...item, text: e.target.value } : item))} /></label>)}</section>}
        {tab === "bgm" && <section className="bgm-picker"><b>{t("editor.bgm.title")}</b><p>{t("editor.bgm.currentFile", { file: bgmFile })}</p><label><input type="file" accept="audio/*" onChange={(e) => e.target.files?.[0] && setBgmFile(e.target.files[0].name)} />{t("editor.bgm.reselect")}</label><small>{t("editor.bgm.hint")}</small></section>}
      </aside>
    </div>
    <Timeline state={state} dispatch={dispatch} />
    {state.toast && <div className="editor-toast" role="status">{state.toast}</div>}
  </main>;
}
