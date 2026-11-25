import { Button, Card, DatePicker, Flex, Tag, Typography } from 'antd'
import dayjs from 'dayjs'
import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import type { TourDetail } from '../../api/types'
import { LOW_SEATS } from '../../components/TourCard'
import { mealLabel } from '../../i18n/labels'
import { PRICE_COLOR } from '../../theme'
import { formatDate, formatPrice } from '../../utils/format'
import { bookingBlock } from './bookingBlock'

const ISO = 'YYYY-MM-DD'

interface Props {
  tour: TourDetail
  /** First bookable start date (from tomorrow, Kyiv) or null when none is left. */
  firstDate: string | null
  date: string | null
  onDateChange: (date: string) => void
  onBook: () => void
}

/** Booking panel (spec §2): price, departure date, the facts, seats and «Забронювати». A large
 * block, so it may use the sand background (CLAUDE.md palette). */
export function BookingPanel({ tour, firstDate, date, onDateChange, onBook }: Props) {
  const { t } = useTranslation()
  const dateId = useId()
  const reasonId = useId()
  const block = bookingBlock(tour, date)
  const departure = tour.transport_type === 'none' || !tour.departure_city ? t('tour.noTransport')
    : t(tour.transport_type === 'bus' ? 'tour.departureBus' : 'tour.departureAir',
      { city: tour.departure_city.name_uk })

  return (
    <Card className="booking-panel" aria-labelledby={`${dateId}-title`}>
      <h2 id={`${dateId}-title`} className="visually-hidden">{t('booking.panel')}</h2>
      {/* White box: the price colour is below 4.5:1 on sand (theme.test.ts). */}
      <div className="booking-price-box">
        <div>
          <span className="booking-price" style={{ color: PRICE_COLOR }}>
            {t('tour.priceFrom', { price: formatPrice(tour.price_from_uah) })}
          </span>{' '}
          <Typography.Text type="secondary">{t('booking.perAdult')}</Typography.Text>
        </div>
        <Typography.Text type="secondary" className="booking-child">
          {t('booking.childPrice', { price: formatPrice(tour.child_price_uah) })}
        </Typography.Text>
      </div>

      <dl className="booking-facts">
        <dt><label htmlFor={dateId}>{t('booking.date')}</label></dt>
        <dd>
          {firstDate === null ? <Typography.Text>{t('booking.noDates')}</Typography.Text>
            : firstDate === tour.departure_to ? <span id={dateId}>{formatDate(firstDate)}</span>
              : (
                <DatePicker id={dateId} value={date ? dayjs(date, ISO) : null} format="DD.MM.YYYY"
                  allowClear={false} style={{ width: '100%' }}
                  disabledDate={(day) => day.isBefore(dayjs(firstDate, ISO), 'day')
                    || day.isAfter(dayjs(tour.departure_to, ISO), 'day')}
                  onChange={(value) => value && onDateChange(value.format(ISO))} />
              )}
        </dd>
        <dt>{t('booking.departure')}</dt>
        <dd>{departure}</dd>
        <dt>{t('booking.nights')}</dt>
        <dd>{t('tour.nights', { count: tour.nights })}</dd>
        {tour.meal_plan && (<><dt>{t('booking.meal')}</dt><dd>{mealLabel(t, tour.meal_plan)}</dd></>)}
        <dt>{t('booking.freeSeats')}</dt>
        <dd>
          {tour.free_seats}
          {tour.free_seats > 0 && tour.free_seats <= LOW_SEATS && (
            <> <Tag color="warning">{t('tour.seatsLeft', { count: tour.free_seats })}</Tag></>
          )}
        </dd>
      </dl>

      <Button type="primary" size="large" block disabled={block !== null} onClick={onBook}
        aria-describedby={block ? reasonId : undefined}>
        {t('booking.book')}
      </Button>
      {block && <Typography.Text id={reasonId} className="booking-reason">{t(`booking.${block}`)}</Typography.Text>}
    </Card>
  )
}

/** Mobile: price and «Забронювати» always visible at the bottom of the screen (spec §1). */
export function MobileBookingBar({ tour, date, onBook }: { tour: TourDetail; date: string | null; onBook: () => void }) {
  const { t } = useTranslation()
  const block = bookingBlock(tour, date)
  return (
    <div className="mobile-booking-bar" role="region" aria-label={t('booking.panel')}>
      <Flex justify="space-between" align="center" gap={12} className="mobile-booking-bar-inner">
        <div>
          <span className="booking-price" style={{ color: PRICE_COLOR }}>
            {t('tour.priceFrom', { price: formatPrice(tour.price_from_uah) })}
          </span>
          <div><Typography.Text type="secondary">{t('booking.perAdult')}</Typography.Text></div>
        </div>
        <Button type="primary" size="large" disabled={block !== null} onClick={onBook}>
          {t('booking.book')}
        </Button>
      </Flex>
    </div>
  )
}
