import { ClockCircleOutlined, DatabaseOutlined, RiseOutlined, TeamOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { ProCard } from '@ant-design/pro-components'
import { Alert, Empty, Statistic, Tag } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { request } from '../api/client'

type StatusSummary = { type: string; status: string; count: number }
type RecentTask = { id: string; task_type?: string; user_id: string; status: string; created_at: string }
type Overview = { users?: { total?: number; active?: number }; tasks?: { total?: number; model_tasks?: number; workflows?: number; by_status?: StatusSummary[] }; credits_today?: Record<string, number>; recent_tasks?: RecentTask[] }
const statusColor = (status: string) => status === 'completed' || status === 'success' ? 'success' : status === 'failed' ? 'error' : status === 'running' ? 'processing' : 'default'
const time = (value: string) => new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value))
export function OverviewPage() {
  const [data, setData] = useState<Overview>(); const [error, setError] = useState<string>(); const [loading, setLoading] = useState(true)
  useEffect(() => { request<Overview>('/overview').then(setData).catch((reason: Error) => setError(reason.message)).finally(() => setLoading(false)) }, [])
  const creditTotal = Object.values(data?.credits_today ?? {}).reduce((sum, amount) => sum + amount, 0)
  const statuses = useMemo(() => data?.tasks?.by_status ?? [], [data?.tasks?.by_status])
  const metrics = [
    { title: '平台用户', value: data?.users?.total, suffix: '人', support: `活跃 ${data?.users?.active ?? '—'} 人`, icon: <TeamOutlined /> },
    { title: '全部任务', value: data?.tasks?.total, suffix: '个', support: `模型 ${data?.tasks?.model_tasks ?? '—'} · 工作流 ${data?.tasks?.workflows ?? '—'}`, icon: <ThunderboltOutlined /> },
    { title: '当日积分变动', value: creditTotal, suffix: ' cr', support: `${Object.keys(data?.credits_today ?? {}).length} 类流水`, icon: <RiseOutlined /> },
  ]
  return <main className="overview-page page-stack">
    <section className="overview-hero" aria-labelledby="overview-title"><div><p className="eyebrow">OPERATIONS · REALTIME</p><h1 id="overview-title">运营总览</h1><p>基于当前管理 API 汇总的平台运行快照。</p></div><div className="live-indicator"><span /> 数据已连接</div></section>
    {error && <Alert type="warning" showIcon message="运营数据暂不可用" description={error} />}
    <section className="metric-grid" aria-label="核心指标">{metrics.map((item) => <ProCard key={item.title} className="metric-card" loading={loading}><div className="metric-card__top"><span>{item.title}</span><i>{item.icon}</i></div><Statistic value={item.value} suffix={item.suffix} valueStyle={{ color: '#eef5fb' }} /><p>{data ? item.support : '正在同步实时数据…'}</p></ProCard>)}</section>
    <section className="overview-content-grid">
      <ProCard className="operations-card" title={<span className="card-title"><DatabaseOutlined /> 任务状态分布</span>} loading={loading} extra={<span className="card-note">当前汇总</span>}>{statuses.length ? <div className="status-list">{statuses.map((item) => <div className="status-row" key={`${item.type}-${item.status}`}><div><strong>{item.type}</strong><span>{item.status}</span></div><Tag color={statusColor(item.status)}>{item.count} 项</Tag></div>)}</div> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无任务状态数据" />}</ProCard>
      <ProCard className="ledger-card" title={<span className="card-title"><RiseOutlined /> 今日积分流水</span>} loading={loading}>{Object.keys(data?.credits_today ?? {}).length ? <div className="ledger-list">{Object.entries(data?.credits_today ?? {}).map(([type, amount]) => <div key={type}><span>{type}</span><strong className={amount >= 0 ? 'amount-positive' : 'amount-negative'}>{amount >= 0 ? '+' : ''}{amount} <small>cr</small></strong></div>)}</div> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无积分流水" />}</ProCard>
      <ProCard className="recent-card" title={<span className="card-title"><ClockCircleOutlined /> 最近模型任务</span>} loading={loading}>{data?.recent_tasks?.length ? <div className="task-feed">{data.recent_tasks.map((task) => <article className="feed-item" key={task.id}><div className="feed-glyph"><ThunderboltOutlined /></div><div><strong>{task.task_type || '模型任务'}</strong><p>{task.user_id} · {task.id}</p></div><div className="feed-state"><Tag color={statusColor(task.status)}>{task.status}</Tag><time>{time(task.created_at)}</time></div></article>)}</div> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无近期任务数据" />}</ProCard>
    </section>
  </main>
}
