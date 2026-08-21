import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft } from "@phosphor-icons/react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { CreateUploadFlow } from "./CreatePage.jsx";
import { DashboardHeader } from "../components/dashboard/DashboardHeader.jsx";
import { DashboardMobileNav } from "../components/dashboard/DashboardMobileNav.jsx";
import { DashboardSidebar } from "../components/dashboard/DashboardSidebar.jsx";
import { DashboardToast } from "../components/dashboard/DashboardToast.jsx";
import { NarrationPreview } from "../components/narration/NarrationPreview.jsx";
import { NarrationSettingsForm } from "../components/narration/NarrationSettingsForm.jsx";
import { NarrationStepper } from "../components/narration/NarrationStepper.jsx";
import { dashboardNavItems } from "../data/dashboardData.js";
import { narrationSteps } from "../data/narrationData.js";
import { useAuth } from "../features/auth/AuthProvider.jsx";
import { estimateProjectCost, getAsset, getNarrationConfig, getNarrationSettings, getProjectStage, removeProjectAsset, saveNarrationSettings, saveSettingsAndStartAnalysis } from "../features/projects/projectApi.js";
import { isStageLocked, normalizeStageSnapshot, stagePath } from "../features/projects/narrationStage.js";
import { cacheSubtitleLayout, readCachedSubtitleLayouts } from "../features/subtitle-region/subtitleRegionStorage.js";
import { uploadAsset } from "../features/uploads/ossPostUpload.js";
import { useI18n } from "../i18n/useI18n.js";

const narrationSettingsInflight = new Map();
const DEFAULT_SOURCE_SUBTITLE_REGION = { x: 0, y: 0.78, width: 1, height: 0.12 };
const DEFAULT_NARRATION_SUBTITLE_POSITION = { y: 0.82, font_scale: 0.9 };
const SOURCE_SUBTITLE_RESOLVED_STATUSES = new Set(["confirmed", "none"]);

function confirmedSourceSubtitleLayout(layout) {
  return {
    status: "confirmed",
    region: layout?.region ? { ...layout.region } : { ...DEFAULT_SOURCE_SUBTITLE_REGION },
    detected_confidence: layout?.detected_confidence ?? null,
  };
}

function confirmPendingSourceSubtitleLayouts(videoAssets, sourceSubtitleLayouts) {
  const layouts = { ...sourceSubtitleLayouts };
  const confirmedAssetIds = [];
  videoAssets.forEach((asset) => {
    const current = layouts[asset.id];
    if (SOURCE_SUBTITLE_RESOLVED_STATUSES.has(current?.status)) return;
    layouts[asset.id] = confirmedSourceSubtitleLayout(current);
    confirmedAssetIds.push(asset.id);
  });
  return { layouts, confirmedAssetIds };
}

function loadNarrationSettingsOnce(projectId) {
  const existing = narrationSettingsInflight.get(projectId);
  if (existing) return existing;
  const request = getNarrationSettings(projectId).catch(async (error) => {
    // 本地 Auth 服务短暂未就绪时只进行一次受控重试，避免 StrictMode 触发两条独立请求。
    if (error?.status !== 503) throw error;
    await new Promise((resolve) => window.setTimeout(resolve, 250));
    return getNarrationSettings(projectId);
  });
  narrationSettingsInflight.set(projectId, request);
  request.finally(() => narrationSettingsInflight.delete(projectId)).catch(() => {});
  return request;
}

