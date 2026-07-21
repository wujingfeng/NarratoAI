import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { logout as logoutRequest, login as loginRequest } from "../../services/narratoApi.js";
import { clearToken, readToken, writeToken } from "./authStorage.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const navigate = useNavigate();
  const [token, setToken] = useState(() => readToken());
  const [user, setUser] = useState(null);

  const clearSession = useCallback(() => {
    clearToken();
    setToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    const handleExpired = () => {
      clearSession();
      navigate("/login", { replace: true });
    };
    window.addEventListener("auth:expired", handleExpired);
    return () => window.removeEventListener("auth:expired", handleExpired);
  }, [clearSession, navigate]);

  const signIn = useCallback(async (credentials) => {
    const session = await loginRequest(credentials);
    writeToken(session.token);
    setToken(session.token);
    setUser(session.user);
    return session;
  }, []);

  const signOut = useCallback(async () => {
    try {
      await logoutRequest();
    } finally {
      clearSession();
      navigate("/login", { replace: true });
    }
  }, [clearSession, navigate]);

  const value = useMemo(
    () => ({ isAuthenticated: Boolean(token), token, user, signIn, signOut }),
    [signIn, signOut, token, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth 必须在 AuthProvider 内使用");
  return context;
}
