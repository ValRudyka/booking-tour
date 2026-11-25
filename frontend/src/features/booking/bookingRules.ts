// Client-side checks of the booking form. They mirror backend/app/services/orders.py and
// services/passports.py (same rules, same Ukrainian texts in uk.json → checkout.rules) so the
// client sees the error before the request; the server checks everything again. Change both
// together. Dates are ISO strings (YYYY-MM-DD) and are handled in UTC, so no time zone can shift them.

/** services/orders.py MAX_TOURISTS */
export const MAX_TOURISTS = 20
/** services/pricing.py CHILD_AGE_LIMIT: a child is under 12 on the start date. */
export const CHILD_AGE_LIMIT = 12
/** services/orders.py PASSPORT_MONTHS_AFTER_RETURN (form 4.6.1.2, field 3.5) */
export const PASSPORT_MONTHS_AFTER_RETURN = 6
/** services/orders.py MAX_WISHES */
export const MAX_WISHES = 1000
const NAME_MAX = 100

/** services/passports.py LATIN_NAME: starts with a letter; letters, space, ' and -. */
const LATIN_NAME = /^[A-Za-z][A-Za-z '-]*$/
/** services/passports.py PASSPORT_NUMBER, after removing spaces and upper-casing. */
const PASSPORT_NUMBER = /^[A-Z0-9]{4,20}$/

/** Like Python's " ".join(value.split()). */
export function cleanName(value: string): string {
  return value.split(/\s+/).filter(Boolean).join(' ')
}

export function isLatinPassportName(value: string): boolean {
  const name = cleanName(value)
  return name.length <= NAME_MAX && LATIN_NAME.test(name)
}

export function cleanPassportNumber(value: string): string {
  return value.replace(/\s+/g, '').toUpperCase()
}

export function isPassportNumber(value: string): boolean {
  return PASSPORT_NUMBER.test(cleanPassportNumber(value))
}

function parts(iso: string): [number, number, number] {
  const [y, m, d] = iso.split('-').map(Number)
  return [y, m, d]
}

function iso(year: number, month: number, day: number): string {
  return `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

export function addDays(date: string, days: number): string {
  const [y, m, d] = parts(date)
  const result = new Date(Date.UTC(y, m - 1, d + days))
  return iso(result.getUTCFullYear(), result.getUTCMonth() + 1, result.getUTCDate())
}

/** services/orders.py add_months: the same day N months later, clamped to the month's end
 * (31 Aug + 6 months = 28/29 Feb). */
export function addMonths(date: string, months: number): string {
  const [y, m, d] = parts(date)
  const index = m - 1 + months
  const year = y + Math.floor(index / 12)
  const month = (index % 12 + 12) % 12 + 1
  const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate()
  return iso(year, month, Math.min(d, lastDay))
}

/** The return date: start + nights (services/orders.py _check_start_date). */
export function returnDate(startDate: string, nights: number): string {
  return addDays(startDate, nights)
}

/** The passport must be valid at least until this date (form 4.6.1.2, field 3.5). */
export function passportValidUntil(endDate: string): string {
  return addMonths(endDate, PASSPORT_MONTHS_AFTER_RETURN)
}

/** Full years on `day`, like services/pricing.py age_on (a birthday not reached yet, 29 Feb). */
export function ageOn(birthDate: string, day: string): number {
  const [by, bm, bd] = parts(birthDate)
  const [y, m, d] = parts(day)
  return y - by - (m < bm || (m === bm && d < bd) ? 1 : 0)
}

export function isChild(birthDate: string, startDate: string): boolean {
  return ageOn(birthDate, startDate) < CHILD_AGE_LIMIT
}

// ---------- saved tourists (services/passports.py, form 4.6.1.1, field 8)
/** services/passports.py MAX_SAVED_PASSPORTS */
export const MAX_SAVED_PASSPORTS = 20
/** services/passports.py EARLIEST_BIRTH_DATE */
export const EARLIEST_BIRTH_DATE = '1900-01-01'
/** services/passports.py AUTHORITY_CODE (field 8.4, optional) */
const AUTHORITY_CODE = /^\d{4}$/

export function isAuthorityCode(value: string): boolean {
  return AUTHORITY_CODE.test(value.trim())
}

/** How soon a saved passport runs out, for its tag: a trip needs it valid 6 months after the
 * return, so «soon» = less than 6 months from today (Kyiv). */
export function expiryState(expiry: string, today: string): 'expired' | 'soon' | null {
  if (expiry <= today) return 'expired'
  if (expiry < addMonths(today, PASSPORT_MONTHS_AFTER_RETURN)) return 'soon'
  return null
}
