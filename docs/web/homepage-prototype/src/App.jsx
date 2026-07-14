import { Route, Routes } from "react-router-dom";
import { RouteEffects } from "./components/RouteEffects.jsx";
import { HomePage } from "./pages/HomePage.jsx";
import { NotFoundPage } from "./pages/NotFoundPage.jsx";

function DashboardRouteBoundary() {
  return (
    <main>
      <h1 data-route-heading tabIndex="-1">
        工作台概览
      </h1>
    </main>
  );
}

export function App() {
  return (
    <>
      <RouteEffects />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/dashboard" element={<DashboardRouteBoundary />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </>
  );
}
