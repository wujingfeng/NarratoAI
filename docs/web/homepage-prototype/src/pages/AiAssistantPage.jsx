import { useCallback, useEffect, useState } from "react";
import { AiAssistantWorkspace } from "../components/ai-assistant/AiAssistantWorkspace.jsx";
import { DashboardHeader } from "../components/dashboard/DashboardHeader.jsx";
import { DashboardMobileNav } from "../components/dashboard/DashboardMobileNav.jsx";
import { DashboardSidebar } from "../components/dashboard/DashboardSidebar.jsx";
import { DashboardToast } from "../components/dashboard/DashboardToast.jsx";
import { dashboardNavItems } from "../data/dashboardData.js";
import { useAuth } from "../features/auth/AuthProvider.jsx";
import "../styles/ai-assistant.css";

export function AiAssistantPage() {
  const { user } = useAuth(); const [toast, setToast] = useState({ id: 0, message: "" });
  const notify = useCallback((message) => setToast((current) => ({ id: current.id + 1, message })), []);
  useEffect(() => { if (!toast.message) return undefined; const timer = window.setTimeout(() => setToast((current) => ({ ...current, message: "" })), 3800); return () => window.clearTimeout(timer); }, [toast.message]);
  return <div className="dashboard-shell ai-assistant-shell" data-page="ai-assistant">
    <DashboardSidebar items={dashboardNavItems} onUnavailable={notify} />
    <div className="dashboard-workspace"><DashboardHeader credits={{ balance: user?.credit_balance ?? null }} onUnavailable={notify} /><main className="ai-assistant-main"><AiAssistantWorkspace notify={notify} /></main></div>
    <DashboardMobileNav items={dashboardNavItems} onUnavailable={notify} />
    {toast.message && <DashboardToast key={toast.id} message={toast.message} onClose={() => setToast((current) => ({ ...current, message: "" }))} />}
  </div>;
}
