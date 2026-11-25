import { Descriptions, Typography } from 'antd'
import type { DescriptionsProps } from 'antd'
import { useTranslation } from 'react-i18next'
import { useCities, useCountries, useHotels, useResorts } from '../../../api/reference'
import type { ManagerTour } from '../../../api/types'
import { mealLabel } from '../../../i18n/labels'
import { formatDate, formatMoney } from '../../../utils/format'
import type { TourFormValues } from './tourForm'
import { payloadOf } from './tourForm'

/** Step 5 «Перевірка»: everything the form will send, as the API will get it (payloadOf). */
export function TourSummaryStep({ values, tour }: { values: TourFormValues; tour?: ManagerTour }) {
  const { t } = useTranslation()
  const body = payloadOf(values)
  const countries = useCountries()
  const resorts = useResorts(values.country_id)
  const hotels = useHotels(values.resort_id)
  const cities = useCities()
  const none = t('office.order.none')

  const country = countries.data?.find((c) => c.id === values.country_id)?.name_uk
    ?? (tour?.hotel.country_id === values.country_id ? tour?.hotel.country_name : undefined)
  const resort = resorts.data?.find((r) => r.id === values.resort_id)?.name_uk
    ?? (tour?.hotel.resort_id === values.resort_id ? tour?.hotel.resort_name : undefined)
  const hotel = hotels.data?.find((h) => h.id === body.hotel_id)?.name
    ?? (tour?.hotel.id === body.hotel_id ? tour?.hotel.name : undefined)
  const city = cities.data?.find((c) => c.id === body.departure_city_id)?.name_uk
  const price = (value: string | null | undefined) => value ? `${formatMoney(value)} ${body.currency ?? ''}`.trim() : none
  const list = (items: string[]) => items.length > 0 ? <ul className="office-plain-list">{items.map((i) => <li key={i}>{i}</li>)}</ul> : none

  const items: DescriptionsProps['items'] = [
    { key: 'title_uk', label: t('office.tours.form.titleUk'), children: body.title_uk ?? (hotel && resort ? `${hotel}, ${resort}` : none) },
    { key: 'title_en', label: t('office.tours.form.titleEn'), children: body.title_en || none },
    { key: 'place', label: t('office.order.place'), children: [country, resort].filter(Boolean).join(', ') || none },
    { key: 'hotel', label: t('office.tours.form.hotel'), children: hotel ?? none },
    { key: 'transport', label: t('office.tours.form.transport'), children: body.transport_type ? t(`transport.${body.transport_type}`) : none },
    { key: 'city', label: t('office.tours.form.departureCity'), children: city ?? none },
    { key: 'flights', label: t('office.tours.summary.flights'), children: [body.flight_out, body.flight_back].filter(Boolean).join(' / ') || none },
    { key: 'meal', label: t('office.tours.form.meal'), children: body.meal_plan ? mealLabel(t, body.meal_plan) : t('office.tours.form.noMeal') },
    { key: 'featured', label: t('office.tours.form.featured'), children: body.is_featured ? t('office.tours.summary.yes') : t('office.tours.summary.no') },
    {
      key: 'dates', label: t('office.tours.form.dates'),
      children: body.departure_from && body.departure_to ? `${formatDate(body.departure_from)} – ${formatDate(body.departure_to)}` : none,
    },
    { key: 'nights', label: t('office.tours.form.nights'), children: body.nights ?? none },
    { key: 'base', label: t('office.tours.form.basePrice'), children: price(body.base_price as string | null) },
    { key: 'child', label: t('office.tours.form.childPrice'), children: body.child_price ? price(body.child_price as string) : t('office.tours.summary.asAdult') },
    { key: 'seats', label: t('office.tours.form.seats'), children: body.seats_total ?? none },
    { key: 'photos', label: t('office.tours.summary.photos'), children: tour ? tour.images.length : t('office.tours.summary.photosLater') },
    { key: 'included', label: t('office.tours.form.included'), span: 'filled', children: list(body.included ?? []) },
    { key: 'excluded', label: t('office.tours.form.excluded'), span: 'filled', children: list(body.excluded ?? []) },
    {
      key: 'description', label: t('office.tours.form.description'), span: 'filled',
      children: body.description ? <Typography.Paragraph className="office-pre">{body.description}</Typography.Paragraph> : none,
    },
    {
      key: 'program', label: t('office.tours.summary.program'), span: 'filled',
      children: body.program_days && body.program_days.length > 0 ? (
        <ol className="office-plain-list">
          {body.program_days.map((day) => <li key={day.day_number}>{t('office.tours.form.day', { n: day.day_number })}: {day.description}</li>)}
        </ol>
      ) : none,
    },
  ]

  return <Descriptions bordered size="small" column={{ xs: 1, md: 2 }} items={items} />
}
