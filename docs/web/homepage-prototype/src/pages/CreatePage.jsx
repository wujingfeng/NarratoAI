import { ShieldCheck } from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { CreationSummary } from "../components/create/CreationSummary.jsx";
import { CreationTypeSelector } from "../components/create/CreationTypeSelector.jsx";
import { VideoUploadPanel } from "../components/create/VideoUploadPanel.jsx";
import { DashboardHeader } from "../components/dashboard/DashboardHeader.jsx";
import { DashboardMobileNav } from "../components/dashboard/DashboardMobileNav.jsx";
import { DashboardSidebar } from "../components/dashboard/DashboardSidebar.jsx";
import { DashboardToast } from "../components/dashboard/DashboardToast.jsx";
import { dashboardCredits, dashboardNavItems } from "../data/dashboardData.js";
import { creationTypes, initialCreateVideos } from "../data/createData.js";
import { uploadAsset } from "../features/uploads/ossPostUpload.js";
import { canStartProject, createProject, estimateProjectCost, getAsset, startProject } from "../features/projects/projectApi.js";

const VIDEO_EXTENSIONS = new Set(["mp4", "mov", "avi"]);
const VIDEO_SIZE_LIMIT = 300 * 1024 * 1024;
const SUBTITLE_SIZE_LIMIT = 50 * 1024 * 1024;

