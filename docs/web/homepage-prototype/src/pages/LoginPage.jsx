import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../services/httpClient.js";
import { useAuth } from "../features/auth/AuthProvider.jsx";

export function LoginPage() {
  const { isAuthenticated, signIn } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const nextPath = location.state?.from?.pathname || "/dashboard";

  if (isAuthenticated) return <Navigate to={nextPath} replace />;

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await signIn({ email, password });
      navigate(nextPath, { replace: true });
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "登录失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="login-title">
        <p className="auth-card__eyebrow">影创工坊</p>
        <h1 id="login-title" data-route-heading tabIndex="-1">登录工作台</h1>
        <p>使用已注册的邮箱账号继续创作。</p>
        <form onSubmit={handleSubmit}>
          <label htmlFor="login-email">邮箱</label>
          <input id="login-email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          <label htmlFor="login-password">密码</label>
          <input id="login-password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
          {error && <p className="auth-card__error" role="alert">{error}</p>}
          <button type="submit" disabled={submitting}>{submitting ? "登录中…" : "登录"}</button>
        </form>
      </section>
    </main>
  );
}
