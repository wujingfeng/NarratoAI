import { ArrowClockwise, ArrowLeft, Check, CheckCircle, DownloadSimple, FileText, FilmStrip, Pause, Play, SpinnerGap, Translate, WarningCircle } from "@phosphor-icons/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { DashboardHeader } from "../components/dashboard/DashboardHeader.jsx";
import { DashboardMobileNav } from "../components/dashboard/DashboardMobileNav.jsx";
import { DashboardSidebar } from "../components/dashboard/DashboardSidebar.jsx";
import { DashboardToast } from "../components/dashboard/DashboardToast.jsx";
import { NarrationPreview } from "../components/narration/NarrationPreview.jsx";
import { dashboardNavItems } from "../data/dashboardData.js";
import { useAuth } from "../features/auth/AuthProvider.jsx";
import { readCachedSubtitleLayouts } from "../features/subtitle-region/subtitleRegionStorage.js";
import { resolveSourceSubtitleRegion } from "../features/subtitle-region/subtitleRegionSelection.js";
import { uploadAsset } from "../features/uploads/ossPostUpload.js";
import { getProjectStage } from "../features/projects/projectApi.js";
import { applyTranslationVoice, estimateTranslationCost, exceedsPreviewLimit, getTranslationConfig, getTranslationResult, getTranslationSegments, getTranslationSettings, getTranslationStage, previewTranslationSegment, renderTranslation, restartTranslationFromSubtitle, retryTranslationFromNode, saveTranslationSegment, saveTranslationSettings, startTranslation, waitForTranslationPreview } from "../features/video-translation/translationApi.js";
import { useI18n } from "../i18n/useI18n.js";
import { CreateUploadFlow } from "./CreatePage.jsx";

const STEPS = ["upload", "settings", "translation", "edit", "render"];
const ORIGINAL_SOUND_MODES = ["voice_replacement", "translated_voice_only"];
const DEFAULT_SOURCE_SUBTITLE_REGION = { x: .08, y: .78, width: .84, height: .12 };
const DEFAULT_TRANSLATED_SUBTITLE_REGION = { x: .08, y: .66, width: .84, height: .12 };
const DEFAULT_TRANSLATION_SETTINGS = {
  target_language: "",
  execution_mode: "manual",
  video_ratio: "original",
  voice_id: "",
  // 默认仅保留译文配音，和创建页的 30 创作点/分钟基础报价保持一致。
  // 用户主动选择“替换人声”后，才增加人声分离附加费。
  original_sound_mode: "translated_voice_only",
  preserve_source_subtitles: false,
  source_subtitle_region: DEFAULT_SOURCE_SUBTITLE_REGION,
  translated_subtitle_region: DEFAULT_TRANSLATED_SUBTITLE_REGION,
  background_music_asset_id: "",
};
const stageFrom = (value) => ({ analysis: "translation", ai_translation: "translation", generated: "export", completed: "export", generate: "render" }[value] || value || "upload");
const time = (ms) => `${String(Math.floor(Number(ms || 0) / 60000)).padStart(2, "0")}:${String(Math.floor(Number(ms || 0) / 1000) % 60).padStart(2, "0")}`;
const regionOrDefault = (region, fallback) => region && typeof region === "object" ? { ...fallback, ...region } : { ...fallback };

