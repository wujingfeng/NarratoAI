import { CloudArrowUp, PlusCircle } from "@phosphor-icons/react";
import { useRef } from "react";
import { UploadedVideoList } from "./UploadedVideoList.jsx";
import { useI18n } from "../../i18n/useI18n.js";

export function VideoUploadPanel({ videos, maxVideos, isDragging, isUploading, isSubtitleDetecting, isReordering, removingSubtitleAssetId, onFiles, onDragStateChange, onRemove, onSubtitleSelect, onSubtitleRemove, onReorder }) {
  const { formatNumber, t } = useI18n();
  const inputRef = useRef(null);
  // 视频翻译必须等字幕区域检测结束后才能进入下一步；检测期间沿用上传遮罩，
  // 避免 OSS 上传完成后给出“操作已结束”的错误反馈。
  const isLoading = isUploading || isSubtitleDetecting;
  const interactionDisabled = isLoading || isReordering;
  const handleFiles = (files) => {
    if (!interactionDisabled && files?.length) onFiles([...files]);
  };
  const openFilePicker = () => {
    if (!interactionDisabled) inputRef.current?.click();
  };

  return (
    <section className="create-upload-section" aria-labelledby="create-upload-heading">
      <h2 id="create-upload-heading">{t("create.upload.title")}</h2>
      <div
        className={`create-video-dropzone${isDragging ? " is-dragging" : ""}${isLoading ? " is-uploading" : ""}`}
        aria-busy={interactionDisabled}
        onDragEnter={(event) => { event.preventDefault(); if (!interactionDisabled) onDragStateChange(true); }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget)) onDragStateChange(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          onDragStateChange(false);
          if (!interactionDisabled) handleFiles(event.dataTransfer.files);
        }}
      >
        <input
          ref={inputRef}
          className="create-file-input"
          type="file"
          accept="video/mp4,video/quicktime,video/x-msvideo,.mp4,.mov,.avi"
          multiple
          disabled={interactionDisabled}
          aria-label={t("create.upload.chooseVideos")}
          onChange={(event) => {
            handleFiles(event.target.files);
            event.target.value = "";
          }}
        />
        <button className="create-upload-add" type="button" disabled={interactionDisabled} onClick={openFilePicker}>
          <PlusCircle aria-hidden="true" />
          {t("create.upload.addMore")}
        </button>
        <div
          className="create-dropzone-copy"
          role="button"
          tabIndex={interactionDisabled ? -1 : 0}
          aria-disabled={interactionDisabled}
          onClick={openFilePicker}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              openFilePicker();
            }
          }}
        >
          <CloudArrowUp weight="duotone" aria-hidden="true" />
          <p>{t("create.upload.dragPrefix")} <span>{t("create.upload.chooseFile")}</span></p>
          <small>{t("create.upload.limits", { count: formatNumber(maxVideos) })}</small>
        </div>
        {isLoading && (
          <div className="create-upload-loading" role="status" aria-live="polite">
            <span className="create-upload-loading__spinner" aria-hidden="true" />
            <span>{isUploading ? t("create.upload.uploadingMaterials") : t("create.upload.detectingVideoSubtitles")}</span>
          </div>
        )}
        <UploadedVideoList
          videos={videos}
          disabled={interactionDisabled}
          removeDisabled={isReordering}
          removingSubtitleAssetId={removingSubtitleAssetId}
          onRemove={onRemove}
          onSubtitleSelect={onSubtitleSelect}
          onSubtitleRemove={onSubtitleRemove}
          onReorder={onReorder}
        />
      </div>
    </section>
  );
}
