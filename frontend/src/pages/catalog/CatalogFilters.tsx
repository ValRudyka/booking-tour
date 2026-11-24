import { Checkbox, DatePicker, Flex, Form, Input, InputNumber, Select } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useCities, useCountries, useResorts } from '../../api/reference'
import { useDebouncedCallback } from '../../hooks/useDebouncedCallback'
import {
  NIGHTS_MAX, NIGHTS_MIN, STAR_OPTIONS, TRANSPORT_TYPES, type CatalogFilters as Filters,
} from './catalogParams'

const DATE_FORMAT = 'DD.MM.YYYY'
const ISO = 'YYYY-MM-DD'
export const SEARCH_DEBOUNCE_MS = 400

/**
 * A text/number field that types locally and reports the value `delayMs` after the last
 * keystroke. A new value from outside (Reset, Back) replaces what is typed; the echo of our
 * own report does not, so fast typing is never cut off.
 */
function useCommittedField<T>(value: T, commit: (value: T) => void, delayMs: number) {
  const [local, setLocal] = useState(value)
  const [seen, setSeen] = useState(value)
  const [committed, setCommitted] = useState(value)
  const debounced = useDebouncedCallback((next: T) => {
    setCommitted(next)
    commit(next)
  }, delayMs)

  if (!Object.is(value, seen)) {
    // Adjusting state while rendering when a prop changed (react.dev "You Might Not Need an Effect").
    setSeen(value)
    if (!Object.is(value, committed)) {
      setCommitted(value)
      setLocal(value)
      debounced.cancel() // a typed value still waiting must not overwrite Reset/Back
    }
  }

  const change = (next: T) => {
    setLocal(next)
    debounced(next)
  }
  return [local, change, () => debounced.flush(local)] as const
}

interface Props {
  value: Filters
  onChange: (patch: Partial<Filters>) => void
  /** Desktop: 400 ms debounce for typed fields. Mobile Drawer: 0, it applies with a button. */
  debounceMs: number
  idPrefix: string
}

/** Catalog filters (spec §4 "Фільтри"): every field has a visible label and works from the
 * keyboard. Meal plan is not here: the API has no such field yet (feature/catalog-improvements). */
