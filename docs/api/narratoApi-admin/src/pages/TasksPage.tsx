import type { ProColumns } from '@ant-design/pro-components'
import { useSearchParams } from 'react-router-dom'
import { adminApi } from '../api/admin'
import { DataTable, StatusTag } from '../components/DataTable'
import { TaskDetail } from '../components/TaskDetail'
import type { AdminTask, ListParams } from '../types/api'

const categoryLabels: Record<string, string> = { short_drama: '短剧解说', video_translation: '视频翻译', ai_video: 'AI 视频' }
const statusLabels = { pending: '等待中', queued: '等待中', running: '处理中', processing: '处理中', completed: '完成', succeeded: '完成', failed: '失败', cancelled: '已取消' }

export function TasksPage() {
  const [searchParams] = useSearchParams()
  const category = searchParams.get('category') ?? undefined
  const title = category ? `${categoryLabels[category] ?? category}任务` : '全部任务'
  const columns: ProColumns<AdminTask>[] = [
    { title: '任务 ID', dataIndex: 'id', copyable: true, ellipsis: true, fieldProps: { placeholder: '任务 ID / 供应商任务 ID' } },
    { title: '用户 ID', dataIndex: 'user_id', copyable: true, ellipsis: true, fieldProps: { placeholder: '用户 ID' } },
    { title: '类别', dataIndex: 'category', valueType: 'select', valueEnum: categoryLabels, renderText: (value) => categoryLabels[String(value)] ?? String(value) },
    { title: '任务类型', dataIndex: 'task_type', valueType: 'select', valueEnum: { llm: 'LLM', image: '图片', video: '视频' }, renderText: (value) => String(value ?? '工作流') },
    { title: '状态', dataIndex: 'status', valueType: 'select', valueEnum: statusLabels, render: (_, record) => <StatusTag status={record.status} /> },
    { title: '预扣积分', dataIndex: 'default_credits_charged', search: false, renderText: (value) => value == null ? '—' : `${value} cr` },
    { title: '创建时间', dataIndex: 'created_at', search: false, valueType: 'dateTime' },
  ]
  const load = (params: ListParams) => adminApi.tasks(params)
  return <DataTable title={title} columns={columns} load={load} detailWidth={780} detail={(record) => <TaskDetail taskId={record.id} />} filterMap={{ id: 'keyword', user_id: 'user_id', category: 'category', task_type: 'task_type', status: 'status' }} />
}
