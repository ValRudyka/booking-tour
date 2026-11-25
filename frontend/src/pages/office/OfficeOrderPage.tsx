import { ArrowLeftOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Col, Descriptions, Flex, Result, Row, Skeleton, Space, Table, Timeline, Typography } from 'antd'
import type { DescriptionsProps, TableColumnsType } from 'antd'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router'
import { ApiError } from '../../api/client'
import { useOfficeOrder } from '../../api/office'
import type { ManagerOrder, StaffPayment, Tourist } from '../../api/types'
import { ApiErrorState } from '../../components/ApiErrorState'
import { StatusTag } from '../../components/StatusTag'
import { cancelReasonLabel, paymentMethodLabel } from '../../constants/orderLabels'
import { useOfficeAction } from '../../features/office/useOfficeAction'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { mealLabel } from '../../i18n/labels'
import { formatDate, formatKyivDateTime, formatMoney } from '../../utils/format'
import { OfficeForbidden } from './OfficeHome'
import { CommentCard, OrderActionsPanel } from './OrderActionsPanel'
import { OrderDocumentsCard } from './OrderDocumentsCard'
import '../../layouts/OfficeLayout.css'

/** /office/orders/:id — the manager's processing of one order (spec 09 §3, form 4.6.2.2). */
export function OfficeOrderPage() {
  const { id } = useParams()
  const orderId = id && /^\d{1,9}$/.test(id) ? Number(id) : null
  return orderId === null ? <OrderNotFound /> : <OrderView id={orderId} />
}

function OrderNotFound() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  useDocumentTitle(t('office.order.notFound'))
  return (
    <Result status="404" title={<h1 className="result-title">{t('office.order.notFound')}</h1>}
      subTitle={t('office.order.invalidId')}
      extra={<Button onClick={() => navigate('/office/orders')}>{t('office.order.back')}</Button>} />
  )
}

function OrderView({ id }: { id: number }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const query = useOfficeOrder(id)
  const action = useOfficeAction(id)
  const order = query.data
  useDocumentTitle(order ? t('office.order.title', { number: order.number }) : t('office.queue.title'))

  if (!order) {
    if (query.error instanceof ApiError && query.error.status === 404) return <OrderNotFound />
    if (query.error instanceof ApiError && query.error.status === 403) return <OfficeForbidden />
    if (query.isError) {
      return <ApiErrorState error={query.error} onRetry={() => void query.refetch()} title={t('office.order.loadFailed')} />
    }
    return <Skeleton active={false} paragraph={{ rows: 10 }} />
  }

  return (
    <Flex vertical gap={16}>
      <div>
        <Button type="link" icon={<ArrowLeftOutlined aria-hidden />} className="office-back"
          onClick={() => navigate('/office/orders')}>
          {t('office.order.back')}
        </Button>
      </div>
      <Flex wrap align="center" gap={12}>
        <h1 className="office-page-title">{t('office.order.title', { number: order.number })}</h1>
        <StatusTag kind="order" status={order.status} />
        <StatusTag kind="payment" status={order.payment_status} />
        <Typography.Text data-testid="responsible">
          {order.manager_name ? t('office.order.responsible', { name: order.manager_name }) : t('office.order.noResponsible')}
        </Typography.Text>
      </Flex>

      {/* The client's cancellation request: an informational text, the actions still come from the API. */}
      {order.status === 'cancel_requested' && (
        <Alert type="warning" showIcon role="status" title={t('office.order.cancelRequest.title')}
          description={(
            <Space orientation="vertical" size={4}>
              {order.cancel_reason_code && (
                <span>{t('office.order.cancelRequest.reason', { reason: cancelReasonLabel(t, order.cancel_reason_code) })}</span>
              )}
              {order.cancel_reason && (
                <span className="office-pre">{t('office.order.cancelRequest.details', { text: order.cancel_reason })}</span>
              )}
              <span>{t('office.order.cancelRequest.note')}</span>
            </Space>
          )} />
      )}

      <Row gutter={[16, 16]}>
        {/* Under 1200 px the actions come first, above the long order data. */}
        <Col xs={{ span: 24, order: 2 }} xl={{ span: 16, order: 1 }}>
          <Flex vertical gap={16}>
            <OrderDetails order={order} />
            <TouristsCard tourists={order.tourists} />
            <OrderDocumentsCard order={order} />
            <PaymentsCard payments={order.payments} />
            <HistoryCard order={order} />
          </Flex>
        </Col>
        <Col xs={{ span: 24, order: 1 }} xl={{ span: 8, order: 2 }}>
          <Flex vertical gap={16} className="office-side">
            <OrderActionsPanel order={order} action={action} />
            <CommentCard key={order.internal_comment ?? ''} order={order} />
          </Flex>
        </Col>
      </Row>
    </Flex>
  )
}

