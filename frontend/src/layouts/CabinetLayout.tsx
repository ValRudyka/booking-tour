import { HeartOutlined, HistoryOutlined, MenuOutlined, ShoppingOutlined, TeamOutlined, UserOutlined } from '@ant-design/icons'
import { Button, Drawer, Grid, Layout, Menu } from 'antd'
import type { MenuProps } from 'antd'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Outlet, useLocation, useNavigate } from 'react-router'
import './CabinetLayout.css'

const { Sider, Content } = Layout
const HISTORY = '/cabinet/orders?group=completed'

/**
 * The client's personal account (spec 06, §1): plain antd Layout + Menu inside PublicLayout, so
 * the header (with the notification bell) stays the same. Only sections with a backend API are
 * listed. «Історія подорожей» is the «Завершені» tab of the orders (spec 08 §4), so it is selected
 * instead of «Мої замовлення» while that tab is open.
 */
export function CabinetLayout() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { pathname, search } = useLocation()
  const isDesktop = Boolean(Grid.useBreakpoint().md)
  const [open, setOpen] = useState(false)

  const items: MenuProps['items'] = [
    { key: '/cabinet/orders', icon: <ShoppingOutlined aria-hidden />, label: t('cabinet.orders.title') },
    { key: HISTORY, icon: <HistoryOutlined aria-hidden />, label: t('cabinet.history.title') },
    { key: '/cabinet/favorites', icon: <HeartOutlined aria-hidden />, label: t('favorites.title') },
    { key: '/cabinet/tourists', icon: <TeamOutlined aria-hidden />, label: t('cabinet.tourists.title') },
    { key: '/cabinet/profile', icon: <UserOutlined aria-hidden />, label: t('nav.profile') },
  ]
  const history = pathname === '/cabinet/orders' && new URLSearchParams(search).get('group') === 'completed'
  const selected = history ? [HISTORY]
    : items.map((item) => String(item?.key)).filter((key) => key !== HISTORY && pathname.startsWith(key))
  const menu = (
    <nav aria-label={t('cabinet.sections')}>
      <Menu mode="inline" items={items} selectedKeys={selected} className="cabinet-menu"
        onClick={({ key }) => {
          setOpen(false)
          navigate(key)
        }} />
    </nav>
  )

  return (
    <Layout className="cabinet-layout">
      {isDesktop ? (
        <Sider width={220} theme="light" className="cabinet-sider">{menu}</Sider>
      ) : (
        <>
          <Button icon={<MenuOutlined aria-hidden />} aria-expanded={open} className="cabinet-menu-button"
            onClick={() => setOpen(true)}>
            {t('cabinet.sections')}
          </Button>
          <Drawer title={t('cabinet.menuTitle')} placement="left" size={260} open={open}
            onClose={() => setOpen(false)}>
            {menu}
          </Drawer>
        </>
      )}
      <Content className="cabinet-content">
        <Outlet />
      </Content>
    </Layout>
  )
}
