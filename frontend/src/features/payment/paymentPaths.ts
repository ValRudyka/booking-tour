// Plain helpers of the payment pages (kept out of the component files for fast refresh).

export function successPath(orderId: number): string {
  return `/payment/success?${new URLSearchParams({ order_id: String(orderId) })}`
}

/** ?order_id= or :id as a positive integer, else null (then the page shows 404). */
export function parseOrderId(value: string | null | undefined): number | null {
  return value && /^\d+$/.test(value) && Number(value) > 0 ? Number(value) : null
}

/** How long the success page waits for the webhook (spec 05: every ~2 s, at most ~30 s).
 * An object, so tests can shorten it. */
export const POLLING = { intervalMs: 2000, timeoutMs: 30_000 }
