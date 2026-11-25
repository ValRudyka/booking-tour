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

/** Kyiv "tomorrow" as YYYY-MM-DD: the earliest start date an order accepts (clock.tomorrow()). */
export function kyivTomorrow(now: Date = new Date()): string {
  // Noon UTC of the Kyiv date, plus a day, cannot slip across a date line or a DST change.
  const next = new Date(`${kyivToday(now)}T12:00:00Z`)
  next.setUTCDate(next.getUTCDate() + 1)
  return next.toISOString().slice(0, 10)
}

/**
 * The nearest start date that can still be booked, for a tour whose start dates run from `from`
 * to `to` (form 4.6.2.1, field 10: one date or a range). Booking starts tomorrow (Kyiv), so once
 * the range has begun the answer is tomorrow; null when nothing is bookable any more (the catalog
 * does not list such tours). ISO dates compare correctly as strings.
 */
export function nearestBookableDate(from: string, to: string,
  tomorrow: string = kyivTomorrow()): string | null {
  const first = from >= tomorrow ? from : tomorrow
  return first <= to ? first : null
}

/** "14:00:00" (API TIME) -> "14:00" */
export function formatTime(value: string): string {
  return value.slice(0, 5)
}

const wholeNumber = new Intl.NumberFormat('uk-UA', { maximumFractionDigits: 0 })

/** 1200 -> "1 200" (distances; integers from the API, never computed with). */
export function formatInteger(value: number): string {
  return wholeNumber.format(value)
}

/** "2027-06" -> [2027, 6] for the review's trip month (only the month is public, by design). */
export function splitYearMonth(value: string): { year: string; month: number } {
  const [year, month] = value.split('-')
  return { year, month: Number(month) }
}

const moneyFormat = new Intl.NumberFormat('uk-UA', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

/** "12345.50" -> "12 345,50": an exact order amount (checkout, payment), kopecks included, so
 * the page shows the same sum as the order in the database. */
export function formatMoney(value: string): string {
  return moneyFormat.format(value as DecimalString)
}

/** "FX123456" -> "FX****56": the review step shows passports only partly (spec 04, §3). */
export function maskPassport(value: string): string {
  if (value.length <= 4) return '*'.repeat(value.length)
  return `${value.slice(0, 2)}${'*'.repeat(value.length - 4)}${value.slice(-2)}`
}

/** An API timestamp ("2026-11-25T12:35:00Z") as Kyiv time "14:35", like every time on the site. */
export function formatKyivTime(timestamp: string): string {
  const format = (timeZone: string) => new Intl.DateTimeFormat('uk-UA',
    { timeZone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date(timestamp))
  try {
    return format(BUSINESS_TIMEZONE)
  } catch {
    return format('Europe/Kiev')
  }
}

const rateFormat = new Intl.NumberFormat('uk-UA', { minimumFractionDigits: 2, maximumFractionDigits: 4 })

/** "48.1250" -> "48,125": a currency rate (Numeric(12,4)) as stored, only formatted. */
export function formatRate(value: string): string {
  return rateFormat.format(value as DecimalString)
}
