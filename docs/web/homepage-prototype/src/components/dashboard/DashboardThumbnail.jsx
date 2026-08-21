import { useEffect, useState } from "react";
import { useI18n } from "../../i18n/useI18n.js";

export function DashboardThumbnail({ src, alt, fallbackLabel, loading = "lazy", mediaType = "image" }) {
  const { t } = useI18n();
  const [failed, setFailed] = useState(false);

  useEffect(() => setFailed(false), [mediaType, src]);

  return (
    <span className="dashboard-thumbnail">
      {src && !failed && (
        mediaType === "video" ? (
          <video src={src} aria-label={alt} muted playsInline preload="metadata" onError={() => setFailed(true)} />
        ) : (
          <img
            src={src}
            alt={alt}
            loading={loading}
            decoding="async"
            onError={() => setFailed(true)}
          />
        )
      )}
      {(!src || failed) && (
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
