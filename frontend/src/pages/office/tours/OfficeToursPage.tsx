import { PlusOutlined } from '@ant-design/icons'
import { Alert, Button, Flex, Space, Table, Typography } from 'antd'
import type { TableColumnsType, TableProps } from 'antd'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { ApiError, mediaUrl } from '../../../api/client'
import { useOfficeTours } from '../../../api/officeTours'
import { useCountries, useResorts } from '../../../api/reference'
import type { ManagerTourRow, ManagerTourSort } from '../../../api/types'
import { ApiErrorState } from '../../../components/ApiErrorState'
import { FilterBar, type FilterField } from '../../../components/office/FilterBar'
import { PhotoPlaceholder } from '../../../components/PhotoPlaceholder'
import { StatusTag } from '../../../components/StatusTag'
import { statusLabel } from '../../../constants/orderStatus'
import { findTourAction, type TourStateLike } from '../../../features/office/tourActions'
import { actionErrorText, useTourAction } from '../../../features/office/useOfficeAction'
import { useDocumentTitle } from '../../../hooks/useDocumentTitle'
import { formatDate, formatInteger, formatMoney } from '../../../utils/format'
import { OfficeForbidden } from '../OfficeHome'
import { CopyTourModal } from './CopyTourModal'
import {
  filtersFromValues, filterValuesOf, OFFICE_TOURS_PAGE_SIZE, officeToursQuery, officeToursSearch,
  parseOfficeTours, TOUR_STATUSES, type OfficeToursState,
} from './officeToursParams'
import { TourActionButtons } from './TourActionButtons'
import '../../../layouts/OfficeLayout.css'

/** Table column → sort of the API. */
const SORT_OF: Record<string, ManagerTourSort> = { title_uk: 'title_asc', nearest_start: 'departure_asc' }

/**
 * «Тури» (spec 10 §1): every manager's tours with the filter bar and a server-paginated table,
 * all in the URL (officeToursParams.ts). The row buttons come from the API's `tour_actions`.
 */
