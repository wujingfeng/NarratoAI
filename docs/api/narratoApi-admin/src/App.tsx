import { lazy, Suspense } from 'react'
import { ConfigProvider, Spin, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { Navigate, Route, Routes } from 'react-router-dom'
import { RequirePermission } from './components/RequirePermission'
import { adminRoutes, legacyTaskRoutes } from './config/routes'
import { LoginPage } from './pages/LoginPage'

const ControlLayout = lazy(() => import('./layouts/ControlLayout').then(({ ControlLayout: Layout }) => ({ default: Layout })))

const routeFallback = <div style={{ minHeight: '45vh', display: 'grid', placeItems: 'center', gap: 12 }} role="status" aria-live="polite"><Spin /><span>正在加载页面</span></div>

export default function App() {
  return <ConfigProvider locale={zhCN} theme={{ algorithm: theme.defaultAlgorithm, token: { colorPrimary: '#19b49a', borderRadius: 10, fontFamily: '"Source Han Sans SC", "Noto Sans SC", PingFang SC, sans-serif' } }}>
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<Suspense fallback={routeFallback}><ControlLayout /></Suspense>}>
        <Route path="/dashboard" element={<Navigate to="/overview" replace />} />
        {adminRoutes.map((route) => <Route key={route.path} path={route.path} element={<RequirePermission permission={route.permission}><Suspense fallback={routeFallback}>{route.element}</Suspense></RequirePermission>} />)}
        {legacyTaskRoutes.map((route) => <Route key={route.path} path={route.path} element={route.element} />)}
      </Route>
      <Route path="*" element={<Navigate to="/overview" replace />} />
    </Routes>
  </ConfigProvider>
}
