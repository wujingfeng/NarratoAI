import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getCurrentUser, logout as logoutRequest, login as loginRequest } from "../../services/narratoApi.js";
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

  const refreshUser = useCallback(async () => {
    const sessionToken = readToken();
    if (!sessionToken) {
      setUser(null);
      return null;
    }
    const current = await getCurrentUser();
    // 登出或另一处登录替换 Token 后，旧请求不得回写当前账户。
    if (readToken() === sessionToken) setUser(current);
    return current;
  }, []);

  useEffect(() => {
    if (!token) return undefined;
    let active = true;
    refreshUser().catch(() => {
      // 401 会由 httpClient 统一清理会话；短暂网络失败只保留未知余额。
      if (active) setUser((current) => current);
    });
    return () => { active = false; };
  }, [refreshUser, token]);

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
    () => ({ isAuthenticated: Boolean(token), token, user, refreshUser, signIn, signOut }),
    [refreshUser, signIn, signOut, token, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth 必须在 AuthProvider 内使用");
  return context;
}