function formatDuration(totalSeconds) {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
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

export function CreatePage() {
  const [toast, setToast] = useState({ id: 0, message: "" });
  const [selectedType, setSelectedType] = useState("narration");
  const [videos, setVideos] = useState(initialCreateVideos);
  const [isDragging, setIsDragging] = useState(false);
  const [projectId, setProjectId] = useState(null);
  const [apiCredits, setApiCredits] = useState(null);
  const showUnavailable = useCallback((message) => {
    setToast(({ id }) => ({ id: id + 1, message }));
  }, []);

  useEffect(() => {
    if (!toast.message) return undefined;
    const timer = window.setTimeout(() => setToast(({ id }) => ({ id, message: "" })), 3200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const summary = useMemo(() => {
    const totalSeconds = videos.reduce((total, video) => total + video.durationSeconds, 0);
    const pendingCount = videos.filter((video) => video.durationSeconds === 0).length;
    return {
      durationLabel: formatDuration(totalSeconds),
      estimatedCredits: Math.ceil(totalSeconds / 6) + pendingCount * 10,
    };
  }, [videos]);

  const selectedCreationType = creationTypes.find((type) => type.id === selectedType);

  const handleTypeChange = (typeId) => {
    setSelectedType(typeId);
  };

  const handleVideoFiles = async (files) => {
    const validFiles = files.filter((file) => {
      const extension = file.name.split(".").pop()?.toLowerCase();
      return VIDEO_EXTENSIONS.has(extension) && file.size <= VIDEO_SIZE_LIMIT;
    });
    if (validFiles.length !== files.length) showUnavailable("仅支持 300 MiB 以内的 MP4、MOV 或 AVI 文件");
    if (!validFiles.length) return;
    const availableCount = selectedCreationType.maxVideos - videos.length;
    if (availableCount <= 0) {
      showUnavailable(`${selectedCreationType.title}最多上传 ${selectedCreationType.maxVideos} 个视频`);
      return;
    }
    const acceptedFiles = validFiles.slice(0, availableCount);
    if (acceptedFiles.length < validFiles.length) {
      showUnavailable(`${selectedCreationType.title}最多上传 ${selectedCreationType.maxVideos} 个视频`);
    }
    const newVideos = acceptedFiles.map((file, index) => ({
        id: `${file.name}-${file.lastModified}-${file.size}-${Date.now()}-${index}`,
        name: file.name,
        durationSeconds: 0,
        durationLabel: "--:--",
        subtitleStatus: "待识别，将使用 AI 识别",
        statusTone: "warning",
        subtitleName: null,
        thumbnail: null,
      }));
    setVideos((current) => [...current, ...newVideos]);
    try {
      const activeProjectId = projectId || (await createProject()).id;
      setProjectId(activeProjectId);
      const uploadedAssets = await Promise.all(acceptedFiles.map((file) => uploadAsset(activeProjectId, file, "video")));
      setVideos((current) => current.map((video) => {
        const assetIndex = newVideos.findIndex((item) => item.id === video.id);
        const asset = uploadedAssets[assetIndex];
        return asset ? { ...video, assetId: asset.id, assetStatus: asset.status } : video;
      }));
      uploadedAssets.forEach((asset) => {
        if (asset.status === "ready" || asset.status === "invalid") return;
        const poll = async () => {
          const latest = await getAsset(asset.id);
          setVideos((current) => current.map((video) => video.assetId === asset.id
            ? { ...video, assetStatus: latest.status }
            : video));
          if (latest.status === "validating") window.setTimeout(poll, 2000);
        };
        window.setTimeout(poll, 2000);
      });
    } catch (error) {
      showUnavailable(error.message || "上传失败，请稍后重试");
    }
    newVideos.forEach((newVideo, index) => {
      readVideoDuration(acceptedFiles[index]).then((durationSeconds) => {
        if (durationSeconds === null) return;
        setVideos((current) => current.map((video) => video.id === newVideo.id
          ? { ...video, durationSeconds, durationLabel: formatDuration(durationSeconds) }
          : video));
      });
    });
  };

  const handleNext = async () => {
    if (videos.length > selectedCreationType.maxVideos) {
      showUnavailable(`${selectedCreationType.title}当前有 ${videos.length} 个视频，最多支持 ${selectedCreationType.maxVideos} 个`);
      return;
    }
    const assets = videos.map((video) => ({ status: video.assetStatus }));
    if (!projectId || !canStartProject(assets)) {
      showUnavailable("请等待全部素材校验完成后再开始");
      return;
    }
    try {
      const estimate = await estimateProjectCost(projectId);
      setApiCredits(estimate.credits);
      await startProject(projectId, assets);
      showUnavailable(`项目已开始，预计消耗 ${estimate.credits} 创作点`);
    } catch (error) {
      showUnavailable(error.message || "项目无法开始");
    }
  };

  const handleVideoSubtitle = (videoId, file) => {
    if (!file.name.toLowerCase().endsWith(".srt") || file.size > SUBTITLE_SIZE_LIMIT) {
      showUnavailable("仅支持 50MB 以内的 SRT 字幕文件");
      return;
    }
    setVideos((current) => current.map((video) => video.id === videoId
      ? { ...video, subtitleName: file.name, subtitleStatus: file.name, statusTone: "success" }
      : video));
  };

  return (
    <div className="dashboard-shell create-page" data-page="create">
      <DashboardSidebar items={dashboardNavItems} onUnavailable={showUnavailable} />
      <div className="dashboard-workspace">
        <DashboardHeader credits={dashboardCredits} onUnavailable={showUnavailable} />
        <main className="create-main">
          <header className="create-heading">
            <h1 data-route-heading tabIndex="-1">创建新的 AI 视频</h1>
            <p>选择创作类型并上传素材</p>
          </header>
          <div className="create-layout">
            <div className="create-form">
              <CreationTypeSelector types={creationTypes} selectedType={selectedType} onChange={handleTypeChange} />
              <VideoUploadPanel
                videos={videos}
                maxVideos={selectedCreationType.maxVideos}
                isDragging={isDragging}
                onFiles={handleVideoFiles}
                onDragStateChange={setIsDragging}
                onRemove={(id) => setVideos((current) => current.filter((video) => video.id !== id))}
                onSubtitleSelect={handleVideoSubtitle}
              />
              <p className="create-autosave"><ShieldCheck aria-hidden="true" />系统会自动保存上传进度</p>
            </div>
            <CreationSummary
              durationLabel={summary.durationLabel}
              estimatedCredits={apiCredits ?? summary.estimatedCredits}
              balance={dashboardCredits.balance}
              onNext={handleNext}
            />
          </div>
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
