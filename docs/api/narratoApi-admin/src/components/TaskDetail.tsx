import { DownloadOutlined, ExportOutlined, FileTextOutlined } from '@ant-design/icons'
import { Alert, Button, Descriptions, Empty, Image, Skeleton, Space, Tabs, Tag, Typography } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { adminApi } from '../api/admin'
import { ApiError } from '../api/client'
import type { AdminTaskDetail, TaskMedia } from '../types/api'
import { StatusTag } from './DataTable'

const labels: Record<string, string> = {
  actual_output_duration_seconds: '实际输出时长', actual_output_image_count: '输出图片数量', audio_enabled: '生成音频',
  category: '任务分类', created_at: '创建时间', current_stage: '当前阶段', default_credits_charged: '预扣积分',
  final_credits: '最终扣除积分', id: '任务 ID', input_token: '输入 Token', model_id: '模型', output_token: '输出 Token',
  play_mode_id: '玩法', product: '产品类型', project_id: '项目 ID', provider_id: '供应商', provider_task_id: '供应商任务 ID',
  ratio: '画面比例', requested_duration_seconds: '请求时长', resolution: '分辨率', settlement_status: '结算状态',
  status: '状态', task_type: '任务类型', updated_at: '更新时间', user_id: '用户 ID', user_name: '用户名称',
  video_ratio: '视频比例', voice_id: '配音音色', narration_style: '解说风格', subtitle_style: '字幕样式',
  target_language: '目标语言', source_language: '源语言', original_sound_mode: '原声音频模式',
}

const mediaType = (item: TaskMedia) => {
  const kind = item.kind.toLowerCase()
  const contentType = item.content_type?.toLowerCase() ?? ''
  if (kind.includes('image') || contentType.startsWith('image/')) return 'image'
  if (kind.includes('video') || contentType.startsWith('video/')) return 'video'
  if (kind.includes('audio') || kind.includes('voice') || contentType.startsWith('audio/')) return 'audio'
  return 'file'
}
const displayLabel = (key: string) => labels[key] ?? `配置项（${key}）`
const typeLabel = (value: string) => ({ image: '图片', video: '视频', audio: '音频', file: '文件', voice: '配音', subtitle: '字幕', timeline: '时间轴' }[value] ?? value)
const statusLabel = (value?: string) => ({ completed: '已完成', succeeded: '已完成', succeeded_with_partial_output: '部分完成', failed: '失败', cancelled: '已取消', queued: '等待中', pending: '等待中', running: '处理中', processing: '处理中', finalizing: '收尾中', ready: '可用', validating: '校验中' }[value ?? ''] ?? value ?? '未知')
const valueText = (value: unknown) => {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}
const fileSize = (value?: number | null) => value == null ? '' : value < 1024 * 1024 ? `${Math.round(value / 1024)} KB` : `${(value / 1024 / 1024).toFixed(1)} MB`
const duration = (value?: number | null) => value == null ? '' : `${Math.round(value * 10) / 10} 秒`

function KeyValues({ data }: { data?: Record<string, unknown> | null }) {
  const entries = Object.entries(data ?? {}).filter(([, value]) => value !== null && value !== undefined && value !== '')
  return entries.length ? <Descriptions className="task-detail-descriptions" column={2} size="small" items={entries.map(([key, value]) => ({ key, label: displayLabel(key), children: <span className="task-detail-value">{valueText(value)}</span> }))} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无配置" />
}

function MediaCard({ item }: { item: TaskMedia }) {
  const type = mediaType(item)
  const title = item.filename || item.kind
  const meta = [item.content_type, fileSize(item.size_bytes), duration(item.duration_seconds)].filter(Boolean).join(' · ')
  return <article className="task-media-card">
    <div className={`task-media-preview task-media-preview--${type}`}>
      {type === 'image' && item.url && <Image src={item.url} alt={title} preview={{ mask: '预览图片' }} />}
      {type === 'video' && item.url && <video controls muted playsInline preload="metadata" src={item.url}>此浏览器不支持视频预览。</video>}
      {type === 'audio' && item.url && <div className="task-audio-preview"><span>音频</span><audio controls preload="metadata" src={item.url}>此浏览器不支持音频预览。</audio></div>}
      {type === 'file' && <div className="task-file-preview"><FileTextOutlined /><span>{item.kind}</span></div>}
    </div>
    <div className="task-media-meta">
      <strong title={title}>{title}</strong>
      {meta && <small>{meta}</small>}
      <Space size={4} wrap>
        <Tag>{typeLabel(type === 'file' ? item.kind : type)}</Tag>
        {item.status && <Tag color={item.status === 'ready' ? 'success' : 'processing'}>{statusLabel(item.status)}</Tag>}
      </Space>
      {item.url && <Space size={4} wrap>
        <Button size="small" type="link" icon={<ExportOutlined />} href={item.url} target="_blank" rel="noreferrer">打开</Button>
        <Button size="small" type="link" icon={<DownloadOutlined />} href={item.url} download>下载</Button>
      </Space>}
    </div>
  </article>
}