function OrderDetails({ order }: { order: ManagerOrder }) {
  const { t } = useTranslation()
  const none = t('office.order.none')
  const money = (value: string) => t('office.money', { amount: formatMoney(value) })
  const items: DescriptionsProps['items'] = [
    { key: 'client', label: t('office.order.client'), children: `${order.client.last_name} ${order.client.first_name}` },
    { key: 'phone', label: t('office.order.phone'), children: <a href={`tel:${order.client.phone}`}>{order.client.phone}</a> },
    { key: 'email', label: t('office.order.email'), children: <a href={`mailto:${order.client.email}`}>{order.client.email}</a> },
    { key: 'tour', label: t('office.order.tour'), children: order.tour_title_uk },
    { key: 'hotel', label: t('office.order.hotel'), children: order.hotel_name },
    { key: 'place', label: t('office.order.place'), children: `${order.country_name}, ${order.resort_name}` },
    { key: 'departure', label: t('office.order.departure'), children: order.departure_city_name ?? none },
    { key: 'transport', label: t('office.order.transport'), children: t(`transport.${order.transport_type}`) },
    { key: 'meal', label: t('office.order.meal'), children: order.meal_plan ? mealLabel(t, order.meal_plan) : t('office.order.noMeal') },
    { key: 'dates', label: t('office.order.dates'), children: `${formatDate(order.start_date)} – ${formatDate(order.end_date)}` },
    {
      key: 'tourists', label: t('office.order.tourists'),
      children: t('office.order.touristsValue', { adults: order.adults, children: order.children }),
    },
    { key: 'insurance', label: t('office.order.insurance'), children: order.insurance_name ?? none },
    { key: 'transfer', label: t('office.order.transfer'), children: order.transfer_name ?? none },
    { key: 'promo', label: t('office.order.promo'), children: order.promo_code ?? none },
    { key: 'discount', label: t('office.order.discount'), children: money(order.discount_uah) },
    { key: 'total', label: t('office.order.total'), children: <strong data-testid="order-total">{money(order.total_uah)}</strong> },
    { key: 'paymentStatus', label: t('office.order.paymentStatus'), children: <StatusTag kind="payment" status={order.payment_status} /> },
    { key: 'pnr', label: t('office.order.pnr'), children: order.pnr ?? none },
    {
      key: 'deadline', label: t('office.order.deadline'),
      children: order.operator_deadline ? formatDate(order.operator_deadline) : none,
    },
    { key: 'created', label: t('office.order.created'), children: formatKyivDateTime(order.created_at) },
    { key: 'wishes', label: t('office.order.wishes'), span: 'filled', children: <span className="office-pre">{order.wishes ?? none}</span> },
    ...(order.reject_reason ? [{
      key: 'reject', label: t('office.order.rejectReason'), span: 'filled' as const,
      children: <span className="office-pre">{order.reject_reason}</span>,
    }] : []),
  ]
  return (
    <Card title={<h2 className="office-card-title">{t('office.order.details')}</h2>}>
      <Descriptions bordered size="small" column={{ xs: 1, md: 2 }} items={items} />
    </Card>
  )
}

/** Full passport data: the manager needs it for the booking (spec 09 §3). It is only rendered,
 * never logged or stored outside the in-memory query cache. */
function TouristsCard({ tourists }: { tourists: Tourist[] }) {
  const { t } = useTranslation()
  const columns: TableColumnsType<Tourist> = [
    { title: t('office.order.tourist.index'), key: 'index', width: 56, render: (_, __, index) => index + 1 },
    { title: t('office.order.tourist.lastName'), dataIndex: 'last_name_lat' },
    { title: t('office.order.tourist.firstName'), dataIndex: 'first_name_lat' },
    { title: t('office.order.tourist.birthDate'), dataIndex: 'birth_date', render: (value: string) => formatDate(value) },
    { title: t('office.order.tourist.passport'), dataIndex: 'passport_number' },
    { title: t('office.order.tourist.expiry'), dataIndex: 'passport_expiry', render: (value: string) => formatDate(value) },
  ]
  return (
    <Card title={<h2 className="office-card-title">{t('office.order.touristsTitle')}</h2>}>
      <Typography.Paragraph type="secondary">{t('office.order.touristsNote')}</Typography.Paragraph>
      <Table<Tourist> rowKey="id" size="small" columns={columns} dataSource={tourists} pagination={false} scroll={{ x: 640 }} />
    </Card>
  )
}

function PaymentsCard({ payments }: { payments: StaffPayment[] }) {
  const { t } = useTranslation()
  const columns: TableColumnsType<StaffPayment> = [
    { title: t('office.order.payment.type'), dataIndex: 'type', render: (value: StaffPayment['type']) => t(`paymentType.${value}`) },
    { title: t('office.order.payment.method'), dataIndex: 'method', render: (value: StaffPayment['method']) => paymentMethodLabel(t, value) },
    { title: t('office.order.payment.status'), dataIndex: 'status', render: (value: StaffPayment['status']) => <StatusTag kind="transaction" status={value} /> },
    {
      title: t('office.order.payment.amount'), dataIndex: 'amount_uah', align: 'right',
      render: (value: string) => t('office.money', { amount: formatMoney(value) }),
    },
    {
      title: t('office.order.payment.date'), key: 'date',
      render: (_, row) => formatKyivDateTime(row.received_at ?? row.created_at),
    },
  ]
  return (
    <Card title={<h2 className="office-card-title">{t('office.order.paymentsTitle')}</h2>}>
      <Table<StaffPayment> rowKey="id" size="small" columns={columns} dataSource={payments} pagination={false}
        scroll={{ x: 560 }} locale={{ emptyText: t('office.order.noPayments') }} />
    </Card>
  )
}

function HistoryCard({ order }: { order: ManagerOrder }) {
  const { t } = useTranslation()
  return (
    <Card title={<h2 className="office-card-title">{t('office.order.historyTitle')}</h2>}>
      <Timeline items={order.history.map((entry, index) => ({
        key: index,
        content: (
          <>
            <Flex gap={8} wrap align="center">
              <StatusTag kind="order" status={entry.new_status} />
              <Typography.Text>{formatKyivDateTime(entry.changed_at)}</Typography.Text>
              <Typography.Text type="secondary">
                {entry.changed_by === null ? t('office.order.system') : entry.changed_by_name ?? t('office.order.none')}
              </Typography.Text>
            </Flex>
            {entry.comment && <Typography.Paragraph className="office-pre office-history-comment">{entry.comment}</Typography.Paragraph>}
          </>
        ),
      }))} />
    </Card>
  )
}
