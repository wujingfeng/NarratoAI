import {
  AppstoreOutlined,
  BellOutlined,
  ClusterOutlined,
  DashboardOutlined,
  FileTextOutlined,
  FundOutlined,
  MenuFoldOutlined,
  MenuOutlined,
  MenuUnfoldOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
  TeamOutlined,
  UserOutlined,
  VideoCameraOutlined,
  WalletOutlined,
  LogoutOutlined,
} from '@ant-design/icons'
import { Avatar, Breadcrumb, Button, Drawer, Dropdown, Layout, Menu, Spin, Tooltip } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../features/auth'
import type { AdminMenu } from '../types/api'

const iconMap: Record<string, typeof DashboardOutlined> = {
  dashboard: DashboardOutlined, overview: DashboardOutlined, user: UserOutlined, users: TeamOutlined,
  task: VideoCameraOutlined, tasks: VideoCameraOutlined, model: AppstoreOutlined, models: AppstoreOutlined,
  config: SettingOutlined, settings: SettingOutlined, rbac: SafetyCertificateOutlined,
  log: FileTextOutlined, logs: FileTextOutlined, credit: WalletOutlined, analytics: FundOutlined,
}
const iconFor = (name?: string) => {
  const Icon = name ? iconMap[name.toLowerCase().replaceAll('-', '')] ?? ClusterOutlined : ClusterOutlined
  return <Icon aria-hidden />
}
const pathName = (menus: AdminMenu[], path: string): string => {
  for (const menu of menus) {
    if (menu.path === path) return String(menu.name)
    const child = menu.children ? pathName(menu.children, path) : ''
    if (child) return child
  }
  const fallback: Record<string, string> = { overview: '运营总览', dashboard: '运营总览', users: '用户列表', tasks: '任务管理', models: '模型配置', logs: '日志中心' }
  return fallback[path.split('/').filter(Boolean).at(-1) ?? 'overview'] ?? '控制台'
}
const asItems = (menus: AdminMenu[]): Parameters<typeof Menu>[0]['items'] => menus.map((menu) => ({
  key: menu.path ?? menu.key,
  icon: iconFor(menu.icon),
  label: menu.path ? <Link to={menu.path}>{menu.name}</Link> : menu.name,
  children: menu.children ? asItems(menu.children) : undefined,
}))
function useViewport() {
  const [width, setWidth] = useState(() => window.innerWidth)
  useEffect(() => { const update = () => setWidth(window.innerWidth); window.addEventListener('resize', update); return () => window.removeEventListener('resize', update) }, [])
  return { isMobile: width < 768, isTablet: width >= 768 && width < 1200 }
}
export function ControlLayout() {
  const { profile, ready, signOut } = useAuth()
  const { isMobile, isTablet } = useViewport()
  const [manualCollapsed, setManualCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const navigate = useNavigate(); const location = useLocation()
  const items = useMemo(() => asItems(profile?.menus ?? []), [profile?.menus])
  const currentName = useMemo(() => pathName(profile?.menus ?? [], location.pathname), [profile?.menus, location.pathname])
  const collapsed = isTablet || manualCollapsed
  useEffect(() => { if (ready && !profile) navigate('/login', { replace: true }) }, [navigate, profile, ready])
  useEffect(() => { setMobileOpen(false) }, [location.pathname])
  if (!ready) return <div className="app-loading" role="status" aria-label="正在加载控制台"><Spin size="large" /></div>
  if (!profile) return null
  const navigation = <>
    <Link className="brand" to="/overview" aria-label="Narrato 控制台首页"><span className="brand-mark">N</span><span className="brand-word"><b>NARRATO</b><i>CONTROL CENTER</i></span></Link>
    <div className="sider-workspace"><span>管理工作区</span><em>ADMIN</em></div>
    <nav aria-label="主导航"><Menu theme="dark" mode="inline" selectedKeys={[location.pathname]} items={items} /></nav>
    <div className="sider-foot">NARRATO API · v1</div>
  </>
  const signOutAndLeave = () => signOut().then(() => navigate('/login'))
  return <Layout className={`control-shell ${isMobile ? 'control-shell--mobile' : ''}`}>
    {!isMobile && <Layout.Sider theme="dark" collapsible collapsed={collapsed} trigger={null} width={240} collapsedWidth={72} className="control-sider">{navigation}</Layout.Sider>}
    {isMobile && <Drawer className="mobile-navigation" title={null} placement="left" width={288} open={mobileOpen} onClose={() => setMobileOpen(false)} styles={{ body: { padding: 0 } }}>{navigation}</Drawer>}
    <Layout className="control-main"><Layout.Header className="control-header">
      <div className="header-start">
        <Tooltip title={isMobile ? '打开导航' : collapsed ? '展开导航' : '收起导航'}><Button type="text" className="collapse-button" aria-label={isMobile ? '打开导航' : collapsed ? '展开导航' : '收起导航'} icon={isMobile ? <MenuOutlined /> : collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />} onClick={() => isMobile ? setMobileOpen(true) : setManualCollapsed((value) => !value)} /></Tooltip>
        <div className="header-context"><Breadcrumb items={[{ title: '控制台' }, { title: currentName }]} /><strong>{currentName}</strong></div>
      </div>
      <div className="header-actions"><Tooltip title="通知"><Button type="text" aria-label="通知" icon={<BellOutlined />} /></Tooltip><span className="header-divider" /><Dropdown trigger={['click']} menu={{ items: [{ key: 'profile', icon: <SafetyCertificateOutlined />, label: `角色：${profile.roles.join('、') || '管理员'}`, disabled: true }, { type: 'divider' }, { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: signOutAndLeave }] }}><button className="operator" type="button" aria-label="打开管理员菜单"><Avatar size={30}>{profile.username.slice(0, 1).toUpperCase()}</Avatar><span><b>{profile.display_name || profile.username}</b><small>{profile.roles[0] || '管理员'}</small></span></button></Dropdown></div>
    </Layout.Header><Layout.Content className="control-content"><Outlet /></Layout.Content></Layout>
  </Layout>
}
