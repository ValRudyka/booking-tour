import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from './client'
import type {
  CancelReason, CancelRequestForm, MyReview, NameDisplay, NotificationPage, OrderDetail, OrderDocument,
  OrderGroup, OrderReview, OrderSummaryPage,
} from './types'

// The client cabinet (spec 06): «Мої замовлення», order documents, cancellation, reviews and
// in-app notifications (backend routers/orders.py, reviews.py, notifications.py).
// Query keys under ['order', id, …] are refreshed together when a notification about that order
// arrives (components/NotificationBell.tsx).

export const ORDERS_PAGE_SIZE = 10

export const orderKeys = {
  list: ['my-orders'] as const,
  documents: (id: number) => ['order', id, 'documents'] as const,
  cancelForm: (id: number) => ['order', id, 'cancel-form'] as const,
  review: (id: number) => ['order', id, 'review'] as const,
}

/** «Мої замовлення»: the tabs are grouped on the server, which also hides abandoned bookings. */
export function useMyOrders(group: OrderGroup, page: number) {
  return useQuery({
    queryKey: [...orderKeys.list, group, page],
    queryFn: async () => (await api.get<OrderSummaryPage>('/orders', {
      params: { group, page, page_size: ORDERS_PAGE_SIZE },
    })).data,
    placeholderData: keepPreviousData,   // the table keeps its rows while the next page loads
    staleTime: 0,                        // statuses are live
  })
}

/** Trip documents: the API lists them from «Підтверджено» on (an empty list before the upload). */
export function useOrderDocuments(orderId: number, enabled: boolean) {
  return useQuery({
    queryKey: orderKeys.documents(orderId),
    queryFn: async () => (await api.get<OrderDocument[]>(`/orders/${orderId}/documents`)).data,
    enabled,
    staleTime: 0,
  })
}

/** The file is private: fetched with the token (an <a href> would not carry it), as a Blob. */
export async function fetchDocument(orderId: number, docId: number): Promise<{ blob: Blob; disposition: string | null }> {
  const response = await api.get<Blob>(`/orders/${orderId}/documents/${docId}/download`, { responseType: 'blob' })
  const header = response.headers['content-disposition']
  return { blob: response.data, disposition: typeof header === 'string' ? header : null }
}

/** Upload limits of the cancellation evidence (form 4.6.1.3, field 4), from the settings. */
export function useCancelRequestForm(orderId: number, enabled: boolean) {
  return useQuery({
    queryKey: orderKeys.cancelForm(orderId),
    queryFn: async () => (await api.get<CancelRequestForm>(`/orders/${orderId}/cancel-request`)).data,
    enabled,
    staleTime: 10 * 60_000,
  })
}

export interface CancelRequestInput {
  reason: CancelReason
  details: string
  files: File[]
}

/** Form 4.6.1.3 as multipart (files and fields together); answers the order «Очікує скасування». */
export async function requestCancellation(orderId: number, input: CancelRequestInput): Promise<OrderDetail> {
  const body = new FormData()
  body.append('reason_code', input.reason)
  body.append('accept_penalty_policy', 'true')   // the form does not send without the checkbox
  if (input.details.trim()) body.append('details', input.details.trim())
  for (const file of input.files) body.append('files', file)
  return (await api.post<OrderDetail>(`/orders/${orderId}/cancel-request`, body)).data
}

/** The order's review (if any), whether one can be written, premoderation and photo limits. */
export function useOrderReview(orderId: number, enabled = true) {
  return useQuery({
    queryKey: orderKeys.review(orderId),
    queryFn: async () => (await api.get<OrderReview>(`/orders/${orderId}/review`)).data,
    enabled,
    staleTime: 0,
  })
}

export interface ReviewInput {
  hotelRating: number
  serviceRating: number
  positive: string
  negative: string
  nameDisplay: NameDisplay
}

function reviewBody(input: ReviewInput, photos: File[]): FormData {
  const body = new FormData()
  body.append('hotel_rating', String(input.hotelRating))
  body.append('service_rating', String(input.serviceRating))
  // An emptied text is sent as "" (the backend stores it as none); both are optional.
  body.append('positive', input.positive.trim())
  body.append('negative', input.negative.trim())
  body.append('name_display', input.nameDisplay)
  for (const photo of photos) body.append('photos', photo)
  return body
}

/** «Опублікувати відгук» (form 4.6.1.4): pending, or published at once without premoderation. */
export async function createReview(orderId: number, input: ReviewInput, photos: File[]): Promise<MyReview> {
  return (await api.post<MyReview>(`/orders/${orderId}/review`, reviewBody(input, photos))).data
}

/**
 * The one resubmission of a rejected review. New photos replace all old ones; `replacePhotos`
 * without new files removes them (clear_photos); otherwise the old photos stay.
 */
export async function resubmitReview(reviewId: number, input: ReviewInput, photos: File[],
  replacePhotos: boolean): Promise<MyReview> {
  const body = reviewBody(input, replacePhotos ? photos : [])
  if (replacePhotos && photos.length === 0) body.append('clear_photos', 'true')
  return (await api.patch<MyReview>(`/me/reviews/${reviewId}`, body)).data
}

/** A private review photo (pending or rejected) needs the token: fetched as a Blob. */
export async function fetchPrivateImage(path: string): Promise<Blob> {
  // Photo urls are API paths like /api/reviews/1/photos/2; the client's baseURL already ends in /api.
  const url = path.replace(/^\/api(?=\/)/, '')
  return (await api.get<Blob>(url, { responseType: 'blob' })).data
}

// ---------- notifications (any signed-in user; the bell is shown to clients for now)
export const NOTIFICATIONS_SHOWN = 10
export const NOTIFICATIONS_REFRESH_MS = 60_000
export const notificationKeys = { all: ['notifications'] as const }

/** The latest notifications and the unread count for the bell, every minute (no WebSocket). */
export function useNotifications(enabled: boolean) {
  return useQuery({
    queryKey: notificationKeys.all,
    queryFn: async () => (await api.get<NotificationPage>('/me/notifications', {
      params: { page_size: NOTIFICATIONS_SHOWN },
    })).data,
    enabled,
    refetchInterval: NOTIFICATIONS_REFRESH_MS,
    refetchOnWindowFocus: true,
    staleTime: 0,
  })
}

export async function markNotificationRead(id: number): Promise<void> {
  await api.post(`/me/notifications/${id}/read`)
}

export async function markAllNotificationsRead(): Promise<void> {
  await api.post('/me/notifications/read-all')
}
