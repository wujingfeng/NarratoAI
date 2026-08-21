import { Button, Form, Input, InputNumber, Modal, Select, Switch, message } from 'antd'
import type { ProColumns } from '@ant-design/pro-components'
import { useEffect, useState } from 'react'
import { adminApi } from '../api/admin'
import { DataTable, JsonDetails, StatusTag } from '../components/DataTable'
import { useAuth } from '../features/auth'
import type { KeyValueRecord } from '../types/api'

const names = { models: '模型配置', 'play-modes': '玩法管理', providers: '渠道配置', 'system-configs': '系统配置', admins: '管理员', roles: '角色与权限', permissions: '权限点', menus: '菜单树' } as const
type Resource = keyof typeof names
const modelResources = new Set<Resource>(['models', 'play-modes', 'providers'])
const rbacResources = new Set<Resource>(['admins', 'roles', 'permissions', 'menus'])
const labels: Record<string, string> = { display_name: '显示名称', description: '说明', category: '运营分类', sort_order: '排序值', is_enabled: '是否启用', is_default: '是否默认', default_credits: '默认积分', provider_model_id: '供应商模型标识', submit_url: '提交地址', status_query_url: '状态查询地址', status_query_method: '状态查询方法', api_key: 'API 密钥', config_key: '配置键', value: '配置值', is_secret: '敏感配置', username: '登录账号', password: '密码', status: '账号状态', role_ids: '角色', is_superuser: '超级管理员', code: '代码', name: '名称', permission_ids: '权限', parent_id: '父级菜单', path: '前端路由', icon: '图标', permission_code: '访问权限代码', menu_type: '菜单类型', is_visible: '是否可见' }
const resourceKeywordFields: Record<Resource, string> = { models: 'display_name', 'play-modes': 'display_name', providers: 'provider_code', 'system-configs': 'config_key', admins: 'username', roles: 'name', permissions: 'name', menus: 'name' }

const text = (title: string, key: string, search = false): ProColumns<KeyValueRecord> => ({ title, dataIndex: key, search, renderText: (value) => Array.isArray(value) ? value.join(', ') : String(value ?? '—') })
const bool = (title: string, key: string): ProColumns<KeyValueRecord> => ({ title, dataIndex: key, valueType: 'select', valueEnum: { true: '启用', false: '停用' }, render: (_, record) => <StatusTag status={record[key] ? 'active' : 'disabled'} /> })
const input = (key: string, required = false, multiline = false) => <Form.Item key={key} name={key} label={labels[key] ?? key} rules={required ? [{ required: true, message: `请输入${labels[key] ?? key}` }] : []}>{multiline ? <Input.TextArea rows={key === 'value' ? 4 : 2} /> : <Input />}</Form.Item>

