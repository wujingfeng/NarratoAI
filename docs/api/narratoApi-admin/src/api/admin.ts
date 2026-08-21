import { list, request } from './client'
import type { AdminProfile, AdminUser, AuditLog, CreditLedger, KeyValueRecord, ListParams, LoginResult, Paginated, AdminTask, AdminTaskDetail } from '../types/api'

export const adminApi = {
  login: (username: string, password: string) => request<LoginResult>('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  me: () => request<{ admin: AdminProfile }>('/auth/me').then(({ admin }) => admin),
  logout: () => request<void>('/auth/logout', { method: 'POST' }),
  users: (params: ListParams) => list<AdminUser>('/users', params),
  user: (id: string) => request<{ user: AdminUser }>(`/users/${id}`).then(({ user }) => user),
  updateUser: (id: string, body: Partial<AdminUser>) => request<{ user: AdminUser }>(`/users/${id}/status`, { method: 'PATCH', body: JSON.stringify({ status: body.status }) }).then(({ user }) => user),
  updateUsersStatus: (user_ids: string[], status: AdminUser['status']) => request<void>('/users/batch-status', { method: 'PATCH', body: JSON.stringify({ user_ids, status }) }),
  tasks: (params: ListParams) => list<AdminTask>('/tasks', params),
  task: (id: string) => request<AdminTaskDetail>(`/tasks/${id}`),
  models: (params: ListParams) => list<KeyValueRecord>('/models', params),
  playModes: (params: ListParams) => list<KeyValueRecord>('/play-modes', params),
  providers: (params: ListParams) => list<KeyValueRecord>('/providers', params),
  systemConfigs: (params: ListParams) => list<KeyValueRecord>('/system-configs', params),
  creditLedger: (params: ListParams) => list<CreditLedger>('/credit-ledger', params),
  operationLogs: (params: ListParams) => list<AuditLog>('/operation-logs', params),
  records: (resource: string, params: ListParams) => list<KeyValueRecord>(`/${resource}`, params),
  updateRecord: (resource: string, id: string, body: Record<string, unknown>) => request<KeyValueRecord>(`/${resource}/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  createRecord: (resource: string, body: Record<string, unknown>) => request<KeyValueRecord>(`/${resource}`, { method: 'POST', body: JSON.stringify(body) }),
  patchResource: (resource: string, id: string, body: Record<string, unknown>) => request<unknown>(`/${resource}/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  patchSystemConfig: (key: string, body: Record<string, unknown>) => request<unknown>(`/system-configs/${encodeURIComponent(key)}`, { method: 'PATCH', body: JSON.stringify(body) }),
  createRbac: (resource: 'admins' | 'roles' | 'permissions' | 'menus', body: Record<string, unknown>) => request<unknown>(`/${resource}`, { method: 'POST', body: JSON.stringify(body) }),
}
export type { Paginated }
