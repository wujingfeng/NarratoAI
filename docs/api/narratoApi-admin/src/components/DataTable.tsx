import { DownloadOutlined, EyeOutlined, ReloadOutlined, SettingOutlined } from '@ant-design/icons'
import { ProTable, type ProColumns } from '@ant-design/pro-components'
import { Alert, Button, Checkbox, Drawer, Popover, Skeleton, Space, Tag, message } from 'antd'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { downloadCurrentPageCsv } from '../api/client'
import type { ListParams, Paginated } from '../types/api'

interface Props<T extends Record<string, unknown>> {
  title: string
  columns: ProColumns<T>[]
  load: (params: ListParams) => Promise<Paginated<T>>
  detail?: (record: T) => ReactNode
  detailWidth?: number
  rowKey?: string
  batchActions?: (selected: T[], clear: () => void, refresh: () => void) => ReactNode
  /** Maps visible form columns to the backend query contract, rather than guessing from labels. */
  filterMap?: Record<string, keyof ListParams>
}

const pageSizes = [10, 30, 50, 100, 500, 1000]

function readParams(search: URLSearchParams): ListParams {
  const entries = Object.fromEntries(search.entries()) as ListParams
  const page = Number(entries.page)
  const pageSize = Number(entries.page_size)
  return { ...entries, page: Number.isInteger(page) && page > 0 ? page : 1, page_size: pageSizes.includes(pageSize) ? pageSize : 30 }
}

function writeParams(params: ListParams): URLSearchParams {
  const next = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') next.set(key, String(value))
  })
  return next
}

