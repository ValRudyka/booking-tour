import { ArrowLeftOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Col, Flex, Row, Space, Timeline, Typography } from 'antd'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router'
import { ApiError } from '../../api/client'
import { useOrder } from '../../api/payments'
import type { OrderDetailWithPrice } from '../../api/types'
import { BankDetailsTable } from '../../components/BankDetails'
import { StatusTag } from '../../components/StatusTag'
import { useAuth } from '../../features/auth/useAuth'
import { parseOrderId } from '../../features/payment/paymentPaths'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { mealLabel } from '../../i18n/labels'
import { formatDate, formatKyivDateTime, formatMoney, maskPassport } from '../../utils/format'
import { PriceLines } from '../booking/BookingSummary'
import { OrderQueryState } from '../payment/paymentShared'
import { ordersPath } from './cabinetPaths'
import { OrderActions } from './OrderActions'
import { OrderDocuments } from './OrderDocuments'
import { OrderMoney } from './OrderMoney'
import '../booking/BookingPage.css'
import './CabinetPages.css'

/** «Деталі замовлення» (spec 06, §3). Someone else's order is a 404 from the API, like a missing one. */
export function OrderDetailsPage() {
  const { t } = useTranslation()
  const orderId = parseOrderId(useParams().id)
  const order = useOrder(orderId)
  useDocumentTitle(order.data ? t('cabinet.order.title', { number: order.data.number }) : t('cabinet.orders.title'))

  if (orderId === null) return <OrderQueryState error={notFound} onRetry={() => undefined} />
  if (!order.data) return <OrderQueryState error={order.error} onRetry={() => void order.refetch()} />
  return <OrderDetails order={order.data} />
}

/** A malformed id gets the same 404 page as a missing order. */
const notFound = new ApiError('not_found', 404, '')

function OrderDetails({ order }: { order: OrderDetailWithPrice }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  return (
    <article aria-labelledby="order-title">
      <Button type="link" icon={<ArrowLeftOutlined aria-hidden />} className="order-back"
        onClick={() => navigate(ordersPath)}>
        {t('cabinet.order.backToList')}
      </Button>
      <Flex className="order-header" wrap gap={8} align="center">
        <h1 id="order-title" className="cabinet-title">{t('cabinet.order.title', { number: order.number })}</h1>
        <StatusTag kind="order" status={order.status} />
        {/* «Очікує оплати» twice would only repeat the order status; the money card has the rest. */}
        {order.payment_status !== 'awaiting' && <StatusTag kind="payment" status={order.payment_status} />}
        <Typography.Text type="secondary">
          {t('cabinet.order.created', { date: formatKyivDateTime(order.created_at) })}
        </Typography.Text>
      </Flex>

      <Row gutter={[24, 16]}>
        <Col xs={{ span: 24, order: 2 }} lg={{ span: 16, order: 1 }}>
          {order.reject_reason && order.status === 'rejected' && (
            <Alert className="order-section" type="error" showIcon
              title={t('cabinet.order.rejectReason', { reason: order.reject_reason })} />
          )}
          {order.pending_transfer && (
            <Card className="order-section" title={<h2 className="cabinet-section-title">{t('cabinet.order.transferTitle')}</h2>}>
              <Typography.Paragraph>{t('cabinet.order.transferText')}</Typography.Paragraph>
              <BankDetailsTable details={order.pending_transfer} />
            </Card>
          )}
          <TourSection order={order} />
          <TouristsSection order={order} />
          <PriceSection order={order} />
          <OrderDocuments order={order} />
          <OrderMoney order={order} />
          <HistorySection order={order} />
        </Col>
        <Col xs={{ span: 24, order: 1 }} lg={{ span: 8, order: 2 }}>
          <OrderActions order={order} />
        </Col>
      </Row>
    </article>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card className="order-section" title={<h2 className="cabinet-section-title">{title}</h2>}>
      {children}
    </Card>
  )
}

/** Tour facts as the API returns them with the order. /tours/:id is linked only while the tour is
 * for sale: a finished or archived tour's page is a 404 (CLAUDE.md). */
