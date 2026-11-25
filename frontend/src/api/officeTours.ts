import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from './client'
import type {
  ManagerTour, ManagerTourPage, ManagerToursQuery, TourCopyIn, TourCreate, TourImage, TourRules, TourUpdate,
} from './types'

// The back office (spec 10): the manager's tours (backend routers/manager_tours.py). Every
// action answers the updated tour card with `tour_actions` and `locked_fields`, which the pages
// show as they are (features/office/tourActions.ts).

export const officeTourKeys = {
  tours: ['office-tours'] as const,
  tour: (id: number) => ['office-tour', id] as const,
  rules: ['office-tour-rules'] as const,
}

export function useOfficeTours(query: ManagerToursQuery) {
  return useQuery({
    queryKey: [...officeTourKeys.tours, query],
    queryFn: async () => (await api.get<ManagerTourPage>('/manager/tours', { params: query })).data,
    placeholderData: keepPreviousData,   // the table keeps its rows while the next page loads
    staleTime: 0,                        // bookings change the actions and counts at any moment
  })
}

export function useOfficeTour(id: number | undefined) {
  return useQuery({
    queryKey: officeTourKeys.tour(id ?? 0),
    queryFn: async () => (await api.get<ManagerTour>(`/manager/tours/${id}`)).data,
    enabled: id !== undefined,
    staleTime: 0,
  })
}

/** Photo and text limits of the form (settings of the backend, never hard-coded here). */
export function useTourRules() {
  return useQuery({
    queryKey: officeTourKeys.rules,
    queryFn: async () => (await api.get<TourRules>('/manager/tours/rules')).data,
    staleTime: 10 * 60_000,
  })
}

const post = async (url: string, body?: unknown) => (await api.post<ManagerTour>(url, body)).data

export const tourApi = {
  create: (body: TourCreate) => post('/manager/tours', body),
  update: async (id: number, body: TourUpdate) => (await api.patch<ManagerTour>(`/manager/tours/${id}`, body)).data,
  publish: (id: number) => post(`/manager/tours/${id}/publish`),
  unpublish: (id: number) => post(`/manager/tours/${id}/unpublish`),
  archive: (id: number) => post(`/manager/tours/${id}/archive`),
  restore: (id: number) => post(`/manager/tours/${id}/restore`),
  copy: (id: number, body: TourCopyIn) => post(`/manager/tours/${id}/copy`, body),
}

/** Several photos in one request (all-or-nothing on the server). */
export async function uploadTourImages(id: number, files: File[]): Promise<TourImage[]> {
  const form = new FormData()
  for (const file of files) form.append('files', file)
  return (await api.post<TourImage[]>(`/manager/tours/${id}/images`, form)).data
}

export async function deleteTourImage(id: number, imageId: number): Promise<void> {
  await api.delete(`/manager/tours/${id}/images/${imageId}`)
}

/** The whole order; the first photo is the main one (catalog card, gallery start). */
export async function reorderTourImages(id: number, imageIds: number[]): Promise<TourImage[]> {
  return (await api.put<TourImage[]>(`/manager/tours/${id}/images/order`, { image_ids: imageIds })).data
}
