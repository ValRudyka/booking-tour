// The booking draft in sessionStorage (spec 04, §4): the wizard survives a reload, «Назад» and a
// sign-in after the 60-minute token ran out (the login page sends the client back to the same URL,
// the draft brings back the step).
//
// Passport numbers are never written here: sessionStorage is readable by any script on the page,
// so the most sensitive field is typed again (or comes back from the server once step 2 is saved).
// The key holds the user id, so another account in the same tab never sees this draft, and an
// explicit sign-out removes every draft (clearAllDrafts); an expired session keeps it.

const PREFIX = 'tour.booking.'

export interface DraftTourist {
  last_name_lat?: string
  first_name_lat?: string
  birth_date?: string | null
  passport_expiry?: string | null
}

export interface BookingDraft {
  step: number
  date: string | null
  adults: number
  children: number
  /** The order in «Оформлення» this draft belongs to (its seats are held). */
  orderId: number | null
  tourists: DraftTourist[]
  insurance_type_id: number | null
  transfer_type_id: number | null
  promo: string
  wishes: string
}

export function draftKey(userId: number, tourId: number): string {
  return `${PREFIX}${userId}.${tourId}`
}

const isDate = (value: unknown) => value === null || value === undefined
  || (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value))
const isText = (value: unknown) => value === undefined || typeof value === 'string'
const isCount = (value: unknown) => Number.isInteger(value) && (value as number) >= 0
const isId = (value: unknown) => value === null || Number.isInteger(value)

function isDraft(value: unknown): value is BookingDraft {
  if (!value || typeof value !== 'object') return false
  const d = value as Record<string, unknown>
  return isCount(d.step) && (d.step as number) <= 3 && isDate(d.date) && isCount(d.adults)
    && isCount(d.children) && isId(d.orderId) && isId(d.insurance_type_id) && isId(d.transfer_type_id)
    && typeof d.promo === 'string' && typeof d.wishes === 'string' && Array.isArray(d.tourists)
    && d.tourists.every((t: unknown) => !!t && typeof t === 'object'
      && isText((t as DraftTourist).last_name_lat) && isText((t as DraftTourist).first_name_lat)
      && isDate((t as DraftTourist).birth_date) && isDate((t as DraftTourist).passport_expiry))
}

/** The stored draft, or null if there is none or it is damaged (then it is simply ignored). */
export function loadDraft(userId: number, tourId: number): BookingDraft | null {
  try {
    const raw = window.sessionStorage.getItem(draftKey(userId, tourId))
    if (!raw) return null
    const value: unknown = JSON.parse(raw)
    return isDraft(value) ? value : null
  } catch {
    return null
  }
}

export function saveDraft(userId: number, tourId: number, draft: BookingDraft): void {
  // Only the listed tourist fields are copied: a passport number can never slip in.
  const tourists = draft.tourists.map(({ last_name_lat, first_name_lat, birth_date, passport_expiry }) =>
    ({ last_name_lat, first_name_lat, birth_date, passport_expiry }))
  try {
    window.sessionStorage.setItem(draftKey(userId, tourId), JSON.stringify({ ...draft, tourists }))
  } catch {
    // Storage full or disabled: the wizard still works, it just will not survive a reload.
  }
}

export function clearDraft(userId: number, tourId: number): void {
  try {
    window.sessionStorage.removeItem(draftKey(userId, tourId))
  } catch {
    // nothing to clear
  }
}

/** On an explicit sign-out: no tourist data stays in the tab. */
export function clearAllDrafts(): void {
  try {
    for (const key of Object.keys(window.sessionStorage)) {
      if (key.startsWith(PREFIX)) window.sessionStorage.removeItem(key)
    }
  } catch {
    // nothing to clear
  }
}