export function VideoTranslationPage({ view }) {
  const { t } = useI18n(); const { user } = useAuth(); const navigate = useNavigate(); const [params] = useSearchParams();
  const projectId = params.get("projectId"); const retrySourceProjectId = params.get("retrySourceProjectId"); const stage = view || stageFrom(params.get("stage")); const index = stage === "export" ? 4 : Math.max(0, STEPS.indexOf(stage));
  const [error, setError] = useState(""); const [toast, setToast] = useState({ id: 0, message: "" });
  const notify = useCallback((message) => setToast(({ id }) => ({ id: id + 1, message })), []);
  const go = useCallback((next) => navigate(`/dashboard/video-translation/${next}${projectId ? `?projectId=${encodeURIComponent(projectId)}` : ""}`), [navigate, projectId]);
  return <div className="dashboard-shell narration-shell translation-shell" data-page="video-translation">
    <DashboardSidebar items={dashboardNavItems} onUnavailable={notify} /><div className="narration-workspace"><DashboardHeader credits={{ balance: user?.credit_balance ?? null }} onUnavailable={notify} />
      <main className="narration-main translation-main"><header className="narration-topbar translation-topbar"><Link to="/dashboard" aria-label={t("videoTranslation.back")}><ArrowLeft /></Link><strong><Translate />{t("videoTranslation.name")}</strong><i /><h2>{t(`videoTranslation.steps.${STEPS[index]}`)}</h2></header>
        <ol className="narration-stepper translation-stepper" aria-label={t("videoTranslation.flow")} >{STEPS.map((item, i) => <li key={item} className={i < index ? "is-complete" : i === index ? "is-current" : ""}><span className="narration-stepper__number">{i < index ? <Check weight="bold" /> : i + 1}</span><span>{t(`videoTranslation.steps.${item}`)}</span></li>)}</ol>
        {error && <p className="translation-alert"><WarningCircle />{error}</p>}
        {stage === "upload" && <section className="narration-upload-stage"><CreateUploadFlow fixedType="translation" initialProjectId={projectId} retrySourceProjectId={retrySourceProjectId} showTypeSelector={false} onFeedback={notify} /></section>}
        {stage === "settings" && <Settings projectId={projectId} onNext={() => go("translation")} onError={setError} />}
        {stage === "translation" && <Progress projectId={projectId} onDone={go} onError={setError} />}
        {stage === "edit" && <Editor projectId={projectId} onNext={() => go("render")} onError={setError} />}
        {stage === "render" && <Render projectId={projectId} onDone={go} onError={setError} />}
        {stage === "export" && <Export projectId={projectId} onError={setError} />}
      </main></div><DashboardMobileNav items={dashboardNavItems} onUnavailable={notify} />{toast.message && <DashboardToast key={toast.id} message={toast.message} onClose={() => setToast(({ id }) => ({ id, message: "" }))} />}
  </div>;
}

