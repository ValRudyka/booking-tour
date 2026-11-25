// Client checks of the tour form (spec 10, spec 03 §2a) that mirror backend services/tours.py
// with the same texts (uk.json office.tours.rule.*): change both together. Limits that are
// settings or may change (photo count and size, text lengths, nights range, list sizes) come from
// GET /manager/tours/rules, not from here. The server checks everything again and its field errors are shown as they are.

/** QU 4433, PS101 (tours.py FLIGHT_RE; the server upper-cases and squeezes spaces first). */
export const FLIGHT_PATTERN = /^[A-Z0-9]{2} ?\d{1,4}[A-Z]?$/

export function normalizeFlight(value: string): string {
  return value.toUpperCase().split(/\s+/).filter(Boolean).join(' ')
}

/** Up to 10 digits before the point and 2 after (Numeric(12, 2)). Prices stay strings. */
export const MONEY_PATTERN = /^\d{1,10}([.,]\d{1,2})?$/

/** "1 250,50" or "1250.5" → "1250.50"-like API value, without any float conversion. */
export function normalizeMoney(value: string): string {
  return value.replace(/\s/g, '').replace(',', '.')
}

/** Is the decimal string above zero? Checked on the digits, never through Number(). */
export function isPositiveMoney(value: string): boolean {
  return /[1-9]/.test(normalizeMoney(value))
}
