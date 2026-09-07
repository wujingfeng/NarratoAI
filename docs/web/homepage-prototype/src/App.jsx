import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./features/auth/AuthProvider.jsx";
import { RouteEffects } from "./components/RouteEffects.jsx";
import { DashboardPage } from "./pages/DashboardPage.jsx";
import { CreatePage } from "./pages/CreatePage.jsx";
import { ProjectsPage } from "./pages/ProjectsPage.jsx";
import { NarrationSettingsPage } from "./pages/NarrationSettingsPage.jsx";
import { NarrationAnalysisPage } from "./pages/NarrationAnalysisPage.jsx";
import { NarrationEditorPage } from "./pages/NarrationEditorPage.jsx";
import { NarrationReviewPage } from "./pages/NarrationReviewPage.jsx";
import { HomePage } from "./pages/HomePage.jsx";
import { LoginPage } from "./pages/LoginPage.jsx";
import { RegisterPage } from "./pages/RegisterPage.jsx";
import { ForgotPasswordPage } from "./pages/ForgotPasswordPage.jsx";
import { NotFoundPage } from "./pages/NotFoundPage.jsx";
import { ProjectResultPage } from "./pages/ProjectResultPage.jsx";
import { ProjectEditorPage } from "./pages/ProjectEditorPage.jsx";
import { NarrationStagePage } from "./pages/NarrationStagePage.jsx";
import { VideoTranslationPage } from "./pages/VideoTranslationPage.jsx";
import { AiVideoPage } from "./pages/AiVideoPage.jsx";
import { AiAssistantPage } from "./pages/AiAssistantPage.jsx";

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
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/dashboard" element={<RequireAuth><DashboardPage /></RequireAuth>} />
        <Route path="/create" element={<RequireAuth><CreatePage /></RequireAuth>} />
        <Route path="/dashboard/create" element={<RequireAuth><CreatePage /></RequireAuth>} />
        <Route path="/dashboard/projects" element={<RequireAuth><ProjectsPage /></RequireAuth>} />
        <Route path="/dashboard/ai-assistant" element={<RequireAuth><AiAssistantPage /></RequireAuth>} />
        <Route path="/dashboard/ai-video" element={<RequireAuth><AiVideoPage /></RequireAuth>} />
        <Route path="/dashboard/video-translation/upload" element={<RequireAuth><VideoTranslationPage view="upload" /></RequireAuth>} />
        <Route path="/dashboard/video-translation/settings" element={<RequireAuth><VideoTranslationPage view="settings" /></RequireAuth>} />
        <Route path="/dashboard/video-translation/translation" element={<RequireAuth><VideoTranslationPage view="translation" /></RequireAuth>} />
        <Route path="/dashboard/video-translation/edit" element={<RequireAuth><VideoTranslationPage view="edit" /></RequireAuth>} />
        <Route path="/dashboard/video-translation/render" element={<RequireAuth><VideoTranslationPage view="render" /></RequireAuth>} />
        <Route path="/dashboard/video-translation/export" element={<RequireAuth><VideoTranslationPage view="export" /></RequireAuth>} />
        <Route path="/dashboard/narration/settings" element={<RequireAuth><NarrationSettingsPage /></RequireAuth>} />
        <Route path="/dashboard/narration/analysis" element={<RequireAuth><NarrationAnalysisPage /></RequireAuth>} />
        <Route path="/dashboard/narration/editor" element={<RequireAuth><NarrationEditorPage /></RequireAuth>} />
        <Route path="/dashboard/narration/review" element={<RequireAuth><NarrationReviewPage /></RequireAuth>} />
        <Route path="/dashboard/narration/generate" element={<RequireAuth><NarrationStagePage stage="render" /></RequireAuth>} />
        <Route path="/dashboard/narration/export" element={<RequireAuth><NarrationStagePage stage="export" /></RequireAuth>} />
        <Route path="/projects/:projectId/result" element={<RequireAuth><ProjectResultPage /></RequireAuth>} />
        <Route path="/projects/:projectId/editor" element={<RequireAuth><ProjectEditorPage /></RequireAuth>} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </>
  );
}
