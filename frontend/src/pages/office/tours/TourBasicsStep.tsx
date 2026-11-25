import { DeleteOutlined, LockOutlined, PlusOutlined } from '@ant-design/icons'
import { Button, Checkbox, Form, Input, Radio, Select, Space } from 'antd'
import type { FormInstance } from 'antd'
import { useTranslation } from 'react-i18next'
import { useCities, useCountries, useHotels, useResorts } from '../../../api/reference'
import type { ManagerTourHotel, MealPlan, TourRules, TransportType } from '../../../api/types'
import { mealLabel } from '../../../i18n/labels'
import { FLIGHT_PATTERN, normalizeFlight } from '../../../features/office/tourRules'
import type { TourFormValues } from './tourForm'

const TRANSPORTS: TransportType[] = ['air', 'bus', 'none']
const MEALS: MealPlan[] = ['ro', 'bb', 'hb', 'fb', 'ai', 'uai']

/** Help text of a locked field: the server's reason (services/tours.py lock_reason). */
export function LockNote({ reason }: { reason: string }) {
  return <span className="office-lock-note"><LockOutlined aria-hidden /> {reason}</span>
}

interface StepProps {
  form: FormInstance<TourFormValues>
  rules: TourRules
  /** The server's reason per locked field (empty when nothing is locked). */
  locked: (field: string) => string | undefined
  /** The saved hotel, shown even when the reference lists no longer offer it (archived). */
  savedHotel?: ManagerTourHotel
}