export function CatalogFilters({ value, onChange, debounceMs, idPrefix }: Props) {
  const { t } = useTranslation()
  const countries = useCountries()
  const resorts = useResorts(value.country_id)
  const cities = useCities()
  const id = (name: string) => `${idPrefix}-${name}`

  const [q, setQ, flushQ] = useCommittedField(value.q ?? '',
    (next) => onChange({ q: next.trim() || undefined }), debounceMs)
  const [nightsMin, setNightsMin] = useCommittedField(value.nights_min,
    (next) => onChange({ nights_min: next }), debounceMs)
  const [nightsMax, setNightsMax] = useCommittedField(value.nights_max,
    (next) => onChange({ nights_max: next }), debounceMs)
  const [priceMin, setPriceMin] = useCommittedField(value.price_min,
    (next) => onChange({ price_min: next }), debounceMs)
  const [priceMax, setPriceMax] = useCommittedField(value.price_max,
    (next) => onChange({ price_max: next }), debounceMs)

  const number = (next: number | null) => (next === null ? undefined : next)
  const dates: [Dayjs, Dayjs] | null = value.date_from && value.date_to
    ? [dayjs(value.date_from, ISO), dayjs(value.date_to, ISO)]
    : null
  const searchSelect = { optionFilterProp: 'label' } as const

  return (
    <Form layout="vertical" component="div" className="catalog-filters">
      <Form.Item label={t('filters.search')} htmlFor={id('q')}>
        <Input.Search id={id('q')} value={q} maxLength={100} allowClear
          placeholder={t('filters.searchPlaceholder')} enterButton={t('filters.searchButton')}
          onChange={(event) => setQ(event.target.value)} onSearch={() => flushQ()} />
      </Form.Item>

      <Form.Item label={t('filters.country')} htmlFor={id('country')}>
        <Select id={id('country')} value={value.country_id} allowClear showSearch={searchSelect}
          placeholder={t('filters.anyCountry')} loading={countries.isLoading}
          options={countries.data?.map((c) => ({ value: c.id, label: c.name_uk }))}
          onChange={(next?: number) => onChange({ country_id: next })} />
      </Form.Item>

      <Form.Item label={t('filters.resort')} htmlFor={id('resort')}
        extra={value.country_id === undefined ? t('filters.resortHint') : undefined}>
        <Select id={id('resort')} value={value.resort_id} allowClear showSearch={searchSelect}
          placeholder={t('filters.anyResort')} disabled={value.country_id === undefined}
          loading={resorts.isLoading}
          options={resorts.data?.map((r) => ({ value: r.id, label: r.name_uk }))}
          onChange={(next?: number) => onChange({ resort_id: next })} />
      </Form.Item>

      <Form.Item label={t('filters.departureCity')} htmlFor={id('city')}>
        <Select id={id('city')} value={value.departure_city_id} allowClear showSearch={searchSelect}
          placeholder={t('filters.anyCity')} loading={cities.isLoading}
          options={cities.data?.map((c) => ({ value: c.id, label: c.name_uk }))}
          onChange={(next?: number) => onChange({ departure_city_id: next })} />
      </Form.Item>

      <Form.Item label={t('filters.transport')} htmlFor={id('transport')}>
        <Select id={id('transport')} value={value.transport_type} allowClear
          placeholder={t('filters.anyTransport')}
          options={TRANSPORT_TYPES.map((type) => ({ value: type, label: t(`transport.${type}`) }))}
          onChange={(next?: Filters['transport_type']) => onChange({ transport_type: next })} />
      </Form.Item>

      <Form.Item label={t('filters.dates')} htmlFor={id('dates')}>
        <DatePicker.RangePicker id={id('dates')} value={dates} format={DATE_FORMAT}
          placeholder={[t('filters.dateFrom'), t('filters.dateTo')]} style={{ width: '100%' }}
          onChange={(range) => onChange({
            date_from: range?.[0]?.format(ISO), date_to: range?.[1]?.format(ISO),
          })} />
      </Form.Item>

      <Form.Item label={t('filters.nights')} htmlFor={id('nights-min')}>
        <Flex gap={8} align="center">
          <InputNumber id={id('nights-min')} aria-label={t('filters.nightsFrom')}
            placeholder={t('filters.from')} min={NIGHTS_MIN} max={NIGHTS_MAX} precision={0}
            value={nightsMin} onChange={(next) => setNightsMin(number(next))} style={{ flex: 1 }} />
          <span aria-hidden>–</span>
          <InputNumber id={id('nights-max')} aria-label={t('filters.nightsTo')}
            placeholder={t('filters.to')} min={NIGHTS_MIN} max={NIGHTS_MAX} precision={0}
            value={nightsMax} onChange={(next) => setNightsMax(number(next))} style={{ flex: 1 }} />
        </Flex>
      </Form.Item>

      <Form.Item label={t('filters.price')} htmlFor={id('price-min')} extra={t('filters.priceHint')}>
        <Flex gap={8} align="center">
          <InputNumber id={id('price-min')} aria-label={t('filters.priceFrom')}
            placeholder={t('filters.from')} min={0} step={1000} precision={0}
            value={priceMin} onChange={(next) => setPriceMin(number(next))} style={{ flex: 1 }} />
          <span aria-hidden>–</span>
          <InputNumber id={id('price-max')} aria-label={t('filters.priceTo')}
            placeholder={t('filters.to')} min={0} step={1000} precision={0}
            value={priceMax} onChange={(next) => setPriceMax(number(next))} style={{ flex: 1 }} />
        </Flex>
      </Form.Item>

      <Form.Item label={<span id={id('stars-label')}>{t('filters.stars')}</span>}>
        <div role="group" aria-labelledby={id('stars-label')}>
          <Checkbox.Group value={value.stars}
            options={STAR_OPTIONS.map((stars) => ({ value: stars, label: t('filters.starsOption', { count: stars }) }))}
            onChange={(next) => onChange({ stars: [...next].sort() })} />
        </div>
      </Form.Item>

      <Form.Item>
        <Checkbox checked={value.has_seats === true}
          onChange={(event) => onChange({ has_seats: event.target.checked || undefined })}>
          {t('filters.hasSeats')}
        </Checkbox>
      </Form.Item>
    </Form>
  )
}
