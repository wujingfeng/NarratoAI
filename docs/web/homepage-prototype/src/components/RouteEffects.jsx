import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { useI18n } from "../i18n/useI18n.js";

const titleKeys = {
  "/": "titles.home",
  "/login": "titles.login",
  "/register": "titles.register",
  "/forgot-password": "titles.forgotPassword",
  "/dashboard": "titles.dashboard",
  "/create": "titles.create",
  "/dashboard/create": "titles.create",
  "/dashboard/projects": "titles.projects",
  "/dashboard/ai-video": "titles.aiVideo",
  "/dashboard/narration/settings": "titles.narrationSettings",
  "/dashboard/narration/analysis": "titles.narrationAnalysis",
  "/dashboard/narration/editor": "titles.narrationEditor",
  "/dashboard/narration/review": "titles.narrationReview",
  "/dashboard/narration/generate": "titles.narrationGenerate",
  "/dashboard/narration/export": "titles.narrationExport",
};

export function RouteEffects() {
  const { pathname } = useLocation();
  const { t } = useI18n();

  useEffect(() => {
    const dynamicTitleKey = /^\/projects\/[^/]+\/result$/.test(pathname)
      ? "titles.projectResult"
      : /^\/projects\/[^/]+\/editor$/.test(pathname)
        ? "titles.projectEditor"
        : null;
    document.title = t(titleKeys[pathname] || dynamicTitleKey || "titles.notFound");
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    requestAnimationFrame(() => document.querySelector("[data-route-heading]")?.focus());
  }, [pathname, t]);

  return null;
}
