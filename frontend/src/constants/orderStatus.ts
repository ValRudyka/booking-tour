import type { TFunction } from 'i18next'
import type { OrderStatus, PaymentStatus, ReviewStatus, TransactionStatus } from '../api/types'

// The one status dictionary of the frontend (spec 06): the client cabinet and the back office
// both use it. Each status has a tone, and its Ukrainian label lives in uk.json under the same
// code (orderStatus.paid, paymentStatus.refunded, ...). `Record<…>` makes tsc fail when the
// generated API types get a status this file does not know, and orderStatus.test.ts reads the
// enums from src/api/openapi.json, so a new backend status without a label fails the tests too.

/** Tag colours of the "Sea and sand" palette (CLAUDE.md): success / warning / error, or the
 * neutral default tag. Contrast of each is checked in theme.test.ts. */
export type StatusTone = 'success' | 'warning' | 'error' | 'neutral'

/** Order statuses, ТЗ 4.4.1 (backend models/enums.py OrderStatus). */
export const ORDER_STATUS_TONES: Record<OrderStatus, StatusTone> = {
  checkout: 'neutral',             // Оформлення
  awaiting_payment: 'warning',     // Очікує оплати
  paid: 'success',                 // Оплачено
  in_progress: 'neutral',          // В роботі
  confirmed: 'success',            // Підтверджено
  documents_ready: 'success',      // Документи готові
  completed: 'success',            // Завершено
  rejected: 'error',               // Відхилено
  cancel_requested: 'warning',     // Очікує скасування
  cancelled: 'error',              // Скасовано
  archived: 'neutral',             // Архівний
}

/** Payment (financial) status, a separate field of the order (ТЗ 4.4.1, form 4.6.3.1). */
export const PAYMENT_STATUS_TONES: Record<PaymentStatus, StatusTone> = {
  awaiting: 'warning',             // Очікує оплати
  partially_paid: 'warning',       // Сплачено частково
  paid: 'success',                 // Сплачено повністю
  partially_refunded: 'neutral',   // Повернено частково
  refunded: 'neutral',             // Повернено
}

/** Review moderation (ТЗ 4.5.7, step 6). */
export const REVIEW_STATUS_TONES: Record<ReviewStatus, StatusTone> = {
  pending: 'warning',              // На модерації
  published: 'success',            // Опубліковано
  rejected: 'error',               // Відхилено
}

/** One money movement (a payment or a refund row). */
export const TRANSACTION_STATUS_TONES: Record<TransactionStatus, StatusTone> = {
  pending: 'warning',              // В обробці
  succeeded: 'success',            // Виконано
  failed: 'error',                 // Не вдалося
}

export type StatusKind = 'order' | 'payment' | 'review' | 'transaction'

export const STATUS_TONES = {
  order: ORDER_STATUS_TONES,
  payment: PAYMENT_STATUS_TONES,
  review: REVIEW_STATUS_TONES,
  transaction: TRANSACTION_STATUS_TONES,
} as const

export interface StatusByKind {
  order: OrderStatus
  payment: PaymentStatus
  review: ReviewStatus
  transaction: TransactionStatus
}

/** The uk.json section of each kind. */
export const STATUS_SECTIONS = {
  order: 'orderStatus',
  payment: 'paymentStatus',
  review: 'reviewStatus',
  transaction: 'transactionStatus',
} as const

export function statusLabel<K extends StatusKind>(t: TFunction, kind: K, status: StatusByKind[K]): string {
  return t(`${STATUS_SECTIONS[kind]}.${status}` as `orderStatus.${OrderStatus}`)
}

export function statusTone<K extends StatusKind>(kind: K, status: StatusByKind[K]): StatusTone {
  return (STATUS_TONES[kind] as Record<string, StatusTone>)[status]
}

/** antd Tag `color` of a tone (undefined = the default, neutral tag). */
export const TAG_COLORS: Record<StatusTone, string | undefined> = {
  success: 'success', warning: 'warning', error: 'error', neutral: undefined,
}
