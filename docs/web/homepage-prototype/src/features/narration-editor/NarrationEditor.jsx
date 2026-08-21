import { ArrowLeft, CaretDown, CheckCircle, FloppyDisk, ListBullets, MusicNotes, Pause, SpeakerHigh, Subtitles } from "@phosphor-icons/react";
import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { LanguageSwitcher } from "../../components/i18n/LanguageSwitcher.jsx";
import { useI18n } from "../../i18n/useI18n.js";
import { ApiError } from "../../services/httpClient.js";
import { createDebouncedEditorSaver, getEditorDraft } from "../projects/projectApi.js";
import { createEditorDraft, readEditorDraft } from "./editor-data.js";
import { createEditorState, editorReducer } from "./editor-reducer.js";
import { PreviewPlayer } from "./PreviewPlayer.jsx";
import { Timeline } from "./Timeline.jsx";
import { createTransitionGuard } from "./transition-guard.js";

export function NarrationEditor({ projectId, onGenerate, generating = false }) {
  const { formatNumber, t } = useI18n();
  const navigate = useNavigate();
  const [state, dispatch] = useReducer(editorReducer, [], createEditorState);
  const [cues, setCues] = useState([]);
  const [tab, setTab] = useState("script");
  const [loading, setLoading] = useState(true);
  const [locked, setLocked] = useState(false);
  const [saveState, setSaveState] = useState("loading");
  const [transition, setTransition] = useState("");
  const [error, setError] = useState("");
  const saverRef = useRef(null);
  const initializedRef = useRef(false);
  const transitionGuardRef = useRef(null);
  if (!transitionGuardRef.current) {
    transitionGuardRef.current = createTransitionGuard(setTransition);
  }
  const transitionBusy = Boolean(transition) || generating;
  const interactionLocked = locked || transitionBusy;
  const active = useMemo(
    () => state.clips.find((clip) => state.activeClipIds.includes(clip.id) && clip.trackId === "script")
      ?? state.clips.find((clip) => clip.trackId === "script"),
    [state],
  );
  const videoClips = useMemo(() => state.clips.filter((clip) => clip.trackId === "video"), [state.clips]);
  const draft = useMemo(() => createEditorDraft({
    clips: state.clips,
    cues,
    voiceRole: state.voiceRole,
    volume: state.volume,
    rate: state.rate,
    subtitleStyle: state.subtitleStyle,
    videoRatio: state.videoRatio,
    backgroundMusic: state.backgroundMusic,
  }), [cues, state.backgroundMusic, state.clips, state.rate, state.subtitleStyle, state.videoRatio, state.voiceRole, state.volume]);

  useEffect(() => {
    saverRef.current = createDebouncedEditorSaver(projectId);
    return () => saverRef.current?.cancel();
  }, [projectId]);

  useEffect(() => {
    let activeRequest = true;
    async function load() {
      setLoading(true);
      setError("");
      initializedRef.current = false;
      try {
        const response = await getEditorDraft(projectId);
        if (!activeRequest) return;
        const saved = readEditorDraft(response.content);
        if (!saved) throw new Error(t("editor.messages.invalidDraft"));
        dispatch({ type: "hydrate", clips: saved.clips, settings: saved.settings });
        setCues(saved.cues);
        setLocked(Boolean(response.locked));
        setSaveState(response.locked ? "locked" : "saved");
      } catch (requestError) {
        if (!activeRequest) return;
        const message = requestError instanceof ApiError && requestError.status === 404
          ? t("editor.messages.draftUnavailable")
          : requestError.message || t("editor.messages.readFailed");
        setError(message);
      } finally {
        if (activeRequest) {
          initializedRef.current = true;
          setLoading(false);
        }
      }
    }
    load();
    return () => { activeRequest = false; };
  }, [projectId]);

  useEffect(() => {
    if (!initializedRef.current || loading || locked || !saverRef.current || error) return;
    setSaveState("saving");
    saverRef.current(draft).then(() => setSaveState("saved")).catch((requestError) => {
      setSaveState("failed");
      setError(requestError.message || t("editor.messages.saveFailed"));
    });
  }, [draft, error, loading, locked]);

  useEffect(() => {
    if (!state.toast) return undefined;
    const timer = setTimeout(() => dispatch({ type: "toast", message: "" }), 2400);
    return () => clearTimeout(timer);
  }, [state.toast]);

  const choose = (video) => {
    if (locked || transitionGuardRef.current.busy || generating) return;
    dispatch({ type: "select", ids: state.clips.filter((clip) => clip.regionId === video.regionId).map((clip) => clip.id) });
    dispatch({ type: "seek", seconds: video.start });
  };

  const saveNow = async () => {
    const action = "save";
    if (locked || generating || !saverRef.current || !transitionGuardRef.current.begin(action)) return;
    setSaveState("saving");
    setError("");
    try {
      saverRef.current(draft).catch(() => {});
      await saverRef.current.flush();
      setSaveState("saved");
      dispatch({ type: "toast", message: t("editor.messages.draftSaved") });
    } catch (requestError) {
      setSaveState("failed");
      setError(requestError.message || t("editor.messages.saveFailed"));
    } finally {
      transitionGuardRef.current.end(action);
    }
  };

  const generate = async () => {
    const action = "generate";
    if (locked || generating || !saverRef.current || !transitionGuardRef.current.begin(action)) return;
    setSaveState("saving");
    setError("");
    try {
      saverRef.current(draft).catch(() => {});
      await saverRef.current.flush();
      saverRef.current.cancel();
      await onGenerate();
    } catch (requestError) {
      setSaveState("failed");
      setError(requestError.message || t("editor.messages.saveBeforeGenerateFailed"));
    } finally {
      transitionGuardRef.current.end(action);
    }
  };

  const openReview = async () => {
    const action = "switch";
    if (generating || !saverRef.current || !transitionGuardRef.current.begin(action)) return;
    try {
      if (locked) {
        navigate(`/dashboard/narration/review?projectId=${encodeURIComponent(projectId)}`);
        return;
      }
      setSaveState("saving");
      setError("");
      saverRef.current(draft).catch(() => {});
      await saverRef.current.flush();
      saverRef.current.cancel();
      navigate(`/dashboard/narration/review?projectId=${encodeURIComponent(projectId)}`);
    } catch (requestError) {
      setSaveState("failed");
      setError(requestError.message || t("editor.messages.switchModeFailed"));
    } finally {
      transitionGuardRef.current.end(action);
    }
  };

  if (loading) return <main className="editor-shell"><p>{t("editor.messages.loading")}</p></main>;
  if (error && saveState !== "failed") return <main className="editor-shell"><p role="alert">{error}</p></main>;
  const statusText = locked ? t("editor.topbar.locked") : saveState === "saving" ? t("editor.topbar.saving") : saveState === "failed" ? t("editor.topbar.saveFailed") : t("editor.topbar.autosaved");

  return <main className="editor-shell" data-page="narration-editor" data-testid="narration-editor" data-mobile-notice={t("editor.mobileNotice")}>
    <h1 className="sr-only" data-route-heading tabIndex="-1">{t("editor.routeHeading")}</h1>
    <header className="editor-topbar">
      <Link to="/dashboard" aria-label={t("editor.topbar.backAria")}><ArrowLeft /> {t("editor.topbar.back")}</Link><i />
      <strong>{projectId}</strong>
      <button className="editor-mode" type="button" onClick={openReview} disabled={transitionBusy} data-testid="editor-review-mode"><ListBullets />{transition === "switch" ? t("editor.topbar.switchingMode") : t("editor.topbar.reviewMode")}</button>
      <span className="editor-status"><b />{locked ? t("editor.topbar.readOnly") : t("editor.topbar.editing")} <CaretDown /></span>
      <span className="editor-save"><CheckCircle weight="fill" /> {statusText}</span>
      <LanguageSwitcher compact />
      <button className="editor-draft" onClick={saveNow} disabled={interactionLocked} data-testid="editor-save"><FloppyDisk />{t("editor.topbar.saveDraft")}</button>
      <button className="editor-export" type="button" onClick={generate} disabled={interactionLocked} data-testid="editor-generate" data-project-id={projectId}>{transition === "generate" || generating ? t("editor.topbar.generating") : t("editor.topbar.generate")}</button>
    </header>
    {error && <p className="editor-save-error" role="alert">{error}</p>}
    <div className="editor-workspace">
      <aside className="editor-clips">
        <header><b>{t("editor.clips.highlights", { count: formatNumber(videoClips.length) })}</b></header>
        <div className="editor-clip-list">{videoClips.map((clip, index) => <button disabled={interactionLocked} className={active?.regionId === clip.regionId ? "is-active" : ""} key={clip.id} onClick={() => choose(clip)}><span className="clip-number">{String(index + 1).padStart(2, "0")}</span><video src={clip.assetUrl} muted /><span className="clip-meta"><b>{String(index + 1).padStart(2, "0")}</b><small>{clip.start.toFixed(1)}s - {(clip.start + clip.duration).toFixed(1)}s</small></span></button>)}</div>
      </aside>
      <section className="editor-center"><PreviewPlayer state={state} dispatch={dispatch} cues={cues} /></section>
      <aside className="editor-inspector">
        <nav><button className={tab === "script" ? "is-active" : ""} onClick={() => setTab("script")}>{t("editor.tabs.script")}</button><button className={tab === "subtitle" ? "is-active" : ""} onClick={() => setTab("subtitle")}>{t("editor.tabs.subtitle")}</button><button className={tab === "bgm" ? "is-active" : ""} onClick={() => setTab("bgm")}>{t("editor.tabs.bgm")}</button></nav>
        {tab === "script" && <>
          <section className="inspector-copy"><header><span>{t("editor.script.current")}</span><small>{t("editor.script.characters", { count: formatNumber(active?.text?.length || 0) })}</small></header><textarea disabled={interactionLocked} aria-label={t("editor.script.input")} value={active?.text || ""} onChange={(event) => active && dispatch({ type: "setText", id: active.id, text: event.target.value })} /></section>
          <section className="inspector-settings"><header><b>{t("editor.settings.summary")}</b></header><div className="setting-line"><SpeakerHigh /><span>{t("editor.settings.voiceRole")}</span><strong>{state.voiceRole || "—"}</strong></div><div className="setting-line"><SpeakerHigh /><span>{t("editor.settings.volume", { value: state.volume })}</span><input disabled={interactionLocked} aria-label={t("editor.settings.volumeControl")} type="range" min="0" max="100" value={state.volume} onChange={(event) => dispatch({ type: "setSetting", key: "volume", value: event.target.value })} /></div><div className="setting-line"><Pause /><span>{t("editor.settings.speed", { value: state.rate })}</span><input disabled={interactionLocked} aria-label={t("editor.settings.speedControl")} type="range" min=".8" max="1.3" step=".05" value={state.rate} onChange={(event) => dispatch({ type: "setSetting", key: "rate", value: event.target.value })} /></div><div className="setting-line"><Subtitles /><span>{t("editor.settings.subtitleStyle")}</span><strong>{state.subtitleStyle || "—"}</strong></div><div className="setting-line"><MusicNotes /><span>{t("editor.settings.backgroundMusic")}</span><strong>{state.backgroundMusic?.filename || state.backgroundMusic?.assetId || t("editor.bgm.none")}</strong></div></section>
        </>}
        {tab === "subtitle" && <section className="subtitle-editor"><header><b>{t("editor.subtitle.title")}</b><small>{locked ? t("editor.topbar.readOnly") : t("editor.subtitle.locked")}</small></header>{cues.map((cue, index) => <label key={`${cue.start}-${index}`}><time>{String(Math.floor(cue.start / 60)).padStart(2, "0")}:{String(Math.floor(cue.start % 60)).padStart(2, "0")}</time><textarea disabled={interactionLocked} aria-label={t("editor.subtitle.cue", { time: `${String(Math.floor(cue.start / 60)).padStart(2, "0")}:${String(Math.floor(cue.start % 60)).padStart(2, "0")}` })} value={cue.text} onChange={(event) => setCues((items) => items.map((item, cueIndex) => cueIndex === index ? { ...item, text: event.target.value } : item))} /></label>)}</section>}
        {tab === "bgm" && <section className="bgm-picker"><b>{t("editor.bgm.title")}</b><p>{t("editor.bgm.currentFile", { file: state.backgroundMusic?.filename || state.backgroundMusic?.assetId || t("editor.bgm.none") })}</p></section>}
      </aside>
    </div>
    <Timeline state={state} dispatch={dispatch} readOnly={interactionLocked} />
    {state.toast && <div className="editor-toast" role="status">{state.toast}</div>}
  </main>;
}
