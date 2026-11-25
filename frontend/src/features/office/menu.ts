import type { UserRole } from '../../api/types'

// The back-office menu (spec 09 §1), one list for the layout, the /office redirect and the
// routes. Only sections with a backend API are listed: «Статистика» (manager) and «Звіти»
// (finance, feature/reports) have none yet. A section whose page is not built yet (`built:
// false`) opens a «з'явиться згодом» page; its spec is noted next to it.

export type OfficeSectionKey =
  | 'orders' | 'tours' | 'reviews' | 'promoCodes'
  | 'transactions' | 'refunds'
  | 'users' | 'references' | 'settings' | 'audit'

export interface OfficeSection {
  key: OfficeSectionKey
  /** Under /office, e.g. `orders` → /office/orders. */
  path: string
  role: Exclude<UserRole, 'client'>
  built: boolean
}

export const OFFICE_SECTIONS: readonly OfficeSection[] = [
  { key: 'orders', path: 'orders', role: 'manager', built: true },              // spec 09
  { key: 'tours', path: 'tours', role: 'manager', built: false },               // spec 10
  { key: 'reviews', path: 'reviews', role: 'manager', built: false },           // spec 11
  { key: 'promoCodes', path: 'promo-codes', role: 'manager', built: false },    // spec 11
  { key: 'transactions', path: 'transactions', role: 'finance', built: false }, // spec 12
  { key: 'refunds', path: 'refunds', role: 'finance', built: false },           // spec 12
  { key: 'users', path: 'users', role: 'admin', built: true },                  // spec 13
  { key: 'references', path: 'references', role: 'admin', built: true },        // spec 13
  { key: 'settings', path: 'settings', role: 'admin', built: true },            // spec 13
  { key: 'audit', path: 'audit-log', role: 'admin', built: false },             // spec 13
]

/** Sections whose page comes with a later spec: the router gives them a «з'явиться згодом» page. */
export const COMING_SOON = OFFICE_SECTIONS.filter((section) => !section.built)

export const officePath = (section: OfficeSection) => `/office/${section.path}`

/** The menu of a role (empty for a client, who never gets into /office). */
export function officeMenu(role: UserRole): OfficeSection[] {
  return OFFICE_SECTIONS.filter((section) => section.role === role)
}

/** Where /office sends the user: the first section of the role (manager → «Заявки»,
 * finance → «Транзакції», admin → «Користувачі»). */
export function officeHome(role: UserRole): string | null {
  const first = officeMenu(role)[0]
  return first ? officePath(first) : null
}

/** The order page of the back office, where a notification about an order leads. Only managers
 * have one so far (finance's order view comes with spec 12). */
export function officeOrderPath(role: UserRole, orderId: number): string | null {
  return role === 'manager' ? `/office/orders/${orderId}` : null
}
