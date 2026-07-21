import { useCallback, useRef, useState } from "react";
import { useI18n } from "../../i18n/useI18n.js";

export function CaseVideo({ src, label }) {
  const { t } = useI18n();
  const [failed, setFailed] = useState(false);
  const videoRef = useRef(null);
  const startPlayback = useCallback(() => {
    videoRef.current?.play().catch(() => {});
  }, []);

  return (
    <span className="case-video">
      {!failed ? (
        <video
          src={src}
          ref={videoRef}
          autoPlay
          muted
          loop
          playsInline
          preload="auto"
          aria-label={t("dashboard.coverAlt", { name: label })}
          onCanPlay={startPlayback}
          onLoadedData={startPlayback}
          onError={() => setFailed(true)}
        />
      ) : (
        <span className="case-video__fallback" role="img" aria-label={t("dashboard.thumbnailUnavailable", { name: label })}>{label}</span>
      )}
    </span>
  );
}
