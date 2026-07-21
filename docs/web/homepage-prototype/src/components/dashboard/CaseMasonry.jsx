import { useEffect, useState } from "react";
import Masonry, { ResponsiveMasonry } from "react-responsive-masonry";
import { CaseVideo } from "./CaseVideo.jsx";
import { useI18n } from "../../i18n/useI18n.js";

export function CaseMasonry({ cases, onUnavailable }) {
  const { t } = useI18n();
  const [page, setPage] = useState(1);
  const visibleCases = cases.slice(0, page * 6);
  const hasMore = visibleCases.length < cases.length;

  useEffect(() => {
    setPage(1);
  }, [cases]);

  useEffect(() => {
    if (!hasMore) return undefined;
    const loadNextPage = () => {
      const nearBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 240;
      if (nearBottom) setPage((current) => Math.min(current + 1, Math.ceil(cases.length / 6)));
    };
    window.addEventListener("scroll", loadNextPage, { passive: true });
    return () => window.removeEventListener("scroll", loadNextPage);
  }, [cases.length, hasMore]);

  return (
    <section className="case-masonry" aria-labelledby="case-masonry-title">
      <div className="workspace-section-heading"><div><p>{t("dashboard.cases.eyebrow")}</p><h2 id="case-masonry-title">{t("dashboard.cases.title")}</h2></div></div>
      <div className="case-masonry__grid" data-case-page-size="6">
        <ResponsiveMasonry columnsCountBreakPoints={{ 1: 2, 700: 2, 1150: 3, 1500: 4, 1800: 5, 2100: 6 }}>
          <Masonry gutter="14px">
            {visibleCases.map((item) => <button type="button" className={`case-masonry__card case-masonry__card--${item.tone}`} key={item.id} onClick={() => onUnavailable(t(item.unavailableMessageKey))}>
              <CaseVideo src={item.video} label={t(item.titleKey)} />
            </button>)}
          </Masonry>
        </ResponsiveMasonry>
      </div>
    </section>
  );
}
