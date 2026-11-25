import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import {
  Button, Checkbox, Drawer, Flex, Form, Input, InputNumber, Select, Space, Table, Tabs, Tag, TimePicker, Typography,
} from 'antd'
import type { TableColumnsType } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import type { TFunction } from 'i18next'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router'
import { adminKeys, referenceApi, useReferenceList, type ReferenceKind } from '../../../api/admin'
import { ApiError } from '../../../api/client'
import type {
  CityAdmin, CountryAdmin, HotelAdmin, ReferenceAction, ReferenceActionInfo, ResortAdmin, ServiceTypeAdmin,
} from '../../../api/types'
import { ApiErrorState } from '../../../components/ApiErrorState'
import { FilterBar, type FilterField } from '../../../components/office/FilterBar'
import { FormModal } from '../../../components/office/FormModal'
import { ServerActionButton } from '../../../components/office/ServerActionButton'
import { StarIcons } from '../../../components/StarIcons'
import { useAdminAction } from '../../../features/admin/useAdminAction'
import {
  BEACH_LINES, DESCRIPTION_MAX, HOTEL_NAME_MAX, IATA_RE, ISO_RE, LIST_ITEM_MAX, LIST_MAX_ITEMS, MAX_DISTANCE_TO_AIRPORT_KM,
  MAX_DISTANCE_TO_BEACH_M, MAX_PRICE_UAH, NAME_MAX, STARS,
} from '../../../features/admin/referenceRules'
import { actionErrorText } from '../../../features/office/useOfficeAction'
import { useDocumentTitle } from '../../../hooks/useDocumentTitle'
import { formatMoney, formatRating } from '../../../utils/format'
import { OfficeForbidden } from '../OfficeHome'
import { useFieldIssues } from './formErrors'
import {
  matches, PARENT_FILTERS, parseReference, REFERENCE_PAGE_SIZE, REFERENCE_TABS, referenceFilterValues,
  referenceFromFilters, referenceSearch, type ReferenceState,
} from './referenceParams'
import '../../../layouts/OfficeLayout.css'
import './admin.css'

type Item = CountryAdmin | CityAdmin | ResortAdmin | HotelAdmin | ServiceTypeAdmin
type Confirm = { action: Extract<ReferenceAction, 'archive' | 'restore' | 'delete' | 'make_default'>; item: Item }
const isService = (kind: ReferenceKind) => kind === 'insurance-types' || kind === 'transfer-types'

/**
 * «Довідники» (spec 13 §2, ТЗ 4.3 «ведення довідників … архівування неактуальних записів»): one
 * tab per directory of the API. «В архів» / «Відновити» instead of deleting; the buttons come from
 * each record's `admin_actions`, so a refusal (a published tour uses the hotel, the default
 * insurance, an archived parent) shows as a disabled button with the server's reason. Currency
 * rates and site languages are global settings (form 4.6.4.1) and live on /office/settings.
 */
