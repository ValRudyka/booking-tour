import dayjs, { type Dayjs } from 'dayjs'
import type { Currency, ManagerTour, MealPlan, TourCreate, TransportType } from '../../../api/types'
import { normalizeFlight, normalizeMoney } from '../../../features/office/tourRules'

// The tour editor's form values and their mapping to the API (form 4.6.2.1). Country and resort
// are not tour fields: they only narrow the hotel list (the hotel decides both). Prices stay
// decimal strings from the API to the API (InputNumber stringMode), never floats.

export interface ProgramDayValue { description: string }

export interface TourFormValues {
  title_uk?: string
  title_en?: string
  country_id?: number
  resort_id?: number
  hotel_id?: number
  transport_type?: TransportType
  departure_city_id?: number | null
  flight_out?: string
  flight_back?: string
  meal_plan?: MealPlan | null
  is_featured: boolean
  description?: string
  included: string[]
  excluded: string[]
  program_days: ProgramDayValue[]
  dates?: [Dayjs, Dayjs] | null
  nights?: number | null
  base_price?: string | null
  child_price?: string | null
  currency?: Currency
  seats_total?: number | null
}

export const STEPS = ['basics', 'program', 'dates', 'photos', 'summary'] as const
export type StepKey = typeof STEPS[number]

/** Fields validated by «Далі» on each step (photos and summary have none). */
export const STEP_FIELDS: Record<StepKey, (keyof TourFormValues)[]> = {
  basics: ['title_uk', 'title_en', 'country_id', 'resort_id', 'hotel_id', 'transport_type',
    'departure_city_id', 'flight_out', 'flight_back', 'meal_plan', 'description', 'included', 'excluded'],
  program: ['program_days'],
  dates: ['dates', 'nights', 'base_price', 'child_price', 'currency', 'seats_total'],
  photos: [],
  summary: [],
}

/** The step of a field the server named (`loc`), to open it with the error. */
export function stepOfField(field: string): StepKey | undefined {
  if (field === 'departure_from' || field === 'departure_to') return 'dates'
  return STEPS.find((step) => (STEP_FIELDS[step] as string[]).includes(field))
}

/** Form field name of an API field (the two dates are one RangePicker). */
export function formFieldOf(field: string): keyof TourFormValues {
  return (field === 'departure_from' || field === 'departure_to' ? 'dates' : field) as keyof TourFormValues
}

export const EMPTY_VALUES: TourFormValues = {
  transport_type: 'air', currency: 'EUR', is_featured: false, included: [], excluded: [], program_days: [],
  meal_plan: null, departure_city_id: null, nights: 7,
}

const DATE = 'YYYY-MM-DD'

export function valuesOf(tour: ManagerTour): TourFormValues {
  return {
    title_uk: tour.title_uk,
    title_en: tour.title_en,
    country_id: tour.hotel.country_id,
    resort_id: tour.hotel.resort_id,
    hotel_id: tour.hotel_id,
    transport_type: tour.transport_type,
    departure_city_id: tour.departure_city_id,
    flight_out: tour.flight_out ?? '',
    flight_back: tour.flight_back ?? '',
    meal_plan: tour.meal_plan,
    is_featured: tour.is_featured,
    description: tour.description ?? '',
    included: [...tour.included],
    excluded: [...tour.excluded],
    program_days: tour.program_days.map((day) => ({ description: day.description })),
    dates: [dayjs(tour.departure_from), dayjs(tour.departure_to)],
    nights: tour.nights,
    base_price: tour.base_price,
    child_price: tour.child_price,
    currency: tour.currency,
    seats_total: tour.seats_total,
  }
}

const text = (value: string | undefined | null) => value?.trim() ?? ''
const optionalMoney = (value: string | null | undefined) => {
  const cleaned = value ? normalizeMoney(String(value)) : ''
  return cleaned === '' ? null : cleaned
}

/**
 * The request body for POST / PATCH (the editor always sends the whole form: locked fields go
 * unchanged, which the server accepts). Program days are numbered by their position, so adding,
 * removing or moving a day renumbers them. Flight numbers are sent only for air.
 */
export function payloadOf(values: TourFormValues): TourCreate {
  const air = values.transport_type === 'air'
  const flight = (value?: string) => (air && text(value) ? normalizeFlight(text(value)) : null)
  return {
    title_uk: text(values.title_uk) || null,
    title_en: text(values.title_en),
    hotel_id: values.hotel_id as number,
    transport_type: values.transport_type as TransportType,
    departure_city_id: values.transport_type === 'none' ? null : values.departure_city_id ?? null,
    flight_out: flight(values.flight_out),
    flight_back: flight(values.flight_back),
    departure_from: values.dates?.[0]?.format(DATE) as string,
    departure_to: values.dates?.[1]?.format(DATE) as string,
    nights: values.nights as number,
    seats_total: values.seats_total as number,
    base_price: optionalMoney(values.base_price) as string,
    child_price: optionalMoney(values.child_price),
    currency: values.currency as Currency,
    description: text(values.description) || null,
    is_featured: values.is_featured,
    meal_plan: values.meal_plan ?? null,
    included: (values.included ?? []).map(text).filter(Boolean),
    excluded: (values.excluded ?? []).map(text).filter(Boolean),
    program_days: (values.program_days ?? []).map((day, index) => ({ day_number: index + 1, description: text(day.description) })),
  }
}

/** Unsaved changes = the request the form would send differs from the saved tour's. */
export function sameTour(a: TourFormValues, b: TourFormValues): boolean {
  return JSON.stringify(payloadOf(a)) === JSON.stringify(payloadOf(b))
}
