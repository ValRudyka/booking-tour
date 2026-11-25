import type { OrderDetailWithPrice } from '../../api/types'

/**
 * Where an order stands for the payment pages (spec 05). Only the Stripe webhook (or the finance
 * controller for a transfer) changes the status; these pages only read it.
 * - paid: the money arrived (`payment_status` "paid"), whatever the manager has done since;
 * - late_refund: the money arrived after the order had been cancelled (hold ran out) or the seats
 *   were gone: the backend refunded it automatically and left the order cancelled;
 * - payable: «Очікує оплати» and the hold still runs (a partly paid transfer always is);
 * - expired: «Очікує оплати» but the hold has run out (the System cancels it within a minute);
 * - checkout: not confirmed yet (back to the booking wizard);
 * - cancelled: cancelled without any money;
 * - closed: any other state (rejected, cancellation requested, …): nothing to pay.
 */
export type PaymentOutcome = 'paid' | 'late_refund' | 'payable' | 'expired' | 'checkout' | 'cancelled' | 'closed'

const PAID_STATUSES = new Set(['paid', 'in_progress', 'confirmed', 'documents_ready', 'completed', 'archived'])

export function paymentOutcome(order: OrderDetailWithPrice, now: number = Date.now()): PaymentOutcome {
  const everPaid = order.history.some((h) => h.new_status === 'paid')
  if (order.status === 'cancelled' && !everPaid
    && (order.payment_status === 'refunded' || order.payments.some((p) => p.type === 'refund'))) {
    return 'late_refund'
  }
  if (order.payment_status === 'paid' && PAID_STATUSES.has(order.status)) return 'paid'
  if (order.status === 'awaiting_payment') {
    const held = order.payment_status === 'partially_paid'
      || (!!order.hold_expires_at && Date.parse(order.hold_expires_at) > now)
    return held ? 'payable' : 'expired'
  }
  if (order.status === 'checkout') return 'checkout'
  if (order.status === 'cancelled') return 'cancelled'
  return PAID_STATUSES.has(order.status) ? 'paid' : 'closed'
}

/** A transfer the client chose and has not paid yet: its details are shown again (spec 05). */
export function hasPendingTransfer(order: OrderDetailWithPrice): boolean {
  return order.payments.some((p) => p.type === 'payment' && p.method === 'bank_transfer' && p.status === 'pending')
}

/** The browser leaves for Stripe through this object, so tests can replace it. */
export const browser = {
  assign(url: string) {
    window.location.assign(url)
  },
}