export function OfficeToursPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const state = useMemo(() => parseOfficeTours(searchParams), [searchParams])
  const tours = useOfficeTours(officeToursQuery(state))
  const action = useTourAction()
  const [copying, setCopying] = useState<TourStateLike | null>(null)
  useDocumentTitle(t('office.tours.title'))

  // The resort list follows the country chosen in the bar, before «Знайти» too; a new URL (applied
  // filters, history) starts from the URL's country again.
  const [draft, setDraft] = useState<{ base?: number; country?: number }>({ base: state.filters.country_id, country: state.filters.country_id })
  const draftCountry = draft.base === state.filters.country_id ? draft.country : state.filters.country_id
  const countries = useCountries()
  const resorts = useResorts(draftCountry)

  const go = (next: OfficeToursState) => setSearchParams(officeToursSearch(next))

  const fields: FilterField[] = [
    { kind: 'text', name: 'q', label: t('office.tours.filter.title'), placeholder: t('office.tours.filter.titlePlaceholder') },
    {
      kind: 'select', name: 'status', label: t('office.tours.filter.status'),
      options: TOUR_STATUSES.map((status) => ({ value: status, label: statusLabel(t, 'tour', status) })),
    },
    {
      kind: 'select', name: 'country_id', label: t('office.tours.filter.country'), clears: ['resort_id'],
      options: (countries.data ?? []).map((c) => ({ value: String(c.id), label: c.name_uk })),
    },
    {
      kind: 'select', name: 'resort_id', label: t('office.tours.filter.resort'),
      options: draftCountry === undefined ? [] : (resorts.data ?? []).map((r) => ({ value: String(r.id), label: r.name_uk })),
    },
    { kind: 'dateRange', name: 'departure', label: t('office.tours.filter.departure'), from: 'departure_from', to: 'departure_to' },
  ]

  const columns: TableColumnsType<ManagerTourRow> = [
    {
      title: t('office.tours.col.photo'), key: 'photo', width: 96,
      render: (_, row) => row.image_url
        ? <img className="office-tour-thumb" src={mediaUrl(row.image_url) ?? undefined} alt={row.title_uk} />
        : <PhotoPlaceholder height={56} className="office-tour-thumb" />,
    },
    {
      title: t('office.tours.col.title'), dataIndex: 'title_uk', key: 'title_uk', width: 240, sorter: true,
      sortOrder: state.sort === 'title_asc' ? 'ascend' : null,
      render: (_, row) => <Link to={`/office/tours/${row.id}/edit`}>{row.title_uk}</Link>,
    },
    {
      title: t('office.tours.col.place'), key: 'place', width: 170,
      render: (_, row) => (
        <Space orientation="vertical" size={0}>
          <span>{row.country_name}</span>
          <Typography.Text type="secondary">{row.resort_name}</Typography.Text>
        </Space>
      ),
    },
    { title: t('office.tours.col.hotel'), dataIndex: 'hotel_name', width: 170 },
    {
      title: t('office.tours.col.nearest'), dataIndex: 'nearest_start', key: 'nearest_start', width: 140, sorter: true,
      sortOrder: state.sort === 'departure_asc' ? 'ascend' : null,
      render: (value: string | null) => value ? formatDate(value)
        : <Typography.Text type="secondary">{t('office.tours.datesPassed')}</Typography.Text>,
    },
    {
      title: t('office.tours.col.price'), key: 'price', width: 130, align: 'right',
      render: (_, row) => t('office.tours.priceFrom', { amount: formatMoney(row.base_price), currency: row.currency }),
    },
    {
      title: t('office.tours.col.seats'), key: 'seats', width: 110, align: 'right',
      render: (_, row) => t('office.tours.seatsValue', { free: formatInteger(row.free_seats), total: formatInteger(row.seats_total) }),
    },
    { title: t('office.tours.col.status'), key: 'status', width: 140, render: (_, row) => <StatusTag kind="tour" status={row.status} /> },
    {
      title: t('office.tours.col.actions'), key: 'actions', width: 380,
      render: (_, row) => (
        <Space wrap size={[8, 8]}>
          <Button size="small" onClick={() => navigate(`/office/tours/${row.id}/edit`)}
            aria-label={`${editLabel(row)}: ${row.title_uk}`}>
            {editLabel(row)}
          </Button>
          <TourActionButtons tour={row} action={action} onCopy={setCopying} />
        </Space>
      ),
    },
  ]

  function editLabel(row: ManagerTourRow) {
    return findTourAction(row, 'edit')?.allowed ? t('tourAction.edit') : t('office.tours.open')
  }

  const onTableChange: TableProps<ManagerTourRow>['onChange'] = (pagination, _filters, sorter) => {
    const one = Array.isArray(sorter) ? sorter[0] : sorter
    const column = typeof one?.columnKey === 'string' ? one.columnKey : undefined
    const sort = column && SORT_OF[column] && one.order ? SORT_OF[column] : 'updated_desc'
    const page = sort !== state.sort ? 1 : pagination.current ?? 1
    go({ ...state, sort, page })
  }

  if (tours.error instanceof ApiError && tours.error.status === 403) return <OfficeForbidden />

  return (
    <Flex vertical gap={16}>
      <Flex justify="space-between" align="center" wrap gap={12}>
        <h1 className="office-page-title">{t('office.tours.title')}</h1>
        <Button type="primary" icon={<PlusOutlined aria-hidden />} onClick={() => navigate('/office/tours/new')}>
          {t('office.tours.create')}
        </Button>
      </Flex>
      <FilterBar fields={fields} values={filterValuesOf(state.filters)}
        onDraftChange={(values) => setDraft({ base: state.filters.country_id, country: values.country_id ? Number(values.country_id) : undefined })}
        onApply={(values) => go({ ...state, filters: filtersFromValues(values), page: 1 })} />
      {action.error && (
        <Alert type="error" showIcon role="alert" closable={{ onClose: action.clearError }}
          title={actionErrorText(action.error, t('office.forbiddenTitle'))} />
      )}
      {tours.isError && !tours.data ? (
        <ApiErrorState error={tours.error} onRetry={() => void tours.refetch()} title={t('office.tours.loadFailed')} />
      ) : (
        <Table<ManagerTourRow> rowKey="id" columns={columns} dataSource={tours.data?.items ?? []}
          loading={tours.isFetching && !tours.data} onChange={onTableChange} scroll={{ x: 1580 }}
          locale={{ emptyText: t('office.tours.empty') }}
          pagination={{
            current: state.page, pageSize: OFFICE_TOURS_PAGE_SIZE, total: tours.data?.total ?? 0,
            showSizeChanger: false,
            showTotal: (total, [from, to]) => t('office.queue.pagination', { from, to, total }),
          }} />
      )}
      <CopyTourModal tour={copying} action={action} onClose={() => setCopying(null)} />
    </Flex>
  )
}
