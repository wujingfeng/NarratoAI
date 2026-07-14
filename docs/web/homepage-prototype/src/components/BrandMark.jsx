import { Triangle } from "@phosphor-icons/react";

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
  return (
    <span className={`brand-mark ${compact ? "brand-mark--compact" : ""}`} aria-label="影创工坊">
      <TrianglesThree />
      <span className="brand-mark__text">影创工坊</span>
    </span>
  );
}
