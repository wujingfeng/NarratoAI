import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./features/auth/AuthProvider.jsx";
import { RouteEffects } from "./components/RouteEffects.jsx";
import { DashboardPage } from "./pages/DashboardPage.jsx";
import { HomePage } from "./pages/HomePage.jsx";
import { LoginPage } from "./pages/LoginPage.jsx";
import { NotFoundPage } from "./pages/NotFoundPage.jsx";

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
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </>
  );
}
