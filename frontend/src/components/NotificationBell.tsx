import { BellOutlined } from '@ant-design/icons'
import { useQueryClient } from '@tanstack/react-query'
import { Alert, Badge, Button, Empty, Flex, Popover, Typography } from 'antd'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import {
  markAllNotificationsRead, markNotificationRead, notificationKeys, orderKeys, useNotifications,
} from '../api/cabinet'
import type { AppNotification } from '../api/types'
import { formatKyivDateTime } from '../utils/format'
import '../pages/cabinet/CabinetPages.css'

/**
 * In-app notifications (spec 06, §5; backend /api/me/notifications): a bell with the unread count,
 * a Popover with the latest ones. Read on page load and every minute (no WebSocket). Opening one
 * marks it read and goes to its order. A new notification about an order also refreshes that
 * order's data, so an open order page shows the new status.
 */
export function NotificationBell() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const notifications = useNotifications(true)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const newest = useRef<number | null>(null)

  const items = notifications.data?.items ?? []
  const unread = notifications.data?.unread ?? 0

  useEffect(() => {
    if (!notifications.data) return
    const seen = newest.current
    const fresh = seen === null ? [] : notifications.data.items.filter((n) => n.id > seen)
    newest.current = Math.max(seen ?? 0, ...notifications.data.items.map((n) => n.id))
    const orders = new Set(fresh.map((n) => n.order_id).filter((id): id is number => id !== null))
    for (const id of orders) void queryClient.invalidateQueries({ queryKey: ['order', id] })
    if (orders.size > 0) void queryClient.invalidateQueries({ queryKey: orderKeys.list })
  }, [notifications.data, queryClient])

  const refresh = () => queryClient.invalidateQueries({ queryKey: notificationKeys.all })

  const openOne = async (note: AppNotification) => {
    setOpen(false)
    if (!note.is_read) {
      try {
        await markNotificationRead(note.id)
      } finally {
        void refresh()
      }
    }
    if (note.order_id !== null) navigate(`/cabinet/orders/${note.order_id}`)
  }

  const readAll = async () => {
    if (busy) return
    setBusy(true)
    try {
      await markAllNotificationsRead()
    } finally {
      setBusy(false)
      void refresh()
    }
  }

  const content = (
    <div className="notification-list">
      {notifications.isError && !notifications.data ? (
        <Alert type="error" showIcon title={t('notifications.error')} />
      ) : items.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('notifications.empty')} />
      ) : (
        <ul className="notification-items">
          {items.map((note) => (
            <li key={note.id}>
              <button type="button" onClick={() => void openOne(note)}
                className={`notification-item${note.is_read ? '' : ' notification-item-unread'}`}>
                <Flex justify="space-between" gap={8}>
                  <Typography.Text strong={!note.is_read}>{note.title}</Typography.Text>
                  {!note.is_read && <Badge color="#0E7490" text={<span className="visually-hidden">{t('notifications.unread')}</span>} />}
                </Flex>
                <Typography.Paragraph className="notification-body">{note.body}</Typography.Paragraph>
                <Typography.Text type="secondary">{formatKyivDateTime(note.created_at)}</Typography.Text>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )

  return (
    <Popover trigger="click" placement="bottomRight" open={open} onOpenChange={setOpen} content={content}
      title={(
        <Flex justify="space-between" align="center" gap={8}>
          <span>{t('notifications.title')}</span>
          {unread > 0 && (
            <Button size="small" type="link" onClick={() => void readAll()} disabled={busy}>
              {t('notifications.markAll')}
            </Button>
          )}
        </Flex>
      )}>
      <Badge count={unread} size="small" overflowCount={99}>
        <Button icon={<BellOutlined aria-hidden />} aria-expanded={open}
          aria-label={unread > 0 ? t('notifications.bellUnread', { count: unread }) : t('notifications.bell')} />
      </Badge>
    </Popover>
  )
}
