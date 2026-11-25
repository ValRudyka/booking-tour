// Form rules of the manager's order dialogs. They mirror backend services/order_processing.py
// (PNR_RE, MAX_TEXT, MAX_COMMENT and the operator deadline checks of confirm()); change both
// together. The server checks again and its text is shown if it refuses. Which actions are
// possible is never decided here: that comes from the API's staff_actions.

export const PNR_PATTERN = /^[A-Z0-9]{5,20}$/
export const PNR_MAX = 20
export const MAX_TEXT = 2000
export const MAX_COMMENT = 5000

/** The operator's payment deadline: from today (Kyiv) up to the tour's start date, inclusive. */
export function deadlineAllowed(date: string, today: string, startDate: string): boolean {
  return date >= today && date <= startDate
}

/** The PNR as the backend stores it: trimmed, upper case. */
export function normalizePnr(value: string): string {
  return value.trim().toUpperCase()
}
