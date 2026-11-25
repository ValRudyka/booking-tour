import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from './client'
import type {
  DocumentRules, ManagerOrder, ManagerOrderPage, ManagerOrdersQuery, ManagerShort, OrderDocumentType,
  StaffUploadedDocument,
} from './types'

// The back office (spec 09): the manager's order queue and order processing
// (backend routers/manager_orders.py). The order card sits under ['order', id, …] like the
// client's, so a notification about the order refreshes it (components/NotificationBell.tsx).
// Passport data in these answers stays in the memory cache only: nothing here is persisted, and
// AuthProvider clears the cache at sign-out.

export const officeKeys = {
  orders: ['office-orders'] as const,
  order: (id: number) => ['order', id, 'office'] as const,
  managers: ['office-managers'] as const,
  documentRules: ['office-document-rules'] as const,
}

export function useOfficeOrders(query: ManagerOrdersQuery) {
  return useQuery({
    queryKey: [...officeKeys.orders, query],
    queryFn: async () => (await api.get<ManagerOrderPage>('/manager/orders', { params: query })).data,
    placeholderData: keepPreviousData,   // the table keeps its rows while the next page loads
    staleTime: 0,                        // another manager may take an order at any moment
  })
}

export function useOfficeOrder(id: number) {
  return useQuery({
    queryKey: officeKeys.order(id),
    queryFn: async () => (await api.get<ManagerOrder>(`/manager/orders/${id}`)).data,
    staleTime: 0,
  })
}

export function useManagers(enabled: boolean) {
  return useQuery({
    queryKey: officeKeys.managers,
    queryFn: async () => (await api.get<ManagerShort[]>('/manager/managers')).data,
    enabled,
    staleTime: 5 * 60_000,
  })
}

export function useDocumentRules(enabled: boolean) {
  return useQuery({
    queryKey: officeKeys.documentRules,
    queryFn: async () => (await api.get<DocumentRules>('/manager/orders/document-rules')).data,
    enabled,
    staleTime: 10 * 60_000,
  })
}

// ---------- actions: each answers the updated order card
const post = async (url: string, body?: unknown) => (await api.post<ManagerOrder>(url, body)).data

export const officeActions = {
  take: (id: number) => post(`/manager/orders/${id}/take`),
  assign: (id: number, managerId: number) => post(`/manager/orders/${id}/assign`, { manager_id: managerId }),
  confirm: (id: number, body: { pnr: string; operator_deadline: string; client_message: string | null }) =>
    post(`/manager/orders/${id}/confirm`, body),
  reject: (id: number, body: { reject_reason: string; client_message: string | null }) =>
    post(`/manager/orders/${id}/reject`, body),
  documentsReady: (id: number, clientMessage: string | null) =>
    post(`/manager/orders/${id}/documents-ready`, { client_message: clientMessage }),
  archive: (id: number) => post(`/manager/orders/${id}/archive`),
  comment: async (id: number, internalComment: string | null) =>
    (await api.patch<ManagerOrder>(`/manager/orders/${id}`, { internal_comment: internalComment })).data,
}

/** Several files of one type in one request (multipart: doc_type + files). */
export async function uploadDocuments(id: number, docType: OrderDocumentType, files: File[]): Promise<StaffUploadedDocument[]> {
  const form = new FormData()
  form.append('doc_type', docType)
  for (const file of files) form.append('files', file)
  return (await api.post<StaffUploadedDocument[]>(`/manager/orders/${id}/documents`, form)).data
}

export async function deleteDocument(id: number, docId: number): Promise<void> {
  await api.delete(`/manager/orders/${id}/documents/${docId}`)
}

/** Private file, fetched with the token as a Blob (see utils/download.ts). */
export async function fetchOfficeDocument(id: number, docId: number): Promise<{ blob: Blob; disposition: string | null }> {
  const response = await api.get<Blob>(`/manager/orders/${id}/documents/${docId}/download`, { responseType: 'blob' })
  const header = response.headers['content-disposition']
  return { blob: response.data, disposition: typeof header === 'string' ? header : null }
}
