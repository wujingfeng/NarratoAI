import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App.jsx";
import { AuthProvider } from "./features/auth/AuthProvider.jsx";
import "./styles/tokens.css";
import "./styles/home.css";
import "./styles/dashboard.css";
import "./styles/auth.css";
import "./styles/project-editor.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