function MediaList({ title, items }: { title: string; items?: TaskMedia[] }) {
  const files = items?.filter((item) => item.url) ?? []
  if (!files.length) return <section className="task-detail-section"><h3>{title}</h3><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无文件" /></section>
  return <section className="task-detail-section"><h3>{title}<span>{files.length}</span></h3><div className="task-media-grid">{files.map((item, index) => <MediaCard key={item.id ?? `${item.url}-${index}`} item={item} />)}</div></section>
}

function DetailContent({ detail }: { detail: AdminTaskDetail }) {
  const task = detail.task
  const outputItems = detail.result.outputs ?? detail.result.artifacts ?? []
  const taskSummary = useMemo(() => ({
    id: task.id, user_name: task.user_name, user_id: task.user_id, status: statusLabel(task.status), category: task.category,
    project_id: task.project_id, provider_task_id: task.provider_task_id, created_at: task.created_at, updated_at: task.updated_at,
  }), [task])
  return <div className="task-detail">
    <section className="task-detail-hero"><div><p>任务状态</p><h2>{task.id}</h2></div><StatusTag status={task.status} /></section>
    <Tabs items={[
      { key: 'input', label: '用户输入', children: <div className="task-detail-stack">
        {detail.input.prompt && <section className="task-detail-section"><h3>提示词</h3><Typography.Paragraph className="task-prompt" copyable>{detail.input.prompt}</Typography.Paragraph></section>}
        <section className="task-detail-section"><h3>输入配置</h3><KeyValues data={detail.input.configuration ?? detail.input.settings} /></section>
        {detail.input.project && <section className="task-detail-section"><h3>关联项目</h3><KeyValues data={detail.input.project} /></section>}
        <MediaList title="源素材" items={detail.input.source_assets} />
      </div> },
      { key: 'result', label: '最终结果', children: <div className="task-detail-stack">
        {detail.result.error && <Alert type="error" showIcon message={detail.result.error.code || '任务执行失败'} description={detail.result.error.message} />}
        <MediaList title="结果文件" items={outputItems} />
        {detail.result.outputs?.some((item) => item.text) && <section className="task-detail-section"><h3>文本结果</h3>{detail.result.outputs.filter((item) => item.text).map((item, index) => <Typography.Paragraph key={item.id ?? index} className="task-prompt" copyable>{item.text}</Typography.Paragraph>)}</section>}
        <section className="task-detail-section"><h3>用量与结算</h3><KeyValues data={detail.result.usage} /></section>
      </div> },
      { key: 'execution', label: '执行记录', children: <div className="task-detail-stack">
        {detail.execution?.nodes?.length ? <div className="task-nodes">{detail.execution.nodes.map((node) => <div className="task-node" key={String(node.id)}><div><strong>{String(node.name)}</strong><small>{String(node.latest_attempt ? `第 ${String((node.latest_attempt as Record<string, unknown>).attempt_number)} 次执行` : '尚未执行')}</small></div><Tag color={String(node.state) === 'completed' ? 'success' : String(node.state) === 'failed' ? 'error' : 'processing'}>{statusLabel(String(node.state))}</Tag></div>)}</div> : <section className="task-detail-section"><h3>基础信息</h3><KeyValues data={taskSummary} /></section>}
      </div> },
    ]} />
  </div>
}

export function TaskDetail({ taskId }: { taskId: string }) {
  const [detail, setDetail] = useState<AdminTaskDetail>()
  const [error, setError] = useState<string>()
  useEffect(() => {
    let disposed = false
    setDetail(undefined); setError(undefined)
    adminApi.task(taskId).then((data) => { if (!disposed) setDetail(data) }).catch((reason: unknown) => { if (!disposed) setError(reason instanceof ApiError ? reason.message : '任务详情加载失败') })
    return () => { disposed = true }
  }, [taskId])
  if (error) return <Alert type="error" showIcon message="详情加载失败" description={error} />
  if (!detail) return <Skeleton active paragraph={{ rows: 12 }} />
  return <DetailContent detail={detail} />
}
