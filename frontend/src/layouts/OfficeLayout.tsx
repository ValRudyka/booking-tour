import {
  AuditOutlined, CommentOutlined, CompassOutlined, DatabaseOutlined, GiftOutlined, HomeOutlined, LogoutOutlined,
  MenuOutlined, RollbackOutlined, SettingOutlined, SolutionOutlined, TeamOutlined, TransactionOutlined,
} from '@ant-design/icons'
import { Button, Drawer, Flex, Grid, Layout, Menu, Space, Typography } from 'antd'
import type { MenuProps } from 'antd'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, Outlet, useLocation, useNavigate } from 'react-router'
import { officeKeys } from '../api/office'
import { NotificationBell } from '../components/NotificationBell'
import { roleLabel } from '../constants/orderLabels'
import { shortName } from '../features/auth/authContext'
import { useAuth } from '../features/auth/useAuth'
import { officeMenu, officeOrderPath, officePath, type OfficeSectionKey } from '../features/office/menu'
import { SITE_NAME } from '../site'
import './OfficeLayout.css'

const { Header, Sider, Content } = Layout

const ICONS: Record<OfficeSectionKey, ReactNode> = {
  orders: <SolutionOutlined aria-hidden />,
  tours: <CompassOutlined aria-hidden />,
  reviews: <CommentOutlined aria-hidden />,
  promoCodes: <GiftOutlined aria-hidden />,
  transactions: <TransactionOutlined aria-hidden />,
  refunds: <RollbackOutlined aria-hidden />,
  users: <TeamOutlined aria-hidden />,
  references: <DatabaseOutlined aria-hidden />,
  settings: <SettingOutlined aria-hidden />,
  audit: <AuditOutlined aria-hidden />,
}
const OFFICE_LISTS = [officeKeys.orders] as const

/**
 * The back office (spec 09 §1): plain antd Layout + Sider + Menu (the same pattern as the
 * cabinet's CabinetLayout), a Drawer under 768 px. The menu comes from the user's role
 * (features/office/menu.ts); RequireAuth around this layout keeps clients out, and each page has
 * its own role check. Header: site name, «Робочий кабінет», the notification bell (the same
 * component as the client's), «На сайт», the user's name and role, «Вийти».
 */
export function OfficeLayout() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const { user, logout } = useAuth()
  const isDesktop = Boolean(Grid.useBreakpoint().md)
  const [open, setOpen] = useState(false)
  if (!user) return null                      // RequireAuth renders this layout for staff only

  const sections = officeMenu(user.role)
  const items: MenuProps['items'] = sections.map((section) => ({
    key: officePath(section), icon: ICONS[section.key], label: t(`office.section.${section.key}`),
  }))
  const selected = sections.map(officePath).filter((path) => pathname === path || pathname.startsWith(`${path}/`))
  const menu = (
    <nav aria-label={t('office.sections')}>
      <Menu mode="inline" items={items} selectedKeys={selected} className="office-menu"
        onClick={({ key }) => {
          setOpen(false)
          navigate(key)
        }} />
    </nav>
  )
  const role = roleLabel(t, user.role)

  return (
    <Layout className="office-layout">
      <a className="skip-link" href="#main">{t('app.skipToContent')}</a>
      <Header className="office-header">
        <Flex align="center" gap={12} className="office-header-row">
          {!isDesktop && (
            <Button icon={<MenuOutlined aria-hidden />} aria-label={t('office.menuButton')} aria-expanded={open}
              onClick={() => setOpen(true)} />
          )}
          <Link to="/" className="site-name office-site-name">{SITE_NAME}</Link>
          <Typography.Text strong className="office-title">{t('office.title')}</Typography.Text>
          <Space size={8} className="office-header-actions">
            <NotificationBell orderPath={(id) => officeOrderPath(user.role, id)} refreshKeys={OFFICE_LISTS} />
            {isDesktop && (
              <Button icon={<HomeOutlined aria-hidden />} onClick={() => navigate('/')}>{t('office.toSite')}</Button>
            )}
            <Typography.Text className="office-user" data-testid="office-user">
              {t('office.userLabel', { name: shortName(user), role })}
            </Typography.Text>
            <Button icon={<LogoutOutlined aria-hidden />} onClick={logout}
              aria-label={isDesktop ? undefined : t('office.logout')}>
              {isDesktop ? t('office.logout') : null}
            </Button>
          </Space>
        </Flex>
      </Header>
      <Layout className="office-body">
        {isDesktop ? (
          <Sider width={232} theme="light" className="office-sider">{menu}</Sider>
        ) : (
          <Drawer title={t('office.menuTitle')} placement="left" size={260} open={open}
            onClose={() => setOpen(false)}>
            {menu}
            <Button block icon={<HomeOutlined aria-hidden />} className="office-drawer-site"
              onClick={() => navigate('/')}>
              {t('office.toSite')}
            </Button>
          </Drawer>
        )}
        <Content className="office-content">
          <main id="main" tabIndex={-1} className="office-main">
            <Outlet />
          </main>
        </Content>
      </Layout>
    </Layout>
  )
}
