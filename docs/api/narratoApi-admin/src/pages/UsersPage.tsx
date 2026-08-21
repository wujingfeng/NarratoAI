import { Button, Descriptions, message, Popconfirm } from 'antd'
import type { ProColumns } from '@ant-design/pro-components'
import { useEffect, useState } from 'react'
import { adminApi } from '../api/admin'
import { DataTable, StatusTag } from '../components/DataTable'
import { useAuth } from '../features/auth'
import type { AdminUser } from '../types/api'

function UserDetail({ user }: { user: AdminUser }) {
  const [data, setData] = useState<AdminUser>(user)
  useEffect(() => { adminApi.user(user.id).then(setData).catch(() => undefined) }, [user.id])
  return <Descriptions column={1} bordered size="small" items={Object.entries(data).map(([label, value]) => ({ key: label, label, children: <span>{String(value ?? '—')}</span> }))} />
}

export function UsersPage() {
  const { profile } = useAuth()
  const canManage = profile?.permissions.includes('*') || profile?.permissions.includes('admin:users:manage')
  const [revision, setRevision] = useState(0)
  const columns: ProColumns<AdminUser>[] = [
    { title: '邮箱', dataIndex: 'email', copyable: true, ellipsis: true, fieldProps: { placeholder: '邮箱关键字' } },
    { title: '状态', dataIndex: 'status', valueType: 'select', valueEnum: { active: '正常', disabled: '禁用' }, render: (_, record) => <StatusTag status={record.status} /> },
    { title: '积分余额', dataIndex: 'credit_balance', search: false, valueType: 'digit' },
    { title: '注册时间', dataIndex: 'created_at', search: false, valueType: 'dateTime' },
    { title: '更新时间', dataIndex: 'updated_at', search: false, valueType: 'dateTime' },
    ...(canManage ? [{ title: '状态操作', valueType: 'option' as const, key: '__status_action', render: (_: unknown, record: AdminUser) => <Popconfirm title={`确认${record.status === 'active' ? '禁用' : '启用'}该用户？`} onConfirm={() => adminApi.updateUser(record.id, { status: record.status === 'active' ? 'disabled' : 'active' }).then(() => { message.success('状态已更新'); setRevision((value) => value + 1) }).catch((error: Error) => message.error(error.message))}><Button type="link">{record.status === 'active' ? '禁用' : '启用'}</Button></Popconfirm> }] : []),
  ]
  return <DataTable key={revision} title="用户列表" columns={columns} load={adminApi.users} detail={(user) => <UserDetail user={user} />} filterMap={{ email: 'keyword', status: 'status' }} batchActions={canManage ? (selected, clear, refresh) => <><Button type="link" disabled={!selected.length} onClick={() => adminApi.updateUsersStatus(selected.map((user) => user.id), 'active').then(() => { message.success('已批量启用'); clear(); refresh() }).catch((error: Error) => message.error(error.message))}>批量启用</Button><Button danger type="link" disabled={!selected.length} onClick={() => adminApi.updateUsersStatus(selected.map((user) => user.id), 'disabled').then(() => { message.success('已批量禁用'); clear(); refresh() }).catch((error: Error) => message.error(error.message))}>批量禁用</Button></> : undefined} />
}