function Settings({ projectId, onNext, onError }) {
  const { t } = useI18n(); const [options, setOptions] = useState({ target_languages: [], video_ratios: [], voices: [] }); const [busy, setBusy] = useState(false); const [videos, setVideos] = useState([]); const [selectedVideoId, setSelectedVideoId] = useState(""); const [cost, setCost] = useState(null); const [settingsProjectId, setSettingsProjectId] = useState("");
  const [config, setConfig] = useState(DEFAULT_TRANSLATION_SETTINGS);
  useEffect(() => { let active = true; setSettingsProjectId(""); getTranslationConfig().then(async (data) => {
    const [saved, stage] = await Promise.all([
      projectId ? getTranslationSettings(projectId) : null,
      projectId ? getProjectStage(projectId).catch(() => null) : null,
    ]);
    if (!active) return;
    const assets = stage?.video_assets || stage?.videoAssets || [];
    const normalized = assets.map((asset) => ({ id: asset.id, filename: asset.filename, cdnUrl: asset.cdn_url || asset.cdnUrl }));
    const selectedId = normalized[0]?.id || "";
    const cachedLayouts = readCachedSubtitleLayouts(projectId);
    setOptions(data); setVideos(normalized); setSelectedVideoId(selectedId);
    setConfig((v) => ({ ...v, ...(saved || {}), source_subtitle_region: resolveSourceSubtitleRegion(saved?.source_subtitle_region, cachedLayouts, selectedId, DEFAULT_SOURCE_SUBTITLE_REGION), translated_subtitle_region: regionOrDefault(saved?.translated_subtitle_region, DEFAULT_TRANSLATED_SUBTITLE_REGION), target_language: saved?.target_language || data.target_languages?.[0]?.id || "", voice_id: saved?.voice_id || data.voices?.[0]?.id || "" })); setSettingsProjectId(projectId || "__new__");
  }).catch(() => { if (active) onError(t("videoTranslation.errors.config")); }); return () => { active = false; }; }, [onError, projectId, t]);
  useEffect(() => { if (!projectId || settingsProjectId !== projectId) { setCost(null); return undefined; } let active = true; setCost(null); estimateTranslationCost(projectId, config.original_sound_mode).then((data) => { if (active) setCost(data); }).catch(() => { if (active) setCost(null); }); return () => { active = false; }; }, [config.original_sound_mode, projectId, settingsProjectId]);
  const set = (key, value) => setConfig((v) => ({ ...v, [key]: value })); const voiceReplacementRate = options.voice_replacement_surcharge_credits_per_minute ?? 10; const costReady = settingsProjectId === projectId && cost?.original_sound_mode === config.original_sound_mode; const submit = async () => { if (!projectId) return onError(t("videoTranslation.errors.project")); if (!costReady) return; setBusy(true); try { await saveTranslationSettings(projectId, config); await startTranslation(projectId); onNext(); } catch { onError(t("videoTranslation.errors.save")); } finally { setBusy(false); } };
  const drag = (key, event) => { const initial = config[key]; const bounds = event.currentTarget.parentElement.getBoundingClientRect(); const start = { x: event.clientX, y: event.clientY }; const move = (next) => set(key, { ...initial, x: Math.max(0, Math.min(1 - initial.width, initial.x + (next.clientX - start.x) / bounds.width)), y: Math.max(0, Math.min(1 - initial.height, initial.y + (next.clientY - start.y) / bounds.height)) }); const end = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", end); }; window.addEventListener("pointermove", move); window.addEventListener("pointerup", end, { once: true }); };
  const bgm = async (file) => { if (!file || !projectId) return; try { const asset = await uploadAsset(projectId, file, "audio"); set("background_music_asset_id", asset.id); } catch { onError(t("videoTranslation.errors.music")); } };
  return <section className="narration-content translation-settings-content"><section className="narration-settings translation-settings-form">
    <fieldset className="narration-fieldset narration-mode-picker"><legend>{t("videoTranslation.mode")}</legend><p className="narration-mode-picker__hint">{t("videoTranslation.modeHint")}</p><div className="narration-mode-grid">{["manual", "auto"].map((id) => <label key={id} className={`narration-mode-card ${config.execution_mode === id ? "is-selected" : ""}`}><input type="radio" checked={config.execution_mode === id} onChange={() => set("execution_mode", id)} /><span><strong>{t(`videoTranslation.${id}`)}</strong><small>{t(`videoTranslation.${id}Hint`)}</small></span>{config.execution_mode === id && <Check />}</label>)}</div></fieldset>
    <Choice title={t("videoTranslation.language")} items={options.target_languages} value={config.target_language} onChange={(v) => set("target_language", v)} label={(item) => t(`videoTranslation.languages.${item.id}`)} />
    <Choice title={t("videoTranslation.ratio")} items={options.video_ratios} value={config.video_ratio} onChange={(v) => set("video_ratio", v)} label={(item) => t(`videoTranslation.ratios.${item.id}`)} />
    <Choice title={t("videoTranslation.voice")} items={options.voices} value={config.voice_id} onChange={(v) => set("voice_id", v)} />
    <fieldset className="narration-fieldset"><legend>{t("videoTranslation.originalSound")}</legend><div className="narration-mode-grid">{ORIGINAL_SOUND_MODES.map((id) => <label key={id} className={`narration-mode-card ${config.original_sound_mode === id ? "is-selected" : ""}`}><input type="radio" checked={config.original_sound_mode === id} onChange={() => set("original_sound_mode", id)} /><span><strong>{t(`videoTranslation.${id}`)}</strong><small>{t(`videoTranslation.${id}Hint`)}</small></span>{config.original_sound_mode === id && <Check />}</label>)}</div><p className="narration-mode-picker__hint">{config.original_sound_mode === "voice_replacement" ? t("videoTranslation.voiceReplacementSurcharge", { credits: voiceReplacementRate }) : t("videoTranslation.noVoiceReplacementSurcharge")}</p>{cost && <p className="narration-mode-picker__hint">{t("videoTranslation.estimatedCost", { credits: cost.credits, minutes: cost.billed_minutes, surcharge: cost.voice_replacement_credits })}</p>}</fieldset>
    <fieldset className="narration-fieldset translation-bgm-picker"><legend>{t("videoTranslation.music")}</legend><p className="narration-bgm-picker__hint">{t("videoTranslation.musicHint")}</p><label className="translation-bgm-upload"><span>{t("videoTranslation.chooseMusic")}</span><input type="file" accept="audio/*,.mp3,.wav,.m4a,.aac,.ogg" onChange={(e) => bgm(e.target.files?.[0])} /></label></fieldset>
    <div className="narration-actions translation-settings-actions"><Link to="/dashboard/video-translation/upload">{t("videoTranslation.previous")}</Link><button disabled={busy || !costReady} onClick={submit}>{busy ? t("videoTranslation.saving") : t("videoTranslation.start")}</button></div>
  </section><NarrationPreview ratio={config.video_ratio === "original" ? "9:16" : config.video_ratio} estimate={null} videos={videos} selectedVideoId={selectedVideoId} onSelectedVideoChange={setSelectedVideoId} sourceSubtitleLayout={{ status: config.preserve_source_subtitles ? "confirmed" : "detected", region: config.source_subtitle_region }} onSourceRegionChange={(region) => set("source_subtitle_region", region)} onConfirmSourceSubtitle={() => set("preserve_source_subtitles", true)} onNoSourceSubtitle={() => set("preserve_source_subtitles", false)} narrationSubtitlePosition={{ y: config.translated_subtitle_region.y, font_scale: 1 }} onNarrationSubtitlePositionChange={(position) => set("translated_subtitle_region", { ...config.translated_subtitle_region, y: position.y })} subtitleStyle="translation" subtitleStyles={[{ id: "translation" }]} /></section>;
}
function Choice({ title, items, value, onChange, label }) { return <fieldset className="narration-fieldset translation-language-picker"><legend>{title}</legend><div className="translation-option-grid">{items.map((item) => <label key={item.id} className={`translation-option ${value === item.id ? "is-selected" : ""}`}><input type="radio" checked={value === item.id} onChange={() => onChange(item.id)} /><span>{label?.(item) || item.name || item.id}</span>{value === item.id && <Check />}</label>)}</div></fieldset>; }
const TRANSLATION_PHASES = [
  { id: "subtitle_recognition", title: "字幕识别", pending: "等待识别字幕", active: "正在识别字幕", Icon: FileText },
  { id: "subtitle_translation", title: "字幕翻译", pending: "等待翻译字幕", active: "正在翻译字幕", Icon: Translate },
];

function translationPhaseState(nodes = [], workflowStatus = "") {
  const stateByName = new Map(nodes.map((node) => [node.name, String(node.state || "").toLowerCase()]));
  const hasRunningNode = [...stateByName.values()].some((state) => state === "running");
  let activeAssigned = false;
  return TRANSLATION_PHASES.map((phase) => {
    const nodeState = stateByName.get(phase.id) || "queued";
    if (["completed", "succeeded", "success", "done"].includes(nodeState)) return { ...phase, state: "done" };
    if (["failed", "error", "cancelled"].includes(nodeState)) return { ...phase, state: "failed" };
    if (nodeState === "running") return { ...phase, state: "active" };
    if (!hasRunningNode && workflowStatus === "queued" && !activeAssigned) { activeAssigned = true; return { ...phase, state: "active" }; }
    return { ...phase, state: "waiting" };
  });
}

function Progress({ projectId, onDone, onError }) {
  const { t } = useI18n();
  const [snapshot, setSnapshot] = useState({ nodes: [], status: "" });
  useEffect(() => {
    let active = true;
    const poll = async () => {
      try {
        const data = await getTranslationStage(projectId);
        if (!active) return;
        setSnapshot(data);
        const next = stageFrom(data.current_stage || data.stage);
        if (["edit", "render", "export"].includes(next)) onDone(next);
      } catch { if (active) onError(t("videoTranslation.errors.progress")); }
    };
    poll();
    const timer = window.setInterval(poll, 2500);
    return () => { active = false; window.clearInterval(timer); };
  }, [onDone, onError, projectId, t]);
  const phases = translationPhaseState(snapshot.nodes, snapshot.status);
  const completed = phases.filter((phase) => phase.state === "done").length;
  const hasFailed = phases.some((phase) => phase.state === "failed");
  const isActive = phases.some((phase) => phase.state === "active");
  const progress = hasFailed ? Math.round((completed / phases.length) * 100) : Math.round(((completed + (isActive ? .5 : 0)) / phases.length) * 100);
  const current = phases.find((phase) => phase.state === "active");
  return <section className="translation-analysis" aria-label="视频翻译处理进度">
    <h1>{hasFailed ? "视频翻译任务异常" : current?.active || t("videoTranslation.processing")}</h1>
    <div className="translation-analysis__content">
      <ol className="translation-analysis__phases">
        {phases.map((phase, index) => { const Icon = phase.Icon; return <li className={`is-${phase.state}`} key={phase.id}>
          <span className="translation-analysis__connector" aria-hidden="true" />
          <span className="translation-analysis__icon"><Icon /></span>
          <span className="translation-analysis__copy"><strong>{phase.title}</strong><small>{phase.state === "done" ? "已完成" : phase.state === "failed" ? "处理失败" : phase.state === "active" ? phase.active : phase.pending}</small></span>
          <span className="translation-analysis__status">{phase.state === "done" ? <CheckCircle weight="fill" /> : phase.state === "active" ? <i /> : null}</span>
        </li>; })}
      </ol>
      <div className={`translation-analysis__meter${isActive ? " is-running" : ""}`} style={{ "--translation-progress": `${progress}%` }}>
        <div className="translation-analysis__meter-inner"><span className="translation-analysis__diamond" aria-hidden="true">✦</span><strong>{progress}%</strong><small>{hasFailed ? "请在项目列表中重试失败节点" : "当前处理进度"}</small></div>
      </div>
    </div>
  </section>;
}
function Editor({ projectId, onNext, onError }) {
  const { t } = useI18n();
  const [rows, setRows] = useState([]);
  const [voices, setVoices] = useState([]);
  const [restarting, setRestarting] = useState(false);
  const [previewingId, setPreviewingId] = useState("");
  const [playingId, setPlayingId] = useState("");
  const [applyingVoiceId, setApplyingVoiceId] = useState("");
  const audioRefs = useRef(new Map());

  useEffect(() => {
    getTranslationConfig().then((x) => setVoices(x.voices || [])).catch(() => onError(t("videoTranslation.errors.config")));
    getTranslationSegments(projectId).then((x) => setRows(Array.isArray(x) ? x : [])).catch(() => onError(t("videoTranslation.errors.segments")));
  }, [onError, projectId, t]);

  const stopPreview = (id) => {
    const audio = audioRefs.current.get(id);
    if (audio) { audio.pause(); audio.currentTime = 0; }
    setPlayingId((current) => current === id ? "" : current);
  };
  const playReadyPreview = (id, restart = false) => {
    const audio = audioRefs.current.get(id);
    if (!audio) return;
    for (const [otherId, otherAudio] of audioRefs.current) {
      if (otherId !== id) { otherAudio.pause(); otherAudio.currentTime = 0; }
    }
    if (restart) audio.currentTime = 0;
    audio.play().catch(() => setPlayingId(""));
  };
  const toggleReadyPreview = (id) => {
    const audio = audioRefs.current.get(id);
    if (!audio) return;
    if (playingId === id && !audio.paused) { audio.pause(); return; }
    playReadyPreview(id);
  };
  const save = (id, patch) => {
    stopPreview(id);
    setRows((all) => all.map((row) => row.id === id ? { ...row, ...patch, preview_audio_url: null, preview_valid: false, tts_duration_ms: null, timing_fit_status: "pending", timing_overflow_ms: 0, fitted_speed: null } : row));
    saveTranslationSegment(projectId, id, patch).catch(() => onError(t("videoTranslation.errors.save")));
  };
  const applyVoiceToAll = async (row) => {
    if (!row.voice_id || applyingVoiceId) return;
    setApplyingVoiceId(row.id);
    try {
      const updated = await applyTranslationVoice(projectId, row.voice_id, { overwriteCustom: true });
      // 不整体替换表格数据：只合并本操作实际改变的音色/试听字段，保留原文、译文
      // 及现有输入 DOM，避免“一键复用”时其它单元格发生视觉闪动。
      const updatedById = new Map((Array.isArray(updated) ? updated : []).map((item) => [item.id, item]));
      setRows((current) => current.map((item) => {
        const serverItem = updatedById.get(item.id);
        if (!serverItem) return item;
        return {
          ...item,
          voice_id: serverItem.voice_id,
          voice_overridden: serverItem.voice_overridden,
          preview_audio_url: serverItem.preview_audio_url ?? null,
          preview_valid: Boolean(serverItem.preview_valid),
          tts_duration_ms: serverItem.tts_duration_ms ?? null,
          timing_fit_status: serverItem.timing_fit_status || "pending",
          timing_overflow_ms: Number(serverItem.timing_overflow_ms || 0),
          fitted_speed: serverItem.fitted_speed ?? null,
        };
      }));
      setPlayingId("");
      for (const audio of audioRefs.current.values()) { audio.pause(); audio.currentTime = 0; }
    } catch { onError(t("videoTranslation.errors.save")); } finally { setApplyingVoiceId(""); }
  };
  const generatePreview = async (row) => {
    if (previewingId) return;
    if (exceedsPreviewLimit(row.translated_text, "")) return onError(t("videoTranslation.errors.limit"));
    setPreviewingId(row.id);
    try {
      const queued = await previewTranslationSegment(projectId, row.id);
      const result = queued.status === "succeeded" ? queued : await waitForTranslationPreview(projectId, row.id, queued);
      if (result.status !== "succeeded" || !result.preview_audio_url) throw new Error("preview failed");
      setRows((all) => all.map((item) => item.id === row.id ? { ...item, preview_audio_url: result.preview_audio_url, preview_valid: true } : item));
      window.setTimeout(() => playReadyPreview(row.id, true), 0);
    } catch { onError(t("videoTranslation.errors.preview")); } finally { setPreviewingId(""); }
  };
  const restart = async () => {
    setRestarting(true);
    try { await restartTranslationFromSubtitle(projectId); window.location.assign(`/dashboard/video-translation/translation?projectId=${encodeURIComponent(projectId)}`); }
    catch { onError("重新执行字幕翻译失败"); setRestarting(false); }
  };

  return <section className="translation-card translation-editor"><header><h1>{t("videoTranslation.edit")}</h1>{rows.length > 0 && <button className="translation-primary" onClick={onNext}>{t("videoTranslation.render")}</button>}</header>{rows.length === 0 ? <div className="translation-empty"><p>未取得可编辑译文。请重新执行字幕翻译以生成台词表。</p><button className="translation-primary" disabled={restarting} onClick={restart}>{restarting ? "正在重新执行…" : "重新执行字幕翻译"}</button></div> : <><div className="translation-table-wrap"><table><thead><tr>{["time", "source", "target", "voice", "preview"].map((x) => <th key={x}>{t(`videoTranslation.${x}`)}</th>)}</tr></thead><tbody>{rows.map((row) => {
    const isPreviewing = previewingId === row.id;
    const isPlaying = playingId === row.id;
    const isApplyingVoice = applyingVoiceId === row.id;
    const slotMs = Math.max(0, Number(row.end_ms || 0) - Number(row.start_ms || 0));
    const wasAutoFitted = row.timing_fit_status === "speed_adjusted" || Number(row.fitted_speed || 1) > Number(row.speed || 1);
    const rowClasses = [row.preview_valid ? "has-ready-preview" : ""].filter(Boolean).join(" ");
    return <tr key={row.id} className={rowClasses}><td>{time(row.start_ms)} – {time(row.end_ms)}{row.tts_duration_ms ? <span className="translation-timing-status is-fit">{wasAutoFitted ? `已自动加速至 ${Number(row.fitted_speed || 1).toFixed(2)}×，配音 ${(Number(row.tts_duration_ms) / 1000).toFixed(2)} 秒 / 时段 ${(slotMs / 1000).toFixed(2)} 秒` : `配音 ${(Number(row.tts_duration_ms) / 1000).toFixed(2)} 秒 / 时段 ${(slotMs / 1000).toFixed(2)} 秒`}</span> : null}</td><td>{row.source_text}</td><td><textarea value={row.translated_text || ""} onChange={(e) => save(row.id, { translated_text: e.target.value })} /></td><td><div className="translation-voice-cell"><select value={row.voice_id || ""} onChange={(e) => save(row.id, { voice_id: e.target.value })}>{voices.map((v) => <option key={v.id} value={v.id}>{v.name || v.id}</option>)}</select><button className="translation-voice-reuse" type="button" disabled={Boolean(applyingVoiceId) || !row.voice_id} onClick={() => applyVoiceToAll(row)}>{isApplyingVoice ? "复用中…" : "一键复用"}</button></div></td><td><button className="translation-preview-button" disabled={Boolean(previewingId)} aria-busy={isPreviewing} onClick={() => generatePreview(row)}>{isPreviewing ? <><span className="translation-preview-spinner" />正在合成…</> : <><ArrowClockwise />合成</>}</button>{row.preview_valid && row.preview_audio_url && <button className="translation-preview-button translation-preview-button--playback" type="button" onClick={() => toggleReadyPreview(row.id)}>{isPlaying ? <><Pause />暂停</> : <><Play />播放</>}</button>}{row.preview_audio_url && <audio ref={(element) => { if (element) audioRefs.current.set(row.id, element); else audioRefs.current.delete(row.id); }} src={row.preview_audio_url} preload="auto" hidden onPlay={() => setPlayingId(row.id)} onPause={() => setPlayingId((current) => current === row.id ? "" : current)} onEnded={() => setPlayingId((current) => current === row.id ? "" : current)} />}{isPreviewing && <small className="translation-preview-status">正在生成试听，成功后自动播放；成功前不会扣费。</small>}</td></tr>;
  })}</tbody></table></div></>}</section>;
}
function renderNodeState(snapshot, name) {
  return String(snapshot?.nodes?.find((node) => node.name === name)?.state || "queued").toLowerCase();
}

function Render({ projectId, onDone }) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState("starting");
  const [failure, setFailure] = useState("");
  const [snapshot, setSnapshot] = useState({ nodes: [], status: "" });
  const retryFailedNode = async () => {
    const failed = (snapshot.nodes || []).find((node) => ["failed", "error"].includes(String(node.state || "").toLowerCase()));
    const nodeName = failed?.name || "tts";
    try {
      await retryTranslationFromNode(projectId, nodeName);
      setAttempt((value) => value + 1);
    } catch (error) {
      setFailure(error?.serverMessage || "重新生成未能提交，请稍后再试。");
    }
  };

  useEffect(() => {
    let active = true;
    let timer;
    const stopPolling = () => {
      if (timer) window.clearInterval(timer);
      timer = undefined;
    };
    const fail = (message) => {
      if (!active) return;
      // 任务已进入终态失败，必须立刻停止 stage 轮询；否则会持续请求
      // `/video-translation/stage` 并用无意义响应覆盖失败提示。
      stopPolling();
      setState("failed");
      setFailure(message || "视频渲染暂时未能启动，请重新尝试。");
    };
    const poll = async () => {
      try {
        const snapshot = await getTranslationStage(projectId);
        if (!active) return;
        setSnapshot(snapshot);
        const failedNode = (snapshot.nodes || []).find((node) => ["failed", "error"].includes(String(node.state || "").toLowerCase()));
        if (failedNode || String(snapshot.status || "").toLowerCase().includes("fail")) {
          const labels = { subtitle_rewrite: "压缩重译", tts: "配音生成", video_render: "视频渲染", publish_artifacts: "成片输出" };
          fail(`${labels[failedNode?.name] || "任务"}失败，请重新生成。`);
          return false;
        }
        if (stageFrom(snapshot.current_stage || snapshot.stage) === "edit") {
          onDone("edit");
          return false;
        }
        if (stageFrom(snapshot.current_stage || snapshot.stage) === "export") {
          onDone("export");
          return false;
        }
        return true;
      } catch {
        fail("无法读取渲染进度，请检查网络后重新尝试。");
        return false;
      }
    };
    const start = async () => {
      setState("starting");
      setFailure("");
      try {
        // 重新打开已经完成的项目时，不要再次 POST /render；直接进入导出页。
        const existing = await getTranslationStage(projectId);
        if (!active) return;
        setSnapshot(existing);
        const existingFailedNode = (existing.nodes || []).find((node) => ["failed", "error"].includes(String(node.state || "").toLowerCase()));
        if (existingFailedNode || String(existing.status || "").toLowerCase().includes("fail")) {
          const labels = { subtitle_rewrite: "压缩重译", tts: "配音生成", video_render: "视频渲染", publish_artifacts: "成片输出" };
          fail(`${labels[existingFailedNode?.name] || "任务"}失败，请重新生成。`);
          return;
        }
        if (stageFrom(existing.current_stage || existing.stage) === "export") {
          onDone("export");
          return;
        }
        await renderTranslation(projectId);
        if (!active) return;
        setState("rendering");
        if (await poll() && active) {
          timer = window.setInterval(async () => {
            if (!await poll()) stopPolling();
          }, 2500);
        }
      } catch (error) { fail(error?.serverMessage || "视频渲染暂时未能启动，请重新尝试。"); }
    };
    start();
    return () => { active = false; stopPolling(); };
  }, [attempt, onDone, projectId]);

  const isFailed = state === "failed";
  const isStarting = state === "starting";
  const ttsState = renderNodeState(snapshot, "tts");
  const videoRenderState = renderNodeState(snapshot, "video_render");
  const publishState = renderNodeState(snapshot, "publish_artifacts");
  const recognitionState = renderNodeState(snapshot, "subtitle_recognition");
  const translationState = renderNodeState(snapshot, "subtitle_translation");
  const isDone = (value) => ["completed", "succeeded", "success", "done"].includes(value);
  const isActive = (value) => ["queued", "running"].includes(value);
  const recognitionDone = isDone(recognitionState);
  const translationDone = isDone(translationState);
  const ttsDone = isDone(ttsState);
  const ttsProgressLabel = `生成配音(${Math.min(Number(snapshot.tts_completed_segments || 0), Number(snapshot.tts_total_segments || 0))}/${Number(snapshot.tts_total_segments || 0)})`;
  const renderDone = isDone(videoRenderState);
  const activeStep = !recognitionDone && isActive(recognitionState) ? "recognition" : !translationDone && isActive(translationState) ? "translation" : !ttsDone && isActive(ttsState) ? "tts" : !renderDone && isActive(videoRenderState) ? "render" : isActive(publishState) ? "publish" : "";
  const currentTitle = activeStep === "tts" ? "正在生成并自动适配配音" : activeStep === "publish" ? "正在输出成片文件" : "正在生成翻译视频";
  const currentDescription = activeStep === "tts" ? "正在按编辑后的译文合成配音，超出原片段时长时会自动加速适配。" : activeStep === "publish" ? "正在登记并输出可下载的成片文件。" : isStarting ? "正在校验译文、音色与字幕位置，请稍候。" : "译文字幕、配音和背景音乐正在合成为可导出的视频。";
  return <section className={`translation-card translation-render is-${state}`} aria-live="polite">
    <header className="translation-render__header"><span className="translation-render__eyebrow"><i />视频翻译 · 成片输出</span><span className="translation-render__state">{isFailed ? "需要重新尝试" : isStarting ? "正在准备" : "渲染队列中"}</span></header>
    <div className="translation-render__body">
      <div className="translation-render__visual" aria-hidden="true"><span className="translation-render__orbit translation-render__orbit--outer" /><span className="translation-render__orbit translation-render__orbit--inner" /><span className="translation-render__core">{isFailed ? <WarningCircle weight="fill" /> : <SpinnerGap />}</span></div>
      <div className="translation-render__copy"><h1>{isFailed ? "生成暂时中断" : currentTitle}</h1><p>{isFailed ? failure : currentDescription}</p>{isFailed ? <button className="translation-primary translation-render__retry" type="button" onClick={retryFailedNode}><ArrowClockwise />从失败节点重试</button> : <ol className="translation-render__steps"><li className={recognitionDone ? "is-done" : activeStep === "recognition" ? "is-active" : ""}>{recognitionDone ? <CheckCircle weight="fill" /> : activeStep === "recognition" ? <SpinnerGap /> : null}<span>字幕识别</span></li><li className={translationDone ? "is-done" : activeStep === "translation" ? "is-active" : ""}>{translationDone ? <CheckCircle weight="fill" /> : activeStep === "translation" ? <SpinnerGap /> : null}<span>字幕翻译</span></li><li className={ttsDone ? "is-done" : activeStep === "tts" ? "is-active" : ""}>{ttsDone ? <CheckCircle weight="fill" /> : activeStep === "tts" ? <SpinnerGap /> : null}<span>{ttsProgressLabel}</span></li><li className={renderDone ? "is-done" : activeStep === "render" ? "is-active" : ""}>{renderDone ? <CheckCircle weight="fill" /> : activeStep === "render" ? <SpinnerGap /> : null}<span>合成画面与字幕</span></li><li className={isDone(publishState) ? "is-done" : activeStep === "publish" ? "is-active" : ""}>{isDone(publishState) ? <CheckCircle weight="fill" /> : activeStep === "publish" ? <SpinnerGap /> : null}<span>输出成片文件</span></li></ol>}</div>
    </div>
    {!isFailed && <footer className="translation-render__footer"><span className="translation-render__pulse" />生成期间可安全离开，任务将继续在后台执行。</footer>}
  </section>;
}
const RESULT_ACTIONS = [
  { kind: "video", label: "视频下载" },
  { kind: "subtitle", label: "字幕下载" },
  { kind: "voice", label: "音频下载" },
  { kind: "timeline", label: "时间线下载" },
];

