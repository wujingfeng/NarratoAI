import { Triangle } from "@phosphor-icons/react";
import { useI18n } from "../i18n/useI18n.js";

function TrianglesThree() {
  return (
    <span className="brand-mark__symbol" aria-hidden="true">
      <Triangle className="brand-mark__triangle brand-mark__triangle--one" weight="duotone" />
      <Triangle className="brand-mark__triangle brand-mark__triangle--two" weight="duotone" />
      <Triangle className="brand-mark__triangle brand-mark__triangle--three" weight="duotone" />
    </span>
  );
}

export function BrandMark({ compact = false }) {
  const { t } = useI18n();
  const brand = t("common.brand");
  return (
    <span className={`brand-mark ${compact ? "brand-mark--compact" : ""}`} aria-label={brand}>
      <TrianglesThree />
      <span className="brand-mark__text">{brand}</span>
    </span>
  );
}