export function OfficeReferencesPage() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const state = useMemo(() => parseReference(searchParams), [searchParams])
  const countries = useReferenceList('countries')
  const resorts = useReferenceList('resorts')
  const list = useReferenceList(state.tab)
  const [editing, setEditing] = useState<{ item: Item | null } | null>(null)
  const [confirm, setConfirm] = useState<Confirm | null>(null)
  const keys = useMemo(() => [adminKeys.reference(state.tab), adminKeys.reference('countries'), adminKeys.reference('resorts')], [state.tab])
  const action = useAdminAction(keys)
  useDocumentTitle(t('admin.references.title'))

  const go = (next: ReferenceState) => setSearchParams(referenceSearch(next))
  const countryName = (id: number) => countries.data?.find((c) => c.id === id)?.name_uk ?? `#${id}`
  const resortOf = (id: number) => resorts.data?.find((r) => r.id === id)
  const parents = PARENT_FILTERS[state.tab]

  const rows = useMemo(() => (list.data ?? []).filter((raw) => {
    const item = raw as Item
    if (!state.archived && item.is_archived) return false
    if (state.tab === 'hotels') {
      const hotel = item as HotelAdmin
      const resort = resorts.data?.find((r) => r.id === hotel.resort_id)
      if (state.resort && hotel.resort_id !== state.resort) return false
      if (state.country && resort?.country_id !== state.country) return false
      return matches(state.q, hotel.name)
    }
    if (state.country && 'country_id' in item && item.country_id !== state.country) return false
    if ('name_uk' in item) return matches(state.q, item.name_uk, 'name_en' in item ? item.name_en : null,
      'iso_code' in item ? item.iso_code : null, 'iata_code' in item ? item.iata_code : null)
    return true
  }) as Item[], [list.data, resorts.data, state])

  const fields: FilterField[] = [
    { kind: 'text', name: 'q', label: t('admin.references.search'), maxLength: 100 },
    ...(parents.country ? [{
      kind: 'select' as const, name: 'country', label: t('admin.references.country'),
      options: (countries.data ?? []).map((c) => ({ value: String(c.id), label: c.name_uk })),
    }] : []),
    ...(parents.resort ? [{
      kind: 'select' as const, name: 'resort', label: t('admin.references.resort'),
      options: (resorts.data ?? []).filter((r) => !state.country || r.country_id === state.country)
        .map((r) => ({ value: String(r.id), label: r.name_uk })),
    }] : []),
    { kind: 'switch', name: 'archived', label: t('admin.references.showArchived') },
  ]

  const find = (item: Item, name: ReferenceAction): ReferenceActionInfo | undefined =>
    item.admin_actions.find((a) => a.action === name)
  const actionButton = (item: Item, name: Confirm['action'], label: string, danger = false) => {
    const info = find(item, name)
    return info && (
      <ServerActionButton key={name} size="small" info={info} busy={action.busy !== null} danger={danger}
        onClick={() => { action.clearError(); setConfirm({ action: name, item }) }}>
        {label}
      </ServerActionButton>
    )
  }

  const status = (item: Item) => (
    <Space size={4} wrap>
      {item.is_archived ? <Tag>{t('admin.references.archived')}</Tag> : <Tag color="success">{t('admin.references.active')}</Tag>}
      {'is_default' in item && item.is_default && <Tag color="processing">{t('admin.references.default')}</Tag>}
    </Space>
  )

  const columns: TableColumnsType<Item> = [
    ...kindColumns(t, state.tab, countryName, resortOf),
    { title: t('admin.references.col.status'), key: 'status', width: 170, render: (_, item) => status(item) },
    {
      title: t('admin.references.col.actions'), key: 'actions', width: 380,
      render: (_, item) => (
        <Space wrap size={4}>
          <Button size="small" disabled={action.busy !== null} onClick={() => { action.clearError(); setEditing({ item }) }}>
            {t('admin.references.edit')}
          </Button>
          {actionButton(item, 'make_default', t('admin.references.makeDefault.button'))}
          {actionButton(item, 'archive', t('admin.references.archive.button'))}
          {actionButton(item, 'restore', t('admin.references.restore.button'))}
          {actionButton(item, 'delete', t('admin.references.delete.button'), true)}
        </Space>
      ),
    },
  ]

  if (list.error instanceof ApiError && list.error.status === 403) return <OfficeForbidden />
  const errorText = action.error && !action.error.issues.length ? actionErrorText(action.error, t('office.forbiddenTitle')) : null

  return (
    <Flex vertical gap={16}>
      <Flex justify="space-between" align="center" wrap gap={12}>
        <h1 className="office-page-title">{t('admin.references.title')}</h1>
        <Button type="primary" icon={<PlusOutlined aria-hidden />} onClick={() => { action.clearError(); setEditing({ item: null }) }}>
          {t(`admin.references.add.${state.tab}`)}
        </Button>
      </Flex>
      <Typography.Paragraph type="secondary" className="admin-intro">{t('admin.references.intro')}</Typography.Paragraph>
      <Tabs activeKey={state.tab} aria-label={t('admin.references.tabs')}
        onChange={(key) => go({ tab: key as ReferenceKind, archived: false, page: 1 })}
        items={REFERENCE_TABS.map((tab) => ({ key: tab, label: t(`admin.references.tab.${tab}`) }))} />
      <FilterBar key={state.tab} fields={fields} values={referenceFilterValues(state)}
        onApply={(values) => go(referenceFromFilters(state, values))} />
      {list.isError && !list.data ? (
        <ApiErrorState error={list.error} onRetry={() => void list.refetch()} title={t('admin.references.loadFailed')} />
      ) : (
        <Table<Item> rowKey="id" columns={columns} dataSource={rows} loading={list.isFetching && !list.data}
          scroll={{ x: 1100 }} locale={{ emptyText: t('admin.references.empty') }}
          onChange={(pagination) => go({ ...state, page: pagination.current ?? 1 })}
          pagination={{
            current: state.page, pageSize: REFERENCE_PAGE_SIZE, total: rows.length, showSizeChanger: false, hideOnSinglePage: true,
            showTotal: (total, [from, to]) => t('admin.pagination', { from, to, total }),
          }} />
      )}
      {editing && state.tab === 'hotels' && (
        <HotelDrawer hotel={editing.item as HotelAdmin | null} countries={countries.data ?? []} resorts={resorts.data ?? []}
          action={action} error={errorText} onClose={() => setEditing(null)} />
      )}
      {editing && state.tab !== 'hotels' && (
        <ItemModal kind={state.tab} item={editing.item} countries={countries.data ?? []} action={action} error={errorText}
          onClose={() => setEditing(null)} />
      )}
      {confirm && (
        <ConfirmModal kind={state.tab} confirm={confirm} action={action} error={errorText} onClose={() => setConfirm(null)} />
      )}
    </Flex>
  )
}

