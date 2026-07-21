import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { useI18n } from "../i18n/useI18n.js";

const titleKeys = {
  "/": "titles.home",
  "/dashboard": "titles.dashboard",
  "/dashboard/create": "titles.create",
  "/dashboard/projects": "titles.projects",
  "/dashboard/projects/overlord/result": "titles.projectResult",
  "/dashboard/narration/settings": "titles.narrationSettings",
  "/dashboard/narration/analysis": "titles.narrationAnalysis",
  "/dashboard/narration/editor": "titles.narrationEditor",
};

export function RouteEffects() {
  const { pathname } = useLocation();
  const { t } = useI18n();

  useEffect(() => {
    document.title = t(titleKeys[pathname] || "titles.notFound");
  }, [pathname, t]);

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    requestAnimationFrame(() => document.querySelector("[data-route-heading]")?.focus());
  }, [pathname]);

  return null;
}
