import { CloudArrowUp, PlusCircle } from "@phosphor-icons/react";
import { useRef } from "react";
import { UploadedVideoList } from "./UploadedVideoList.jsx";
import { useI18n } from "../../i18n/useI18n.js";

export function VideoUploadPanel({ videos, maxVideos, isDragging, isUploading, onFiles, onDragStateChange, onRemove, onSubtitleSelect }) {
  const { formatNumber, t } = useI18n();
  const inputRef = useRef(null);
  const handleFiles = (files) => {
    if (!isUploading && files?.length) onFiles([...files]);
  };

  return (
    <section className="create-upload-section" aria-labelledby="create-upload-heading">
      <h2 id="create-upload-heading">{t("create.upload.title")}</h2>
      <div
        className={`create-video-dropzone${isDragging ? " is-dragging" : ""}${isUploading ? " is-uploading" : ""}`}
        aria-busy={isUploading}
        onDragEnter={(event) => { event.preventDefault(); if (!isUploading) onDragStateChange(true); }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget)) onDragStateChange(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          onDragStateChange(false);
          if (!isUploading) handleFiles(event.dataTransfer.files);
        }}
      >
        <input
          ref={inputRef}
          className="create-file-input"
          type="file"
          accept="video/mp4,video/quicktime,video/x-msvideo,.mp4,.mov,.avi"
          multiple
          disabled={isUploading}
          aria-label={t("create.upload.chooseVideos")}
          onChange={(event) => {
            handleFiles(event.target.files);
            event.target.value = "";
          }}
        />
        <button className="create-upload-add" type="button" disabled={isUploading} onClick={() => inputRef.current?.click()}>
          <PlusCircle aria-hidden="true" />
          {t("create.upload.addMore")}
        </button>
        <div className="create-dropzone-copy">
          <CloudArrowUp weight="duotone" aria-hidden="true" />
          <p>{t("create.upload.dragPrefix")} <button type="button" disabled={isUploading} onClick={() => inputRef.current?.click()}>{t("create.upload.chooseFile")}</button></p>
          <small>{t("create.upload.limits", { count: formatNumber(maxVideos) })}</small>
        </div>
        {isUploading && (
          <div className="create-upload-loading" role="status" aria-live="polite">
            <span className="create-upload-loading__spinner" aria-hidden="true" />
            <span>正在上传素材，请勿继续添加文件</span>
          </div>
        )}
        <UploadedVideoList videos={videos} onRemove={onRemove} onSubtitleSelect={onSubtitleSelect} />
      </div>
    </section>
  );
}
