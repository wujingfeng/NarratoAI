import type { ApiEnvelope, ListParams, Paginated } from '../types/api'

const baseURL = import.meta.env.VITE_ADMIN_API_BASE_URL ?? 'http://127.0.0.1:8001/api/v1/admin'
const tokenKey = 'narrato_admin_token'
export const getToken = () => localStorage.getItem(tokenKey)
export const setToken = (token: string) => localStorage.setItem(tokenKey, token)
export const clearToken = () => localStorage.removeItem(tokenKey)

export class ApiError extends Error { constructor(message: string, public readonly status?: number, public readonly requestId?: string) { super(message) } }

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken()
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  let response: Response
  try { response = await fetch(`${baseURL}${path}`, { ...init, headers }) } catch { throw new ApiError('网络连接失败，请检查管理 API 服务') }
  const envelope = await response.json().catch(() => null) as ApiEnvelope<T> | null
  if (!response.ok || !envelope) {
    if (response.status === 401) clearToken()
    throw new ApiError(envelope?.message ?? `请求失败 (${response.status})`, response.status, envelope?.request_id)
  }
  return envelope.data
}

export function query(params: ListParams) {
  const entries = Object.entries(params).filter(([, value]) => value !== undefined && value !== '')
  return entries.length ? `?${new URLSearchParams(entries.map(([key, value]) => [key, String(value)])).toString()}` : ''
}
export const list = <T>(path: string, params: ListParams) => request<Partial<Paginated<T>> & { items: T[] }>(`${path}${query(params)}`).then((data) => ({ items: data.items, total: data.total ?? data.items.length, page: data.page ?? params.page ?? 1, page_size: data.page_size ?? params.page_size ?? data.items.length }))
export const downloadCurrentPageCsv = (filename: string, records: Record<string, unknown>[], fields: { key: string; label: string }[]) => {
  const escape = (value: unknown) => `"${String(value ?? '').replaceAll('"', '""')}"`
  const csv = [fields.map((field) => escape(field.label)).join(','), ...records.map((record) => fields.map((field) => escape(record[field.key])).join(','))].join('\n')
  const href = URL.createObjectURL(new Blob(['\ufeff', csv], { type: 'text/csv;charset=utf-8' }))
  const a = document.createElement('a'); a.href = href; a.download = filename; a.click(); URL.revokeObjectURL(href)
}
