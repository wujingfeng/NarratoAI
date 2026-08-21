import { ArrowRightOutlined, LockOutlined, SafetyCertificateOutlined, UserOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Form, Input, Typography } from 'antd'
import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../features/auth'

export function LoginPage() {
  const { profile, signIn } = useAuth(); const navigate = useNavigate(); const [form] = Form.useForm<{ username: string; password: string }>(); const [submitting, setSubmitting] = useState(false)
  if (profile) return <Navigate to="/overview" replace />
  const submit = async (values: { username: string; password: string }) => { setSubmitting(true); try { await signIn(values.username, values.password); navigate('/overview') } catch (error) { form.setFields([{ name: 'password', errors: [error instanceof Error ? error.message : '登录失败，请重试'] }]) } finally { setSubmitting(false) } }
  return <main className="login-page"><section className="login-intro" aria-label="Narrato 控制台介绍"><div className="login-orbit" aria-hidden="true"><i /><i /><i /></div><header className="login-brand"><span className="login-logo">N</span><span><b>NARRATO</b><em>CONTROL CENTER</em></span></header><div className="login-copy"><p className="eyebrow">NARRATO API · ADMINISTRATION</p><h1>从创作流<br />到控制面。</h1><p>为运营、模型与服务治理提供统一的高密度工作台。</p></div><footer><span>SECURE ADMIN WORKSPACE</span><span>01 / 01</span></footer></section><section className="login-panel"><Card variant="borderless"><p className="eyebrow">SECURE ACCESS</p><Typography.Title level={2}>登录控制台</Typography.Title><Typography.Paragraph type="secondary">使用管理员账户访问受控资源与审计记录。</Typography.Paragraph><Form form={form} layout="vertical" requiredMark={false} onFinish={submit}>
    <Form.Item name="username" label="管理员账号" rules={[{ required: true, message: '请输入管理员账号' }]}><Input prefix={<UserOutlined />} autoComplete="username" size="large" placeholder="请输入账号" /></Form.Item>
    <Form.Item name="password" label="登录密码" rules={[{ required: true, message: '请输入登录密码' }]}><Input.Password prefix={<LockOutlined />} autoComplete="current-password" size="large" placeholder="请输入密码" /></Form.Item>
    <Alert type="info" showIcon icon={<SafetyCertificateOutlined />} message="所有登录、配置变更和导出行为都会写入审计日志。" />
    <Button type="primary" htmlType="submit" loading={submitting} size="large" block>进入控制台 <ArrowRightOutlined /></Button>
  </Form></Card><p className="login-security">TLS 加密传输 · RBAC 权限控制 · 操作可追溯</p></section></main>
}
