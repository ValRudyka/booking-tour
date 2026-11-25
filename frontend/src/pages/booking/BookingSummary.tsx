import { Card, Collapse, Typography } from 'antd'
import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { mediaUrl } from '../../api/client'
import type { Price, TourDetail } from '../../api/types'
import { PhotoPlaceholder } from '../../components/PhotoPlaceholder'
import { mealLabel } from '../../i18n/labels'
import { PRICE_COLOR } from '../../theme'
import { formatDate, formatMoney, formatRate } from '../../utils/format'

interface Props {
  tour: TourDetail
  startDate: string | null
  endDate: string | null
  adults: number
  childCount: number
  /** From the server (quote before the order exists, the order's price after). Never computed here. */
  price: Price | null
  /** Under 768 px: a short «Разом: N ₴» panel that opens the details. */
  compact?: boolean
}

/** The summary next to the form (spec 04, §3). A large block, so it may use the sand background;
 * the price colour is below 4.5:1 on sand, so the total sits on a white box (theme.test.ts). */
export function BookingSummary({ tour, startDate, endDate, adults, childCount, price, compact }: Props) {
  const { t } = useTranslation()
  const titleId = useId()
  const details = <SummaryDetails tour={tour} startDate={startDate} endDate={endDate} adults={adults}
    childCount={childCount} price={price} />
  if (compact) {
    return (
      <Collapse className="booking-summary booking-summary-compact" items={[{
        key: 'summary',
        label: price ? t('checkout.summary.showDetails', { amount: formatMoney(price.total_uah) })
          : t('checkout.summary.pending'),
        children: details,
      }]} />
    )
  }
  return (
    <Card className="booking-summary" aria-labelledby={titleId}>
      <h2 id={titleId} className="booking-summary-title">{t('checkout.summary.title')}</h2>
      {details}
    </Card>
  )
}

function SummaryDetails({ tour, startDate, endDate, adults, childCount, price }: Omit<Props, 'compact'>) {
  const { t } = useTranslation()
  const image = mediaUrl(tour.image_url)
  const people = [t('checkout.summary.adults', { count: adults }),
    childCount > 0 ? t('checkout.summary.children', { count: childCount }) : null].filter(Boolean).join(', ')
  return (
    <>
      <div className="booking-summary-tour">
        {image ? <img src={image} alt="" className="booking-summary-photo" />
          : <PhotoPlaceholder height={72} className="booking-summary-photo" />}
        <div>
          <Typography.Text strong>{tour.title_uk}</Typography.Text>
          <div className="booking-summary-muted">
            {[tour.hotel.name, tour.meal_plan ? mealLabel(t, tour.meal_plan) : null].filter(Boolean).join(' · ')}
          </div>
        </div>
      </div>
      <dl className="booking-summary-facts">
        {startDate && endDate && (
          <>
            <dt>{t('checkout.review.dates')}</dt>
            <dd>
              {t('checkout.summary.dates', { from: formatDate(startDate), to: formatDate(endDate) })}
              {', '}{t('tour.nights', { count: tour.nights })}
            </dd>
          </>
        )}
        <dt>{t('checkout.review.tourists')}</dt>
        <dd>{people}</dd>
      </dl>
      <div className="booking-summary-price">
        {price ? <PriceLines price={price} /> : (
          <Typography.Text type="secondary">{t('checkout.summary.pending')}</Typography.Text>
        )}
      </div>
    </>
  )
}

/** Every line comes from the server's PriceOut as a decimal string; only formatted here. */
export function PriceLines({ price }: { price: Price }) {
  const { t } = useTranslation()
  const money = (value: string) => t('checkout.summary.amount', { amount: formatMoney(value) })
  return (
    <dl className="booking-price-lines">
      <dt>{t('checkout.summary.tour')}</dt>
      <dd>{money(price.tour_uah)}</dd>
      {price.insurance_name && (
        <><dt>{t('checkout.summary.insurance', { name: price.insurance_name })}</dt><dd>{money(price.insurance_uah)}</dd></>
      )}
      {price.transfer_name && (
        <><dt>{t('checkout.summary.transfer', { name: price.transfer_name })}</dt><dd>{money(price.transfer_uah)}</dd></>
      )}
      {price.promo_code && (
        <>
          <dt>{t('checkout.summary.discount', { code: price.promo_code })}</dt>
          <dd style={{ color: PRICE_COLOR }}>{t('checkout.summary.discountAmount', { amount: formatMoney(price.discount_uah) })}</dd>
        </>
      )}
      <dt className="booking-total-label">{t('checkout.summary.total')}</dt>
      <dd className="booking-total" style={{ color: PRICE_COLOR }} data-testid="booking-total">
        {money(price.total_uah)}
      </dd>
      {price.currency !== 'UAH' && (
        <dd className="booking-rate">{t('checkout.summary.rate', { currency: price.currency, rate: formatRate(price.rate) })}</dd>
      )}
    </dl>
  )
}