function fields(resource: Resource, editing: boolean, roleOptions: { label: string; value: string }[], permissionOptions: { label: string; value: string }[]) {
  if (resource === 'models') return <>{input('display_name', true)}{input('description', false, true)}{input('category', true)}<Form.Item name="sort_order" label="排序值"><InputNumber min={0} className="full-width" /></Form.Item><Form.Item name="is_enabled" label="是否启用" valuePropName="checked"><Switch /></Form.Item><Form.Item name="is_default" label="默认模型" valuePropName="checked"><Switch /></Form.Item></>
  if (resource === 'play-modes') return <>{input('display_name', true)}{input('description', false, true)}<Form.Item name="default_credits" label="默认积分"><InputNumber min={0} className="full-width" /></Form.Item><Form.Item name="sort_order" label="排序值"><InputNumber min={0} className="full-width" /></Form.Item><Form.Item name="is_enabled" label="是否启用" valuePropName="checked"><Switch /></Form.Item><Form.Item name="is_default" label="默认玩法" valuePropName="checked"><Switch /></Form.Item></>
  if (resource === 'providers') return <>{input('provider_model_id', true)}{input('submit_url', true)}{input('status_query_url')}<Form.Item name="status_query_method" label="状态查询方法"><Select options={['GET', 'POST'].map((value) => ({ value, label: value }))} /></Form.Item><Form.Item name="api_key" label="API 密钥"><Input.Password autoComplete="new-password" placeholder={editing ? '留空则不修改，密钥不会回显' : '仅在此输入一次'} /></Form.Item><Form.Item name="is_enabled" label="是否启用" valuePropName="checked"><Switch /></Form.Item></>
  if (resource === 'system-configs') return <>{!editing && input('config_key', true)}<Form.Item name="value" label="配置值"><Input.TextArea rows={4} placeholder={editing ? '敏感配置留空则保留原值，内容不会回显' : undefined} /></Form.Item>{input('description', false, true)}<Form.Item name="is_secret" label="敏感配置" valuePropName="checked"><Switch /></Form.Item></>
  if (resource === 'admins') return <>{!editing && <>{input('username', true)}{input('display_name', true)}<Form.Item name="password" label="初始密码" rules={[{ required: true, message: '请输入初始密码' }]}><Input.Password autoComplete="new-password" /></Form.Item></>}{editing && input('display_name', true)}<Form.Item name="status" label="账号状态"><Select options={[{ value: 'active', label: '启用' }, { value: 'disabled', label: '禁用' }]} /></Form.Item><Form.Item name="role_ids" label="角色"><Select mode="multiple" options={roleOptions} placeholder="选择角色" /></Form.Item>{editing && <Form.Item name="password" label="重置密码"><Input.Password autoComplete="new-password" placeholder="留空则不修改" /></Form.Item>}<Form.Item name="is_superuser" label="超级管理员" valuePropName="checked"><Switch disabled={editing} /></Form.Item></>
  if (resource === 'roles') return <>{input('code', true)}{input('name', true)}{input('description', false, true)}<Form.Item name="permission_ids" label="权限"><Select mode="multiple" options={permissionOptions} placeholder="选择权限" /></Form.Item></>
  if (resource === 'permissions') return <>{input('code', true)}{input('name', true)}{input('description', false, true)}</>
  return <>{input('name', true)}{input('code', true)}{input('path')}{input('icon')}<Form.Item name="parent_id" label="父级菜单"><Input placeholder="留空代表一级菜单" /></Form.Item><Form.Item name="permission_code" label="访问权限代码"><Input placeholder="例如：admin:users:read" /></Form.Item><Form.Item name="menu_type" label="菜单类型" initialValue="menu"><Select options={[['directory', '目录'], ['menu', '菜单'], ['button', '按钮']].map(([value, label]) => ({ value, label }))} /></Form.Item><Form.Item name="sort_order" label="排序值"><InputNumber min={0} className="full-width" /></Form.Item><Form.Item name="is_visible" label="是否可见" valuePropName="checked"><Switch /></Form.Item></>
}

function Editor({ resource, record, onClose, onSaved }: { resource: Resource; record?: KeyValueRecord; onClose: () => void; onSaved: () => void }) {
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)
  const [roleOptions, setRoleOptions] = useState<{ label: string; value: string }[]>([])
  const [permissionOptions, setPermissionOptions] = useState<{ label: string; value: string }[]>([])
  const editing = Boolean(record)
  useEffect(() => {
    if (resource === 'admins') adminApi.records('roles', { page: 1, page_size: 1000 }).then(({ items }) => {
      const options = items.map((item) => ({ value: String(item.id), label: String(item.name ?? item.code ?? item.id) }))
      setRoleOptions(options)
      const roleCodes = Array.isArray(record?.roles) ? record.roles.map(String) : []
      form.setFieldValue('role_ids', items.filter((item) => roleCodes.includes(String(item.code))).map((item) => String(item.id)))
    }).catch(() => undefined)
    if (resource === 'roles') adminApi.records('permissions', { page: 1, page_size: 1000 }).then(({ items }) => setPermissionOptions(items.map((item) => ({ value: String(item.id), label: String(item.name ?? item.code ?? item.id) })))).catch(() => undefined)
  }, [form, record?.id, record?.roles, resource])
  const initialValues: Record<string, unknown> = { ...(record ?? {}), is_enabled: record?.is_enabled ?? true, is_visible: record?.is_visible ?? true, is_secret: record?.is_secret ?? false, sort_order: record?.sort_order ?? 0 }
  if (resource === 'providers') delete initialValues.api_key
  if (resource === 'system-configs' && initialValues.is_secret) delete initialValues.value
  if (resource === 'admins') delete initialValues.role_ids
  const highRisk = resource === 'providers' || resource === 'system-configs' || rbacResources.has(resource)
  const confirmHighRisk = () => !highRisk || window.confirm(`即将保存${names[resource]}。该操作会立即影响后台权限、系统行为或供应商调用，确认继续吗？`)
  const save = async () => {
    const values = await form.validateFields()
    if (!confirmHighRisk()) return false
    const normalized = Object.fromEntries(Object.entries(values).filter(([, value]) => value !== undefined && value !== '')) as Record<string, unknown>
    if (!normalized.password) delete normalized.password
    if (resource === 'system-configs') { const key = String(editing ? record?.config_key : normalized.config_key); delete normalized.config_key; await adminApi.patchSystemConfig(key, normalized) }
    else if (editing) await adminApi.patchResource(resource, String(record?.id), normalized)
    else await adminApi.createRbac(resource as 'admins' | 'roles' | 'permissions' | 'menus', normalized)
    return true
  }
  return <Modal open title={`${editing ? '编辑' : '新建'}${names[resource]}`} width={580} okText="保存" confirmLoading={saving} onCancel={onClose} onOk={() => { setSaving(true); void save().then((saved) => { if (saved) { message.success('保存成功'); onSaved(); onClose() } }).catch((error: Error) => message.error(error.message)).finally(() => setSaving(false)) }}><Form form={form} layout="vertical" initialValues={initialValues}>{fields(resource, editing, roleOptions, permissionOptions)}</Form></Modal>
}

