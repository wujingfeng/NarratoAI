import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./features/auth/AuthProvider.jsx";
import { RouteEffects } from "./components/RouteEffects.jsx";
import { DashboardPage } from "./pages/DashboardPage.jsx";
import { CreatePage } from "./pages/CreatePage.jsx";
import { ProjectsPage } from "./pages/ProjectsPage.jsx";
import { NarrationSettingsPage } from "./pages/NarrationSettingsPage.jsx";
import { NarrationAnalysisPage } from "./pages/NarrationAnalysisPage.jsx";
import { NarrationEditorPage } from "./pages/NarrationEditorPage.jsx";
import { HomePage } from "./pages/HomePage.jsx";
import { LoginPage } from "./pages/LoginPage.jsx";
import { NotFoundPage } from "./pages/NotFoundPage.jsx";
import { ProjectResultPage } from "./pages/ProjectResultPage.jsx";
import { ProjectEditorPage } from "./pages/ProjectEditorPage.jsx";

function RequireAuth({ children }) {
  const { isAuthenticated } = useAuth();
  const location = useLocation();
  return isAuthenticated ? children : <Navigate to="/login" replace state={{ from: location }} />;
}

export function App() {
  return (
    <>
      <RouteEffects />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/dashboard" element={<RequireAuth><DashboardPage /></RequireAuth>} />
        <Route path="/create" element={<RequireAuth><CreatePage /></RequireAuth>} />
        <Route path="/dashboard/create" element={<RequireAuth><CreatePage /></RequireAuth>} />
        <Route path="/dashboard/projects" element={<RequireAuth><ProjectsPage /></RequireAuth>} />
        <Route path="/dashboard/projects/overlord/result" element={<Navigate to="/projects/overlord/result" replace />} />
        <Route path="/dashboard/narration/settings" element={<RequireAuth><NarrationSettingsPage /></RequireAuth>} />
        <Route path="/dashboard/narration/analysis" element={<RequireAuth><NarrationAnalysisPage /></RequireAuth>} />
        <Route path="/dashboard/narration/editor" element={<RequireAuth><NarrationEditorPage /></RequireAuth>} />
        <Route path="/projects/:projectId/result" element={<RequireAuth><ProjectResultPage /></RequireAuth>} />
        <Route path="/projects/:projectId/editor" element={<RequireAuth><ProjectEditorPage /></RequireAuth>} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </>
  );
}
