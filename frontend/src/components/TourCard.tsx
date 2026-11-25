import {
  CalendarOutlined, CarOutlined, EnvironmentOutlined, MoonOutlined, SendOutlined, StarFilled,
} from '@ant-design/icons'
import { Card, Flex, Tag, Typography } from 'antd'
import { useTranslation } from 'react-i18next'
import { Link, useLocation } from 'react-router'
import { mediaUrl } from '../api/client'
import type { TourCard as TourCardData } from '../api/types'
import { mealLabel } from '../i18n/labels'
import { PRICE_COLOR } from '../theme'
import { PhotoPlaceholder } from './PhotoPlaceholder'
import { formatDate, formatPrice, formatRating, nearestBookableDate } from '../utils/format'
import './TourCard.css'

/** Free seats at or below this number get the "Залишилось N місць" tag. */
export const LOW_SEATS = 3

/** Router state of a link from the catalog to a tour page. */
export interface TourLinkState {
  catalogSearch: string
}

function Departure({ tour }: { tour: TourCardData }) {
  const { t } = useTranslation()
  if (tour.transport_type === 'none' || !tour.departure_city) {
    return <span>{t('tour.noTransport')}</span>
  }
  const city = tour.departure_city.name_uk
  return tour.transport_type === 'bus'
    ? <span><CarOutlined aria-hidden /> {t('tour.departureBus', { city })}</span>
    : <span><SendOutlined aria-hidden /> {t('tour.departureAir', { city })}</span>
}

/** One tour in the catalog grid (spec §4 "Картка туру"). The whole card is one link. */
export function TourCard({ tour }: { tour: TourCardData }) {
  const { t } = useTranslation()
  // The catalog's filters travel with the link, so the tour page's «Каталог» crumb returns to them.
  const { search } = useLocation()
  const image = mediaUrl(tour.image_url)
  const stars = tour.hotel.stars
  const rating = tour.hotel.rating_avg
  const nearest = nearestBookableDate(tour.departure_from, tour.departure_to)

  const cover = image
    ? <img className="tour-card-image" src={image} alt={tour.title_uk} loading="lazy" />
    : <PhotoPlaceholder className="tour-card-image" />

  return (
    <Link to={`/tours/${tour.id}`} state={{ catalogSearch: search } satisfies TourLinkState}
      className="tour-card-link">
      <Card hoverable cover={cover} className="tour-card" styles={{ body: { padding: 16 } }}>
        <Flex vertical gap={6}>
          <h2 className="tour-card-title">{tour.title_uk}</h2>

          <Typography.Text type="secondary">
            <EnvironmentOutlined aria-hidden /> {tour.country.name_uk}, {tour.resort.name_uk}
          </Typography.Text>

          <Flex gap={8} align="center" wrap>
            <Typography.Text>{tour.hotel.name}</Typography.Text>
            {stars ? (
              <span role="img" aria-label={t('tour.stars', { count: stars })} className="tour-card-stars">
                {Array.from({ length: stars }, (_, index) => <StarFilled key={index} aria-hidden />)}
              </span>
            ) : null}
          </Flex>

          <Typography.Text type="secondary" className="tour-card-facts">
            <span><MoonOutlined aria-hidden /> {t('tour.nights', { count: tour.nights })}</span>
            {nearest && (
              <span>
                <CalendarOutlined aria-hidden /> {t('tour.nearestDate', { date: formatDate(nearest) })}
              </span>
            )}
            <Departure tour={tour} />
          </Typography.Text>

          <Typography.Text>
            {rating !== null ? t('tour.rating', { rating: formatRating(rating) }) : t('tour.noReviews')}
          </Typography.Text>

          {tour.meal_plan && <div><Tag>{mealLabel(t, tour.meal_plan)}</Tag></div>}

          {tour.free_seats === 0 ? <div><Tag color="error">{t('tour.noSeats')}</Tag></div>
            : tour.free_seats <= LOW_SEATS
              ? <div><Tag color="warning">{t('tour.seatsLeft', { count: tour.free_seats })}</Tag></div>
              : null}

          <div className="tour-card-price">
            <span style={{ color: PRICE_COLOR }} className="tour-card-price-value">
              {t('tour.priceFrom', { price: formatPrice(tour.price_from_uah) })}
            </span>{' '}
            <Typography.Text type="secondary">{t('tour.perAdult')}</Typography.Text>
          </div>
        </Flex>
      </Card>
    </Link>
  )
}
