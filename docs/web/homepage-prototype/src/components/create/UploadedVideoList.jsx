import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { CheckCircle, DotsSixVertical, FilmStrip, SpinnerGap, Trash, WarningCircle } from "@phosphor-icons/react";
import { useI18n } from "../../i18n/useI18n.js";

function SortableVideoRow({ video, index, disabled, removeDisabled, sortingDisabled, removingSubtitleAssetId, onRemove, onSubtitleSelect, onSubtitleRemove }) {
  const { t } = useI18n();
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: video.id, disabled: sortingDisabled });
  const isDetectingSubtitle = video.subtitleDetectionStatus === "detecting";
  const canRemoveSubtitle = Boolean(video.subtitleAssetId && video.subtitleAssetStatus === "ready");
  const isRemovingSubtitle = removingSubtitleAssetId === video.subtitleAssetId;
  const StatusIcon = isDetectingSubtitle ? SpinnerGap : video.statusTone === "success" ? CheckCircle : WarningCircle;

  return (
    <article
      ref={setNodeRef}
      className={`create-video-row${isDragging ? " is-dragging" : ""}`}
      data-video-row
      style={{ transform: CSS.Transform.toString(transform), transition }}
    >
      <button
        className="create-video-row__handle"
        type="button"
        disabled={sortingDisabled}
        aria-label={t("create.upload.reorderVideo", { name: video.name })}
        {...attributes}
        {...listeners}
      >
        <DotsSixVertical weight="bold" aria-hidden="true" />
      </button>
      <span className="create-video-row__index" data-video-index>{String(index + 1).padStart(2, "0")}</span>
      <span className="create-video-row__thumb" aria-hidden="true">
        {video.thumbnail ? <img src={video.thumbnail} alt="" /> : <FilmStrip weight="duotone" />}
      </span>
      <strong title={video.name}>{video.name}</strong>
      <time>{video.durationLabel}</time>
      <div className={`create-video-row__status create-video-row__status--${video.statusTone}${isDetectingSubtitle ? " is-detecting" : ""}`}>
        <label className="create-video-row__subtitle-picker">
          <input
            className="create-file-input"
            type="file"
            accept=".srt,application/x-subrip,text/plain"
            disabled={disabled}
            aria-label={t("create.upload.uploadSubtitle", { name: video.name })}
            onChange={(event) => {
              if (event.target.files?.[0]) onSubtitleSelect(video.id, event.target.files[0]);
              event.target.value = "";
            }}
          />
          <StatusIcon weight="bold" aria-hidden="true" />
          <span>{video.subtitleName || (video.subtitleStatusKey ? t(video.subtitleStatusKey) : video.subtitleStatus || t("create.subtitle.clickOrAi"))}</span>
          {isDetectingSubtitle && <small>{t("create.subtitle.detecting", { progress: video.subtitleDetectionProgress || "…" })}</small>}
        </label>
        {canRemoveSubtitle && <button
          className="create-video-row__subtitle-remove"
          type="button"
          disabled={disabled || isRemovingSubtitle}
          aria-label={t("create.upload.removeSubtitle", { name: video.subtitleName })}
          onClick={() => onSubtitleRemove(video.id)}
        >
          <Trash aria-hidden="true" />
        </button>}
      </div>
      <button
        className="create-video-row__remove"
        type="button"
        disabled={removeDisabled}
        aria-label={t("create.upload.removeVideo", { name: video.name })}
        onClick={() => onRemove(video.id)}
      >
        <Trash aria-hidden="true" />
      </button>
    </article>
  );
}

export function UploadedVideoList({ videos, disabled = false, removeDisabled = false, removingSubtitleAssetId = null, onRemove, onSubtitleSelect, onSubtitleRemove, onReorder }) {
  const { t } = useI18n();
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const sortingDisabled = disabled || videos.length < 2;

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragEnd={({ active, over }) => {
        if (sortingDisabled || !over || active.id === over.id) return;
        const previousIndex = videos.findIndex((video) => video.id === active.id);
        const nextIndex = videos.findIndex((video) => video.id === over.id);
        if (previousIndex < 0 || nextIndex < 0) return;
        onReorder(arrayMove(videos, previousIndex, nextIndex));
      }}
    >
      <SortableContext
        items={videos.map((video) => video.id)}
        strategy={verticalListSortingStrategy}
      >
        <div className="create-video-list" aria-label={t("create.upload.selectedVideos")}>
          {videos.map((video, index) => (
            <SortableVideoRow
              key={video.id}
              video={video}
              index={index}
              disabled={disabled}
              removeDisabled={removeDisabled}
              sortingDisabled={sortingDisabled}
              removingSubtitleAssetId={removingSubtitleAssetId}
              onRemove={onRemove}
              onSubtitleSelect={onSubtitleSelect}
              onSubtitleRemove={onSubtitleRemove}
            />
          ))}
        </div>
      </SortableContext>
    </DndContext>
  );
}
