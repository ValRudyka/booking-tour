import { Alert, Button, Checkbox, Descriptions, Form, Typography } from 'antd'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import type { Price, ServiceOption, TourDetail } from '../../api/types'
import { formatDate, formatMoney, maskPassport } from '../../utils/format'
import type { BookingOrder } from './bookingForm'
import { PriceLines } from './BookingSummary'

/** Under this, card payment may not finish before the hold ends (the hold also covers payment). */
export const LOW_HOLD_MS = 5 * 60_000

interface Props {
  tour: TourDetail
  order: BookingOrder
  price: Price | null
  insurance: ServiceOption[] | undefined
  transfer: ServiceOption[] | undefined
  remaining: number | null
  busy: boolean
  onRestart: () => void
}

/** Step 4: everything once more, the offer consent (form 4.6.1.2, field 9), then confirm. */
export function StepReview({ tour, order, price, insurance, transfer, remaining, busy, onRestart }: Props) {
  const { t } = useTranslation()
  const none = t('checkout.review.none')
  const optionName = (list: ServiceOption[] | undefined, id: number | null) =>
    list?.find((o) => o.id === id)?.name_uk ?? none
  const departure = tour.transport_type === 'none' || !tour.departure_city ? t('tour.noTransport')
    : t(tour.transport_type === 'bus' ? 'tour.departureBus' : 'tour.departureAir', { city: tour.departure_city.name_uk })

  const items = [
    { key: 'number', label: t('checkout.review.number'), children: order.number },
    { key: 'tour', label: t('checkout.review.tour'), children: `${order.tour_title_uk} (${order.hotel_name})` },
    {
      key: 'dates', label: t('checkout.review.dates'),
      children: `${t('checkout.summary.dates', { from: formatDate(order.start_date), to: formatDate(order.end_date) })}, ${t('tour.nights', { count: tour.nights })}`,
    },
    { key: 'departure', label: t('checkout.review.departure'), children: departure },
    {
      key: 'tourists', label: t('checkout.review.tourists'),
      children: (
        <ul className="booking-review-tourists">
          {order.tourists.map((tourist) => (
            <li key={tourist.id}>
              {t('checkout.review.touristLine', {
                name: `${tourist.last_name_lat} ${tourist.first_name_lat}`, birth: formatDate(tourist.birth_date),
                passport: maskPassport(tourist.passport_number), expiry: formatDate(tourist.passport_expiry),
              })}
            </li>
          ))}
        </ul>
      ),
    },
    {
      key: 'insurance', label: t('checkout.review.insurance'),
      children: price?.insurance_name
        ? `${price.insurance_name}: ${t('checkout.summary.amount', { amount: formatMoney(price.insurance_uah) })}`
        : optionName(insurance, order.insurance_type_id),
    },
    {
      key: 'transfer', label: t('checkout.review.transfer'),
      children: price?.transfer_name
        ? `${price.transfer_name}: ${t('checkout.summary.amount', { amount: formatMoney(price.transfer_uah) })}`
        : optionName(transfer, order.transfer_type_id),
    },
    { key: 'promo', label: t('checkout.review.promo'), children: order.promo_code ?? none },
    { key: 'wishes', label: t('checkout.review.wishes'), children: order.wishes ?? none },
    {
      key: 'total', label: t('checkout.review.total'),
      children: price ? <PriceLines price={price} />
        : t('checkout.summary.amount', { amount: formatMoney(order.total_uah) }),
    },
  ]

  return (
    <>
      {remaining !== null && remaining > 0 && remaining < LOW_HOLD_MS && (
        <Alert type="warning" showIcon className="booking-block" title={t('checkout.review.lowTimeTitle')}
          description={t('checkout.review.lowTimeText')}
          action={<Button disabled={busy} onClick={onRestart}>{t('checkout.hold.restart')}</Button>} />
      )}
      <Descriptions bordered column={1} size="small" items={items} className="booking-review" />
      <Typography.Paragraph type="secondary" className="booking-review-note">
        {t('checkout.review.priceNote')}
      </Typography.Paragraph>
      <Form.Item name="accept" valuePropName="checked" rules={[{
        validator: (_, value?: boolean) => (value ? Promise.resolve()
          : Promise.reject(new Error(t('checkout.rules.consent')))),
      }]}>
        <Checkbox>
          {t('checkout.review.consentBefore')}
          <Link to="/terms" target="_blank" rel="noopener">{t('checkout.review.consentLink')}</Link>
        </Checkbox>
      </Form.Item>
    </>
  )
}
