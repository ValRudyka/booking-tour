import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Col, Descriptions, Flex, Radio, Row, Typography } from 'antd'
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate, useLocation, useNavigate, useParams } from 'react-router'
import { ApiError } from '../../api/client'
import { payOrder, useOrder } from '../../api/payments'
import type { OrderDetailWithPrice, PaymentMethod, PayOut } from '../../api/types'
import { BankDetailsTable } from '../../components/BankDetails'
import { HelpGuide } from '../../components/HelpGuide'
import { isHoldExpired, serverText } from '../../features/booking/bookingErrors'
import type { PayPageState } from '../../features/booking/payHandOff'
import { browser, hasPendingTransfer, paymentOutcome } from '../../features/payment/orderOutcome'
import { parseOrderId, successPath } from '../../features/payment/paymentPaths'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { formatDate, formatMoney } from '../../utils/format'
import { PriceLines } from '../booking/BookingSummary'
import { orderPath } from '../cabinet/cabinetPaths'
import { useHoldRemaining } from '../booking/holdClock'
import { HoldTimer } from '../booking/HoldTimer'
import { LOW_HOLD_MS } from '../booking/StepReview'
import '../booking/BookingPage.css'
import {
  CheckingResult, MyOrdersButton, OrderNotFound, OrderQueryState, PageResult, RebookButton,
} from './paymentShared'
import './PaymentPages.css'

const ZERO = /^0+(\.0+)?$/
/** «Оплата вже обробляється»: the client completed a Stripe session; wait for the webhook. */
const ALREADY_PROCESSING = 'Оплата вже обробляється'

/** /orders/:id/pay — choose card (Stripe Checkout) or bank transfer (spec 05, ТЗ 4.5.3 7.2). */
export function PayPage() {
  const { t } = useTranslation()
  const orderId = parseOrderId(useParams().id)
  const order = useOrder(orderId)
  useDocumentTitle(t('pages.orderPay'))

  if (orderId === null) return <OrderNotFound />
  if (!order.isSuccess) return <OrderQueryState error={order.error} onRetry={() => void order.refetch()} />
  const data = order.data
  switch (paymentOutcome(data)) {
    case 'payable':
      return <PayForm key={data.id} order={data} />
    case 'checkout':
      return <Navigate to={`/booking/${data.tour_id}`} replace />   // the wizard resumes it
    case 'paid':
      return <PageResult status="success" title={t('payment.states.paidTitle')} text={t('payment.states.paidText')}
        extra={<MyOrdersButton primary />} />
    case 'late_refund':
      return <PageResult status="warning" title={t('payment.states.lateTitle')} text={t('payment.states.lateText')}
        extra={[<RebookButton key="rebook" tourId={data.tour_id} />, <MyOrdersButton key="orders" />]} />
    case 'expired':
      return <Expired order={data} />
    case 'cancelled':
      return <PageResult status="warning" title={t('payment.states.cancelledTitle')} text={t('payment.states.cancelledText')}
        extra={[<RebookButton key="rebook" tourId={data.tour_id} />, <MyOrdersButton key="orders" />]} />
    default:
      return <PageResult status="info" title={t('payment.states.closedTitle')} text={t('payment.states.closedText')}
        extra={<MyOrdersButton primary />} />
  }
}

function Expired({ order }: { order: OrderDetailWithPrice }) {
  const { t } = useTranslation()
  return <PageResult status="warning" title={t('payment.states.expiredTitle')} text={t('payment.states.expiredText')}
    extra={[<RebookButton key="rebook" tourId={order.tour_id} />, <MyOrdersButton key="orders" />]} />
}

