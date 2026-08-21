import { Result, Spin } from 'antd'
import type { PropsWithChildren } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../features/auth'

/** Client-side guard improves navigation feedback; every API request remains server-authorized. */
export function RequirePermission({ permission, children }: PropsWithChildren<{ permission: string }>) {
  const { profile, ready } = useAuth()
  const location = useLocation()
  if (!ready) return <div style={{ minHeight: 240, display: 'grid', placeItems: 'center', gap: 12 }} role="status" aria-live="polite"><Spin /><span>正在验证权限</span></div>
  if (!profile) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  if (!profile.permissions.includes('*') && !profile.permissions.includes(permission)) return <Result status="403" title="没有访问权限" subTitle="请联系超级管理员授予所需的后台权限。" />
  return <>{children}</>
}