/** Step 1 «Основне» (form 4.6.2.1 fields 1–9, 16, 19, 21–23). */
export function TourBasicsStep({ form, rules, locked, savedHotel }: StepProps) {
  const { t } = useTranslation()
  const countryId = Form.useWatch('country_id', form)
  const resortId = Form.useWatch('resort_id', form)
  const hotelId = Form.useWatch('hotel_id', form)
  const transport = Form.useWatch('transport_type', form)
  const countries = useCountries()
  const resorts = useResorts(countryId)
  const hotels = useHotels(resortId)
  const cities = useCities()

  const hotelLock = locked('hotel_id')
  const archived = t('office.tours.form.archivedOption')
  // An archived saved hotel (or its resort or country) is not in the reference lists: add it,
  // marked, so the form shows what the tour has.
  const withSaved = <T extends { value: number; label: string }>(options: T[], id: number | undefined, label: string) =>
    id !== undefined && !options.some((o) => o.value === id) ? [...options, { value: id, label: `${label} ${archived}` } as T] : options
  const countryOptions = withSaved((countries.data ?? []).map((c) => ({ value: c.id, label: c.name_uk })),
    savedHotel?.country_id === countryId ? savedHotel?.country_id : undefined, savedHotel?.country_name ?? '')
  const resortOptions = withSaved((resorts.data ?? []).map((r) => ({ value: r.id, label: r.name_uk })),
    savedHotel?.resort_id === resortId ? savedHotel?.resort_id : undefined, savedHotel?.resort_name ?? '')
  const hotelOptions = withSaved((hotels.data ?? []).map((h) => ({
    value: h.id, label: h.stars ? `${h.name} ${'*'.repeat(h.stars)}` : h.name,
  })), savedHotel?.id === hotelId ? savedHotel?.id : undefined, savedHotel?.name ?? '')

  // Form 4.6.2.1 field 1: an empty Ukrainian title becomes «Готель, Курорт» on the server.
  const hotelName = hotelOptions.find((o) => o.value === hotelId)?.label.replace(/ \*+$/, '')
  const resortName = resortOptions.find((o) => o.value === resortId)?.label
  const autoTitle = hotelName && resortName ? `${hotelName}, ${resortName}` : undefined

  const lockedItem = (field: string) => {
    const reason = locked(field)
    return reason ? { extra: <LockNote reason={reason} /> } : {}
  }

  return (
    <>
      <Form.Item name="title_uk" label={t('office.tours.form.titleUk')}
        extra={locked('title_uk') ? <LockNote reason={locked('title_uk')!} /> : t('office.tours.form.titleUkHint')}
        rules={[{ max: rules.max_title, message: t('office.tours.rule.title', { max: rules.max_title }) }]}>
        <Input maxLength={rules.max_title} disabled={locked('title_uk') ? true : undefined} placeholder={autoTitle} />
      </Form.Item>
      <Form.Item name="title_en" label={t('office.tours.form.titleEn')} {...lockedItem('title_en')}
        rules={[{ required: true, whitespace: true, message: t('office.tours.rule.titleEn') },
          { max: rules.max_title, message: t('office.tours.rule.title', { max: rules.max_title }) }]}>
        <Input maxLength={rules.max_title} disabled={locked('title_en') ? true : undefined} lang="en" />
      </Form.Item>

      <Space wrap align="start" size={[16, 0]} className="office-form-row">
        <Form.Item name="country_id" label={t('office.tours.form.country')} {...(hotelLock ? { extra: <LockNote reason={hotelLock} /> } : {})}
          rules={[{ required: true, message: t('office.tours.rule.country') }]}>
          <Select showSearch optionFilterProp="label" options={countryOptions} disabled={hotelLock ? true : undefined}
            loading={countries.isLoading} className="office-select" placeholder={t('office.tours.form.choose')} />
        </Form.Item>
        <Form.Item name="resort_id" label={t('office.tours.form.resort')}
          rules={[{ required: true, message: t('office.tours.rule.resort') }]}>
          <Select showSearch optionFilterProp="label" options={resortOptions} disabled={hotelLock || countryId === undefined ? true : undefined}
            loading={resorts.isLoading && countryId !== undefined} className="office-select"
            placeholder={countryId === undefined ? t('office.tours.form.countryFirst') : t('office.tours.form.choose')} />
        </Form.Item>
        <Form.Item name="hotel_id" label={t('office.tours.form.hotel')}
          rules={[{ required: true, message: t('office.tours.rule.hotel') }]}>
          <Select showSearch optionFilterProp="label" options={hotelOptions} disabled={hotelLock || resortId === undefined ? true : undefined}
            loading={hotels.isLoading && resortId !== undefined} className="office-select-wide"
            placeholder={resortId === undefined ? t('office.tours.form.resortFirst') : t('office.tours.form.choose')} />
        </Form.Item>
      </Space>

      <Form.Item name="transport_type" label={t('office.tours.form.transport')} {...lockedItem('transport_type')}
        rules={[{ required: true }]}>
        <Radio.Group disabled={locked('transport_type') ? true : undefined}
          options={TRANSPORTS.map((value) => ({ value, label: t(`transport.${value}`) }))} />
      </Form.Item>
      {transport !== 'none' && (
        <Form.Item name="departure_city_id" label={t('office.tours.form.departureCity')} {...lockedItem('departure_city_id')}
          rules={[{ required: true, message: t('office.tours.rule.departureCity') }]}>
          <Select showSearch optionFilterProp="label" disabled={locked('departure_city_id') ? true : undefined} className="office-select"
            options={(cities.data ?? []).map((c) => ({ value: c.id, label: c.name_uk }))} placeholder={t('office.tours.form.choose')} />
        </Form.Item>
      )}
      {transport === 'air' && (
        <Space wrap align="start" size={[16, 0]} className="office-form-row">
          {(['flight_out', 'flight_back'] as const).map((name) => (
            <Form.Item key={name} name={name} label={t(`office.tours.form.${name}`)} extra={t('office.tours.form.flightHint')}
              normalize={(value: string) => value.toUpperCase()}
              rules={[{
                validator: (_, value?: string) => !value?.trim() || FLIGHT_PATTERN.test(normalizeFlight(value))
                  ? Promise.resolve() : Promise.reject(new Error(t('office.tours.rule.flight'))),
              }]}>
              <Input maxLength={10} className="office-select" lang="en" />
            </Form.Item>
          ))}
        </Space>
      )}

      <Form.Item name="meal_plan" label={t('office.tours.form.meal')}
        extra={locked('meal_plan') ? <LockNote reason={locked('meal_plan')!} /> : t('office.tours.form.mealHint')}>
        <Select allowClear disabled={locked('meal_plan') ? true : undefined} className="office-select" placeholder={t('office.tours.form.noMeal')}
          options={MEALS.map((value) => ({ value, label: mealLabel(t, value) }))} />
      </Form.Item>
      <Form.Item name="is_featured" valuePropName="checked" extra={t('office.tours.form.featuredHint')}>
        <Checkbox>{t('office.tours.form.featured')}</Checkbox>
      </Form.Item>
      <Form.Item name="description" label={t('office.tours.form.description')}
        rules={[{ max: rules.max_description, message: t('office.tours.rule.description', { max: rules.max_description }) }]}>
        <Input.TextArea rows={6} maxLength={rules.max_description} showCount className="office-textarea" />
      </Form.Item>

      <TextList name="included" label={t('office.tours.form.included')} hint={t('office.tours.form.includedHint')} rules={rules} />
      <TextList name="excluded" label={t('office.tours.form.excluded')} hint={t('office.tours.form.excludedHint')} rules={rules} />
    </>
  )
}

/** «Що включено» / «Що не включено»: short lines (services/text_lists.py limits from the API). */
function TextList({ name, label, hint, rules }: { name: 'included' | 'excluded'; label: string; hint: string; rules: TourRules }) {
  const { t } = useTranslation()
  return (
    <Form.Item label={label} extra={hint} required={false}>
      <Form.List name={name}>
        {(items, { add, remove }) => (
          <Space orientation="vertical" className="office-full-width">
            {items.map((item, index) => (
              <Space key={item.key} align="start" className="office-list-row">
                <Form.Item name={item.name} noStyle
                  rules={[{ max: rules.max_list_item_length, message: t('office.tours.rule.listItem', { max: rules.max_list_item_length }) }]}>
                  <Input maxLength={rules.max_list_item_length} aria-label={t('office.tours.form.listItem', { label, n: index + 1 })} />
                </Form.Item>
                <Button icon={<DeleteOutlined aria-hidden />} onClick={() => remove(item.name)}
                  aria-label={t('office.tours.form.removeItem', { label, n: index + 1 })} />
              </Space>
            ))}
            <Button icon={<PlusOutlined aria-hidden />} onClick={() => add('')} disabled={items.length >= rules.max_list_items || undefined}>
              {t('office.tours.form.addItem')}
            </Button>
          </Space>
        )}
      </Form.List>
    </Form.Item>
  )
}