function kindColumns(t: TFunction, kind: ReferenceKind, countryName: (id: number) => string,
  resortOf: (id: number) => ResortAdmin | undefined): TableColumnsType<Item> {
  const nameUk = { title: t('admin.references.col.nameUk'), key: 'name_uk', width: 200, render: (_: unknown, item: Item) => (item as CountryAdmin).name_uk }
  const nameEn = { title: t('admin.references.col.nameEn'), key: 'name_en', width: 180, render: (_: unknown, item: Item) => (item as CountryAdmin).name_en ?? '—' }
  const country = { title: t('admin.references.country'), key: 'country', width: 160, render: (_: unknown, item: Item) => countryName((item as ResortAdmin).country_id) }
  switch (kind) {
    case 'countries':
      return [nameUk, nameEn, { title: t('admin.references.col.iso'), key: 'iso', width: 110, render: (_, item) => (item as CountryAdmin).iso_code }]
    case 'resorts':
      return [nameUk, nameEn, country]
    case 'cities':
      return [nameUk, nameEn, { title: t('admin.references.col.iata'), key: 'iata', width: 110, render: (_, item) => (item as CityAdmin).iata_code ?? '—' }, country]
    case 'hotels':
      return [
        { title: t('admin.references.col.hotel'), key: 'name', width: 220, render: (_, item) => (item as HotelAdmin).name },
        { title: t('admin.references.col.stars'), key: 'stars', width: 130, render: (_, item) => {
          const stars = (item as HotelAdmin).stars
          return stars ? <StarIcons value={stars} label={t('admin.references.field.starsValue', { count: stars })} /> : '—'
        } },
        { title: t('admin.references.resort'), key: 'resort', width: 150, render: (_, item) => resortOf((item as HotelAdmin).resort_id)?.name_uk ?? '—' },
        { title: t('admin.references.country'), key: 'country', width: 150, render: (_, item) => {
          const resort = resortOf((item as HotelAdmin).resort_id)
          return resort ? countryName(resort.country_id) : '—'
        } },
        { title: t('admin.references.col.rating'), key: 'rating', width: 110, render: (_, item) => {
          const rating = (item as HotelAdmin).rating_avg
          return rating ? formatRating(rating) : '—'
        } },
      ]
    default:
      return [nameUk, { title: t('admin.references.col.price'), key: 'price', width: 150, align: 'right',
        render: (_, item) => t('office.money', { amount: formatMoney((item as ServiceTypeAdmin).price_uah) }) }]
  }
}