function columnsFor(resource: Resource, onEdit?: (record: KeyValueRecord) => void): ProColumns<KeyValueRecord>[] {
  const updated = text('更新时间', 'updated_at')
  const edit = onEdit ? { title: '编辑', key: '__edit', valueType: 'option' as const, render: (_: unknown, record: KeyValueRecord) => <Button type="link" onClick={() => onEdit(record)}>编辑</Button> } : undefined
  const cols: ProColumns<KeyValueRecord>[] = resource === 'models' ? [text('模型名称', 'display_name', true), text('类型', 'model_type'), text('运营分类', 'category'), text('排序值', 'sort_order'), bool('是否启用', 'is_enabled'), bool('默认模型', 'is_default'), updated] : resource === 'play-modes' ? [text('玩法名称', 'display_name', true), text('玩法代码', 'code'), text('模型 ID', 'model_id'), text('默认积分', 'default_credits'), bool('是否启用', 'is_enabled'), bool('默认玩法', 'is_default'), updated] : resource === 'providers' ? [text('供应商', 'provider_code', true), text('供应商模型', 'provider_model_id'), text('玩法 ID', 'play_mode_id'), text('提交地址', 'submit_url'), bool('是否启用', 'is_enabled'), updated] : resource === 'system-configs' ? [text('配置键', 'config_key', true), text('配置值', 'value'), text('说明', 'description'), bool('敏感配置', 'is_secret'), updated] : resource === 'admins' ? [text('账号', 'username', true), text('显示名', 'display_name'), text('角色', 'roles'), bool('超级管理员', 'is_superuser'), text('状态', 'status'), updated] : resource === 'roles' ? [text('名称', 'name', true), text('代码', 'code'), text('权限', 'permission_ids'), bool('系统角色', 'is_system'), updated] : resource === 'permissions' ? [text('名称', 'name', true), text('权限代码', 'code'), text('说明', 'description'), text('创建时间', 'created_at')] : [text('菜单名称', 'name', true), text('代码', 'code'), text('前端路由', 'path'), text('父级菜单', 'parent_id'), text('访问权限', 'permission_code'), bool('是否可见', 'is_visible'), updated]
  return edit ? [...cols, edit] : cols
}

export function RecordsPage({ resource }: { resource: Resource }) {
  const { profile } = useAuth()
  const [record, setRecord] = useState<KeyValueRecord>()
  const [creating, setCreating] = useState(false)
  const [revision, setRevision] = useState(0)
  const requiredPermission = modelResources.has(resource) ? 'admin:models:manage' : resource === 'system-configs' ? 'admin:configs:manage' : 'admin:rbac:manage'
  const canManage = profile?.permissions.includes('*') || profile?.permissions.includes(requiredPermission)
  const canCreate = canManage && (resource === 'system-configs' || rbacResources.has(resource))
  return <><DataTable key={`${resource}:${revision}`} title={names[resource]} columns={columnsFor(resource, canManage ? setRecord : undefined)} load={(params) => adminApi.records(resource, params)} detail={(item) => <JsonDetails record={item} />} filterMap={{ [resourceKeywordFields[resource]]: 'keyword', ...(resource === 'admins' ? { status: 'status' } : {}) }} />{canCreate && <div className="floating-create"><Button type="primary" onClick={() => setCreating(true)}>新建{names[resource]}</Button></div>}{(creating || record) && <Editor key={record?.id ?? 'create'} resource={resource} record={creating ? undefined : record} onClose={() => { setCreating(false); setRecord(undefined) }} onSaved={() => setRevision((value) => value + 1)} />}</>
}
