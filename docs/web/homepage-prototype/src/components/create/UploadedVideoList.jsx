import { CheckCircle, DotsSixVertical, FilmStrip, Trash, WarningCircle } from "@phosphor-icons/react";
import { useI18n } from "../../i18n/useI18n.js";

export function UploadedVideoList({ videos, onRemove, onSubtitleSelect }) {
  const { t } = useI18n();
  return (
    <div className="create-video-list" aria-label={t("create.upload.selectedVideos")}>
      {videos.map((video, index) => {
        const StatusIcon = video.statusTone === "success" ? CheckCircle : WarningCircle;
        return (
          <article className="create-video-row" data-video-row key={video.id}>
            <DotsSixVertical className="create-video-row__handle" weight="bold" aria-hidden="true" />
            <span className="create-video-row__index" data-video-index>{String(index + 1).padStart(2, "0")}</span>
            <span className="create-video-row__thumb" aria-hidden="true">
              {video.thumbnail ? <img src={video.thumbnail} alt="" /> : <FilmStrip weight="duotone" />}
            </span>
            <strong title={video.name}>{video.name}</strong>
            <time>{video.durationLabel}</time>
            <label className={`create-video-row__status create-video-row__status--${video.statusTone}`}>
              <input
                className="create-file-input"
                type="file"
                accept=".srt,application/x-subrip,text/plain"
                aria-label={t("create.upload.uploadSubtitle", { name: video.name })}
                onChange={(event) => {
                  if (event.target.files?.[0]) onSubtitleSelect(video.id, event.target.files[0]);
                  event.target.value = "";
                }}
              />
              <StatusIcon weight="bold" aria-hidden="true" />
              <span>{video.subtitleName || (video.subtitleStatusKey ? t(video.subtitleStatusKey) : video.subtitleStatus || t("create.subtitle.clickOrAi"))}</span>
            </label>
            <button type="button" aria-label={t("create.upload.removeVideo", { name: video.name })} onClick={() => onRemove(video.id)}>
              <Trash aria-hidden="true" />
            </button>
          </article>
        );
      })}
    </div>
  );
}
