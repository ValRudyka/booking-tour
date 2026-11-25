import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { FavoritePage } from './types'

// «Обране» of the client (backend routers/favorites.py, spec 08 §5). Clients only: the backend
// answers 403 to staff, so the hooks are enabled only for a signed-in client.

export const FAVORITES_PAGE_SIZE = 12

export const favoriteKeys = {
  all: ['me', 'favorites'] as const,
  ids: ['me', 'favorites', 'ids'] as const,
  page: (page: number) => ['me', 'favorites', 'page', page] as const,
}

/** The tour ids in «Обране»: one small request for every heart button on the page. */
export function useFavoriteIds(enabled: boolean) {
  return useQuery({
    queryKey: favoriteKeys.ids,
    queryFn: async () => (await api.get<number[]>('/me/favorites/ids')).data,
    enabled,
  })
}

export function useFavorites(page: number) {
  return useQuery({
    queryKey: favoriteKeys.page(page),
    queryFn: async () => (await api.get<FavoritePage>('/me/favorites', {
      params: { page, page_size: FAVORITES_PAGE_SIZE },
    })).data,
    placeholderData: keepPreviousData,
  })
}

/** Add (PUT) or remove (DELETE); both are idempotent on the server. The ids list changes at once
 * (optimistic) and goes back if the server refuses; afterwards every favourites query refreshes. */
export function useToggleFavorite() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ tourId, add }: { tourId: number; add: boolean }) => {
      if (add) await api.put(`/me/favorites/${tourId}`)
      else await api.delete(`/me/favorites/${tourId}`)
    },
    onMutate: async ({ tourId, add }) => {
      await queryClient.cancelQueries({ queryKey: favoriteKeys.ids })
      const before = queryClient.getQueryData<number[]>(favoriteKeys.ids)
      queryClient.setQueryData<number[]>(favoriteKeys.ids, (ids = []) =>
        add ? [tourId, ...ids.filter((id) => id !== tourId)] : ids.filter((id) => id !== tourId))
      return { before }
    },
    onError: (_error, _vars, context) => {
      queryClient.setQueryData(favoriteKeys.ids, context?.before)
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: favoriteKeys.all }),
  })
}
