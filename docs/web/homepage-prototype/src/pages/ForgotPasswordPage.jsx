import { useEffect, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../features/auth/AuthProvider.jsx";
import { ApiError } from "../services/httpClient.js";
import { resetPassword, sendPasswordResetCode } from "../services/narratoApi.js";

const RESEND_COOLDOWN_SECONDS = 60;

export function ForgotPasswordPage() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [verificationCode, setVerificationCode] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [sendingCode, setSendingCode] = useState(false);
  const [resendSeconds, setResendSeconds] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [resetSucceeded, setResetSucceeded] = useState(false);

  useEffect(() => {
    if (!resetSucceeded) return undefined;

    const redirectTimer = window.setTimeout(() => {
      navigate("/login", { replace: true });
    }, 3000);
    return () => window.clearTimeout(redirectTimer);
  }, [navigate, resetSucceeded]);

  useEffect(() => {
    if (resendSeconds <= 0) return undefined;

    const countdownTimer = window.setInterval(() => {
      setResendSeconds((seconds) => Math.max(0, seconds - 1));
    }, 1000);
    return () => window.clearInterval(countdownTimer);
  }, [resendSeconds]);

  if (isAuthenticated) return <Navigate to="/dashboard" replace />;

  async function handleSendCode() {
    setError("");
    setNotice("");
    setSendingCode(true);
    try {
      await sendPasswordResetCode(email);
      setNotice("如该邮箱已注册，验证码已发送，请在 10 分钟内完成重置。");
      setResendSeconds(RESEND_COOLDOWN_SECONDS);
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "验证码发送失败，请稍后重试");
    } finally {
      setSendingCode(false);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await resetPassword({ email, password, verificationCode });
      setResetSucceeded(true);
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "密码重置失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="forgot-password-title">
        <p className="auth-card__eyebrow">影创工坊</p>
        <h1 id="forgot-password-title" data-route-heading tabIndex="-1">重置密码</h1>
        <p>输入注册邮箱并验证后，设置新的登录密码。</p>
        <form onSubmit={handleSubmit}>
          <label htmlFor="reset-email">邮箱</label>
          <input id="reset-email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          <label htmlFor="reset-password">新密码</label>
          <input id="reset-password" type="password" autoComplete="new-password" minLength="8" value={password} onChange={(event) => setPassword(event.target.value)} required />
          <p className="auth-card__hint">至少 8 位，且同时包含字母和数字。</p>
          <label htmlFor="reset-code">邮箱验证码</label>
          <div className="auth-card__code-row">
            <input id="reset-code" inputMode="numeric" pattern="[0-9]{6}" maxLength="6" autoComplete="one-time-code" value={verificationCode} onChange={(event) => setVerificationCode(event.target.value)} required />
            <button type="button" className="auth-card__code-button" disabled={sendingCode || resendSeconds > 0 || !email} onClick={handleSendCode}>{sendingCode ? "发送中…" : resendSeconds > 0 ? `${resendSeconds} 秒后重发` : "发送验证码"}</button>
          </div>
          {notice && <p className="auth-card__notice" role="status">{notice}</p>}
          {error && <p className="auth-card__error" role="alert">{error}</p>}
          <button type="submit" disabled={submitting}>{submitting ? "重置中…" : "重置密码"}</button>
        </form>
        <p className="auth-card__secondary">想起密码了？ <Link to="/login">返回登录</Link></p>
      </section>
      {resetSucceeded && (
        <div className="auth-success-modal" role="dialog" aria-modal="true" aria-labelledby="reset-success-title">
          <section className="auth-success-modal__panel">
            <p className="auth-success-modal__eyebrow">密码已更新</p>
            <h2 id="reset-success-title">重置成功</h2>
            <p>正在为你跳转到登录页…</p>
            <Link className="auth-success-modal__login" to="/login" replace>立即登录</Link>
          </section>
        </div>
      )}
    </main>
  );
}