export function DataTable<T extends Record<string, unknown>>({ title, columns, load, detail, detailWidth = 520, rowKey = 'id', batchActions, filterMap = {} }: Props<T>) {
  const [searchParams, setSearchParams] = useSearchParams()
  const searchKey = searchParams.toString()
  const params = useMemo(() => readParams(new URLSearchParams(searchKey)), [searchKey])
  const [result, setResult] = useState<Paginated<T>>({ items: [], total: 0, page: 1, page_size: 30 })
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string>()
  const [selectedRows, setSelectedRows] = useState<T[]>([])
  const [selected, setSelected] = useState<T>()
  const fieldColumns = useMemo(() => columns.filter((column) => {
    const key = String(column.dataIndex ?? column.key ?? '')
    return key && !key.startsWith('__')
  }), [columns])
  const [visibleKeys, setVisibleKeys] = useState(() => fieldColumns.map((column) => String(column.dataIndex ?? column.key)))
  const visibleColumns = useMemo(() => columns.filter((column) => {
    const key = String(column.dataIndex ?? column.key ?? '')
    return key.startsWith('__') || !column.dataIndex || visibleKeys.includes(key)
  }), [columns, visibleKeys])
  const filterColumns = useMemo<ProColumns<T>[]>(() => [
    ...visibleColumns,
    { title: '时间范围', dataIndex: '__date_range', valueType: 'dateRange', hideInTable: true },
    ...(detail ? [{ title: '操作', key: '__detail', valueType: 'option' as const, fixed: 'right' as const, render: (_: unknown, record: T) => <Button type="link" icon={<EyeOutlined />} onClick={() => setSelected(record)}>查看详情</Button> }] : []),
  ], [detail, visibleColumns])
  const refresh = useCallback((next: ListParams = params) => {
    setLoading(true)
    setLoadError(undefined)
    return load(next).then(setResult).catch((error: Error) => {
      const content = error.message || '列表加载失败'
      setLoadError(content)
      message.error(content)
    }).finally(() => setLoading(false))
  }, [load, params])

  useEffect(() => { void refresh(params) }, [params, refresh])

  const setUrl = (next: ListParams) => setSearchParams(writeParams(next), { replace: true })
  const exportFields = fieldColumns.filter((column) => visibleKeys.includes(String(column.dataIndex ?? column.key))).map((column) => ({ key: String(column.dataIndex ?? column.key), label: String(column.title ?? column.dataIndex ?? '') }))
  const formParamNames = new Set(Object.values(filterMap).map(String))

  return <>
    {loading && !result.items.length ? <Skeleton active paragraph={{ rows: 8 }} /> : null}
    {loadError ? <Alert className="control-table-error" type="error" showIcon message="列表加载失败" description={loadError} action={<Button size="small" onClick={() => void refresh()}>重试</Button>} /> : null}
    <ProTable<T>
      className="control-table" headerTitle={title} rowKey={rowKey} loading={loading} columns={filterColumns}
      dataSource={result.items} search={{ labelWidth: 'auto', span: { xs: 24, sm: 12, md: 8, lg: 8, xl: 6, xxl: 6 } }}
      toolBarRender={() => [
        <Button key="export" icon={<DownloadOutlined />} disabled={!result.items.length} onClick={() => downloadCurrentPageCsv(`${title}-${result.page}.csv`, result.items, exportFields)}>导出当前页</Button>,
        <Popover key="fields" trigger="click" placement="bottomRight" content={<Checkbox.Group value={visibleKeys} onChange={(keys) => setVisibleKeys(keys.map(String))} options={fieldColumns.map((column) => ({ value: String(column.dataIndex ?? column.key), label: String(column.title ?? column.dataIndex) }))} />}><Button icon={<SettingOutlined />}>显示字段</Button></Popover>,
        <Button key="refresh" icon={<ReloadOutlined />} onClick={() => void refresh()}>刷新</Button>,
      ]}
      pagination={{ current: result.page, pageSize: result.page_size, total: result.total, showSizeChanger: true, pageSizeOptions: pageSizes, showQuickJumper: true, showTotal: (total) => `共 ${total} 条` }}
      onSubmit={(values) => {
        const next: ListParams = { ...params, page: 1 }
        formParamNames.forEach((name) => delete next[name])
        delete next.start_at; delete next.end_at
        const raw = values as Record<string, unknown>
        Object.entries(filterMap).forEach(([field, target]) => {
          const value = raw[field]
          if (value !== undefined && value !== null && value !== '') next[target] = value as string | number | boolean
        })
        const range = raw.__date_range as { toISOString?: () => string }[] | undefined
        if (range?.[0]?.toISOString) next.start_at = range[0].toISOString()
        if (range?.[1]?.toISOString) next.end_at = range[1].toISOString()
        setUrl(next)
      }}
      onReset={() => {
        const next: ListParams = { ...params, page: 1 }
        formParamNames.forEach((name) => delete next[name])
        delete next.start_at; delete next.end_at
        setUrl(next)
      }}
      onChange={(pagination) => setUrl({ ...params, page: pagination.current ?? 1, page_size: pagination.pageSize ?? 30 })}
      rowSelection={batchActions ? { onChange: (_, rows) => setSelectedRows(rows) } : undefined}
      tableAlertRender={batchActions ? () => <span>已选择 {selectedRows.length} 项</span> : undefined}
      tableAlertOptionRender={batchActions ? () => <Space>{batchActions(selectedRows, () => setSelectedRows([]), () => void refresh())}</Space> : undefined}
    />
    <Drawer title={`${title} · 详情`} open={Boolean(selected)} onClose={() => setSelected(undefined)} width={detailWidth}>{selected && detail?.(selected)}</Drawer>
  </>
}

export const StatusTag = ({ status }: { status?: string }) => <Tag color={status === 'active' || status === 'success' || status === 'completed' ? 'success' : status === 'disabled' || status === 'failed' ? 'error' : 'processing'}>{status ?? '未知'}</Tag>
export const JsonDetails = ({ record }: { record: Record<string, unknown> }) => <div className="detail-grid">{Object.entries(record).map(([key, value]) => <div key={key}><small>{key}</small><strong>{typeof value === 'object' ? JSON.stringify(value) : String(value ?? '—')}</strong></div>)}</div>
