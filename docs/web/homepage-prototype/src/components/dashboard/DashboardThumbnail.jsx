import { useState } from "react";

export function DashboardThumbnail({ src, alt, fallbackLabel }) {
  const [failed, setFailed] = useState(false);

  return (
    <span className="dashboard-thumbnail">
      {!failed && (
        <img
          src={src}
          alt={alt}
          loading="lazy"
          decoding="async"
          onError={() => setFailed(true)}
        />
      )}
      {failed && (
        <span
          className="dashboard-thumbnail__fallback"
          role="img"
          aria-label={`${fallbackLabel}缩略图不可用`}
        >
          {fallbackLabel}
        </span>
      )}
    </span>
  );
}