function itemName(item: Item): string {
  return 'name_uk' in item ? item.name_uk : item.name
}

type Action = ReturnType<typeof useAdminAction>

/** Archive / restore / delete / make default, each explained before it runs. */
function ConfirmModal({ kind, confirm, action, error, onClose }: {
  kind: ReferenceKind; confirm: Confirm; action: Action; error: string | null; onClose: () => void
}) {
  const { t } = useTranslation()
  const [form] = Form.useForm<object>()
  const { item } = confirm
  const run = (): Promise<unknown> => {
    switch (confirm.action) {
      case 'archive': return referenceApi.archive(kind, item.id)
      case 'restore': return referenceApi.restore(kind, item.id)
      case 'delete': return referenceApi.remove(kind, item.id).then(() => true)
      default: return referenceApi.update(kind, item.id, { is_default: true })
    }
  }
  const warning = confirm.action === 'archive'
    ? <>{t('admin.references.archive.warning')}{kind === 'countries' && <> {t('admin.references.archive.countryWarning')}</>}</>
    : t(`admin.references.${confirm.action === 'make_default' ? 'makeDefault' : confirm.action}.warning`)
  return (
    <FormModal open form={form} busy={action.busy === confirm.action} error={error} danger={confirm.action === 'delete'}
      title={t(`admin.references.${confirm.action === 'make_default' ? 'makeDefault' : confirm.action}.title`, { name: itemName(item) })}
      okText={t(`admin.references.${confirm.action === 'make_default' ? 'makeDefault' : confirm.action}.ok`)}
      cancelText={t('admin.cancel')} warning={warning} onCancel={() => { action.clearError(); onClose() }}
      onSubmit={async () => (await action.run(confirm.action, run)) !== null} />
  )
}

interface ItemValues {
  iso_code?: string
  name_uk: string
  name_en?: string
  country_id?: number
  iata_code?: string
  price_uah?: string
  is_default?: boolean
}

const optional = (value?: string | null) => (value?.trim() ? value.trim() : null)

