import { ApiError } from '../../api/client'
import i18n from '../../i18n'

// How the booking wizard reads checkout errors (backend services/orders.py, services/promo.py).
// Unlike the auth forms (features/auth/authErrors.ts), the wizard shows the backend's text: these
// are Ukrainian business messages written for the client (free seats left, why a promo code was
// refused, which date a passport must reach), and spec 04 asks for the server's reason.
// Technical texts (pydantic's English 422 messages) are never shown.

export const TOURIST_FIELDS = ['last_name_lat', 'first_name_lat', 'birth_date', 'passport_number',
  'passport_expiry'] as const
export type TouristField = (typeof TOURIST_FIELDS)[number]

export interface TouristIssue {
  index: number
  field: TouristField
  message: string
}

const HOLD_EXPIRED = 'Час на оформлення замовлення минув'
const TOUR_UNAVAILABLE = 'Тур недоступний для бронювання'
const NO_SEATS = 'Недостатньо вільних місць'

function detailOf(error: unknown): string | null {
  return error instanceof ApiError ? error.detail : null
}

/** 409 from any edit or confirm once the hold ran out: the System has just cancelled the order. */
export function isHoldExpired(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409 && !!detailOf(error)?.startsWith(HOLD_EXPIRED)
}

/** The tour went back to draft or was archived during the booking. */
export function isTourUnavailable(error: unknown): boolean {
  return error instanceof ApiError && error.status === 422 && detailOf(error) === TOUR_UNAVAILABLE
}

/** 409 «Недостатньо вільних місць: …» from create or from a PATCH with more tourists. */
export function isSeatsError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409 && !!detailOf(error)?.startsWith(NO_SEATS)
}

export function isMaintenance(error: unknown): boolean {
  return error instanceof ApiError && error.kind === 'maintenance'
}

/**
 * Field errors of tourists: the backend's checkout rules answer
 * [{loc: ["body", "tourists", i, field], msg, type: "checkout_rule"}]; msg is shown as is. A plain
 * pydantic 422 for a tourist field (a malformed value) gets a generic text instead.
 */
export function touristIssues(error: unknown): TouristIssue[] {
  if (!(error instanceof ApiError) || error.kind !== 'validation') return []
  return error.issues.flatMap((issue) => {
    const [body, list, index, field] = issue.loc
    if (body !== 'body' || list !== 'tourists' || typeof index !== 'number'
      || !TOURIST_FIELDS.includes(field as TouristField)) return []
    const message = issue.type === 'checkout_rule' ? issue.msg : i18n.t('checkout.errors.badValue')
    return [{ index, field: field as TouristField, message }]
  })
}

/** The text for an Alert or a field: the backend's business message, else the client's generic
 * one (network, server error, maintenance — ApiError already has a Ukrainian message). */
export function serverText(error: unknown): string {
  if (error instanceof ApiError) {
    if ((error.kind === 'client' || error.kind === 'validation' || error.kind === 'not_found') && error.detail) {
      return error.detail
    }
    return error.message
  }
  return i18n.t('errors.generic')
}
