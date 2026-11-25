import { Alert, Button, Flex, Space, Table, Tabs, Tag, Typography } from 'antd'
import type { TableColumnsType, TableProps } from 'antd'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { officeActions, useOfficeOrders } from '../../api/office'
import type { ManagerOrderRow, ManagerOrderSort, ManagerQueue } from '../../api/types'
import { ApiErrorState } from '../../components/ApiErrorState'
import { FilterBar, type FilterField } from '../../components/office/FilterBar'
import { StatusTag } from '../../components/StatusTag'
import { statusLabel } from '../../constants/orderStatus'
import { actionErrorText, useOfficeAction } from '../../features/office/useOfficeAction'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { formatDate, formatKyivDateTime, formatMoney } from '../../utils/format'
import { ApiError } from '../../api/client'
import { OfficeForbidden } from './OfficeHome'
import {
  filtersFromValues, filterValuesOf, OFFICE_ORDERS_PAGE_SIZE, officeOrdersQuery, officeOrdersSearch,
  ORDER_STATUSES, parseOfficeOrders, QUEUES, type OfficeOrdersState,
} from './officeOrdersParams'
import '../../layouts/OfficeLayout.css'

/** Table column → sort of the API (ascending / descending). */
const SORT_OF: Record<string, [ManagerOrderSort, ManagerOrderSort]> = {
  created_at: ['created_asc', 'created_desc'],
  start_date: ['start_asc', 'start_desc'],
}

/**
 * «Заявки» (spec 09 §2, ТЗ 4.5.4 step 1): tabs «Нові / Мої в роботі / Усі» with the server's
 * counts, the filter bar and a server-paginated table. Everything is in the URL
 * (officeOrdersParams.ts). «Взяти в роботу» is offered in «Нові» only: that tab holds exactly the
 * orders the server counts as new; if another manager was faster, the 409 text is shown and the
 * list reloads.
 */
