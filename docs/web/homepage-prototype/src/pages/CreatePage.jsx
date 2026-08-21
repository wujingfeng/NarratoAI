import { ShieldCheck } from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { CreationSummary } from "../components/create/CreationSummary.jsx";
import { CreationTypeSelector } from "../components/create/CreationTypeSelector.jsx";
import { VideoUploadPanel } from "../components/create/VideoUploadPanel.jsx";
import { DashboardHeader } from "../components/dashboard/DashboardHeader.jsx";
import { DashboardMobileNav } from "../components/dashboard/DashboardMobileNav.jsx";
import { DashboardSidebar } from "../components/dashboard/DashboardSidebar.jsx";
import { DashboardToast } from "../components/dashboard/DashboardToast.jsx";
import { dashboardNavItems } from "../data/dashboardData.js";
import { creationTypes } from "../data/createData.js";
import { useAuth } from "../features/auth/AuthProvider.jsx";
import { uploadAsset } from "../features/uploads/ossPostUpload.js";
import { canStartProject, createProject, createRetryDraft, estimateProjectCost, getAsset, getProjectStage, removeProjectAsset, reorderProjectVideoAssets } from "../features/projects/projectApi.js";
import { normalizeStageSnapshot } from "../features/projects/narrationStage.js";
import { estimateTranslationCost } from "../features/video-translation/translationApi.js";
import { SubtitleDetectionAbortedError, getSubtitleRegionDetector } from "../features/subtitle-region/subtitleRegionDetector.js";
import { cacheSubtitleLayout } from "../features/subtitle-region/subtitleRegionStorage.js";
import { useI18n } from "../i18n/useI18n.js";

const VIDEO_EXTENSIONS = new Set(["mp4", "mov", "avi"]);
const VIDEO_SIZE_LIMIT = 300 * 1024 * 1024;
const SUBTITLE_SIZE_LIMIT = 5 * 1024 * 1024;
const newClientVideoId = () => globalThis.crypto?.randomUUID?.() || `local-${Date.now()}-${Math.random().toString(16).slice(2)}`;

function formatDuration(totalSeconds) {
  // 探测服务返回浮点秒数；展示和计费摘要必须先归整到整数秒，避免 06:0.001996 这类精度尾巴。
  const safeTotalSeconds = Math.max(0, Math.round(Number(totalSeconds) || 0));
  const hours = Math.floor(safeTotalSeconds / 3600);
  const minutes = Math.floor((safeTotalSeconds % 3600) / 60);
  const seconds = safeTotalSeconds % 60;
  return hours > 0
    ? [hours, minutes, seconds].map((value) => String(value).padStart(2, "0")).join(":")
    : [minutes, seconds].map((value) => String(value).padStart(2, "0")).join(":");
}

function readVideoDuration(file) {
  return new Promise((resolve) => {
    const video = document.createElement("video");
    const objectUrl = URL.createObjectURL(file);
    let settled = false;
    const settle = (duration) => {
      if (settled) return;
      settled = true;
      video.removeEventListener("loadedmetadata", handleMetadata);
      video.removeEventListener("error", handleError);
      URL.revokeObjectURL(objectUrl);
      resolve(duration);
    };
    const handleMetadata = () => {
      const duration = Number(video.duration);
      settle(Number.isFinite(duration) && duration >= 0 ? Math.round(duration) : null);
    };
    const handleError = () => settle(null);
    video.preload = "metadata";
    video.addEventListener("loadedmetadata", handleMetadata);
    video.addEventListener("error", handleError);
    video.src = objectUrl;
    video.load();
  });
}

const ignoreFeedback = () => {};

