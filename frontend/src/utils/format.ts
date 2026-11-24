// Display helpers. Money and ratings arrive from the API as decimal strings ("32000.00",
// "4.60"): they are only formatted here, never turned into floats for arithmetic.
// Intl.NumberFormat formats a numeric string exactly (ES2023), rounding half away from zero,
// which matches the backend's ROUND_HALF_UP.

type DecimalString = `${number}`

const priceFormat = new Intl.NumberFormat('uk-UA', { maximumFractionDigits: 0 })
const ratingFormat = new Intl.NumberFormat('uk-UA', { minimumFractionDigits: 1, maximumFractionDigits: 1 })

/** "32000.00" -> "32 000" (whole hryvnias: a catalog "from" price, the exact sum is shown at checkout). */
export function formatPrice(value: string): string {
  return priceFormat.format(value as DecimalString)
}

/** "4.60" -> "4,6" */
export function formatRating(value: string): string {
  return ratingFormat.format(value as DecimalString)
}

/** "2026-12-01" -> "01.12.2026" (no Date object, so no time-zone shift). */
export function formatDate(isoDate: string): string {
  const [year, month, day] = isoDate.split('-')
  return `${day}.${month}.${year}`
}

/** The business time zone of the backend (settings BUSINESS_TIMEZONE, services/clock.py). */
const BUSINESS_TIMEZONE = 'Europe/Kyiv'

function dateIn(timeZone: string, now: Date): string {
  // en-CA formats as YYYY-MM-DD.
  return new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit' })
    .format(now)
}

/** "Today" in Kyiv as YYYY-MM-DD, the same date the backend's clock.today() uses, whatever the
 * visitor's own time zone is. */
export function kyivToday(now: Date = new Date()): string {
  try {
    return dateIn(BUSINESS_TIMEZONE, now)
  } catch {
    return dateIn('Europe/Kiev', now) // older ICU data knows only the old spelling
  }
}

/**
 * Nearest start date of a tour whose start dates run from `from` to `to` (form 4.6.2.1,
 * field 10: one date or a range). Once the range has begun, the nearest start is today.
 * ISO dates compare correctly as strings.
 */
export function nearestDeparture(from: string, to: string, today: string = kyivToday()): string {
  if (from >= today) return from
  return to >= today ? today : to
}