export function OfficeOrdersPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const state = useMemo(() => parseOfficeOrders(searchParams), [searchParams])
  const orders = useOfficeOrders(officeOrdersQuery(state))
  const action = useOfficeAction()
  useDocumentTitle(t('office.queue.title'))

  const go = (next: OfficeOrdersState) => setSearchParams(officeOrdersSearch(next))

  const fields: FilterField[] = [
    { kind: 'text', name: 'number', label: t('office.queue.number'), placeholder: t('office.queue.numberPlaceholder'), maxLength: 30 },
    { kind: 'text', name: 'client', label: t('office.queue.client'), placeholder: t('office.queue.clientPlaceholder') },
    {
      kind: 'select', name: 'status', label: t('office.queue.status'), multiple: true,
      options: ORDER_STATUSES.map((status) => ({ value: status, label: statusLabel(t, 'order', status) })),
    },
    { kind: 'dateRange', name: 'created', label: t('office.queue.created'), from: 'created_from', to: 'created_to' },
    { kind: 'dateRange', name: 'start', label: t('office.queue.start'), from: 'start_from', to: 'start_to' },
    { kind: 'switch', name: 'overdue', label: t('office.queue.overdue') },
  ]

  const take = async (row: ManagerOrderRow) => {
    const taken = await action.run(`take-${row.id}`, () => officeActions.take(row.id))
    if (taken) navigate(`/office/orders/${taken.id}`)
  }

  const counts = orders.data?.queue_counts
  const sortOrder = (column: keyof typeof SORT_OF) => {
    const [asc, desc] = SORT_OF[column]
    return state.sort === asc ? 'ascend' as const : state.sort === desc ? 'descend' as const : null
  }

  const columns: TableColumnsType<ManagerOrderRow> = [
    {
      title: t('office.queue.col.number'), dataIndex: 'number', fixed: 'left', width: 150,
      render: (_, row) => <Link to={`/office/orders/${row.id}`}>{row.number}</Link>,
    },
    {
      title: t('office.queue.col.client'), key: 'client', width: 190,
      render: (_, row) => (
        <Space orientation="vertical" size={0}>
          <span>{row.client_name}</span>
          <Typography.Text type="secondary">{row.client_phone}</Typography.Text>
        </Space>
      ),
    },
    {
      title: t('office.queue.col.tour'), key: 'tour', width: 240,
      render: (_, row) => (
        <Space orientation="vertical" size={0}>
          <span>{row.tour_title_uk}</span>
          <Typography.Text type="secondary">{row.hotel_name}</Typography.Text>
        </Space>
      ),
    },
    {
      title: t('office.queue.col.start'), dataIndex: 'start_date', key: 'start_date', width: 130,
      sorter: true, sortOrder: sortOrder('start_date'), render: (value: string) => formatDate(value),
    },
    { title: t('office.queue.col.tourists'), key: 'tourists', width: 100, align: 'right', render: (_, row) => row.adults + row.children },
    {
      title: t('office.queue.col.total'), dataIndex: 'total_uah', width: 140, align: 'right',
      render: (value: string) => t('office.money', { amount: formatMoney(value) }),
    },
    {
      title: t('office.queue.col.status'), key: 'status', width: 190,
      render: (_, row) => (
        <Flex wrap gap={4}>
          <StatusTag kind="order" status={row.status} />
          {row.overdue && <Tag color="warning" title={t('office.queue.overdueHint')}>{t('office.queue.overdueTag')}</Tag>}
        </Flex>
      ),
    },
    {
      title: t('office.queue.col.manager'), key: 'manager', width: 150,
      render: (_, row) => row.manager_name ?? <Typography.Text type="secondary">{t('office.queue.noManager')}</Typography.Text>,
    },
    {
      title: t('office.queue.col.created'), dataIndex: 'created_at', key: 'created_at', width: 160,
      sorter: true, sortOrder: sortOrder('created_at'), render: (value: string) => formatKyivDateTime(value),
    },
    {
      title: t('office.queue.col.actions'), key: 'actions', width: 210, fixed: 'right',
      render: (_, row) => (
        <Space wrap>
          {state.queue === 'new' && (
            <Button type="primary" size="small" loading={action.busy === `take-${row.id}`}
              disabled={action.busy !== null} onClick={() => void take(row)}>
              {t('staffAction.take')}
            </Button>
          )}
          <Button size="small" onClick={() => navigate(`/office/orders/${row.id}`)}
            aria-label={`${t('office.queue.open')} ${row.number}`}>
            {t('office.queue.open')}
          </Button>
        </Space>
      ),
    },
  ]

  const onTableChange: TableProps<ManagerOrderRow>['onChange'] = (pagination, _filters, sorter) => {
    const one = Array.isArray(sorter) ? sorter[0] : sorter
    const column = typeof one?.columnKey === 'string' ? one.columnKey : undefined
    let sort = state.sort
    if (column && SORT_OF[column] && one.order) sort = SORT_OF[column][one.order === 'ascend' ? 0 : 1]
    else if (column && !one.order) sort = 'created_desc'
    const page = sort !== state.sort ? 1 : pagination.current ?? 1
    go({ ...state, sort, page })
  }

  if (orders.error instanceof ApiError && orders.error.status === 403) return <OfficeForbidden />

  return (
    <Flex vertical gap={16}>
      <h1 className="office-page-title">{t('office.queue.title')}</h1>
      <Tabs activeKey={state.queue} aria-label={t('office.queue.tabs')}
        onChange={(key) => go({ ...state, queue: key as ManagerQueue, page: 1 })}
        items={QUEUES.map((queue) => ({
          key: queue,
          label: counts ? t('office.queue.tabLabel', { label: t(`managerQueue.${queue}`), count: counts[queue] })
            : t(`managerQueue.${queue}`),
        }))} />
      <FilterBar fields={fields} values={filterValuesOf(state.filters)}
        onApply={(values) => go({ ...state, filters: filtersFromValues(values), page: 1 })} />
      {action.error && (
        <Alert type="error" showIcon role="alert" closable={{ onClose: action.clearError }}
          title={actionErrorText(action.error, t('office.forbiddenTitle'))} />
      )}
      {orders.isError && !orders.data ? (
        <ApiErrorState error={orders.error} onRetry={() => void orders.refetch()} title={t('office.queue.loadFailed')} />
      ) : (
        <Table<ManagerOrderRow> rowKey="id" columns={columns} dataSource={orders.data?.items ?? []}
          loading={orders.isFetching && !orders.data} onChange={onTableChange} scroll={{ x: 1300 }}
          // A row's `children` is the number of children travelling, not tree rows of the table.
          expandable={{ childrenColumnName: 'tree_rows' }}
          locale={{ emptyText: t('office.queue.empty') }}
          pagination={{
            current: state.page, pageSize: OFFICE_ORDERS_PAGE_SIZE, total: orders.data?.total ?? 0,
            showSizeChanger: false,
            showTotal: (total, [from, to]) => t('office.queue.pagination', { from, to, total }),
          }} />
      )}
    </Flex>
  )
}