export function CreateUploadFlow({ fixedType = null, initialProjectId = null, retrySourceProjectId = null, onFeedback = ignoreFeedback, showTypeSelector = true }) {
  const { t } = useI18n();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [selectedType, setSelectedType] = useState(fixedType || "narration");
  const [videos, setVideos] = useState([]);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isReordering, setIsReordering] = useState(false);
  const [removingSubtitleAssetId, setRemovingSubtitleAssetId] = useState(null);
  const uploadInFlight = useRef(false);
  const subtitleDetectionJobsRef = useRef(new Map());
  const subtitleDetectionResultsRef = useRef(new Map());
  const uploadedAssetByClientIdRef = useRef(new Map());
  const removedClientIdsRef = useRef(new Set());
  const pendingRemovedAssetIdsRef = useRef(new Set());
  const assetStatusPollTimersRef = useRef(new Map());
  // 重试入口会在加载时物化一个新草稿。用同一 Promise 抵御 Strict Mode
  // 的 effect 重放，避免一次点击创建多个草稿。
  const retryDraftPromiseRef = useRef(null);
  const [projectId, setProjectId] = useState(null);
  const [apiCredits, setApiCredits] = useState(null);

  const cacheDetectedSubtitleLayout = useCallback((activeProjectId, clientId) => {
    const result = subtitleDetectionResultsRef.current.get(clientId);
    const assetId = uploadedAssetByClientIdRef.current.get(clientId);
    if (!result || !assetId || !activeProjectId || removedClientIdsRef.current.has(clientId)) return;
    cacheSubtitleLayout(activeProjectId, assetId, {
      status: result.status,
      region: result.region || null,
      detected_confidence: result.confidence || null,
    });
  }, []);

  const cancelAssetStatusPoll = useCallback((assetId) => {
    const timer = assetStatusPollTimersRef.current.get(assetId);
    if (timer) window.clearTimeout(timer);
    assetStatusPollTimersRef.current.delete(assetId);
  }, []);

  useEffect(() => () => {
    assetStatusPollTimersRef.current.forEach((timer) => window.clearTimeout(timer));
    assetStatusPollTimersRef.current.clear();
  }, []);

  const startSubtitleDetection = useCallback((file, clientId, activeProjectIdRef) => {
    const controller = new AbortController();
    subtitleDetectionJobsRef.current.set(clientId, controller);
    getSubtitleRegionDetector().detect(file, {
      signal: controller.signal,
      onProgress: ({ current, total }) => setVideos((currentVideos) => currentVideos.map((video) => video.clientId === clientId
        ? { ...video, subtitleDetectionStatus: "detecting", subtitleDetectionProgress: `${current}/${total}` }
        : video)),
    }).then((result) => {
      subtitleDetectionResultsRef.current.set(clientId, result);
      if (removedClientIdsRef.current.has(clientId)) return;
      setVideos((currentVideos) => currentVideos.map((video) => video.clientId === clientId
        ? { ...video, subtitleDetectionStatus: result.status, subtitleDetectionProgress: null, detectedSubtitleRegion: result.region || null, detectedSubtitleConfidence: result.confidence || null }
        : video));
      cacheDetectedSubtitleLayout(activeProjectIdRef.current, clientId);
    }).catch((error) => {
      if (error instanceof SubtitleDetectionAbortedError) return;
      const assetId = uploadedAssetByClientIdRef.current.get(clientId);
      if (assetId && activeProjectIdRef.current) {
        cacheSubtitleLayout(activeProjectIdRef.current, assetId, { status: "failed", region: null, error: error.message || "字幕检测模型运行失败" });
      }
      setVideos((currentVideos) => currentVideos.map((video) => video.clientId === clientId
        ? { ...video, subtitleDetectionStatus: "failed", subtitleDetectionProgress: null }
        : video));
    }).finally(() => subtitleDetectionJobsRef.current.delete(clientId));
  }, [cacheDetectedSubtitleLayout]);

  useEffect(() => {
    if (fixedType) setSelectedType(fixedType);
  }, [fixedType]);

  useEffect(() => {
    const preloadProjectId = initialProjectId || retrySourceProjectId;
    if (!preloadProjectId) return undefined;
    let active = true;
    if (initialProjectId) setProjectId(initialProjectId);
    setApiCredits(null);
    const stageVideos = (payload) => normalizeStageSnapshot(payload).videoAssets.map((asset) => ({
      id: asset.id,
      assetId: asset.id,
      assetStatus: "ready",
      name: asset.filename,
      durationSeconds: asset.durationSeconds || 0,
      durationLabel: asset.durationSeconds === null ? "--:--" : formatDuration(Math.ceil(asset.durationSeconds || 0)),
      subtitleAssetId: asset.subtitleAssetId,
      subtitleAssetStatus: asset.subtitleAssetId ? "ready" : null,
      subtitleName: asset.subtitleFilename,
      subtitleStatus: asset.subtitleFilename ? "字幕已校验" : "上传 SRT 字幕文件",
      statusTone: asset.subtitleFilename ? "success" : "warning",
      thumbnail: null,
    }));
    getProjectStage(preloadProjectId)
      .then(async (payload) => {
        if (!active) return;
        // 旧项目的报价是已冻结的历史扣费，不能拿来作为新一次重新生成的初始
        // 报价。视频翻译在进入上传页时先物化草稿，再由草稿的无冻结报价计算。
        if (retrySourceProjectId && !initialProjectId && selectedType === "translation") {
          if (!retryDraftPromiseRef.current) retryDraftPromiseRef.current = createRetryDraft(retrySourceProjectId);
          const draft = await retryDraftPromiseRef.current;
          const draftProjectId = draft.project_id || draft.projectId;
          if (!draftProjectId) throw new Error("草稿创建失败，未返回项目 ID");
          const draftStage = await getProjectStage(draftProjectId);
          if (!active) return;
          setProjectId(draftProjectId);
          setVideos(stageVideos(draftStage));
          // URL 绑定新草稿，刷新或返回此页不会再次从已收费的源项目报价。
          navigate(`/dashboard/video-translation/upload?projectId=${encodeURIComponent(draftProjectId)}`, { replace: true });
          return;
        }
        setVideos(stageVideos(payload));
      })
      .catch((error) => {
        retryDraftPromiseRef.current = null;
        if (active) onFeedback(error.message || "原项目素材读取失败，请重新上传。 ");
      });
    return () => { active = false; };
  }, [initialProjectId, navigate, onFeedback, retrySourceProjectId, selectedType]);

  const summary = useMemo(() => {
    const totalSeconds = videos.reduce((total, video) => total + video.durationSeconds, 0);
    return {
      // 后端视频翻译报价先向上取整到秒、再向上取整到分钟；展示不能把
      // 180.01 秒误显示成 03:00 而让 4 分钟报价看起来像计算错误。
      durationLabel: formatDuration(selectedType === "translation" ? Math.ceil(totalSeconds) : totalSeconds),
    };
  }, [selectedType, videos]);

  const selectedCreationType = creationTypes.find((type) => type.id === selectedType);
  const assets = videos.flatMap((video) => [
    { status: video.assetStatus },
    ...(video.subtitleAssetStatus ? [{ status: video.subtitleAssetStatus }] : []),
  ]);
  const canStart = Boolean(projectId || retrySourceProjectId) && canStartProject(assets);
  // 视频翻译必须携带对应视频的字幕检测结果进入设置页；检测未完成时禁止抢跑，
  // 避免设置页落回默认字幕框。其它创作类型不受这个门禁影响。
  const pendingSubtitleDetectionCount = selectedType === "translation"
    ? videos.filter((video) => video.subtitleDetectionStatus === "detecting").length
    : 0;
  const subtitleDetectionPending = pendingSubtitleDetectionCount > 0;
  useEffect(() => {
    // 创建任务阶段只展示视频翻译的基础时长费用。人声分离由第二步的
    // “替换人声”选项决定，设置页会按该选项重新报价并加上附加费。
    const estimateProjectId = projectId || (selectedType === "translation" ? retrySourceProjectId : null);
    if (!estimateProjectId || !canStart || isUploading || isReordering || apiCredits !== null) return undefined;
    let active = true;
    const estimate = selectedType === "translation"
      ? estimateTranslationCost(estimateProjectId, "translated_voice_only")
      : estimateProjectCost(estimateProjectId);
    estimate
      .then((result) => {
        if (!active) return;
        setApiCredits(result.credits);
        // 视频翻译以服务端媒体探测的时长作为最终展示和计费依据，避免浏览器
        // loadedmetadata 与后端探测相差一秒时出现“显示 03:00、按 03:01 收费”。
        const authoritativeSeconds = Math.ceil(Number(result.total_source_seconds));
        if (selectedType === "translation" && Number.isFinite(authoritativeSeconds) && authoritativeSeconds > 0) {
          setVideos((current) => current.map((video, index) => index === 0
            ? {
              ...video,
              durationSeconds: authoritativeSeconds,
              durationLabel: formatDuration(authoritativeSeconds),
              durationSource: "server",
            }
            : video));
        }
      })
      .catch((error) => { if (active) onFeedback(error.message || "无法获取 API 费用"); });
    return () => { active = false; };
  }, [apiCredits, canStart, isReordering, isUploading, onFeedback, projectId, retrySourceProjectId, selectedType]);

  const handleTypeChange = (typeId) => {
    if (fixedType) return;
    setSelectedType(typeId);
  };

  // 把"重新生成"流下的回填素材物化为可编辑草稿。已存在 projectId 时直接复用，
  // 未存在时拉取源项目、写入新草稿、刷新本地素材列表，并清空当前报价。
  // 克隆后的 asset ID 与源项目不同，因此同时返回源/新草稿视频 ID 映射。
  const ensureRetryDraft = useCallback(async () => {
    if (!retrySourceProjectId || projectId) {
      return { projectId, sourceVideoIdToDraftId: new Map() };
    }
    const sourceVideoIds = videos.map((video) => video.id);
    const draft = await createRetryDraft(retrySourceProjectId);
    const activeProjectId = draft.project_id || draft.projectId;
    if (!activeProjectId) throw new Error("草稿创建失败，未返回项目 ID");
    const stage = normalizeStageSnapshot(await getProjectStage(activeProjectId));
    const draftVideos = stage.videoAssets.map((asset) => ({
      id: asset.id,
      assetId: asset.id,
      assetStatus: "ready",
      name: asset.filename,
      durationSeconds: asset.durationSeconds || 0,
      durationLabel: asset.durationSeconds === null ? "--:--" : formatDuration(asset.durationSeconds),
      subtitleAssetId: asset.subtitleAssetId,
      subtitleAssetStatus: asset.subtitleAssetId ? "ready" : null,
      subtitleName: asset.subtitleFilename,
      subtitleStatus: asset.subtitleFilename ? "字幕已校验" : "上传 SRT 字幕文件",
      statusTone: asset.subtitleFilename ? "success" : "warning",
      thumbnail: null,
    }));
    const sourceVideoIdToDraftId = new Map(sourceVideoIds.flatMap((sourceVideoId, index) => {
      const draftVideoId = draftVideos[index]?.id;
      return draftVideoId ? [[sourceVideoId, draftVideoId]] : [];
    }));
    setVideos(draftVideos);
    setProjectId(activeProjectId);
    setApiCredits(null);
    return { projectId: activeProjectId, sourceVideoIdToDraftId };
  }, [projectId, retrySourceProjectId, videos]);

  const handleVideoFiles = async (files) => {
    if (isUploading || isReordering || uploadInFlight.current) return;
    const validFiles = files.filter((file) => {
      const extension = file.name.split(".").pop()?.toLowerCase();
      return VIDEO_EXTENSIONS.has(extension) && file.size <= VIDEO_SIZE_LIMIT;
    });
    if (validFiles.length !== files.length) onFeedback("仅支持 300 MiB 以内的 MP4、MOV 或 AVI 文件");
    if (!validFiles.length) return;
    const availableCount = selectedCreationType.maxVideos - videos.length;
    if (availableCount <= 0) {
      onFeedback(`${selectedCreationType.title}最多上传 ${selectedCreationType.maxVideos} 个视频`);
      return;
    }
    const acceptedFiles = validFiles.slice(0, availableCount);
    if (acceptedFiles.length < validFiles.length) {
      onFeedback(`${selectedCreationType.title}最多上传 ${selectedCreationType.maxVideos} 个视频`);
    }
    // 上传和本地 OCR 同时开始；探测不依赖 OSS 传输完成。
    const activeProjectIdRef = { current: projectId };
    const pendingVideos = acceptedFiles.map((file) => ({
      id: newClientVideoId(),
      clientId: null,
      assetId: null,
      assetStatus: "uploading",
      name: file.name,
      durationSeconds: 0,
      durationLabel: "--:--",
      subtitleStatus: "上传 SRT 字幕文件",
      statusTone: "warning",
      subtitleName: null,
      thumbnail: null,
      subtitleDetectionStatus: "detecting",
      subtitleDetectionProgress: "准备中",
    })).map((video) => ({ ...video, clientId: video.id }));
    setVideos((current) => [...current, ...pendingVideos]);
    pendingVideos.forEach((video, index) => startSubtitleDetection(acceptedFiles[index], video.clientId, activeProjectIdRef));
    uploadInFlight.current = true;
    setIsUploading(true);
    setApiCredits(null);
    try {
      let activeProjectId = projectId;
      let existingVideos = videos;
      // 回填本身不创建草稿；用户首次继续上传时才将回填素材物化为可编辑草稿。
      if (retrySourceProjectId && !activeProjectId) {
        const draft = await createRetryDraft(retrySourceProjectId);
        activeProjectId = draft.project_id || draft.projectId;
        const stage = normalizeStageSnapshot(await getProjectStage(activeProjectId));
        existingVideos = stage.videoAssets.map((asset) => ({
          id: asset.id,
          assetId: asset.id,
          assetStatus: "ready",
          name: asset.filename,
          durationSeconds: asset.durationSeconds || 0,
          durationLabel: asset.durationSeconds === null ? "--:--" : formatDuration(asset.durationSeconds),
          subtitleAssetId: asset.subtitleAssetId,
          subtitleAssetStatus: asset.subtitleAssetId ? "ready" : null,
          subtitleName: asset.subtitleFilename,
          subtitleStatus: asset.subtitleFilename ? "字幕已校验" : "上传 SRT 字幕文件",
          statusTone: asset.subtitleFilename ? "success" : "warning",
          thumbnail: null,
        }));
        setVideos([...existingVideos, ...pendingVideos]);
      }
      if (!activeProjectId) activeProjectId = (await createProject(selectedType)).id;
      setProjectId(activeProjectId);
      activeProjectIdRef.current = activeProjectId;
      const uploaded = await Promise.all(pendingVideos.map(async (pendingVideo, index) => {
        const file = acceptedFiles[index];
        const asset = await uploadAsset(activeProjectId, file, "video");
        if (removedClientIdsRef.current.has(pendingVideo.clientId)) {
          await removeProjectAsset(activeProjectId, asset.id).catch(() => {});
          return null;
        }
        uploadedAssetByClientIdRef.current.set(pendingVideo.clientId, asset.id);
        cacheSubtitleLayout(activeProjectId, asset.id, { status: "detecting", region: null });
        setVideos((current) => current.map((video) => video.clientId === pendingVideo.clientId
          ? { ...video, id: asset.id, assetId: asset.id, assetStatus: asset.status }
          : video));
        cacheDetectedSubtitleLayout(activeProjectId, pendingVideo.clientId);
        return { file, asset, clientId: pendingVideo.clientId };
      }));
      const completedUploads = uploaded.filter(Boolean);
      const orderedVideos = [...existingVideos, ...completedUploads.map(({ asset }) => ({ assetId: asset.id }))];
      try {
        await reorderProjectVideoAssets(
          activeProjectId,
          orderedVideos.map((video) => video.assetId),
        );
      } catch (error) {
        onFeedback(error.message || t("create.messages.orderSaveAfterUploadFailed"));
      }
      completedUploads.forEach(({ asset, file, clientId }) => {
        readVideoDuration(file).then((durationSeconds) => {
          if (durationSeconds === null) return;
          setVideos((current) => current.map((video) => video.clientId === clientId
            // 报价接口已返回权威时长后，不能再让本地 metadata 的近似值覆盖它。
            ? video.durationSource === "server" ? video : { ...video, durationSeconds, durationLabel: formatDuration(durationSeconds), durationSource: "local" }
            : video));
        });
      });
      completedUploads.forEach(({ asset, clientId }) => {
        if (asset.status === "ready" || asset.status === "invalid") return;
        const poll = async () => {
          // 用户移除素材后取消定时器；避免已删除 asset 的 404 轮询请求。
          if (removedClientIdsRef.current.has(clientId)) {
            cancelAssetStatusPoll(asset.id);
            return;
          }
          try {
            const latest = await getAsset(asset.id);
            if (removedClientIdsRef.current.has(clientId)) {
              cancelAssetStatusPoll(asset.id);
              return;
            }
            setVideos((current) => current.map((video) => video.assetId === asset.id
              ? {
                ...video,
                assetStatus: latest.status,
              }
              : video));
            if (latest.status === "validating") {
              const timer = window.setTimeout(poll, 2000);
              assetStatusPollTimersRef.current.set(asset.id, timer);
            } else cancelAssetStatusPoll(asset.id);
          } catch (error) {
            if (removedClientIdsRef.current.has(clientId) || error?.status === 404) {
              cancelAssetStatusPoll(asset.id);
              return;
            }
            onFeedback(error.message || "素材校验状态读取失败，请稍后重试。");
          }
        };
        const timer = window.setTimeout(poll, 2000);
        assetStatusPollTimersRef.current.set(asset.id, timer);
      });
    } catch (error) {
      onFeedback(error.message || "上传失败，请稍后重试");
    } finally {
      uploadInFlight.current = false;
      setIsUploading(false);
    }
  };

  const handleNext = async () => {
    if (videos.length > selectedCreationType.maxVideos) {
      onFeedback(`${selectedCreationType.title}当前有 ${videos.length} 个视频，最多支持 ${selectedCreationType.maxVideos} 个`);
      return;
    }
    if (!canStart) {
      onFeedback("请等待全部素材校验完成后再开始");
      return;
    }
    if (subtitleDetectionPending) {
      onFeedback(t("create.messages.waitSubtitleDetection", { count: pendingSubtitleDetectionCount }));
      return;
    }
    // 页面跳转前再做一次顺序屏障：即使上传后的首次同步遇到网络抖动，
    // 工作流也绝不能读取到与用户当前可见列表不一致的视频顺序。
    setIsReordering(true);
    try {
      if (retrySourceProjectId && !projectId) {
        const draft = await createRetryDraft(retrySourceProjectId);
        const draftProjectId = draft.project_id || draft.projectId;
        setProjectId(draftProjectId);
        navigate(selectedType === "translation" ? `/dashboard/video-translation/settings?projectId=${encodeURIComponent(draftProjectId)}` : `/dashboard/narration/settings?projectId=${encodeURIComponent(draftProjectId)}`, { replace: true });
        return;
      }
      // 用户移除后的后台清理若遇到瞬时错误，在进入参数设置前重试一次。
      // 否则服务端会保留已从界面消失的 asset，完整顺序校验必然返回 422。
      const visibleAssetIds = new Set(videos.map((video) => video.assetId).filter(Boolean));
      const serverStage = normalizeStageSnapshot(await getProjectStage(projectId));
      const serverOnlyAssetIds = serverStage.videoAssets
        .map((asset) => asset.id)
        .filter((assetId) => !visibleAssetIds.has(assetId));
      const pendingRemovedAssetIds = [...new Set([
        ...pendingRemovedAssetIdsRef.current,
        ...serverOnlyAssetIds,
      ])];
      if (pendingRemovedAssetIds.length) {
        await Promise.all(pendingRemovedAssetIds.map(async (assetId) => {
          await removeProjectAsset(projectId, assetId);
          pendingRemovedAssetIdsRef.current.delete(assetId);
        }));
      }
      await reorderProjectVideoAssets(
        projectId,
        videos.map((video) => video.assetId),
      );
      // 工作流只能在参数快照持久化后启动；这里仅完成“创建任务”阶段。
      navigate(selectedType === "translation" ? `/dashboard/video-translation/settings?projectId=${encodeURIComponent(projectId)}` : `/dashboard/narration/settings?projectId=${encodeURIComponent(projectId)}`, { replace: true });
    } catch (error) {
      onFeedback(error.message || t("create.messages.orderSaveBeforeNextFailed"));
    } finally {
      setIsReordering(false);
    }
  };

  const handleRemoveVideo = async (videoId) => {
    const video = videos.find((item) => item.id === videoId);
    if (!video || isReordering) return;
    const clientId = video.clientId || video.id;
    removedClientIdsRef.current.add(clientId);
    subtitleDetectionJobsRef.current.get(clientId)?.abort();
    subtitleDetectionJobsRef.current.delete(clientId);
    if (video.assetId) cancelAssetStatusPoll(video.assetId);
    // 本地待上传条目没有服务端 asset，先从界面移除；upload 完成回调会立即清理刚建成的 asset。
    if (!video.assetId) {
      setVideos((current) => current.filter((item) => item.id !== videoId));
      setApiCredits(null);
      return;
    }
    // 重新生成回填后用户首次删除回填素材时，把回填素材物化为可编辑草稿后再调用服务端删除。
    if (retrySourceProjectId && !projectId) {
      try {
        await ensureRetryDraft();
      } catch (error) {
        onFeedback(error.message || "草稿创建失败，请稍后重试");
        return;
      }
    }
    if (!projectId) return;
    // 已完成上传的素材在服务端/OSS 也有记录，因此仍需后台清理；但不应阻塞前端移除。
    setVideos((current) => current.filter((item) => item.id !== videoId));
    setApiCredits(null);
    pendingRemovedAssetIdsRef.current.add(video.assetId);
    removeProjectAsset(projectId, video.assetId)
      .then(() => pendingRemovedAssetIdsRef.current.delete(video.assetId))
      .catch((error) => {
        onFeedback(error.message || "素材已从列表移除，进入下一步时会自动重试服务端清理。");
      });
  };

  const handleVideoSubtitle = async (videoId, file) => {
    if (!file.name.toLowerCase().endsWith(".srt") || file.size > SUBTITLE_SIZE_LIMIT) {
      onFeedback("仅支持 5 MiB 以内的 SRT 字幕文件");
      return;
    }
    if (isUploading || isReordering || uploadInFlight.current) return;
    const previousSubtitle = videos.find((video) => video.id === videoId);
    uploadInFlight.current = true;
    setIsUploading(true);
    // SRT 只影响字幕内容，不改变源视频时长或计费规则；保留已计算的创作小结，
    // 避免上传字幕时闪空并触发一次不必要的重新报价。
    // 重新生成回填后用户首次上传字幕/编辑素材，都要先把回填素材物化为可编辑草稿。
    // 失败时回滚 UI 状态并提示，不要再用旧的"请下一步后再编辑"误导用户。
    let activeProjectId;
    let activeVideoId = videoId;
    try {
      const retryDraft = await ensureRetryDraft();
      activeProjectId = retryDraft.projectId;
      activeVideoId = retryDraft.sourceVideoIdToDraftId.get(videoId) || videoId;
    } catch (error) {
      uploadInFlight.current = false;
      setIsUploading(false);
      onFeedback(error.message || "草稿创建失败，请稍后重试");
      return;
    }
    if (!activeProjectId) {
      uploadInFlight.current = false;
      setIsUploading(false);
      return;
    }
    // 在 policy 请求返回前就让 canStart 失效，避免旧的 ready 状态触发并发报价。
    setVideos((current) => current.map((video) => video.id === activeVideoId
      ? {
        ...video,
        subtitleName: file.name,
        subtitleAssetStatus: "uploading",
        subtitleStatus: "字幕上传中",
        statusTone: "warning",
      }
      : video));
    try {
      const asset = await uploadAsset(activeProjectId, file, "subtitle");
      setVideos((current) => current.map((video) => video.id === activeVideoId
        ? {
          ...video,
          subtitleName: file.name,
          subtitleAssetId: asset.id,
          subtitleAssetStatus: asset.status,
          subtitleStatus: asset.status === "ready" ? "字幕已校验" : "字幕校验中",
          statusTone: asset.status === "ready" ? "success" : "warning",
        }
        : video));
      if (asset.status !== "ready" && asset.status !== "invalid") {
        const poll = async () => {
          try {
            const latest = await getAsset(asset.id);
            setVideos((current) => current.map((video) => video.subtitleAssetId === asset.id
              ? {
                ...video,
                subtitleAssetStatus: latest.status,
                subtitleStatus: latest.status === "ready" ? "字幕已校验" : latest.status === "invalid" ? "字幕校验失败" : "字幕校验中",
                statusTone: latest.status === "ready" ? "success" : "warning",
              }
              : video));
            if (latest.status === "validating") window.setTimeout(poll, 2000);
          } catch (error) {
            onFeedback(error.message || "字幕校验状态读取失败，请稍后重试。");
          }
        };
        window.setTimeout(poll, 2000);
      }
    } catch (error) {
      setVideos((current) => current.map((video) => video.id === activeVideoId
        ? {
          ...video,
          subtitleName: previousSubtitle?.subtitleName ?? null,
          subtitleAssetId: previousSubtitle?.subtitleAssetId,
          subtitleAssetStatus: previousSubtitle?.subtitleAssetStatus,
          subtitleStatus: previousSubtitle?.subtitleStatus || "上传 SRT 字幕文件",
          statusTone: previousSubtitle?.statusTone || "warning",
        }
        : video));
      onFeedback(error.message || "字幕上传失败，请稍后重试");
    } finally {
      uploadInFlight.current = false;
      setIsUploading(false);
    }
  };

  const handleRemoveVideoSubtitle = async (videoId) => {
    if (isUploading || isReordering || uploadInFlight.current) return;
    const video = videos.find((item) => item.id === videoId);
    if (!video?.subtitleAssetId || video.subtitleAssetStatus !== "ready" || !projectId) return;

    setRemovingSubtitleAssetId(video.subtitleAssetId);
    try {
      await removeProjectAsset(projectId, video.subtitleAssetId);
      setVideos((current) => current.map((item) => item.id === videoId
        ? {
          ...item,
          subtitleAssetId: null,
          subtitleAssetStatus: null,
          subtitleName: null,
          subtitleStatus: "上传 SRT 字幕文件",
          statusTone: "warning",
        }
        : item));
    } catch (error) {
      onFeedback(error.message || "字幕移除失败，请稍后重试");
    } finally {
      setRemovingSubtitleAssetId(null);
    }
  };

  const handleReorderVideos = async (orderedVideos) => {
    const previousOrder = videos.map((video) => video.id);
    // 重新生成回填后用户首次重排素材时，把回填素材物化为可编辑草稿后再调用服务端排序。
    if (retrySourceProjectId && !projectId) {
      uploadInFlight.current = true;
      setIsReordering(true);
      try {
        await ensureRetryDraft();
      } catch (error) {
        uploadInFlight.current = false;
        setIsReordering(false);
        onFeedback(error.message || "草稿创建失败，请稍后重试");
        return;
      }
    }
    if (!projectId || isUploading || uploadInFlight.current) return;
    setVideos(orderedVideos);
    try {
      await reorderProjectVideoAssets(
        projectId,
        orderedVideos.map((video) => video.assetId),
      );
      setApiCredits(null);
    } catch (error) {
      setVideos((current) => previousOrder
        .map((id) => current.find((video) => video.id === id))
        .filter(Boolean));
      onFeedback(error.message || t("create.messages.orderSaveFailed"));
    } finally {
      uploadInFlight.current = false;
      setIsReordering(false);
    }
  };

  return <div className={`create-layout${showTypeSelector ? "" : " create-layout--upload-only"}`}>
    <div className="create-form">
      {showTypeSelector && <CreationTypeSelector types={creationTypes} selectedType={selectedType} onChange={handleTypeChange} />}
      <VideoUploadPanel
        videos={videos}
        maxVideos={selectedCreationType.maxVideos}
        isDragging={isDragging}
        isUploading={isUploading}
        isSubtitleDetecting={subtitleDetectionPending}
        isReordering={isReordering}
        removingSubtitleAssetId={removingSubtitleAssetId}
        onFiles={handleVideoFiles}
        onDragStateChange={setIsDragging}
        onRemove={handleRemoveVideo}
        onSubtitleSelect={handleVideoSubtitle}
        onSubtitleRemove={handleRemoveVideoSubtitle}
        onReorder={handleReorderVideos}
      />
      <p className="create-autosave"><ShieldCheck aria-hidden="true" />{t("create.autosave")}</p>
    </div>
    <CreationSummary
      durationLabel={summary.durationLabel}
      estimatedCredits={apiCredits}
      balance={user?.credit_balance ?? null}
      onNext={handleNext}
      disabled={!canStart || apiCredits === null || isUploading || isReordering || subtitleDetectionPending}
    />
  </div>;
}

