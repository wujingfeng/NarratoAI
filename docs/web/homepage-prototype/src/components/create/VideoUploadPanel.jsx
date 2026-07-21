import { CloudArrowUp, PlusCircle } from "@phosphor-icons/react";
import { useRef } from "react";
import { UploadedVideoList } from "./UploadedVideoList.jsx";
import { useI18n } from "../../i18n/useI18n.js";

export function VideoUploadPanel({ videos, maxVideos, isDragging, onFiles, onDragStateChange, onRemove, onSubtitleSelect }) {
  const { formatNumber, t } = useI18n();
  const inputRef = useRef(null);
  const handleFiles = (files) => {
    if (files?.length) onFiles([...files]);
  };

  return (
    <section className="create-upload-section" aria-labelledby="create-upload-heading">
      <h2 id="create-upload-heading">{t("create.upload.title")}</h2>
      <div
        className={`create-video-dropzone${isDragging ? " is-dragging" : ""}`}
        onDragEnter={(event) => { event.preventDefault(); onDragStateChange(true); }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget)) onDragStateChange(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          onDragStateChange(false);
          handleFiles(event.dataTransfer.files);
        }}
      >
        <input
          ref={inputRef}
          className="create-file-input"
          type="file"
          accept="video/mp4,video/quicktime,video/x-msvideo,.mp4,.mov,.avi"
          multiple
          aria-label={t("create.upload.chooseVideos")}
          onChange={(event) => {
            handleFiles(event.target.files);
            event.target.value = "";
          }}
        />
        <button className="create-upload-add" type="button" onClick={() => inputRef.current?.click()}>
          <PlusCircle aria-hidden="true" />
          {t("create.upload.addMore")}
        </button>
        <div className="create-dropzone-copy">
          <CloudArrowUp weight="duotone" aria-hidden="true" />
          <p>{t("create.upload.dragPrefix")} <button type="button" onClick={() => inputRef.current?.click()}>{t("create.upload.chooseFile")}</button></p>
          <small>{t("create.upload.limits", { count: formatNumber(maxVideos) })}</small>
        </div>
        <UploadedVideoList videos={videos} onRemove={onRemove} onSubtitleSelect={onSubtitleSelect} />
      </div>
    </section>
  );
}
