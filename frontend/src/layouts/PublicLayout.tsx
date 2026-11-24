import { MailOutlined, MenuOutlined, PhoneOutlined } from '@ant-design/icons'
import { Button, Drawer, Flex, Grid, Layout, Menu, Space, Typography } from 'antd'
import type { MenuProps } from 'antd'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, Outlet, useLocation, useNavigate } from 'react-router'
import { AppLink } from '../components/AppLink'
import { CONTACT_EMAIL, CONTACT_PHONE, SITE_NAME } from '../site'
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

  const items: MenuProps['items'] = [
    { key: '/tours', label: <Link to="/tours">{t('nav.tours')}</Link> },
    { key: '/about', label: <Link to="/about">{t('nav.about')}</Link> },
  ]
  const selected = items.map((item) => String(item?.key)).filter((key) => pathname.startsWith(key))

  const go = (path: string) => {
    setMenuOpen(false)
    navigate(path)
  }
  const authButtons = (
    <>
      <Button onClick={() => go('/login')}>{t('nav.login')}</Button>
      <Button type="primary" onClick={() => go('/register')}>{t('nav.register')}</Button>
    </>
  )

  return (
    <Layout className="public-layout">
      <a className="skip-link" href="#main">{t('app.skipToContent')}</a>
      <Header className="public-header">
        <Flex align="center" gap={16} className="public-container">
          <Link to="/tours" className="site-name">{SITE_NAME}</Link>
          {isDesktop ? (
            <>
              <nav aria-label={t('nav.mainMenu')} className="public-nav">
                <Menu mode="horizontal" items={items} selectedKeys={selected} disabledOverflow />
              </nav>
              <Space>{authButtons}</Space>
            </>
          ) : (
            <Button className="menu-button" icon={<MenuOutlined aria-hidden />} aria-label={t('nav.menu')}
              aria-expanded={menuOpen} onClick={() => setMenuOpen(true)} />
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
          <Flex vertical gap={8} className="drawer-auth">{authButtons}</Flex>
        </Drawer>
      )}

      <Content>
        <main id="main" tabIndex={-1} className="public-container public-main">
          <Outlet />
        </main>
      </Content>

      <Footer className="public-footer">
        <Flex wrap gap={24} justify="space-between" className="public-container">
          <Space orientation="vertical" size={4}>
            <Typography.Text strong>{t('footer.contacts')}</Typography.Text>
            <Typography.Text>
              <PhoneOutlined aria-hidden /> {t('footer.phone')}:{' '}
              <a href={`tel:${CONTACT_PHONE.replace(/\s/g, '')}`}>{CONTACT_PHONE}</a>
            </Typography.Text>
            <Typography.Text>
              <MailOutlined aria-hidden /> {t('footer.email')}:{' '}
              <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>
            </Typography.Text>
          </Space>
          <Space orientation="vertical" size={4}>
            <AppLink to="/terms">{t('footer.terms')}</AppLink>
            <AppLink to="/privacy">{t('footer.privacy')}</AppLink>
            <Typography.Text type="secondary">
              {t('footer.copyright', { year: YEAR, site: SITE_NAME })}
            </Typography.Text>
          </Space>
        </Flex>
      </Footer>
    </Layout>
  )
}
