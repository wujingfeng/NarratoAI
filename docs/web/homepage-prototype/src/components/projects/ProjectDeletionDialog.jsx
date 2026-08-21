import { useEffect, useRef } from "react";
import { Trash, WarningCircle } from "@phosphor-icons/react";
import { useI18n } from "../../i18n/useI18n.js";

export function ProjectDeletionDialog({ open, count, deleting, onCancel, onConfirm }) {
  const { t } = useI18n();
  const dialogRef = useRef(null);
  const cancelRef = useRef(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
      cancelRef.current?.focus();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  const handleCancel = (event) => {
    event.preventDefault();
    if (!deleting) onCancel();
  };

  return (
    <dialog
      ref={dialogRef}
      className="project-delete-dialog"
      aria-labelledby="project-delete-dialog-title"
      aria-describedby="project-delete-dialog-description"
      aria-busy={deleting}
      onCancel={handleCancel}
    >
      <div className="project-delete-dialog__icon"><WarningCircle aria-hidden="true" /></div>
      <div className="project-delete-dialog__copy">
        <h2 id="project-delete-dialog-title">{t("projects.bulkDelete.dialogTitle")}</h2>
        <p id="project-delete-dialog-description">{t("projects.bulkDelete.dialogDescription", { count })}</p>
      </div>
      <div className="project-delete-dialog__actions">
        <button ref={cancelRef} type="button" disabled={deleting} onClick={onCancel}>{t("projects.bulkDelete.cancel")}</button>
        <button className="project-delete-dialog__confirm" type="button" disabled={deleting} onClick={onConfirm}>
          <Trash aria-hidden="true" />
          {deleting ? t("projects.bulkDelete.deleting") : t("projects.bulkDelete.confirm", { count })}
        </button>
      </div>
    </dialog>
  );
}
