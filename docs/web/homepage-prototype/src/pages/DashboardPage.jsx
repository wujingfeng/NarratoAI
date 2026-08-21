import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CaseMasonry } from "../components/dashboard/CaseMasonry.jsx";
import { CreationStudio } from "../components/dashboard/CreationStudio.jsx";
import { DashboardHeader } from "../components/dashboard/DashboardHeader.jsx";
import { DashboardMobileNav } from "../components/dashboard/DashboardMobileNav.jsx";
import { DashboardSidebar } from "../components/dashboard/DashboardSidebar.jsx";
import { DashboardToast } from "../components/dashboard/DashboardToast.jsx";
import { FeaturedTools } from "../components/dashboard/FeaturedTools.jsx";
import { MarketingCarousel } from "../components/dashboard/MarketingCarousel.jsx";
import {
  dashboardNavItems,
  dashboardCases,
  dashboardCreationEntries,
  dashboardPromotions,
  dashboardTools,
} from "../data/dashboardData.js";
import { useAuth } from "../features/auth/AuthProvider.jsx";
import { useI18n } from "../i18n/useI18n.js";

export function DashboardPage() {
  const { t } = useI18n();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [toast, setToast] = useState({ id: 0, message: "" });
  const showUnavailable = useCallback((message) => {
    if (message === t("dashboard.unavailable.aiVideo")) {
      navigate("/dashboard/ai-video");
      return;
    }
    setToast(({ id }) => ({ id: id + 1, message }));
  }, [navigate, t]);

  useEffect(() => {
    if (!toast.message) return undefined;
    const timer = window.setTimeout(() => setToast(({ id }) => ({ id, message: "" })), 3200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  return (
    <div className="dashboard-shell" data-page="dashboard">
      <h1 className="sr-only" data-route-heading tabIndex="-1">{t("dashboard.routeHeading")}</h1>
      <DashboardSidebar items={dashboardNavItems} onUnavailable={showUnavailable} />
      <div className="dashboard-workspace">
        <DashboardHeader credits={{ balance: user?.credit_balance ?? null }} onUnavailable={showUnavailable} />
        <main className="dashboard-main">
          <div className="dashboard-launch-grid">
            <MarketingCarousel promotions={dashboardPromotions} onUnavailable={showUnavailable} />
            <CreationStudio entries={dashboardCreationEntries} onUnavailable={showUnavailable} compact />
          </div>
          <FeaturedTools tools={dashboardTools} onUnavailable={showUnavailable} />
          <CaseMasonry cases={dashboardCases} onUnavailable={showUnavailable} />
        </main>
        <footer className="dashboard-footer">{t("dashboard.footer")}</footer>
      </div>
      <DashboardMobileNav items={dashboardNavItems} onUnavailable={showUnavailable} />
      {toast.message && <DashboardToast key={toast.id} message={toast.message} onClose={() => setToast(({ id }) => ({ id, message: "" }))} />}
    </div>
  );
}
