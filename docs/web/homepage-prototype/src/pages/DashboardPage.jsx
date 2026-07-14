import { useCallback, useEffect, useState } from "react";
import { CreationEntryCard } from "../components/dashboard/CreationEntryCard.jsx";
import { CreditsOverview } from "../components/dashboard/CreditsOverview.jsx";
import { DashboardHeader } from "../components/dashboard/DashboardHeader.jsx";
import { DashboardMobileNav } from "../components/dashboard/DashboardMobileNav.jsx";
import { DashboardSidebar } from "../components/dashboard/DashboardSidebar.jsx";
import { DashboardToast } from "../components/dashboard/DashboardToast.jsx";
import { InspirationPanel } from "../components/dashboard/InspirationPanel.jsx";
import { PromotionBanner } from "../components/dashboard/PromotionBanner.jsx";
import { RecentProjects } from "../components/dashboard/RecentProjects.jsx";
import { ToolQuickStart } from "../components/dashboard/ToolQuickStart.jsx";
import {
  dashboardCredits,
  dashboardNavItems,
  dashboardPrimaryAction,
  dashboardTools,
  inspirations,
  recentProjects,
} from "../data/dashboardData.js";

export function DashboardPage() {
  const [bannerVisible, setBannerVisible] = useState(true);
  const [toast, setToast] = useState({ id: 0, message: "" });
  const showUnavailable = useCallback((message) => {
    setToast(({ id }) => ({ id: id + 1, message }));
  }, []);

  useEffect(() => {
    if (!toast.message) return undefined;
    const timer = window.setTimeout(() => setToast(({ id }) => ({ id, message: "" })), 3200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  return (
    <div className="dashboard-shell" data-page="dashboard">
      <h1 className="sr-only" data-route-heading tabIndex="-1">工作台概览</h1>
      <DashboardSidebar items={dashboardNavItems} onUnavailable={showUnavailable} />
      <div className="dashboard-workspace">
        <DashboardHeader primaryAction={dashboardPrimaryAction} onUnavailable={showUnavailable} />
        <main className="dashboard-main">
          {bannerVisible && <PromotionBanner onClose={() => setBannerVisible(false)} onUnavailable={showUnavailable} />}
          <CreationEntryCard action={dashboardPrimaryAction} onUnavailable={showUnavailable} />
          <ToolQuickStart tools={dashboardTools} onUnavailable={showUnavailable} />
          <div className="dashboard-content-grid">
            <RecentProjects projects={recentProjects} onUnavailable={showUnavailable} />
            <div className="dashboard-content-grid__side">
              <CreditsOverview credits={dashboardCredits} onUnavailable={showUnavailable} />
              <InspirationPanel inspirations={inspirations} onUnavailable={showUnavailable} />
            </div>
          </div>
        </main>
      </div>
      <DashboardMobileNav items={dashboardNavItems} onUnavailable={showUnavailable} />
      {toast.message && <DashboardToast key={toast.id} message={toast.message} onClose={() => setToast(({ id }) => ({ id, message: "" }))} />}
    </div>
  );
}
