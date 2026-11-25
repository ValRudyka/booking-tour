import { Button, Card, Empty, Flex, Grid, List, Pagination, Segmented, Skeleton, Space, Table, Typography } from 'antd'
import type { TableProps } from 'antd'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { ORDERS_PAGE_SIZE, useMyOrders } from '../../api/cabinet'
import type { OrderSummary } from '../../api/types'
import { ApiErrorState } from '../../components/ApiErrorState'
import { StatusTag } from '../../components/StatusTag'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { formatDate, formatKyivDate, formatMoney } from '../../utils/format'
import { checkoutPath, has, orderPath, payPath } from './cabinetPaths'
import { ORDER_GROUPS, readOrdersParams, toOrdersSearch, type OrdersParams } from './ordersParams'
import { ReviewState } from './ReviewState'
import './CabinetPages.css'

/** «Мої замовлення» (spec 06, §2): server-side tabs and pages, a table or cards under 768 px. */
export function OrdersPage() {
  const { t } = useTranslation()
  const title = t('cabinet.orders.title')
  useDocumentTitle(title)
  const [search, setSearch] = useSearchParams()
  const params = readOrdersParams(search)
  const orders = useMyOrders(params.group, params.page)
  // The table needs the width next to the cabinet menu; below 992 px the orders are cards.
  const isDesktop = Boolean(Grid.useBreakpoint().lg)

  const update = (next: Partial<OrdersParams>) => setSearch(toOrdersSearch({ ...params, ...next }))
  const data = orders.data
  const empty = data && data.total === 0

  return (
    <section aria-labelledby="orders-title">
      <h1 id="orders-title" className="cabinet-title">{title}</h1>
      <Segmented<OrdersParams['group']> className="orders-groups" aria-label={t('cabinet.orders.groupLabel')}
        value={params.group} onChange={(group) => update({ group, page: 1 })}
        options={ORDER_GROUPS.map((group) => ({ value: group, label: t(`cabinet.orders.groups.${group}`) }))} />

      {orders.isError && !data ? (
        <ApiErrorState error={orders.error} onRetry={() => void orders.refetch()} title={title} />
      ) : !data ? (
        <Skeleton active={false} paragraph={{ rows: 6 }} />
      ) : empty ? (
        <EmptyOrders group={params.group} onShowAll={() => update({ group: 'all', page: 1 })} />
      ) : (
        <>
          {isDesktop ? <OrdersTable orders={data.items} /> : <OrderCards orders={data.items} />}
          {data.total > ORDERS_PAGE_SIZE && (
            <Pagination className="orders-pagination" current={params.page} pageSize={ORDERS_PAGE_SIZE}
              total={data.total} showSizeChanger={false} onChange={(page) => update({ page })} />
          )}
        </>
      )}
    </section>
  )
}

function EmptyOrders({ group, onShowAll }: { group: OrdersParams['group']; onShowAll: () => void }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  // «Історія подорожей» (spec 08 §4) is the «Завершені» tab: its own empty text and the catalog.
  if (group === 'completed') {
    return (
      <Empty description={t('cabinet.history.empty')}>
        <Button type="primary" onClick={() => navigate('/tours')}>{t('app.toCatalog')}</Button>
      </Empty>
    )
  }
  if (group !== 'all') {
    return (
      <Empty description={t('cabinet.orders.emptyGroup')}>
        <Button onClick={onShowAll}>{t('cabinet.orders.showAll')}</Button>
      </Empty>
    )
  }
  return (
    <Empty description={
      <Space orientation="vertical" size={4}>
        <Typography.Text strong>{t('cabinet.orders.emptyTitle')}</Typography.Text>
        <Typography.Text type="secondary">{t('cabinet.orders.emptyText')}</Typography.Text>
      </Space>
    }>
      <Button type="primary" onClick={() => navigate('/tours')}>{t('app.toCatalog')}</Button>
    </Empty>
  )
}

/** «Туреччина, Анталія»: from the tour row, like the order page (no snapshot yet). */
const place = (order: OrderSummary) => `${order.country_name}, ${order.resort_name}`