/** Countries, resorts, departure cities, insurance and transfer types. */
function ItemModal({ kind, item, countries, action, error, onClose }: {
  kind: Exclude<ReferenceKind, 'hotels'>; item: Item | null; countries: CountryAdmin[]; action: Action; error: string | null
  onClose: () => void
}) {
  const { t } = useTranslation()
  const [form] = Form.useForm<ItemValues>()
  useFieldIssues(form, error === null ? action.error : null, ITEM_FIELDS)
  const current = item as (CountryAdmin & CityAdmin & ServiceTypeAdmin) | null
  const name = item ? 'save' : 'create'

  const submit = async (values: ItemValues) => {
    const body: Record<string, unknown> = { name_uk: values.name_uk.trim() }
    if (kind === 'countries') body.iso_code = values.iso_code?.trim().toUpperCase()
    if (kind === 'countries' || kind === 'resorts' || kind === 'cities') body.name_en = optional(values.name_en)
    if (kind === 'resorts' || kind === 'cities') body.country_id = values.country_id
    if (kind === 'cities') body.iata_code = optional(values.iata_code)?.toUpperCase() ?? null
    if (isService(kind)) {
      body.price_uah = values.price_uah
      if (!item) body.is_default = Boolean(values.is_default)
    }
    const saved = await action.run(name, () => item ? referenceApi.update(kind, item.id, body) : referenceApi.create(kind, body))
    return saved !== null
  }
  const parentOptions = countries.filter((c) => !c.is_archived || c.id === current?.country_id)
    .map((c) => ({ value: c.id, label: c.is_archived ? `${c.name_uk} (${t('admin.references.archived')})` : c.name_uk }))

  return (
    <FormModal open form={form} busy={action.busy === name} error={error} cancelText={t('admin.cancel')}
      title={t(item ? `admin.references.editTitle.${kind}` : `admin.references.add.${kind}`)}
      okText={t(item ? 'admin.save' : 'admin.references.create')} onCancel={() => { action.clearError(); onClose() }} onSubmit={submit}>
      {kind === 'countries' && (
        <Form.Item name="iso_code" label={t('admin.references.field.iso')} extra={t('admin.references.field.isoHint')}
          initialValue={current?.iso_code} rules={[{ required: true, message: t('admin.references.field.isoRequired') },
            { pattern: ISO_RE, message: t('admin.references.field.isoFormat') }]}>
          <Input maxLength={2} className="admin-code-input" />
        </Form.Item>
      )}
      {(kind === 'resorts' || kind === 'cities') && (
        <Form.Item name="country_id" label={t('admin.references.country')} initialValue={current?.country_id}
          rules={[{ required: true, message: t('admin.references.field.countryRequired') }]}>
          <Select showSearch={{ optionFilterProp: 'label' }} options={parentOptions} />
        </Form.Item>
      )}
      <Form.Item name="name_uk" label={t('admin.references.field.nameUk')} initialValue={current?.name_uk}
        rules={[{ required: true, whitespace: true, message: t('admin.references.field.nameRequired') },
          { max: NAME_MAX, message: t('admin.references.field.tooLong', { max: NAME_MAX }) }]}>
        <Input />
      </Form.Item>
      {(kind === 'countries' || kind === 'resorts' || kind === 'cities') && (
        <Form.Item name="name_en" label={t('admin.references.field.nameEn')} initialValue={current?.name_en ?? undefined}
          rules={[{ max: NAME_MAX, message: t('admin.references.field.tooLong', { max: NAME_MAX }) }]}>
          <Input />
        </Form.Item>
      )}
      {kind === 'cities' && (
        <Form.Item name="iata_code" label={t('admin.references.field.iata')} extra={t('admin.references.field.iataHint')}
          initialValue={current?.iata_code ?? undefined} rules={[{ pattern: IATA_RE, message: t('admin.references.field.iataFormat') }]}>
          <Input maxLength={3} className="admin-code-input" />
        </Form.Item>
      )}
      {isService(kind) && (
        <>
          <Form.Item name="price_uah" label={t(kind === 'insurance-types' ? 'admin.references.field.priceInsurance' : 'admin.references.field.priceTransfer')}
            initialValue={current?.price_uah} rules={[{ required: true, message: t('admin.references.field.priceRequired') }]}>
            <InputNumber<string> stringMode min="0" max={String(MAX_PRICE_UAH)} precision={2} step="10" className="admin-number" />
          </Form.Item>
          {!item && (
            <Form.Item name="is_default" valuePropName="checked" initialValue={false} extra={t('admin.references.field.defaultHint')}>
              <Checkbox>{t('admin.references.field.default')}</Checkbox>
            </Form.Item>
          )}
        </>
      )}
    </FormModal>
  )
}
const ITEM_FIELDS = ['iso_code', 'name_uk', 'name_en', 'country_id', 'iata_code', 'price_uah'] as const

interface HotelValues {
  country_id?: number
  resort_id?: number
  name: string
  stars?: number | null
  description?: string
  beach_line?: number | null
  distance_to_beach_m?: number | null
  distance_to_airport_km?: number | null
  check_in?: Dayjs | null
  check_out?: Dayjs | null
  amenities?: string[]
  room_types?: string[]
}
const HOTEL_FIELDS = ['resort_id', 'name', 'stars', 'description', 'beach_line', 'distance_to_beach_m',
  'distance_to_airport_km', 'check_in', 'check_out', 'amenities', 'room_types'] as const

const time = (value: string | null | undefined) => (value ? dayjs(value, 'HH:mm:ss') : null)

