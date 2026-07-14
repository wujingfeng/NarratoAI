import { useEffect } from "react";
import { useLocation } from "react-router-dom";

const titles = {
  "/": "影创工坊｜AI 出片工作台",
  "/dashboard": "工作台概览｜影创工坊",
};

export function RouteEffects() {
  const { pathname } = useLocation();

  useEffect(() => {
    document.title = titles[pathname] || "页面未找到｜影创工坊";
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    requestAnimationFrame(() => document.querySelector("[data-route-heading]")?.focus());
  }, [pathname]);

  return null;
}