function PayForm({ order }: { order: OrderDetailWithPrice }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()
  const priceChanged = (location.state as PayPageState | null)?.priceChanged
  const pendingTransfer = hasPendingTransfer(order)
  const [method, setMethod] = useState<PaymentMethod>(pendingTransfer ? 'bank_transfer' : 'card')
  const [expired, setExpired] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(false)   // one click, one request (the lock is taken synchronously)
  const partlyPaid = order.payment_status === 'partially_paid'   // never cancelled automatically
  const remaining = useHoldRemaining(partlyPaid ? null : order.hold_expires_at, () => setExpired(true))
  const zeroTotal = ZERO.test(order.total_uah)

  // A transfer chosen earlier: its details again (the backend returns the same pending transfer
  // and does not extend the hold a second time).
  const transferKey = ['order', order.id, 'transfer']
  const transfer = useQuery({
    queryKey: transferKey,
    queryFn: () => payOrder(order.id, 'bank_transfer'),
    enabled: pendingTransfer,
    staleTime: Infinity,
    retry: false,
  })
  // A promo code covered everything: «pay» marks the order paid at once, then the success page.
  const zero = useQuery({
    queryKey: ['order', order.id, 'zero'],
    queryFn: () => payOrder(order.id, 'card'),
    enabled: zeroTotal,
    staleTime: Infinity,
    retry: false,
  })

  const run = (action: () => Promise<void>) => {
    if (busyRef.current) return
    busyRef.current = true
    setBusy(true)
    setError(null)
    void (async () => {
      try {
        await action()
      } catch (failure) {
        if (isHoldExpired(failure)) {
          setExpired(true)
        } else if (failure instanceof ApiError && failure.status === 409 && failure.detail?.startsWith(ALREADY_PROCESSING)) {
          void navigate(successPath(order.id))   // paid on Stripe already: wait for the webhook there
        } else {
          setError(failure)
        }
      } finally {
        busyRef.current = false
        setBusy(false)
      }
    })()
  }

  const payByCard = () => run(async () => {
    const result = await payOrder(order.id, 'card')
    if (result.order_status === 'paid') void navigate(successPath(order.id))
    else if (result.checkout_url) browser.assign(result.checkout_url)
  })
  const getDetails = () => run(async () => {
    const result = await payOrder(order.id, 'bank_transfer')
    queryClient.setQueryData<PayOut>(transferKey, result)
    void queryClient.invalidateQueries({ queryKey: ['order', order.id], exact: true })   // the longer hold
  })

  if (expired) return <Expired order={order} />
  if (zeroTotal) {
    if (zero.data) return <Navigate to={successPath(order.id)} replace />
    if (zero.isError) {
      return <Alert type="error" showIcon title={t('payment.states.payFailed')} description={serverText(zero.error)} />
    }
    return <CheckingResult />
  }

  const bank = transfer.data?.bank_details ?? null
  const tourists = [t('checkout.summary.adults', { count: order.adults }),
    order.children > 0 ? t('checkout.summary.children', { count: order.children }) : null].filter(Boolean).join(', ')

  return (
    <div className="payment-page">
      <Typography.Title level={1} className="booking-title">{t('payment.title', { number: order.number })}</Typography.Title>
      {order.hold_expires_at && remaining !== null && remaining > 0 && (
        <HoldTimer expiresAt={order.hold_expires_at} remaining={remaining} />
      )}
      {remaining !== null && remaining > 0 && remaining < LOW_HOLD_MS && (
        <Alert type="warning" showIcon className="booking-block" title={t('payment.lowTime.title')}
          description={t('payment.lowTime.text')} />
      )}

      <Row gutter={[24, 24]}>
        <Col xs={24} md={14} lg={15}>
          {priceChanged && (
            // Before any pay button: the client never pays an amount they have not seen.
            <Alert type="warning" showIcon className="booking-block" title={t('payment.priceChanged.title')}
              description={t('payment.priceChanged.text', {
                shown: formatMoney(priceChanged.shown), frozen: formatMoney(order.total_uah),
              })} />
          )}
          <Card className="payment-methods">
            <h2 className="payment-subtitle" id="payment-method">{t('payment.method.label')}</h2>
            <Radio.Group value={method} onChange={(e) => setMethod(e.target.value as PaymentMethod)}
              aria-labelledby="payment-method" disabled={busy}>
              <Flex vertical gap={8}>
                <Radio value="card">{t('payment.method.card')}</Radio>
                <Radio value="bank_transfer">{t('payment.method.transfer')}</Radio>
              </Flex>
            </Radio.Group>

            {method === 'card' && (
              <div className="payment-method-body">
                <Typography.Paragraph type="secondary">{t('payment.method.cardHint')}</Typography.Paragraph>
                {pendingTransfer && <Alert type="info" showIcon className="booking-block" title={t('payment.cardAfterTransfer')} />}
                {import.meta.env.DEV && (
                  <Alert type="info" showIcon className="booking-block" title={t('payment.testCard')} data-testid="test-card" />
                )}
                <Button type="primary" size="large" loading={busy} onClick={payByCard}>
                  {t('payment.payCard', { amount: formatMoney(order.total_uah) })}
                </Button>
              </div>
            )}

            {method === 'bank_transfer' && (
              <div className="payment-method-body">
                <Typography.Paragraph type="secondary">{t('payment.method.transferHint')}</Typography.Paragraph>
                {bank ? <BankDetailsBlock details={bank} orderId={order.id} /> : (
                  <Button type="primary" size="large" loading={busy || transfer.isFetching} onClick={getDetails}>
                    {t('payment.getDetails')}
                  </Button>
                )}
              </div>
            )}

            {(error || transfer.isError) ? (
              <Alert type="error" showIcon className="booking-block payment-error" title={t('payment.states.payFailed')}
                description={serverText(error ?? transfer.error)} />
            ) : null}
          </Card>
        </Col>
        <Col xs={24} md={10} lg={9}>
          <Card className="payment-summary">
            <Descriptions column={1} size="small" items={[
              { key: 'tour', label: t('payment.summary.tour'), children: `${order.tour_title_uk} (${order.hotel_name})` },
              {
                key: 'dates', label: t('payment.summary.dates'),
                children: t('checkout.summary.dates', { from: formatDate(order.start_date), to: formatDate(order.end_date) }),
              },
              { key: 'tourists', label: t('payment.summary.tourists'), children: tourists },
            ]} />
            <div className="payment-price">
              {order.price ? <PriceLines price={order.price} /> : (
                <Typography.Text strong>
                  {t('payment.summary.total')}: {t('checkout.summary.amount', { amount: formatMoney(order.total_uah) })}
                </Typography.Text>
              )}
            </div>
          </Card>
        </Col>
      </Row>
      <HelpGuide content={{
        title: t('help.paymentTitle'),
        steps: (['1', '2', '3', '4', '5'] as const).map((n) => t(`help.paymentSteps.${n}`)),
      }} />
    </div>
  )
}

function BankDetailsBlock({ details, orderId }: { details: NonNullable<PayOut['bank_details']>; orderId: number }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  return (
    <div className="payment-bank">
      <h3 className="payment-subtitle">{t('payment.bank.title')}</h3>
      <BankDetailsTable details={details} />
      <Typography.Paragraph className="payment-bank-note">{t('payment.bank.note')}</Typography.Paragraph>
      <Typography.Paragraph>
        {t('payment.bank.again')}{' '}
        <Typography.Text copyable={{
          text: window.location.href,
          tooltips: [t('payment.bank.copy', { field: t('payment.bank.pageLink') }), t('payment.bank.copied')],
        }}>
          {t('payment.bank.pageLink')}
        </Typography.Text>
      </Typography.Paragraph>
      <Button type="primary" onClick={() => navigate(orderPath(orderId))}>{t('payment.bank.done')}</Button>
    </div>
  )
}
