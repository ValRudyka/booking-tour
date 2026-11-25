import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from './client'
import type { ReviewPage, TourDetail } from './types'

export const REVIEWS_PAGE_SIZE = 10 // the API's default

export async function fetchTour(tourId: number): Promise<TourDetail> {
  return (await api.get<TourDetail>(`/tours/${tourId}`)).data
}

export async function fetchTourReviews(tourId: number, page: number): Promise<ReviewPage> {
  return (await api.get<ReviewPage>(`/tours/${tourId}/reviews`,
    { params: { page, page_size: REVIEWS_PAGE_SIZE } })).data
}

/** The tour page. A tour that is no longer for sale is a 404 (ApiError kind "not_found"). */
export function useTour(tourId: number) {
  return useQuery({ queryKey: ['tour', tourId], queryFn: () => fetchTour(tourId) })
}

/** Published reviews of a tour. Separate from the tour query and `enabled` only when the reviews
 * tab is open, so a visitor who never opens it never loads them (spec §4). */
export function useTourReviews(tourId: number, page: number, enabled: boolean) {
  return useQuery({
    queryKey: ['tour', tourId, 'reviews', page],
    queryFn: () => fetchTourReviews(tourId, page),
    enabled,
    placeholderData: keepPreviousData,
  })
}
