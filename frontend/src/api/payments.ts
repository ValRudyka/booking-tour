import { useQuery, type Query } from '@tanstack/react-query'
import { api } from './client'
import { fetchOrder } from './orders'
import type { OrderDetailWithPrice, PaymentMethod, PayOut } from './types'

/**
 * «Оплатити» (backend routers/orders.py pay_order), only for an order in «Очікує оплати».
 * Card: the same open Stripe session is returned on a repeated call (no second payment).
 * Bank transfer: the same pending transfer and its details are returned on a repeated call; the
 * first choice extends the seat hold (bank_transfer_hold_hours). A zero total is paid at once.
 */
export async function payOrder(orderId: number, method: PaymentMethod): Promise<PayOut> {
  return (await api.post<PayOut>(`/orders/${orderId}/pay`, { method })).data
}

/** The client's own order (someone else's is a 404, like a missing one). */
export function useOrder(orderId: number | null,
  refetchInterval: number | false | ((query: Query<OrderDetailWithPrice, Error>) => number | false) = false) {
  return useQuery({
    queryKey: ['order', orderId],
    queryFn: () => fetchOrder(orderId!),
    enabled: orderId !== null,
    refetchInterval,
    // The status is live (the webhook changes it any second): every page that opens an order
    // reads it again instead of trusting the 30 s cache of the catalog.
    staleTime: 0,
    retry: false,
  })
}
