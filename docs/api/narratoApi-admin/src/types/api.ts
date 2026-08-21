import type { MenuDataItem } from '@ant-design/pro-components'

export interface ApiEnvelope<T> { code: string; message: string; data: T; request_id: string }
export interface Paginated<T> { items: T[]; total: number; page: number; page_size: number }
export interface AdminMenu extends MenuDataItem { key: string; path?: string; icon?: string; children?: AdminMenu[]; permission?: string }
export interface AdminProfile { id: string; username: string; display_name: string; roles: string[]; permissions: string[]; menus: AdminMenu[] }
export interface LoginResult { token: string; token_type?: string; admin: AdminProfile }
export interface ListParams { page?: number; page_size?: number; keyword?: string; status?: string; start_at?: string; end_at?: string; [key: string]: string | number | boolean | undefined }
export interface AdminUser extends Record<string, unknown> { id: string; email?: string; username?: string; nickname?: string; status: 'active' | 'disabled'; credits?: number; created_at: string; last_login_at?: string; task_count?: number }
export interface AdminTask extends Record<string, unknown> { id: string; project_id?: string; user_id: string; user_name?: string | null; task_type?: string; category: string; source: string; status: string; default_credits_charged?: number; final_credits?: number; created_at: string; updated_at: string }
export interface TaskMedia { id?: string; kind: string; url?: string | null; text?: string | null; filename?: string | null; content_type?: string | null; size_bytes?: number | null; duration_seconds?: number | null; status?: string; [key: string]: unknown }
export interface AdminTaskDetail { task: AdminTask & Record<string, unknown>; input: { prompt?: string | null; configuration?: Record<string, unknown>; settings?: Record<string, unknown>; source_assets: TaskMedia[]; project?: Record<string, unknown> | null }; result: { outputs?: TaskMedia[]; artifacts?: TaskMedia[]; error?: { code?: string | null; message?: string | null } | null; usage?: Record<string, unknown> }; execution?: { nodes: Array<Record<string, unknown>> } }
export interface AuditLog extends Record<string, unknown> { id: string; admin_id: string; username: string; action: string; resource_type: string; resource_id?: string; result: 'success' | 'failed'; ip_address?: string; request_id: string; method: string; path: string; created_at: string; before_data?: unknown; after_data?: unknown }
export interface CreditLedger extends Record<string, unknown> { id: string; user_id: string; entry_type: string; amount: number; idempotency_key?: string; reference_id?: string; reason?: string; created_at: string }
export interface KeyValueRecord { id: string; name: string; key?: string; code?: string; provider?: string; status?: string; updated_at?: string; created_at?: string; [key: string]: unknown }
