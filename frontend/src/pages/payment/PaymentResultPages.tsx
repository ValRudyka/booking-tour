import { useEffect, useState } from 'react'
import type { OrderDetailWithPrice } from '../../api/types'
import { useTranslation } from 'react-i18next'
import { Navigate, useNavigate, useSearchParams } from 'react-router'
import { Button } from 'antd'
import { useOrder } from '../../api/payments'
import { BackToCatalogButton } from '../../components/BackToCatalogButton'
import { paymentOutcome } from '../../features/payment/orderOutcome'
import { parseOrderId, POLLING, successPath } from '../../features/payment/paymentPaths'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { formatKyivDateTime } from '../../utils/format'
import {
  CheckingResult, MyOrdersButton, OrderNotFound, OrderQueryState, PageResult, RebookButton,
} from './paymentShared'

/**
 * /payment/success?order_id=… — Stripe's success_url. Coming back here does NOT mean the money
 * arrived: only the signed webhook marks the order paid, maybe a few seconds later. So the page
 * reads the order until it is paid (or refunded as a late payment), and after the time limit
 * says the payment is being processed, never that it failed (the money was most likely taken).
 */
export function PaymentSuccessPage() {
  const { t } = useTranslation()
  const orderId = parseOrderId(useSearchParams()[0].get('order_id'))
  const [timedOut, setTimedOut] = useState(false)
  // Polling stops once the outcome is final (paid or refunded cannot change back) or time is up.
  const order = useOrder(orderId, (query) => (timedOut || isFinal(query.state.data) ? false : POLLING.intervalMs))
  const outcome = order.data ? paymentOutcome(order.data) : null
  // The tab title follows what the page says (not «Перевіряємо…» after the money arrived).
  useDocumentTitle(outcome === 'paid' ? t('payment.success.paidTitle')
    : outcome === 'late_refund' ? t('payment.states.lateTitle')
      : timedOut ? t('payment.success.slowTitle') : t('payment.success.checkingTitle'))

  useEffect(() => {
    const timer = setTimeout(() => setTimedOut(true), POLLING.timeoutMs)
    return () => clearTimeout(timer)
  }, [])

  if (orderId === null) return <OrderNotFound />
  if (order.error && !order.data) return <OrderQueryState error={order.error} onRetry={() => void order.refetch()} />
  if (!order.data) return <CheckingResult />
  if (outcome === 'paid') {
    return <PageResult status="success" title={t('payment.success.paidTitle')}
      text={t('payment.success.paidText', { number: order.data.number })}
      extra={[<MyOrdersButton key="orders" primary />, <BackToCatalogButtonPlain key="catalog" />]} />
  }
  if (outcome === 'late_refund') {
    return <PageResult status="warning" title={t('payment.states.lateTitle')} text={t('payment.states.lateText')}
      extra={[<RebookButton key="rebook" tourId={order.data.tour_id} />, <MyOrdersButton key="orders" />]} />
  }
  if (timedOut) {
    return <PageResult status="info" title={t('payment.success.slowTitle')} text={t('payment.success.slowText')}
      extra={<MyOrdersButton primary />} />
  }
  return <CheckingResult />
}

function isFinal(order: OrderDetailWithPrice | undefined): boolean {
  const outcome = order ? paymentOutcome(order) : null
  return outcome === 'paid' || outcome === 'late_refund'
}

function BackToCatalogButtonPlain() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  return <Button onClick={() => navigate('/tours')}>{t('app.toCatalog')}</Button>
}

/** /payment/cancel?order_id=… — Stripe's cancel_url: the client left the payment page. */
export function PaymentCancelPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  useDocumentTitle(t('payment.cancel.title'))
  const orderId = parseOrderId(useSearchParams()[0].get('order_id'))
  const order = useOrder(orderId)

  if (orderId === null) return <OrderNotFound />
  if (!order.isSuccess) return <OrderQueryState error={order.error} onRetry={() => void order.refetch()} />
  const outcome = paymentOutcome(order.data)
  // Paid after all (e.g. the client paid in another tab): the success page says so.
  if (outcome === 'paid' || outcome === 'late_refund') return <Navigate to={successPath(order.data.id)} replace />
  const payable = outcome === 'payable'
  return (
    <PageResult status="warning" title={t('payment.cancel.title')}
      text={payable ? t('payment.cancel.payableText', {
        number: order.data.number, time: formatKyivDateTime(order.data.hold_expires_at ?? ''),
      }) : t('payment.cancel.notPayableText')}
      extra={payable
        ? [<Button key="retry" type="primary" onClick={() => navigate(`/orders/${order.data.id}/pay`)}>{t('payment.cancel.retry')}</Button>,
          <MyOrdersButton key="orders" />]
        : [<MyOrdersButton key="orders" primary />, <BackToCatalogButton key="catalog" />]} />
  )
}
