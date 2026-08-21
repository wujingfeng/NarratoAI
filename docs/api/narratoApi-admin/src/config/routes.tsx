import { lazy, type ReactNode } from 'react'
import { Navigate } from 'react-router-dom'

const OverviewPage = lazy(() => import('../pages/OverviewPage').then(({ OverviewPage: Page }) => ({ default: Page })))
const UsersPage = lazy(() => import('../pages/UsersPage').then(({ UsersPage: Page }) => ({ default: Page })))
const TasksPage = lazy(() => import('../pages/TasksPage').then(({ TasksPage: Page }) => ({ default: Page })))
const RecordsPage = lazy(() => import('../pages/RecordsPage').then(({ RecordsPage: Page }) => ({ default: Page })))
const OperationLogsPage = lazy(() => import('../pages/LogsPage').then(({ OperationLogsPage: Page }) => ({ default: Page })))
const CreditLogsPage = lazy(() => import('../pages/LogsPage').then(({ CreditLogsPage: Page }) => ({ default: Page })))

export interface AdminRouteDefinition {
  path: string
  permission: string
  element: ReactNode
}

export const adminRoutes: AdminRouteDefinition[] = [
  { path: '/overview', permission: 'admin:overview:read', element: <OverviewPage /> },
  { path: '/users', permission: 'admin:users:read', element: <UsersPage /> },
  { path: '/tasks', permission: 'admin:tasks:read', element: <TasksPage /> },
  { path: '/config/models', permission: 'admin:models:read', element: <RecordsPage resource="models" /> },
  { path: '/config/play-modes', permission: 'admin:models:read', element: <RecordsPage resource="play-modes" /> },
  { path: '/config/providers', permission: 'admin:models:read', element: <RecordsPage resource="providers" /> },
  { path: '/config/system', permission: 'admin:configs:read', element: <RecordsPage resource="system-configs" /> },
  { path: '/rbac/admins', permission: 'admin:rbac:read', element: <RecordsPage resource="admins" /> },
  { path: '/rbac/roles', permission: 'admin:rbac:read', element: <RecordsPage resource="roles" /> },
  { path: '/rbac/permissions', permission: 'admin:rbac:read', element: <RecordsPage resource="permissions" /> },
  { path: '/rbac/menus', permission: 'admin:rbac:read', element: <RecordsPage resource="menus" /> },
  { path: '/logs/operations', permission: 'admin:logs:read', element: <OperationLogsPage /> },
  { path: '/logs/credits', permission: 'admin:logs:read', element: <CreditLogsPage /> },
]

export const legacyTaskRoutes = [
  { path: '/tasks/short-drama', element: <Navigate to="/tasks?category=short_drama" replace /> },
  { path: '/tasks/video-translation', element: <Navigate to="/tasks?category=video_translation" replace /> },
  { path: '/tasks/ai-video', element: <Navigate to="/tasks?category=ai_video" replace /> },
]