/** A hotel has more fields (form 4.6.4.2), so it opens in a Drawer; the resort depends on the country. */
function HotelDrawer({ hotel, countries, resorts, action, error, onClose }: {
  hotel: HotelAdmin | null; countries: CountryAdmin[]; resorts: ResortAdmin[]; action: Action; error: string | null
  onClose: () => void
}) {
  const { t } = useTranslation()
  const [form] = Form.useForm<HotelValues>()
  useFieldIssues(form, error === null ? action.error : null, HOTEL_FIELDS)
  const startResort = hotel ? resorts.find((r) => r.id === hotel.resort_id) : undefined
  const country = Form.useWatch('country_id', form)
  const name = hotel ? 'save' : 'create'

  const countryOptions = countries.filter((c) => !c.is_archived || c.id === startResort?.country_id)
    .map((c) => ({ value: c.id, label: c.is_archived ? `${c.name_uk} (${t('admin.references.archived')})` : c.name_uk }))
  const resortOptions = resorts.filter((r) => r.country_id === country && (!r.is_archived || r.id === hotel?.resort_id))
    .map((r) => ({ value: r.id, label: r.is_archived ? `${r.name_uk} (${t('admin.references.archived')})` : r.name_uk }))

  const submit = async () => {
    let values: HotelValues
    try {
      values = await form.validateFields()
    } catch {
      return
    }
    const list = (items?: string[]) => (items ?? []).map((v) => v?.trim()).filter(Boolean)
    const body = {
      resort_id: values.resort_id, name: values.name.trim(), stars: values.stars ?? null,
      description: optional(values.description), beach_line: values.beach_line ?? null,
      distance_to_beach_m: values.distance_to_beach_m ?? null, distance_to_airport_km: values.distance_to_airport_km ?? null,
      check_in: values.check_in ? values.check_in.format('HH:mm') : null,
      check_out: values.check_out ? values.check_out.format('HH:mm') : null,
      amenities: list(values.amenities), room_types: list(values.room_types),
    }
    const saved = await action.run(name, () => hotel ? referenceApi.update('hotels', hotel.id, body) : referenceApi.create('hotels', body))
    if (saved !== null) onClose()
  }
  const close = () => { action.clearError(); onClose() }

  return (
    <Drawer open size={640} destroyOnHidden onClose={close} maskClosable={action.busy === null}
      title={hotel ? t('admin.references.editTitle.hotels') : t('admin.references.add.hotels')}
      footer={(
        <Flex justify="end" gap={8}>
          <Button onClick={close} disabled={action.busy !== null}>{t('admin.cancel')}</Button>
          <Button type="primary" loading={action.busy === name} onClick={() => void submit()}>
            {hotel ? t('admin.save') : t('admin.references.create')}
          </Button>
        </Flex>
      )}>
      <Form form={form} layout="vertical" validateTrigger={['onBlur', 'onChange']} preserve={false}
        initialValues={{
          country_id: startResort?.country_id, resort_id: hotel?.resort_id, name: hotel?.name, stars: hotel?.stars,
          description: hotel?.description ?? undefined, beach_line: hotel?.beach_line,
          distance_to_beach_m: hotel?.distance_to_beach_m, distance_to_airport_km: hotel?.distance_to_airport_km,
          check_in: time(hotel?.check_in), check_out: time(hotel?.check_out),
          amenities: hotel?.amenities ?? [], room_types: hotel?.room_types ?? [],
        }}
        onValuesChange={(changed: Partial<HotelValues>) => {
          if ('country_id' in changed) form.setFieldValue('resort_id', undefined)   // a resort belongs to its country
        }}>
        <Flex gap={12} wrap>
          <Form.Item name="country_id" label={t('admin.references.country')} className="admin-half"
            rules={[{ required: true, message: t('admin.references.field.countryRequired') }]}>
            <Select showSearch={{ optionFilterProp: 'label' }} options={countryOptions} />
          </Form.Item>
          <Form.Item name="resort_id" label={t('admin.references.resort')} className="admin-half"
            extra={country ? undefined : t('admin.references.field.resortHint')}
            rules={[{ required: true, message: t('admin.references.field.resortRequired') }]}>
            <Select showSearch={{ optionFilterProp: 'label' }} options={resortOptions} disabled={!country} />
          </Form.Item>
        </Flex>
        <Form.Item name="name" label={t('admin.references.field.hotelName')}
          rules={[{ required: true, whitespace: true, message: t('admin.references.field.nameRequired') },
            { max: HOTEL_NAME_MAX, message: t('admin.references.field.tooLong', { max: HOTEL_NAME_MAX }) }]}>
          <Input />
        </Form.Item>
        <Flex gap={12} wrap>
          <Form.Item name="stars" label={t('admin.references.col.stars')} className="admin-half">
            <Select allowClear options={STARS.map((n) => ({ value: n, label: t('admin.references.field.starsValue', { count: n }) }))} />
          </Form.Item>
          <Form.Item name="beach_line" label={t('hotel.beachLine')} className="admin-half">
            <Select allowClear options={BEACH_LINES.map((n) => ({ value: n, label: t('admin.references.field.lineValue', { line: n }) }))} />
          </Form.Item>
        </Flex>
        <Flex gap={12} wrap>
          <Form.Item name="distance_to_beach_m" label={t('admin.references.field.toBeach')} className="admin-half"
            extra={t('admin.references.field.toBeachHint')}>
            <InputNumber min={0} max={MAX_DISTANCE_TO_BEACH_M} precision={0} className="admin-number" />
          </Form.Item>
          <Form.Item name="distance_to_airport_km" label={t('admin.references.field.toAirport')} className="admin-half">
            <InputNumber min={0} max={MAX_DISTANCE_TO_AIRPORT_KM} precision={0} className="admin-number" />
          </Form.Item>
        </Flex>
        <Flex gap={12} wrap>
          <Form.Item name="check_in" label={t('admin.references.field.checkIn')} className="admin-half">
            <TimePicker format="HH:mm" minuteStep={5} needConfirm={false} className="admin-number" />
          </Form.Item>
          <Form.Item name="check_out" label={t('admin.references.field.checkOut')} className="admin-half">
            <TimePicker format="HH:mm" minuteStep={5} needConfirm={false} className="admin-number" />
          </Form.Item>
        </Flex>
        <Form.Item name="description" label={t('admin.references.field.description')}
          rules={[{ max: DESCRIPTION_MAX, message: t('admin.references.field.tooLong', { max: DESCRIPTION_MAX }) }]}>
          <Input.TextArea rows={4} showCount maxLength={DESCRIPTION_MAX} />
        </Form.Item>
        <TextList name="amenities" label={t('admin.references.field.amenities')} addText={t('admin.references.field.addAmenity')} />
        <TextList name="room_types" label={t('admin.references.field.roomTypes')} addText={t('admin.references.field.addRoomType')} />
        {error && <Typography.Paragraph type="danger" role="alert">{error}</Typography.Paragraph>}
      </Form>
    </Drawer>
  )
}

