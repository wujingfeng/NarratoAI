import { useCallback, useEffect, useState } from "react";
import { ArrowLeft } from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import { DashboardHeader } from "../components/dashboard/DashboardHeader.jsx";
import { DashboardMobileNav } from "../components/dashboard/DashboardMobileNav.jsx";
import { DashboardSidebar } from "../components/dashboard/DashboardSidebar.jsx";
import { DashboardToast } from "../components/dashboard/DashboardToast.jsx";
import { NarrationPreview } from "../components/narration/NarrationPreview.jsx";
import { NarrationSettingsForm } from "../components/narration/NarrationSettingsForm.jsx";
import { NarrationStepper } from "../components/narration/NarrationStepper.jsx";
import { dashboardCredits, dashboardNavItems } from "../data/dashboardData.js";
import { narrationRatios, narrationSteps, narrationStyles, subtitleStyles } from "../data/narrationData.js";
import { useI18n } from "../i18n/useI18n.js";

export function NarrationSettingsPage() {
  const { t } = useI18n();
  const [style, setStyle] = useState("reversal"); const [ratio, setRatio] = useState("original"); const [subtitle, setSubtitle] = useState("glow"); const [requirements, setRequirements] = useState(""); const [toast, setToast] = useState({ id: 0, message: "" });
  const showToast = useCallback((message) => setToast(({ id }) => ({ id: id + 1, message })), []);
  useEffect(() => { if (!toast.message) return undefined; const timer = window.setTimeout(() => setToast(({ id }) => ({ id, message: "" })), 3200); return () => window.clearTimeout(timer); }, [toast]);
  return <div className="narration-shell" data-page="narration-settings"><h1 className="sr-only" data-route-heading tabIndex="-1">{t("narration.routeHeading")}</h1><DashboardSidebar items={dashboardNavItems} onUnavailable={showToast} /><div className="narration-workspace"><DashboardHeader credits={dashboardCredits} onUnavailable={showToast} /><main className="narration-main"><header className="narration-topbar"><Link to="/dashboard" aria-label={t("narration.back")}><ArrowLeft aria-hidden="true" /></Link><strong>{t("narration.name")}</strong><i /><h2>霸总短剧解说 01</h2><button type="button" aria-label={t("narration.rename")} onClick={() => showToast(t("narration.messages.renameUnavailable"))}>⌑</button><p><span>✓</span> {t("narration.autosaved")}</p></header><NarrationStepper steps={narrationSteps} /><div className="narration-content"><NarrationSettingsForm styles={narrationStyles} ratios={narrationRatios} subtitleStyles={subtitleStyles} selectedStyle={style} selectedRatio={ratio} selectedSubtitle={subtitle} requirements={requirements} onStyleChange={setStyle} onRatioChange={setRatio} onSubtitleChange={setSubtitle} onRequirementsChange={setRequirements} onUnavailable={showToast} /><div className="narration-right"><NarrationPreview style={subtitle} /><footer className="narration-actions"><Link to="/dashboard">{t("narration.actions.previous")}</Link><Link to="/dashboard/narration/analysis">{t("narration.actions.startAnalysis")}</Link></footer></div></div></main></div><DashboardMobileNav items={dashboardNavItems} onUnavailable={showToast} />{toast.message && <DashboardToast key={toast.id} message={toast.message} onClose={() => setToast(({ id }) => ({ id, message: "" }))} />}</div>;
}
