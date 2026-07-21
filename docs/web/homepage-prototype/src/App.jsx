import { Route, Routes } from "react-router-dom";
import { RouteEffects } from "./components/RouteEffects.jsx";
import { DashboardPage } from "./pages/DashboardPage.jsx";
import { CreatePage } from "./pages/CreatePage.jsx";
import { ProjectsPage } from "./pages/ProjectsPage.jsx";
import { ProjectResultPage } from "./pages/ProjectResultPage.jsx";
import { NarrationSettingsPage } from "./pages/NarrationSettingsPage.jsx";
import { NarrationAnalysisPage } from "./pages/NarrationAnalysisPage.jsx";
import { NarrationEditorPage } from "./pages/NarrationEditorPage.jsx";
import { HomePage } from "./pages/HomePage.jsx";
import { NotFoundPage } from "./pages/NotFoundPage.jsx";

export function App() {
  return (
    <>
      <RouteEffects />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/dashboard/create" element={<CreatePage />} />
        <Route path="/dashboard/projects" element={<ProjectsPage />} />
        <Route path="/dashboard/projects/overlord/result" element={<ProjectResultPage />} />
        <Route path="/dashboard/narration/settings" element={<NarrationSettingsPage />} />
        <Route path="/dashboard/narration/analysis" element={<NarrationAnalysisPage />} />
        <Route path="/dashboard/narration/editor" element={<NarrationEditorPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </>
  );
}