function Export({ projectId, onError }) {
  const { t } = useI18n();
  const [result, setResult] = useState(null);
  useEffect(() => {
    getTranslationResult(projectId).then(setResult).catch(() => onError(t("videoTranslation.errors.result")));
  }, [onError, projectId, t]);
  const artifacts = result?.artifacts || [];
  const video = artifacts.find((item) => item.kind === "video");
  return <section className="result-layout translation-result-layout" aria-label="视频翻译任务结果">
    <div className="result-layout__player">
      {video ? <video className="result-layout__video" src={video.cdn_url} controls playsInline preload="metadata" aria-label="视频翻译成片" /> : <div className="result-layout__empty"><SpinnerGap aria-hidden="true" /><p>正在读取成片文件…</p></div>}
    </div>
    <aside className="result-layout__panel" aria-label="结果操作">
      <header className="result-layout__panel-header"><FilmStrip aria-hidden="true" /><h3>任务结果</h3></header>
      <ul className="result-layout__actions">
        {RESULT_ACTIONS.map((action) => {
          const artifact = artifacts.find((item) => item.kind === action.kind);
          if (!artifact) return null;
          return <li key={artifact.id}><div className="result-layout__action">
            <div className="result-layout__action-meta"><span className="result-layout__action-icon" aria-hidden="true"><DownloadSimple /></span><span className="result-layout__action-label">{action.label}</span></div>
            <div className="result-layout__action-ops"><a className="result-layout__pill" href={artifact.cdn_url} target="_blank" rel="noopener noreferrer">预览</a><a className="result-layout__pill result-layout__pill--primary" href={artifact.cdn_url} download>下载</a></div>
            <span className="result-layout__action-id" title={artifact.id}>{artifact.id}</span>
          </div></li>;
        })}
      </ul>
      <div className="result-layout__panel-actions"><Link to="/dashboard/projects" className="result-layout__primary"><ArrowLeft aria-hidden="true" /><span>返回我的项目</span></Link></div>
    </aside>
  </section>;
}