function TourSection({ order }: { order: OrderDetailWithPrice }) {
  const { t } = useTranslation()
  const departure = order.transport_type === 'none' || !order.departure_city_name
    ? t('cabinet.order.noTransport')
    : t('cabinet.order.transportFrom', { transport: t(`transport.${order.transport_type}`), city: order.departure_city_name })
  return (
    <Section title={t('cabinet.order.tourSection')}>
      <Typography.Text strong>
        {order.tour_for_sale
          ? <Link to={`/tours/${order.tour_id}`}>{order.tour_title_uk}</Link>
          : order.tour_title_uk}
      </Typography.Text>
      <dl className="order-facts">
        <dt>{t('cabinet.order.country')}</dt>
        <dd>{`${order.country_name}, ${order.resort_name}`}</dd>
        <dt>{t('cabinet.order.hotel')}</dt>
        <dd>{order.hotel_name}</dd>
        <dt>{t('cabinet.order.dates')}</dt>
        <dd>{t('checkout.summary.dates', { from: formatDate(order.start_date), to: formatDate(order.end_date) })}</dd>
        <dt>{t('cabinet.order.departure')}</dt>
        <dd>{departure}</dd>
        {order.meal_plan && (
          <><dt>{t('cabinet.order.meal')}</dt><dd>{mealLabel(t, order.meal_plan)}</dd></>
        )}
        {order.pnr && (
          <><dt>{t('cabinet.order.pnr')}</dt><dd>{order.pnr}</dd></>
        )}
      </dl>
      {!order.tour_for_sale && <Typography.Text type="secondary">{t('cabinet.order.tourNotForSale')}</Typography.Text>}
    </Section>
  )
}

/** Passports only partly visible (spec 06, §3), as on the booking review step. */
function TouristsSection({ order }: { order: OrderDetailWithPrice }) {
  const { t } = useTranslation()
  if (order.tourists.length === 0) return null
  return (
    <Section title={t('cabinet.order.touristsSection')}>
      <Space orientation="vertical" size={12} className="order-tourists">
        {order.tourists.map((tourist) => (
          <dl key={tourist.id} className="order-facts">
            <dt>{t('cabinet.order.touristName')}</dt>
            <dd>{`${tourist.last_name_lat} ${tourist.first_name_lat}`}</dd>
            <dt>{t('cabinet.order.birthDate')}</dt>
            <dd>{formatDate(tourist.birth_date)}</dd>
            <dt>{t('cabinet.order.passport')}</dt>
            <dd>{t('cabinet.order.passportValue', {
              number: maskPassport(tourist.passport_number), expiry: formatDate(tourist.passport_expiry),
            })}</dd>
          </dl>
        ))}
      </Space>
    </Section>
  )
}

/** The server's price breakdown (GET /orders/{id}); null when it cannot be rebuilt exactly, then
 * only the stored total. Amounts are strings from the API, only formatted. */
function PriceSection({ order }: { order: OrderDetailWithPrice }) {
  const { t } = useTranslation()
  return (
    <Section title={t('cabinet.order.priceSection')}>
      {order.price ? <PriceLines price={order.price} /> : (
        <>
          <Typography.Paragraph type="secondary">{t('cabinet.order.priceUnavailable')}</Typography.Paragraph>
          <Typography.Text strong>
            {t('cabinet.order.total')}: {t('checkout.summary.amount', { amount: formatMoney(order.total_uah) })}
          </Typography.Text>
        </>
      )}
      {order.wishes && (
        <dl className="order-facts">
          <dt>{t('cabinet.order.wishes')}</dt>
          <dd>{order.wishes}</dd>
        </dl>
      )}
    </Section>
  )
}

/** Every status change with its Kyiv date and time (the API stores UTC). */
function HistorySection({ order }: { order: OrderDetailWithPrice }) {
  const { t } = useTranslation()
  const { user } = useAuth()
  const who = (changedBy: number | null) => changedBy === null ? t('cabinet.order.system')
    : changedBy === user?.id ? t('cabinet.order.you') : null
  return (
    <Section title={t('cabinet.order.history')}>
      <Timeline className="order-timeline" items={order.history.map((entry, index) => ({
        key: index,
        content: (
          <>
            <Flex gap={8} wrap align="center">
              <StatusTag kind="order" status={entry.new_status} />
              <Typography.Text>{formatKyivDateTime(entry.changed_at)}</Typography.Text>
              {who(entry.changed_by) && <Typography.Text type="secondary">{who(entry.changed_by)}</Typography.Text>}
            </Flex>
            {entry.comment && <Typography.Text type="secondary">{entry.comment}</Typography.Text>}
          </>
        ),
      }))} />
    </Section>
  )
}
