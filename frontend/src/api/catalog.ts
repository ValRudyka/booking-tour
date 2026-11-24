import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from './client'
import type { TourPage, TourSearchParams } from './types'

export async function fetchTours(params: TourSearchParams): Promise<TourPage> {
  const { data } = await api.get<TourPage>('/tours', { params })
  return data
}

export function useTours(params: TourSearchParams) {
  return useQuery({
    queryKey: ['tours', params],
    queryFn: () => fetchTours(params),
    // Keep the previous page on screen while the next one loads, instead of flashing skeletons.
    placeholderData: keepPreviousData,
  })
}
