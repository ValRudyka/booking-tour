import type { ClientAction, OrderSummary } from '../../api/types'

// Addresses of the client cabinet. Which buttons exist is never decided here: the API sends
// `client_actions` for every order (backend services/order_actions.py).

export const ordersPath = '/cabinet/orders'
export const orderPath = (id: number) => `/cabinet/orders/${id}`
export const reviewPath = (id: number) => `/cabinet/orders/${id}/review`
export const payPath = (id: number) => `/orders/${id}/pay`
/** The booking wizard resumes the client's «Оформлення» order of this tour (spec 04). */
export const checkoutPath = (order: Pick<OrderSummary, 'tour_id' | 'start_date'>) =>
  `/booking/${order.tour_id}?${new URLSearchParams({ date: order.start_date })}`

export function has(order: { client_actions: ClientAction[] }, action: ClientAction): boolean {
  return order.client_actions.includes(action)
}
