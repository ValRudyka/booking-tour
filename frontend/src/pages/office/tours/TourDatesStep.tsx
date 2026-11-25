import { Alert, DatePicker, Form, InputNumber, Select, Space } from 'antd'
import type { Dayjs } from 'dayjs'
import { useTranslation } from 'react-i18next'
import type { Currency, ManagerTour, TourRules } from '../../../api/types'
import { isPositiveMoney, MONEY_PATTERN } from '../../../features/office/tourRules'
import { kyivTomorrow } from '../../../utils/format'
import { LockNote } from './TourBasicsStep'

const CURRENCIES: Currency[] = ['EUR', 'USD', 'UAH']
const DATE = 'YYYY-MM-DD'

interface Props {
  rules: TourRules
  locked: (field: string) => string | undefined
  /** The saved tour (undefined for a new one): its sold and held seats set the quota's minimum. */
  tour?: ManagerTour
}

/**
 * Step 3 «Дати, ціни, квота» (form 4.6.2.1, fields 10–15). One date range per tour (a single
 * date when both ends are the same); a different price period is a copy of the tour. Prices are
 * typed and sent as decimal strings (InputNumber stringMode), never floats.
 */
export function TourDatesStep({ rules, locked, tour }: Props) {
  const { t } = useTranslation()
  const tomorrow = kyivTomorrow()
  const datesLock = locked('departure_from') ?? locked('departure_to')
  const nightsLock = locked('nights')
  const minSeats = Math.max(1, (tour?.seats_sold ?? 0) + (tour?.seats_held ?? 0))
  const savedDates = tour ? [tour.departure_from, tour.departure_to].join('/') : null

  const money = (required: boolean) => [{
    validator: async (_: unknown, value?: string | null) => {
      const text = value === null || value === undefined ? '' : String(value).trim()
      if (!text) {
        if (required) throw new Error(t('office.tours.rule.basePrice'))
        return
      }
      if (!MONEY_PATTERN.test(text)) throw new Error(t('office.tours.rule.money'))
      if (required && !isPositiveMoney(text)) throw new Error(t('office.tours.rule.basePrice'))
    },
  }]

  return (
    <>
      <Alert type="info" showIcon role="note" title={t('office.tours.form.datesNote')} className="office-block" />
      <Space wrap align="start" size={[16, 0]} className="office-form-row">
        <Form.Item name="dates" label={t('office.tours.form.dates')}
          required
          extra={datesLock ? <LockNote reason={datesLock} /> : t('office.tours.form.datesHint')}
          rules={[{
            validator: async (_, value?: [Dayjs, Dayjs] | null) => {
              if (!value?.[0] || !value[1]) throw new Error(t('office.tours.rule.datesRequired'))
              // The saved range may already have begun; only a range the manager picks now must
              // start from tomorrow (the earliest start date a client can book).
              const picked = [value[0].format(DATE), value[1].format(DATE)].join('/')
              if (picked !== savedDates && value[0].format(DATE) < tomorrow) {
                throw new Error(t('office.tours.rule.datesPast'))
              }
            },
          }]}>
          <DatePicker.RangePicker format="DD.MM.YYYY" disabled={datesLock ? true : undefined}
            disabledDate={(day) => day.format(DATE) < tomorrow}
            placeholder={[t('office.filters.from'), t('office.filters.to')]} />
        </Form.Item>
        <Form.Item name="nights" label={t('office.tours.form.nights')}
          extra={nightsLock ? <LockNote reason={nightsLock} /> : t('office.tours.form.nightsHint', { min: rules.min_nights, max: rules.max_nights })}
          rules={[{ required: true, message: t('office.tours.rule.nights', { min: rules.min_nights, max: rules.max_nights }) },
            { type: 'number', min: rules.min_nights, max: rules.max_nights, message: t('office.tours.rule.nights', { min: rules.min_nights, max: rules.max_nights }) }]}>
          <InputNumber min={rules.min_nights} max={rules.max_nights} precision={0} disabled={nightsLock ? true : undefined} />
        </Form.Item>
      </Space>
      <Space wrap align="start" size={[16, 0]} className="office-form-row">
        <Form.Item name="base_price" label={t('office.tours.form.basePrice')} rules={money(true)}
          required
          extra={t('office.tours.form.basePriceHint')}>
          <InputNumber<string> stringMode min="0" precision={2} decimalSeparator="," className="office-money" />
        </Form.Item>
        <Form.Item name="child_price" label={t('office.tours.form.childPrice')} rules={money(false)}
          extra={t('office.tours.form.childPriceHint')}>
          <InputNumber<string> stringMode min="0" precision={2} decimalSeparator="," className="office-money" />
        </Form.Item>
        <Form.Item name="currency" label={t('office.tours.form.currency')} rules={[{ required: true }]}>
          <Select options={CURRENCIES.map((value) => ({ value, label: value }))} className="office-select-narrow" />
        </Form.Item>
      </Space>
      <Form.Item name="seats_total" label={t('office.tours.form.seats')}
        extra={tour ? t('office.tours.form.seatsUsed', { sold: tour.seats_sold, held: tour.seats_held }) : t('office.tours.form.seatsHint')}
        rules={[{ required: true, message: t('office.tours.rule.seats') },
          { type: 'number', min: minSeats, message: minSeats > 1 ? t('office.tours.rule.seatsUsed', { min: minSeats }) : t('office.tours.rule.seats') }]}>
        <InputNumber min={0} precision={0} />
      </Form.Item>
    </>
  )
}
