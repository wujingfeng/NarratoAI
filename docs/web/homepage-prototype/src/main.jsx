import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App.jsx";
import { I18nProvider } from "./i18n/I18nProvider.jsx";
import { AuthProvider } from "./features/auth/AuthProvider.jsx";
import "./styles/tokens.css";
import "./styles/home.css";
import "./styles/dashboard.css";
import "./styles/create.css";
import "./styles/projects.css";
import "./styles/project-result.css";
import "./styles/narration.css";
import "./styles/video-translation.css";
import "./styles/narration-analysis.css";
import "./styles/narration-editor.css";
import "./styles/narration-review.css";
import "./styles/auth.css";
import "./styles/project-editor.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <I18nProvider>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </I18nProvider>
  </React.StrictMode>,
);
