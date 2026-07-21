import { useState } from "react";
import { useI18n } from "../../i18n/useI18n.js";

export function DashboardThumbnail({ src, alt, fallbackLabel, loading = "lazy" }) {
  const { t } = useI18n();
  const [failed, setFailed] = useState(false);

  return (
    <span className="dashboard-thumbnail">
      {!failed && (
        <img
          src={src}
          alt={alt}
          loading={loading}
          decoding="async"
          onError={() => setFailed(true)}
        />
      )}
      {failed && (
        <span
          className="dashboard-thumbnail__fallback"
          role="img"
          aria-label={t("dashboard.thumbnailUnavailable", { name: fallbackLabel })}
        >
          {fallbackLabel}
        </span>
      )}
    </span>
  );
}
