import { useQuery } from '@tanstack/react-query'
import { api } from './client'
import type {
  OrderCreate, OrderDetailWithPrice, OrderSummaryPage, OrderUpdate, OrderWithPrice, Price,
  QuoteRequest, SavedPassport, ServiceOption,
} from './types'

// Client checkout (backend routers/orders.py, ТЗ 4.5.3). The server calculates every price; the
// page only shows the strings it returns.

/** Price preview before the order exists: checks the same rules, saves nothing, holds no seats. */
export async function quoteOrder(body: QuoteRequest): Promise<Price> {
  return (await api.post<Price>('/orders/quote', body)).data
}

/** «Забронювати»: status «Оформлення», seats held until hold_expires_at. */
export async function createOrder(body: OrderCreate): Promise<OrderWithPrice> {
  return (await api.post<OrderWithPrice>('/orders', body)).data
}

/** Edit while in «Оформлення»; returns the recalculated price. The hold is never extended. */
export async function updateOrder(orderId: number, body: OrderUpdate): Promise<OrderWithPrice> {
  return (await api.patch<OrderWithPrice>(`/orders/${orderId}`, body)).data
}

/** «Підтвердити й перейти до оплати»: price frozen, status «Очікує оплати». */
export async function confirmOrder(orderId: number): Promise<OrderWithPrice> {
  return (await api.post<OrderWithPrice>(`/orders/${orderId}/confirm`, { accept_offer: true })).data
}

export async function cancelOrder(orderId: number): Promise<void> {
  await api.post(`/orders/${orderId}/cancel`)
}

/** Read-only, with the price breakdown (calculated on read, never saved). */
export async function fetchOrder(orderId: number): Promise<OrderDetailWithPrice> {
  return (await api.get<OrderDetailWithPrice>(`/orders/${orderId}`)).data
}

/** The client's orders still in «Оформлення» (to resume an unfinished booking). */
export async function fetchCheckoutOrders(): Promise<OrderSummaryPage> {
  return (await api.get<OrderSummaryPage>('/orders', { params: { status: 'checkout', page_size: 50 } })).data
}

const REFERENCE_STALE_MS = 10 * 60_000

export function useInsuranceTypes() {
  return useQuery({
    queryKey: ['reference', 'insurance-types'],
    queryFn: async () => (await api.get<ServiceOption[]>('/reference/insurance-types')).data,
    staleTime: REFERENCE_STALE_MS,
  })
}

export function useTransferTypes() {
  return useQuery({
    queryKey: ['reference', 'transfer-types'],
    queryFn: async () => (await api.get<ServiceOption[]>('/reference/transfer-types')).data,
    staleTime: REFERENCE_STALE_MS,
  })
}

/** Saved foreign passports for autofill (ТЗ form 4.6.1.1, field 8). */
export function useSavedPassports() {
  return useQuery({
    queryKey: ['me', 'passports'],
    queryFn: async () => (await api.get<SavedPassport[]>('/me/passports')).data,
  })
}