function useTourists() {
  const { t } = useTranslation()
  return (order: OrderSummary) => [t('checkout.summary.adults', { count: order.adults }),
    order.children > 0 ? t('checkout.summary.children', { count: order.children }) : null].filter(Boolean).join(', ')
}

/** The buttons the API allows for this order (client_actions), plus «Деталі» (the order page
 * also has the trip documents) and the review state of a past trip. */
function RowActions({ order }: { order: OrderSummary }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  return (
    <Flex gap={8} wrap align="center">
      <ReviewState order={order} />
      {has(order, 'pay') && (
        <Button type="primary" size="small" onClick={() => navigate(payPath(order.id))}>{t('cabinet.orders.pay')}</Button>
      )}
      {has(order, 'continue_checkout') && (
        <Button type="primary" size="small" onClick={() => navigate(checkoutPath(order))}>
          {t('cabinet.orders.continue')}
        </Button>
      )}
      <Button size="small" aria-label={t('cabinet.orders.detailsOf', { number: order.number })}
        onClick={() => navigate(orderPath(order.id))}>
        {t('cabinet.orders.details')}
      </Button>
    </Flex>
  )
}

function OrdersTable({ orders }: { orders: OrderSummary[] }) {
  const { t } = useTranslation()
  const tourists = useTourists()
  const columns: TableProps<OrderSummary>['columns'] = [
    {
      key: 'number', title: t('cabinet.orders.number'),
      render: (_, order) => <Link to={orderPath(order.id)} className="orders-nowrap">{order.number}</Link>,
    },
    {
      key: 'tour', title: t('cabinet.orders.tour'), width: '30%',
      render: (_, order) => (   // the hotel is on the order page
        <>
          <div>{order.tour_title_uk}</div>
          <Typography.Text type="secondary">{place(order)}</Typography.Text>
        </>
      ),
    },
    {
      key: 'dates', title: t('cabinet.orders.dates'),
      render: (_, order) => (
        <>
          <span className="orders-nowrap">{formatDate(order.start_date)} –</span>{' '}
          <span className="orders-nowrap">{formatDate(order.end_date)}</span>
        </>
      ),
    },
    { key: 'tourists', title: t('cabinet.orders.tourists'), render: (_, order) => tourists(order) },
    {
      key: 'total', title: t('cabinet.orders.total'), align: 'right',
      render: (_, order) => <span className="orders-nowrap">{t('checkout.summary.amount', { amount: formatMoney(order.total_uah) })}</span>,
    },
    { key: 'status', title: t('cabinet.orders.status'), render: (_, order) => <StatusTag kind="order" status={order.status} /> },
    { key: 'created', title: t('cabinet.orders.created'), render: (_, order) => formatKyivDate(order.created_at) },
    { key: 'actions', title: t('cabinet.orders.actions'), render: (_, order) => <RowActions order={order} /> },
  ]
  return <Table<OrderSummary> rowKey="id" columns={columns} dataSource={orders} pagination={false}
    scroll={{ x: true }} />
}

function OrderCards({ orders }: { orders: OrderSummary[] }) {
  const { t } = useTranslation()
  const tourists = useTourists()
  return (
    <List dataSource={orders} rowKey="id" renderItem={(order) => (
      <List.Item>
        <Card className="order-card" size="small" title={<Link to={orderPath(order.id)}>{order.number}</Link>}
          extra={<StatusTag kind="order" status={order.status} />}>
          <Typography.Text strong>{order.tour_title_uk}</Typography.Text>
          <dl className="order-card-facts">
            <dt>{t('cabinet.history.place')}</dt>
            <dd>{place(order)}</dd>
            <dt>{t('cabinet.orders.dates')}</dt>
            <dd>{t('checkout.summary.dates', { from: formatDate(order.start_date), to: formatDate(order.end_date) })}</dd>
            <dt>{t('cabinet.orders.tourists')}</dt>
            <dd>{tourists(order)}</dd>
            <dt>{t('cabinet.orders.total')}</dt>
            <dd>{t('checkout.summary.amount', { amount: formatMoney(order.total_uah) })}</dd>
            <dt>{t('cabinet.orders.created')}</dt>
            <dd>{formatKyivDate(order.created_at)}</dd>
          </dl>
          <RowActions order={order} />
        </Card>
      </List.Item>
    )} />
  )
}