export function NarrationSettingsPage() {
  const { t } = useI18n();
  const { refreshUser, user } = useAuth();
  const { state: navigationState } = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const projectId = searchParams.get("projectId") || navigationState?.projectId;
  const retrySourceProjectId = searchParams.get("retrySourceProjectId");
  const [config, setConfig] = useState(null);
  const [executionMode, setExecutionMode] = useState("manual");
  const [projectTitle, setProjectTitle] = useState("");
  const [videoAssets, setVideoAssets] = useState([]);
  const [style, setStyle] = useState("");
  const [originalSoundRatio, setOriginalSoundRatio] = useState(30);
  const [ratio, setRatio] = useState("");
  const [voice, setVoice] = useState("");
  const [subtitle, setSubtitle] = useState("");
  const [sourceSubtitleLayouts, setSourceSubtitleLayouts] = useState({});
  const [narrationSubtitlePosition, setNarrationSubtitlePosition] = useState(() => ({ ...DEFAULT_NARRATION_SUBTITLE_POSITION }));
  const [previewVideoId, setPreviewVideoId] = useState("");
  const [sourceSubtitleConfirmationOpen, setSourceSubtitleConfirmationOpen] = useState(false);
  const [customStyle, setCustomStyle] = useState("");
  const [requirements, setRequirements] = useState("");
  const [backgroundMusic, setBackgroundMusic] = useState(null);
  const [backgroundMusicVolume, setBackgroundMusicVolume] = useState(50);
  const [backgroundMusicUploading, setBackgroundMusicUploading] = useState(false);
  const [backgroundMusicError, setBackgroundMusicError] = useState("");
  const [estimate, setEstimate] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [currentStage, setCurrentStage] = useState("settings");
  const [stageLoading, setStageLoading] = useState(Boolean(projectId));
  const [isStartingAnalysis, setIsStartingAnalysis] = useState(false);
  const [toast, setToast] = useState({ id: 0, message: "" });
  const volumeSaveTimerRef = useRef(null);
  const backgroundMusicSaveChainRef = useRef(Promise.resolve());
  // 滑杆采用防抖保存；启动分析前必须以此值同步落库，不能冻结旧音量。
  const pendingBackgroundMusicVolumeRef = useRef(50);
  const isMountedRef = useRef(true);
  const pollCancelledRef = useRef(false);
  const showToast = useCallback((message) => setToast(({ id }) => ({ id: id + 1, message })), []);

  useEffect(() => {
    if (!projectId) return undefined;
    let active = true;
    getNarrationConfig().then((data) => {
      if (!active) return;
      setConfig(data);
      setStyle(data.narration_styles[0]?.id || "");
      setOriginalSoundRatio(data.original_sound_ratios?.includes(30) ? 30 : (data.original_sound_ratios?.[0] ?? 30));
      setRatio(data.video_ratios[0]?.id || "");
      setVoice(data.voices[0]?.id || "");
      setSubtitle(data.subtitle_styles[0]?.id || "");
    }).catch((error) => active && setLoadError(error.message || "解说配置加载失败，请稍后重试。"));
    return () => { active = false; };
  }, [projectId]);

  useEffect(() => {
    if (!projectId) return undefined;
    let active = true;
    estimateProjectCost(projectId)
      .then((data) => active && setEstimate(data))
      .catch(() => active && setEstimate(null));
    return () => { active = false; };
  }, [projectId]);

  useEffect(() => {
    if (!projectId) return undefined;
    let active = true;
    getProjectStage(projectId).then((payload) => {
      if (!active) return;
      const snapshot = normalizeStageSnapshot(payload);
      setCurrentStage(snapshot.currentStage);
      setProjectTitle(snapshot.projectTitle);
      setVideoAssets(snapshot.videoAssets);
      setPreviewVideoId((current) => current || snapshot.videoAssets[0]?.id || "");
      if (isStageLocked(snapshot.currentStage, "settings")) navigate(stagePath(snapshot.currentStage, projectId), { replace: true });
    }).catch((error) => active && setLoadError(error.message || "任务阶段加载失败，请稍后重试。"))
      .finally(() => active && setStageLoading(false));
    return () => { active = false; };
  }, [navigate, projectId]);

  useEffect(() => {
    if (!projectId) return undefined;
    let active = true;
    loadNarrationSettingsOnce(projectId).then((settings) => {
      const music = settings?.background_music;
      if (!active) return;
      if (settings?.narration_style) setStyle(settings.narration_style);
      setOriginalSoundRatio(Number.isInteger(settings?.original_sound_ratio) ? settings.original_sound_ratio : 30);
      if (settings?.video_ratio) setRatio(settings.video_ratio);
      if (settings?.voice_id) setVoice(settings.voice_id);
      if (settings?.subtitle_style) setSubtitle(settings.subtitle_style);
      // 上传页的纯前端探测先写入 sessionStorage；服务端设置可用时以其已确认结果为准。
      setSourceSubtitleLayouts({ ...readCachedSubtitleLayouts(projectId), ...(settings?.source_subtitle_layouts || {}) });
      setNarrationSubtitlePosition(settings?.narration_subtitle_position || { ...DEFAULT_NARRATION_SUBTITLE_POSITION });
      setExecutionMode(settings?.execution_mode === "auto" ? "auto" : "manual");
      setCustomStyle(settings?.custom_style || "");
      setRequirements(settings?.requirements || "");
      if (music?.asset_id) {
        setBackgroundMusic({ assetId: music.asset_id, fileName: music.filename || "背景音乐", playbackUrl: music.cdn_url || "", status: "ready" });
        const restoredVolume = Number.isFinite(music.volume) ? music.volume : 50;
        pendingBackgroundMusicVolumeRef.current = restoredVolume;
        setBackgroundMusicVolume(restoredVolume);
      }
    }).catch(() => {
      // 旧项目没有设置记录时保持空状态，不影响原有解说流程。
    });
    return () => { active = false; };
  }, [projectId]);

  useEffect(() => {
    if (!projectId) return undefined;
    const updateFromUploadDetection = (event) => {
      const { projectId: eventProjectId, assetId, layout } = event.detail || {};
      if (eventProjectId !== projectId || !assetId || !layout) return;
      setSourceSubtitleLayouts((current) => {
        // 用户已经明确确认或选择无字幕后，迟到的探测结果不得覆盖人工决策。
        if (SOURCE_SUBTITLE_RESOLVED_STATUSES.has(current[assetId]?.status)) return current;
        return { ...current, [assetId]: layout };
      });
    };
    window.addEventListener("subtitle-region-layout-updated", updateFromUploadDetection);
    return () => window.removeEventListener("subtitle-region-layout-updated", updateFromUploadDetection);
  }, [projectId]);

  useEffect(() => {
    if (!previewVideoId && videoAssets[0]?.id) setPreviewVideoId(videoAssets[0].id);
  }, [previewVideoId, videoAssets]);

  useEffect(() => {
    // StrictMode 会执行 setup → cleanup → setup；每次 setup 均恢复本实例的轮询标志。
    isMountedRef.current = true;
    pollCancelledRef.current = false;
    return () => {
      isMountedRef.current = false;
      pollCancelledRef.current = true;
      window.clearTimeout(volumeSaveTimerRef.current);
    };
  }, []);

  useEffect(() => {
    if (!toast.message) return undefined;
    const timer = window.setTimeout(() => setToast(({ id }) => ({ id, message: "" })), 3200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const saveBackgroundMusic = useCallback(async (assetId, volume) => {
    if (!projectId) return;
    await saveNarrationSettings(projectId, {
      background_music_asset_id: assetId,
      background_music_volume: volume,
    });
  }, [projectId]);

  // 同一音乐设置严格串行，防止先前的防抖请求在最终保存后返回并覆盖新音量。
  const persistBackgroundMusic = useCallback((assetId, volume) => {
    const operation = backgroundMusicSaveChainRef.current
      .catch(() => {})
      .then(() => saveBackgroundMusic(assetId, volume));
    backgroundMusicSaveChainRef.current = operation;
    return operation;
  }, [saveBackgroundMusic]);

  const waitForBackgroundMusicReady = useCallback(async (asset) => {
    let latest = asset;
    // 前 90 秒快速反馈；之后降为低频轮询，保留 validating 资产直至最终状态。
    for (let attempt = 0; !pollCancelledRef.current; attempt += 1) {
      if (latest.status === "ready") return latest;
      if (latest.status === "invalid") {
        const error = new Error(latest.validation_error || "背景音乐校验失败，请更换音频文件。");
        error.invalidAsset = true;
        error.assetId = latest.id || asset.id;
        throw error;
      }
      await new Promise((resolve) => window.setTimeout(resolve, attempt < 45 ? 2000 : 10000));
      if (pollCancelledRef.current) break;
      try {
        latest = await getAsset(asset.id);
      } catch {
        // 短暂网络抖动不应丢弃仍在 validating 的音乐资产；下个周期继续检测。
      }
    }
    const error = new Error("背景音乐校验已停止。");
    error.pollCancelled = true;
    throw error;
  }, []);

  const handleBackgroundMusicUpload = useCallback(async (file) => {
    if (!projectId || backgroundMusicUploading) return;
    pollCancelledRef.current = false;
    window.clearTimeout(volumeSaveTimerRef.current);
    setBackgroundMusicError("");
    setBackgroundMusic({ fileName: file.name, playbackUrl: "", status: "uploading" });
    setBackgroundMusicUploading(true);
    try {
      const asset = await uploadAsset(projectId, file, "audio");
      setBackgroundMusic({ assetId: asset.id, fileName: asset.filename || asset.name || file.name, playbackUrl: "", status: "validating" });
      const readyAsset = await waitForBackgroundMusicReady(asset);
      const playbackUrl = readyAsset.cdn_url || readyAsset.playback_url || readyAsset.url || readyAsset.source_url || readyAsset.download_url;
      if (!playbackUrl) throw new Error("背景音乐已校验完成，但未取得播放地址。");
      setBackgroundMusic({ assetId: readyAsset.id, fileName: readyAsset.filename || readyAsset.name || file.name, playbackUrl, status: "ready" });
      await persistBackgroundMusic(readyAsset.id, backgroundMusicVolume);
    } catch (error) {
      if (error.invalidAsset) await removeProjectAsset(projectId, error.assetId).catch(() => {});
      if (!error.pollCancelled && isMountedRef.current) {
        setBackgroundMusic(null);
        setBackgroundMusicError(error.message || "背景音乐上传失败，请稍后重试。");
      }
    } finally {
      if (isMountedRef.current) setBackgroundMusicUploading(false);
    }
  }, [backgroundMusicUploading, backgroundMusicVolume, persistBackgroundMusic, projectId, waitForBackgroundMusicReady]);

  const handleBackgroundMusicRemove = useCallback(async () => {
    if (!backgroundMusic || backgroundMusicUploading) return;
    window.clearTimeout(volumeSaveTimerRef.current);
    const removed = backgroundMusic;
    setBackgroundMusic(null);
    setBackgroundMusicError("");
    try {
      await persistBackgroundMusic(null, backgroundMusicVolume);
    } catch (error) {
      setBackgroundMusic(removed);
      setBackgroundMusicError(error.message || "移除背景音乐失败，请稍后重试。");
    }
  }, [backgroundMusic, backgroundMusicUploading, backgroundMusicVolume, persistBackgroundMusic]);

  const handleBackgroundMusicVolumeChange = useCallback((volume) => {
    pendingBackgroundMusicVolumeRef.current = volume;
    setBackgroundMusicVolume(volume);
    if (!projectId || !backgroundMusic?.assetId) return;
    window.clearTimeout(volumeSaveTimerRef.current);
    volumeSaveTimerRef.current = window.setTimeout(() => {
      persistBackgroundMusic(backgroundMusic.assetId, volume).catch((error) => setBackgroundMusicError(error.message || "背景音乐音量保存失败，请稍后重试。"));
    }, 400);
  }, [backgroundMusic?.assetId, persistBackgroundMusic, projectId]);

  const saveSourceSubtitleLayout = useCallback(async (assetId, nextLayout) => {
    if (!projectId || !assetId) return;
    setSourceSubtitleLayouts((current) => ({ ...current, [assetId]: nextLayout }));
    cacheSubtitleLayout(projectId, assetId, nextLayout);
    // 所有字幕布局会在 start-analysis 的同一事务内提交，避免每次拖动/确认都依赖后端。
  }, [projectId]);

  const handleSourceRegionChange = useCallback((region) => {
    if (!previewVideoId) return;
    setSourceSubtitleLayouts((current) => ({
      ...current,
      [previewVideoId]: { ...current[previewVideoId], status: "detected", region },
    }));
  }, [previewVideoId]);

  const handleConfirmSourceSubtitle = useCallback(() => {
    const current = sourceSubtitleLayouts[previewVideoId];
    saveSourceSubtitleLayout(previewVideoId, confirmedSourceSubtitleLayout(current));
  }, [previewVideoId, saveSourceSubtitleLayout, sourceSubtitleLayouts]);

  const handleNoSourceSubtitle = useCallback(() => {
    saveSourceSubtitleLayout(previewVideoId, { status: "none", region: null });
  }, [previewVideoId, saveSourceSubtitleLayout]);

  const handleGoToSourceSubtitleConfirmation = useCallback(() => {
    const firstUnresolved = videoAssets.find((asset) => !SOURCE_SUBTITLE_RESOLVED_STATUSES.has(sourceSubtitleLayouts[asset.id]?.status));
    if (firstUnresolved) setPreviewVideoId(firstUnresolved.id);
    setSourceSubtitleConfirmationOpen(false);
    window.requestAnimationFrame(() => {
      const target = document.getElementById("narration-source-subtitle-controls");
      target?.scrollIntoView({ behavior: "smooth", block: "center" });
      target?.querySelector("button:not(:disabled)")?.focus({ preventScroll: true });
    });
  }, [sourceSubtitleLayouts, videoAssets]);

  const handleConfirmAllSourceSubtitles = useCallback(() => {
    if (!projectId) return;
    const { layouts, confirmedAssetIds } = confirmPendingSourceSubtitleLayouts(videoAssets, sourceSubtitleLayouts);
    confirmedAssetIds.forEach((assetId) => cacheSubtitleLayout(projectId, assetId, layouts[assetId]));
    setSourceSubtitleLayouts(layouts);
    setSourceSubtitleConfirmationOpen(false);
    showToast(`已一键确认 ${confirmedAssetIds.length} 个视频的原字幕位置。`);
  }, [projectId, showToast, sourceSubtitleLayouts, videoAssets]);

  const handleStartAnalysis = useCallback(async () => {
    if (!projectId || isStartingAnalysis || backgroundMusicUploading) return;
    const unresolved = videoAssets.filter((asset) => !SOURCE_SUBTITLE_RESOLVED_STATUSES.has(sourceSubtitleLayouts[asset.id]?.status));
    if (unresolved.length && executionMode === "manual") {
      const firstUnresolved = unresolved[0];
      setPreviewVideoId(firstUnresolved.id);
      setSourceSubtitleConfirmationOpen(true);
      setBackgroundMusicError("");
      return;
    }
    let layoutsForStart = sourceSubtitleLayouts;
    if (unresolved.length) {
      // 自动模式不阻塞用户，按探测结果或默认安全区冻结字幕遮罩决策。
      const { layouts, confirmedAssetIds } = confirmPendingSourceSubtitleLayouts(videoAssets, sourceSubtitleLayouts);
      confirmedAssetIds.forEach((assetId) => cacheSubtitleLayout(projectId, assetId, layouts[assetId]));
      layoutsForStart = layouts;
      setSourceSubtitleLayouts(layouts);
    }
    if (config?.narration_styles.find((item) => item.id === style)?.is_custom && !customStyle.trim()) {
      setBackgroundMusicError("请先填写自定义解说类型。");
      return;
    }
    setIsStartingAnalysis(true);
    setBackgroundMusicError("");
    try {
      // 取消尚未触发的防抖写入，并显式等待最后一个音量值保存完成。
      // start-analysis 会读取该持久化设置制作不可变快照，不能与旧值竞争。
      window.clearTimeout(volumeSaveTimerRef.current);
      if (backgroundMusic?.assetId) {
        await persistBackgroundMusic(backgroundMusic.assetId, pendingBackgroundMusicVolumeRef.current);
      }
      await saveSettingsAndStartAnalysis(projectId, {
        narration_style: style,
        custom_style: customStyle.trim() || null,
        original_sound_ratio: originalSoundRatio,
        video_ratio: ratio,
        voice_id: voice,
        subtitle_style: subtitle,
        requirements: requirements.trim() || null,
        execution_mode: executionMode,
        source_subtitle_layouts: layoutsForStart,
        narration_subtitle_position: narrationSubtitlePosition,
      });
      refreshUser().catch(() => {});
      // 启动接口只返回 workflow_id；成功即表示原子保存与阶段切换均已完成。
      navigate(stagePath("analysis", projectId), { replace: true });
    } catch (error) {
      setBackgroundMusicError(error.message || "参数保存失败，未启动 AI 分析。");
    } finally {
      setIsStartingAnalysis(false);
    }
  }, [backgroundMusic?.assetId, backgroundMusicUploading, config?.narration_styles, customStyle, executionMode, isStartingAnalysis, navigate, narrationSubtitlePosition, originalSoundRatio, persistBackgroundMusic, projectId, ratio, refreshUser, requirements, sourceSubtitleLayouts, style, subtitle, videoAssets, voice]);

  const settingsLocked = isStageLocked(currentStage, "settings");
  const unresolvedSubtitleCount = videoAssets.filter((asset) => !SOURCE_SUBTITLE_RESOLVED_STATUSES.has(sourceSubtitleLayouts[asset.id]?.status)).length;
  return (
    <div className="narration-shell" data-page={projectId ? "narration-settings" : "narration-upload"}>
      <h1 className="sr-only" data-route-heading tabIndex="-1">{t("narration.routeHeading")}</h1>
      <DashboardSidebar items={dashboardNavItems} onUnavailable={showToast} />
      <div className="narration-workspace">
        <DashboardHeader credits={{ balance: user?.credit_balance ?? null }} onUnavailable={showToast} />
        <main className="narration-main">
          <header className="narration-topbar">
            <Link to="/dashboard" aria-label={t("narration.back")}><ArrowLeft aria-hidden="true" /></Link>
            <strong>{t("narration.name")}</strong>
            <i />
            <h2>{projectId ? (projectTitle || projectId) : t("create.routeHeading")}</h2>
          </header>
          {/* 设置页本身就是 "参数设置" 阶段，进度条高亮应跟随当前所在页面，不被后端 current_stage 残留值（如 create）覆盖。 */}
          <NarrationStepper steps={narrationSteps} currentStage={projectId ? "settings" : "create"} />
          {!projectId ? (
            <section className="narration-upload-stage" aria-label={t("create.upload.title")}>
              <CreateUploadFlow fixedType="narration" retrySourceProjectId={retrySourceProjectId} onFeedback={showToast} showTypeSelector={false} />
            </section>
          ) : loadError ? (
            <p role="alert">{loadError}</p>
          ) : stageLoading || !config ? (
            <p>{t("narration.messages.loadingConfig")}</p>
          ) : (
            <div className="narration-content">
              <NarrationSettingsForm
                config={config}
                executionMode={executionMode}
                selectedStyle={style}
                selectedOriginalSoundRatio={originalSoundRatio}
                selectedRatio={ratio}
                selectedVoice={voice}
                selectedSubtitle={subtitle}
                customStyle={customStyle}
                requirements={requirements}
                backgroundMusic={backgroundMusic}
                backgroundMusicVolume={backgroundMusicVolume}
                backgroundMusicUploading={backgroundMusicUploading}
                backgroundMusicError={backgroundMusicError}
                backgroundMusicDisabled={!projectId || settingsLocked}
                disabled={settingsLocked || isStartingAnalysis}
                onExecutionModeChange={setExecutionMode}
                onStyleChange={setStyle}
                onOriginalSoundRatioChange={setOriginalSoundRatio}
                onRatioChange={setRatio}
                onVoiceChange={setVoice}
                onSubtitleChange={setSubtitle}
                onCustomStyleChange={setCustomStyle}
                onRequirementsChange={setRequirements}
                onBackgroundMusicUpload={handleBackgroundMusicUpload}
                onBackgroundMusicRemove={handleBackgroundMusicRemove}
                onBackgroundMusicVolumeChange={handleBackgroundMusicVolumeChange}
              />
              <div className="narration-right">
                <NarrationPreview
                  ratio={ratio}
                  estimate={estimate}
                  videos={videoAssets}
                  selectedVideoId={previewVideoId}
                  onSelectedVideoChange={setPreviewVideoId}
                  sourceSubtitleLayout={sourceSubtitleLayouts[previewVideoId]}
                  onSourceRegionChange={handleSourceRegionChange}
                  onConfirmSourceSubtitle={handleConfirmSourceSubtitle}
                  onNoSourceSubtitle={handleNoSourceSubtitle}
                  narrationSubtitlePosition={narrationSubtitlePosition}
                  onNarrationSubtitlePositionChange={setNarrationSubtitlePosition}
                  subtitleStyle={subtitle}
                  subtitleStyles={config.subtitle_styles}
                  disabled={settingsLocked || isStartingAnalysis}
                />
                <footer className="narration-actions">
                  <Link to="/dashboard">{t("narration.actions.previous")}</Link>
                  <button type="button" onClick={handleStartAnalysis} disabled={settingsLocked || isStartingAnalysis || backgroundMusicUploading}>
                    {isStartingAnalysis
                      ? t(executionMode === "auto" ? "narration.actions.startingAuto" : "narration.actions.startingAnalysis")
                      : t(executionMode === "auto" ? "narration.actions.startAuto" : "narration.actions.startAnalysis")}
                  </button>
                </footer>
              </div>
            </div>
          )}
        </main>
      </div>
      <DashboardMobileNav items={dashboardNavItems} onUnavailable={showToast} />
      {sourceSubtitleConfirmationOpen && unresolvedSubtitleCount > 0 && <div className="narration-subtitle-dialog" role="dialog" aria-modal="true" aria-labelledby="source-subtitle-confirmation-title"><div><span className="narration-subtitle-dialog__eyebrow">开始分析前</span><h2 id="source-subtitle-confirmation-title">还有 {unresolvedSubtitleCount} 个视频未确认字幕处理方式</h2><p>请逐个确认原字幕遮罩位置，或选择“无字幕”。也可以按当前探测结果与默认遮罩区域一键完成确认。</p><div className="narration-subtitle-dialog__summary"><strong>{unresolvedSubtitleCount}</strong><span>个视频待确认</span></div><footer><button type="button" autoFocus onClick={handleGoToSourceSubtitleConfirmation}>去确认</button><button type="button" onClick={handleConfirmAllSourceSubtitles}>一键确认</button></footer></div></div>}
      {toast.message && <DashboardToast key={toast.id} message={toast.message} onClose={() => setToast(({ id }) => ({ id, message: "" }))} />}
    </div>
  );
}
