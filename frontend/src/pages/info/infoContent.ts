/** Section and question keys of the info pages, in display order. The texts live in
 * `i18n/uk.json` under `info.*`; these lists keep the keys type-checked. */

export const ABOUT_SECTIONS = ['what', 'how', 'project'] as const

export const TERMS_SECTIONS = [
  'general', 'account', 'booking', 'price', 'payment', 'confirmation', 'cancellation', 'refunds',
  'reviews', 'contacts',
] as const

export const PRIVACY_SECTIONS = [
  'about', 'collected', 'purpose', 'access', 'payments', 'protection', 'rights', 'contacts',
] as const

/** FAQ questions; each key is also the anchor other pages link to (`/faq#cancel`). */
export const FAQ_KEYS = [
  'book', 'hold', 'pay', 'late-payment', 'documents', 'cancel', 'refund', 'review', 'profile',
  'password',
] as const

export type FaqKey = (typeof FAQ_KEYS)[number]

export function isFaqKey(value: string): value is FaqKey {
  return (FAQ_KEYS as readonly string[]).includes(value)
}

/** Questions the contacts page suggests before writing to support. */
export const CONTACTS_FAQ: readonly FaqKey[] = ['password', 'cancel', 'refund', 'documents']