/** Amenities / room types: up to 20 lines of 200 characters (backend services/text_lists.py). */
function TextList({ name, label, addText }: { name: 'amenities' | 'room_types'; label: string; addText: string }) {
  const { t } = useTranslation()
  return (
    <Form.List name={name}>
      {(items, { add, remove }) => (
        <fieldset className="admin-fieldset">
          <legend>{label}</legend>
          {items.map((item, index) => (
            <Flex key={item.key} gap={8} align="start">
              <Form.Item {...item} className="admin-grow" rules={[{ max: LIST_ITEM_MAX, message: t('admin.references.field.tooLong', { max: LIST_ITEM_MAX }) }]}>
                <Input aria-label={t('admin.references.field.listItem', { label, n: index + 1 })} maxLength={LIST_ITEM_MAX} />
              </Form.Item>
              <Button icon={<DeleteOutlined aria-hidden />} onClick={() => remove(item.name)}
                aria-label={t('admin.references.field.removeItem', { label, n: index + 1 })} />
            </Flex>
          ))}
          <Button icon={<PlusOutlined aria-hidden />} onClick={() => add('')} disabled={items.length >= LIST_MAX_ITEMS}>
            {addText}
          </Button>
          {items.length >= LIST_MAX_ITEMS && (
            <Typography.Paragraph type="secondary">{t('admin.references.field.listFull', { max: LIST_MAX_ITEMS })}</Typography.Paragraph>
          )}
        </fieldset>
      )}
    </Form.List>
  )
}

