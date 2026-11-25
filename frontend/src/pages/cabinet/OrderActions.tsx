import { useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Flex, Typography } from 'antd'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { orderKeys } from '../../api/cabinet'
import { cancelOrder } from '../../api/orders'
import type { OrderDetail, OrderDetailWithPrice } from '../../api/types'
import { serverText } from '../../features/booking/bookingErrors'
import { CancelRequestDialog } from './CancelRequestDialog'
import { checkoutPath, has, payPath, reviewPath } from './cabinetPaths'

/**
 * The actions card (spec 06, §3). Every button comes from the API's `client_actions`, computed by
 * the same backend checks that accept or refuse the action, so nothing is decided by status here.
 */
export function OrderActions({ order }: { order: OrderDetailWithPrice }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [requestOpen, setRequestOpen] = useState(false)
  const refresh = useOrderRefresh(order.id)
  const buttons = [
    has(order, 'pay') && (
      <Button key="pay" type="primary" block onClick={() => navigate(payPath(order.id))}>{t('cabinet.order.pay')}</Button>
    ),
    has(order, 'continue_checkout') && (
      <Button key="continue" type="primary" block onClick={() => navigate(checkoutPath(order))}>
        {t('cabinet.order.continue')}
      </Button>
    ),
    has(order, 'review') && (
      <Button key="review" type="primary" block onClick={() => navigate(reviewPath(order.id))}>{t('cabinet.order.review')}</Button>
    ),
    has(order, 'view_review') && (
      <Button key="view-review" block onClick={() => navigate(reviewPath(order.id))}>{t('cabinet.order.viewReview')}</Button>
    ),
    has(order, 'cancel') && <CancelUnpaidButton key="cancel" order={order} onDone={refresh} />,
    has(order, 'cancel_request') && (
      <Button key="cancel-request" danger block onClick={() => setRequestOpen(true)}>{t('cabinet.order.cancelRequest')}</Button>
    ),
  ].filter(Boolean)

  return (
    <Card className="order-actions" title={<h2 className="cabinet-section-title">{t('cabinet.order.actions')}</h2>}>
      {buttons.length > 0
        ? <Flex vertical gap={8}>{buttons}</Flex>
        : <Typography.Text type="secondary">{t('cabinet.order.noActions')}</Typography.Text>}
      {has(order, 'cancel_request') && (
        <CancelRequestDialog order={order} open={requestOpen} onClose={() => setRequestOpen(false)}
          onDone={(updated) => {
            setRequestOpen(false)
            refresh(updated)
          }} />
      )}
    </Card>
  )
}

/** After a change: the answer (an order without the price) goes into the cache at once, then the
 * order (with its price) and the list are read again. */
function useOrderRefresh(orderId: number) {
  const queryClient = useQueryClient()
  return (updated: OrderDetail) => {
    queryClient.setQueryData<OrderDetailWithPrice>(['order', orderId], (old) => old && { ...old, ...updated })
    void queryClient.invalidateQueries({ queryKey: ['order', orderId] })
    void queryClient.invalidateQueries({ queryKey: orderKeys.list })
  }
}

/** An unpaid order is cancelled at once, without a request (ТЗ 4.5.5, step 1). */
function CancelUnpaidButton({ order, onDone }: { order: OrderDetailWithPrice; onDone: (o: OrderDetail) => void }) {
  const { t } = useTranslation()
  const { modal, message } = App.useApp()
  const [busy, setBusy] = useState(false)
  const confirm = () => {
    if (busy) return
    modal.confirm({
      title: t('cabinet.cancel.confirmTitle'),
      content: t('cabinet.cancel.confirmText'),
      okText: t('cabinet.cancel.confirm'),
      okButtonProps: { danger: true },
      cancelText: t('cabinet.cancel.keep'),
      onOk: async () => {
        setBusy(true)
        try {
          onDone(await cancelOrder(order.id))
          void message.success(t('cabinet.cancel.done'))
        } catch (error) {
          modal.error({ title: t('cabinet.cancel.confirmTitle'), content: serverText(error) })
        } finally {
          setBusy(false)
        }
      },
    })
  }
  return <Button danger block loading={busy} onClick={confirm}>{t('cabinet.order.cancel')}</Button>
}