export function CreatePage() {
  const { t } = useI18n();
  const { user } = useAuth();
  const [toast, setToast] = useState({ id: 0, message: "" });
  const [searchParams] = useSearchParams();
  const initialProjectId = searchParams.get("projectId");
  const showUnavailable = useCallback((message) => {
    setToast(({ id }) => ({ id: id + 1, message }));
  }, []);

  useEffect(() => {
    if (!toast.message) return undefined;
    const timer = window.setTimeout(() => setToast(({ id }) => ({ id, message: "" })), 3200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  return (
    <div className="dashboard-shell create-page" data-page="create">
      <DashboardSidebar items={dashboardNavItems} onUnavailable={showUnavailable} />
      <div className="dashboard-workspace">
        <DashboardHeader credits={{ balance: user?.credit_balance ?? null }} onUnavailable={showUnavailable} />
        <main className="create-main">
          <header className="create-heading">
            <h1 data-route-heading tabIndex="-1">{t("create.routeHeading")}</h1>
            <p>{t("create.description")}</p>
          </header>
          <CreateUploadFlow initialProjectId={initialProjectId} onFeedback={showUnavailable} />
        </main>
      </div>
      <DashboardMobileNav items={dashboardNavItems} onUnavailable={showUnavailable} />
      {toast.message && (
        <DashboardToast
          key={toast.id}
          message={toast.message}
          onClose={() => setToast(({ id }) => ({ id, message: "" }))}
        />
      )}
    </div>
  );
}
