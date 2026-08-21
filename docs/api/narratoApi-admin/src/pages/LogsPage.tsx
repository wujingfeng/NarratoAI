import type { ProColumns } from '@ant-design/pro-components'
import { adminApi } from '../api/admin'
import { DataTable, JsonDetails, StatusTag } from '../components/DataTable'
import type { AuditLog, CreditLedger } from '../types/api'

export function OperationLogsPage() {
  const columns: ProColumns<AuditLog>[] = [
    { title: '管理员 ID', dataIndex: 'admin_id', copyable: true, ellipsis: true, fieldProps: { placeholder: '管理员 ID' } },
    { title: '管理员', dataIndex: 'username', search: false },
    { title: '操作', dataIndex: 'action', fieldProps: { placeholder: '操作关键字' } },
    { title: '资源类型', dataIndex: 'resource_type', search: false },
    { title: '结果', dataIndex: 'result', search: false, render: (_, record) => <StatusTag status={record.result} /> },
    { title: 'IP', dataIndex: 'ip_address', search: false },
    { title: 'Request ID', dataIndex: 'request_id', search: false, copyable: true, ellipsis: true },
    { title: '时间', dataIndex: 'created_at', search: false, valueType: 'dateTime' },
  ]
  return <DataTable title="后台操作日志" columns={columns} load={adminApi.operationLogs} detail={(record) => <JsonDetails record={record} />} filterMap={{ admin_id: 'admin_id', action: 'action' }} />
}

export function CreditLogsPage() {
  const columns: ProColumns<CreditLedger>[] = [
    { title: '用户 ID', dataIndex: 'user_id', copyable: true, ellipsis: true, fieldProps: { placeholder: '用户 ID' } },
    { title: '类型', dataIndex: 'entry_type', fieldProps: { placeholder: '流水类型' } },
    { title: '变动', dataIndex: 'amount', search: false, renderText: (value) => `${Number(value) > 0 ? '+' : ''}${value}` },
    { title: '关联对象', dataIndex: 'reference_id', search: false },
    { title: '原因', dataIndex: 'reason', search: false },
    { title: '时间', dataIndex: 'created_at', search: false, valueType: 'dateTime' },
  ]
  return <DataTable title="用户积分日志" columns={columns} load={adminApi.creditLedger} detail={(record) => <JsonDetails record={record} />} filterMap={{ user_id: 'user_id', entry_type: 'entry_type' }} />
}
