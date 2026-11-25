// The tabs' content of the tour page: description (with the included lists), programme, hotel.
import { CheckOutlined, CloseOutlined } from '@ant-design/icons'
import { Descriptions, Empty, Flex, Timeline, Typography } from 'antd'
import type { DescriptionsProps } from 'antd'
import { useTranslation } from 'react-i18next'
import type { TourDetail } from '../../api/types'
import { StarIcons } from '../../components/StarIcons'
import { formatInteger, formatRating, formatTime } from '../../utils/format'

function TextBlock({ text }: { text: string }) {
  return <Typography.Paragraph className="tour-text">{text}</Typography.Paragraph>
}

function CheckList({ title, items, kind }: { title: string; items: string[]; kind: 'yes' | 'no' }) {
  if (items.length === 0) return null      // an empty list is not shown at all
  const Icon = kind === 'yes' ? CheckOutlined : CloseOutlined
  return (
    <section className="tour-checklist">
      <h3 className="tour-subheading">{title}</h3>
      <ul className={`tour-checklist-items tour-checklist-${kind}`}>
        {items.map((item) => <li key={item}><Icon aria-hidden /> <span>{item}</span></li>)}
      </ul>
    </section>
  )
}

/** «Опис»: the tour description, transport, and what the price includes (form 4.6.2.1, 21–23).
 * The lists are shown as the API gives them: insurance and transfer are already listed under
 * "not included" (chosen at checkout). */
export function DescriptionTab({ tour }: { tour: TourDetail }) {
  const { t } = useTranslation()
  const flights = tour.flight_out && tour.flight_back
    ? t('tourPage.flights', { out: tour.flight_out, back: tour.flight_back }) : null
  return (
    <Flex vertical gap={16}>
      {tour.description ? <TextBlock text={tour.description} /> : <Typography.Text type="secondary">{t('tourPage.noDescription')}</Typography.Text>}
      <div>
        <h3 className="tour-subheading">{t('tourPage.transport')}</h3>
        <Typography.Text>
          {t(`transport.${tour.transport_type}`)}
          {tour.departure_city ? ` · ${tour.departure_city.name_uk}` : ''}
          {flights ? ` · ${flights}` : ''}
        </Typography.Text>
      </div>
      <div className="tour-checklists">
        <CheckList title={t('tourPage.included')} items={tour.included} kind="yes" />
        <CheckList title={t('tourPage.excluded')} items={tour.excluded} kind="no" />
      </div>
    </Flex>
  )
}

/** «Програма»: day by day (form 4.6.2.1, field 17). The API has no day titles, so «День N». */
export function ProgramTab({ tour }: { tour: TourDetail }) {
  const { t } = useTranslation()
  if (tour.program_days.length === 0) return <Empty description={t('tourPage.noProgram')} />
  return (
    <Timeline items={tour.program_days.map((day) => ({
      key: day.day_number,
      title: <strong>{t('tourPage.day', { n: day.day_number })}</strong>,
      content: <span className="tour-text">{day.description}</span>,
    }))} />
  )
}

/** «Готель»: a table of the hotel's facts (form 4.6.4.2) — only the rows that have a value —
 * then the hotel description as text. */
export function HotelTab({ tour }: { tour: TourDetail }) {
  const { t } = useTranslation()
  const hotel = tour.hotel
  const rows: DescriptionsProps['items'] = [
    { key: 'name', label: t('hotel.name'), children: hotel.name },
    hotel.stars ? {
      key: 'stars', label: t('hotel.stars'),
      children: <StarIcons value={hotel.stars} label={t('tour.stars', { count: hotel.stars })} />,
    } : null,
    { key: 'location', label: t('hotel.location'), children: `${tour.country.name_uk}, ${tour.resort.name_uk}` },
    { key: 'rating', label: t('hotel.rating'),
      children: hotel.rating_avg !== null ? t('reviews.scoreValue', { rating: formatRating(hotel.rating_avg) })
        : t('hotel.noRating') },
    hotel.beach_line ? { key: 'beachLine', label: t('hotel.beachLine'),
      children: t(`hotel.beachLines.${hotel.beach_line}` as 'hotel.beachLines.1') } : null,
    hotel.distance_to_beach_m !== null ? { key: 'toBeach', label: t('hotel.toBeach'),
      children: hotel.distance_to_beach_m === 0 ? t('hotel.onTheBeach')
        : t('hotel.meters', { value: formatInteger(hotel.distance_to_beach_m) }) } : null,
    hotel.distance_to_airport_km !== null ? { key: 'toAirport', label: t('hotel.toAirport'),
      children: t('hotel.kilometers', { value: formatInteger(hotel.distance_to_airport_km) }) } : null,
    hotel.check_in ? { key: 'checkIn', label: t('hotel.checkIn'),
      children: t('hotel.checkInAt', { time: formatTime(hotel.check_in) }) } : null,
    hotel.check_out ? { key: 'checkOut', label: t('hotel.checkOut'),
      children: t('hotel.checkOutAt', { time: formatTime(hotel.check_out) }) } : null,
    hotel.amenities.length > 0 ? { key: 'amenities', label: t('hotel.amenities'),
      children: <ul className="tour-plain-list">{hotel.amenities.map((a) => <li key={a}>{a}</li>)}</ul> } : null,
    hotel.room_types.length > 0 ? { key: 'roomTypes', label: t('hotel.roomTypes'),
      children: <ul className="tour-plain-list">{hotel.room_types.map((r) => <li key={r}>{r}</li>)}</ul> } : null,
  ].filter((row) => row !== null)

  return (
    <Flex vertical gap={16}>
      <Descriptions bordered size="small" column={1} items={rows} className="tour-hotel-facts" />
      {tour.hotel_description && (
        <section>
          <h3 className="tour-subheading">{t('hotel.about')}</h3>
          <TextBlock text={tour.hotel_description} />
        </section>
      )}
    </Flex>
  )
}
