import dayjs, { type Dayjs } from 'dayjs'
import type { OrderDetailWithPrice, Tourist, TouristIn } from '../../api/types'
import type { BookingDraft, DraftTourist } from '../../features/booking/bookingDraft'
import { cleanName, cleanPassportNumber } from '../../features/booking/bookingRules'

export const ISO = 'YYYY-MM-DD'
export const DATE_FORMAT = 'DD.MM.YYYY'

/** The order the wizard works on: create / PATCH return it with a price, GET may return price null. */
export type BookingOrder = OrderDetailWithPrice

export interface TouristValues {
  last_name_lat?: string
  first_name_lat?: string
  birth_date?: Dayjs | null
  passport_number?: string
  passport_expiry?: Dayjs | null
}

/** One antd Form across the four steps; hidden steps keep their values. */
export interface BookingValues {
  date?: Dayjs | null
  adults?: number | null
  children?: number | null
  tourists?: TouristValues[]
  insurance_type_id?: number | null
  transfer_type_id?: number | null
  promo?: string
  wishes?: string
  accept?: boolean
}

const toIso = (value: Dayjs | null | undefined) => (value ? value.format(ISO) : null)
const fromIso = (value: string | null | undefined) => (value ? dayjs(value, ISO) : null)

/** The list follows the numbers of adults and children: kept values stay, new slots are empty. */
export function resizeTourists(list: TouristValues[] | undefined, count: number): TouristValues[] {
  const result = (list ?? []).slice(0, count)
  while (result.length < count) result.push({})
  return result
}

/** Form values -> the API body (names and passport cleaned like the backend does). */
export function toTouristsIn(list: TouristValues[]): TouristIn[] {
  return list.map((t) => ({
    last_name_lat: cleanName(t.last_name_lat ?? ''),
    first_name_lat: cleanName(t.first_name_lat ?? ''),
    birth_date: toIso(t.birth_date) ?? '',
    passport_number: cleanPassportNumber(t.passport_number ?? ''),
    passport_expiry: toIso(t.passport_expiry) ?? '',
  }))
}

export function fromServerTourists(list: Tourist[]): TouristValues[] {
  return list.map((t) => ({
    last_name_lat: t.last_name_lat,
    first_name_lat: t.first_name_lat,
    birth_date: fromIso(t.birth_date),
    passport_number: t.passport_number,
    passport_expiry: fromIso(t.passport_expiry),
  }))
}

function fromDraftTourists(list: DraftTourist[]): TouristValues[] {
  return list.map((t) => ({
    last_name_lat: t.last_name_lat, first_name_lat: t.first_name_lat,
    birth_date: fromIso(t.birth_date), passport_expiry: fromIso(t.passport_expiry),
  }))
}

/** Form values -> the stored draft. Passport numbers are left out here and again in saveDraft. */
export function toDraft(values: BookingValues, step: number, orderId: number | null): BookingDraft {
  return {
    step, orderId,
    date: toIso(values.date),
    adults: values.adults ?? 1,
    children: values.children ?? 0,
    tourists: (values.tourists ?? []).map((t) => ({
      last_name_lat: t.last_name_lat, first_name_lat: t.first_name_lat,
      birth_date: toIso(t.birth_date), passport_expiry: toIso(t.passport_expiry),
    })),
    insurance_type_id: values.insurance_type_id ?? null,
    transfer_type_id: values.transfer_type_id ?? null,
    promo: values.promo ?? '',
    wishes: values.wishes ?? '',
  }
}

/**
 * Starting values: the order on the server wins (its date, numbers, tourists with passports,
 * services), then the draft, then the date from the tour page. `date` is already checked to be
 * bookable by the caller.
 */
export function initialValues(order: BookingOrder | null, draft: BookingDraft | null,
  date: string | null): BookingValues {
  if (order) {
    const tourists = order.tourists.length ? fromServerTourists(order.tourists)
      : fromDraftTourists(draft?.tourists ?? [])
    return {
      date: fromIso(order.start_date), adults: order.adults, children: order.children,
      tourists: resizeTourists(tourists, order.adults + order.children),
      insurance_type_id: order.insurance_type_id, transfer_type_id: order.transfer_type_id,
      promo: order.promo_code ?? draft?.promo ?? '', wishes: order.wishes ?? draft?.wishes ?? '',
      accept: false,
    }
  }
  return {
    date: fromIso(date), adults: draft?.adults || 1, children: draft?.children ?? 0,
    tourists: fromDraftTourists(draft?.tourists ?? []),
    insurance_type_id: draft?.insurance_type_id ?? null, transfer_type_id: draft?.transfer_type_id ?? null,
    promo: draft?.promo ?? '', wishes: draft?.wishes ?? '', accept: false,
  }
}

/** True when the draft had tourist data but (by design) no passport numbers to restore. */
export function draftNeedsNumbers(draft: BookingDraft | null, order: BookingOrder | null): boolean {
  if (order?.tourists.length) return false
  return !!draft?.tourists.some((t) => t.last_name_lat || t.first_name_lat || t.birth_date)
}
