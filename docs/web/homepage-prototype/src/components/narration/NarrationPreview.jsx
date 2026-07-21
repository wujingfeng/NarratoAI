import { CaretLeft, CaretRight } from "@phosphor-icons/react";
import { useI18n } from "../../i18n/useI18n.js";

export function NarrationPreview({ style }) {
  const { formatNumber, t } = useI18n();
  return <aside className="narration-preview" aria-labelledby="preview-title">
    <h2 id="preview-title">{t("narration.preview.title")}</h2>
    <div className="narration-preview__frame">
      <div className="narration-preview__tags"><span>{t("narration.preview.voicing")}</span><span>{t("narration.preview.captionsOn")}</span></div>
      <span className="narration-preview__safe-area">{t("narration.preview.safeArea")}</span>
      <div className="narration-preview__scene" aria-label={t("narration.preview.sceneLabel")}>
        <div className="narration-preview__lamp" />
        <div className="narration-preview__window" />
        <div className="narration-preview__chair" />
        <div className="narration-preview__person"><i /><b /><em /></div>
      </div>
      <p className={`narration-preview__caption ${style === "classic" ? "is-classic" : style === "shadow" ? "is-shadow" : ""}`}>{t("narration.preview.captionLine1")}<br />{t("narration.preview.captionLine2")}</p>
    </div>
    <div className="narration-preview__dots" aria-label={t("narration.preview.carousel")}><CaretLeft aria-hidden="true" /><i /><i className="is-active" /><i /><CaretRight aria-hidden="true" /></div>
    <div className="narration-preview__stats">
      <div><span>{t("narration.preview.source")}</span><strong>08:42</strong></div><div><span>{t("narration.preview.estimatedOutput")}</span><strong>01:25</strong></div><div><span>{t("narration.preview.estimatedCost")}</span><strong>{t("narration.preview.credits", { count: formatNumber(87) })}</strong></div>
    </div>
  </aside>;
}
