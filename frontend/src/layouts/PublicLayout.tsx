import { DesktopOutlined, DownOutlined, MailOutlined, MenuOutlined, PhoneOutlined, UserOutlined } from '@ant-design/icons'
import { Button, Drawer, Dropdown, Flex, Grid, Layout, Menu, Space, Typography } from 'antd'
import type { MenuProps } from 'antd'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, Outlet, useLocation, useNavigate } from 'react-router'
import { useSiteContacts } from '../api/site'
import { AppLink } from '../components/AppLink'
import { NotificationBell } from '../components/NotificationBell'
import { shortName } from '../features/auth/authContext'
import { OFFICE_HOME, STAFF_ROLES } from '../features/auth/redirect'
import { useAuth } from '../features/auth/useAuth'
import { SITE_NAME } from '../site'
import './PublicLayout.css'

const { Header, Content, Footer } = Layout
const YEAR = new Date().getFullYear() // footer copyright; read once, not on every render

/** Public pages: header with navigation, content up to 1200 px, footer (spec §3). */
export function PublicLayout() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const screens = Grid.useBreakpoint()
  const [menuOpen, setMenuOpen] = useState(false)
  const isDesktop = Boolean(screens.md)
  const { user, logout } = useAuth()
  const contacts = useSiteContacts()

  const items: MenuProps['items'] = [
    { key: '/tours', label: <Link to="/tours">{t('nav.tours')}</Link> },
    { key: '/about', label: <Link to="/about">{t('nav.about')}</Link> },
    { key: '/faq', label: <Link to="/faq">{t('nav.faq')}</Link> },
    { key: '/contacts', label: <Link to="/contacts">{t('nav.contacts')}</Link> },
  ]
  const selected = items.map((item) => String(item?.key)).filter((key) => pathname.startsWith(key))

  const go = (path: string) => {
    setMenuOpen(false)
    navigate(path)
  }
  // A signed-in user: the account pages (clients) or the back office (staff), and sign-out.
  const userItems = user ? [
    ...(STAFF_ROLES.includes(user.role)
      ? [{ key: '/office', label: t('nav.office') }]
      : [{ key: '/cabinet/orders', label: t('nav.myOrders') }, { key: '/cabinet/profile', label: t('nav.profile') }]),
    { type: 'divider' as const },
    { key: 'logout', label: t('nav.logout') },
  ] : []
  const onUserItem = (key: string) => {
    setMenuOpen(false)
    if (key === 'logout') logout()
    else navigate(key)
  }
  // In-app notifications (spec 06, §5): clients only for now; staff get them in the back office.
  const bell = user?.role === 'client' ? <NotificationBell /> : null
  // Staff get a visible way into the back office (spec 09), not only the item in the user menu.
  const officeButton = user && STAFF_ROLES.includes(user.role) ? (
    <Button type="primary" icon={<DesktopOutlined aria-hidden />} onClick={() => go(OFFICE_HOME)}>
      {t('nav.officeButton')}
    </Button>
  ) : null
  const authButtons = (
    <>
      <Button onClick={() => go('/login')}>{t('nav.login')}</Button>
      <Button type="primary" onClick={() => go('/register')}>{t('nav.register')}</Button>
    </>
  )
  const userMenu = user && (
    <Dropdown trigger={['click']} menu={{ items: userItems, onClick: ({ key }) => onUserItem(key) }}>
      <Button icon={<UserOutlined aria-hidden />} aria-label={t('nav.userMenu', { name: shortName(user) })}>
        {shortName(user)} <DownOutlined aria-hidden />
      </Button>
    </Dropdown>
  )

  return (
    <Layout className="public-layout">
      <a className="skip-link" href="#main">{t('app.skipToContent')}</a>
      <Header className="public-header">
        <Flex align="center" gap={16} className="public-container">
          <Link to="/" className="site-name">{SITE_NAME}</Link>
          {isDesktop ? (
            <>
              <nav aria-label={t('nav.mainMenu')} className="public-nav">
                <Menu mode="horizontal" items={items} selectedKeys={selected} disabledOverflow />
              </nav>
              {user ? <Space>{bell}{officeButton}{userMenu}</Space> : <Space>{authButtons}</Space>}
            </>
          ) : (
            <Space>
              {bell}
              <Button className="menu-button" icon={<MenuOutlined aria-hidden />} aria-label={t('nav.menu')}
                aria-expanded={menuOpen} onClick={() => setMenuOpen(true)} />
            </Space>
          )}
        </Flex>
      </Header>

      {!isDesktop && (
        <Drawer title={SITE_NAME} placement="right" size={280} open={menuOpen}
          onClose={() => setMenuOpen(false)}>
          <nav aria-label={t('nav.mainMenu')}>
            <Menu mode="vertical" items={items} selectedKeys={selected}
              onClick={() => setMenuOpen(false)} className="drawer-menu" />
          </nav>
          {user ? (
            <nav aria-label={t('nav.userMenu', { name: shortName(user) })} className="drawer-auth">
              <Typography.Text strong>{shortName(user)}</Typography.Text>
              <Menu mode="vertical" className="drawer-menu"
                items={userItems}
                onClick={({ key }) => onUserItem(key)} />
            </nav>
          ) : <Flex vertical gap={8} className="drawer-auth">{authButtons}</Flex>}
        </Drawer>
      )}

      <Content>
        <main id="main" tabIndex={-1} className="public-container public-main">
          <Outlet />
        </main>
      </Content>

      <Footer className="public-footer">
        <Flex wrap gap={24} justify="space-between" className="public-container">
          {/* Support contacts from the admin's settings; nothing is shown until they are set. */}
          <Space orientation="vertical" size={4}>
            {(contacts.data?.phone || contacts.data?.email) && (
              <Typography.Text strong>{t('footer.contacts')}</Typography.Text>
            )}
            {contacts.data?.phone && (
              <Typography.Text>
                <PhoneOutlined aria-hidden /> {t('footer.phone')}:{' '}
                <a href={`tel:${contacts.data.phone}`}>{contacts.data.phone}</a>
              </Typography.Text>
            )}
            {contacts.data?.email && (
              <Typography.Text>
                <MailOutlined aria-hidden /> {t('footer.email')}:{' '}
                <a href={`mailto:${contacts.data.email}`}>{contacts.data.email}</a>
              </Typography.Text>
            )}
          </Space>
          <nav aria-label={t('footer.info')}>
            <Space orientation="vertical" size={4}>
              <Typography.Text strong>{t('footer.info')}</Typography.Text>
              <AppLink to="/about">{t('nav.about')}</AppLink>
              <AppLink to="/contacts">{t('nav.contacts')}</AppLink>
              <AppLink to="/faq">{t('nav.faq')}</AppLink>
              <AppLink to="/terms">{t('footer.terms')}</AppLink>
              <AppLink to="/privacy">{t('footer.privacy')}</AppLink>
            </Space>
          </nav>
          <Space orientation="vertical" size={4}>
            <Typography.Text type="secondary">
              {t('footer.copyright', { year: YEAR, site: SITE_NAME })}
            </Typography.Text>
          </Space>
        </Flex>
      </Footer>
    </Layout>
  )
}
