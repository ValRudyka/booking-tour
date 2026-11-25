import { useQueryClient, type QueryKey } from '@tanstack/react-query'
import { useCallback } from 'react'
import { toApiError } from '../../api/client'
import { useOfficeAction } from '../office/useOfficeAction'

/**
 * The admin pages' actions (spec 13) on top of the back office's useOfficeAction, which stays
 * unchanged (spec 10 is generalising it): one action at a time, `busy` and `error` come from it.
 * Called without an order id it only refreshes the order lists, which no admin page shows, so
 * this hook refreshes the admin data itself: `keys` after a success, and also after a 409 (the
 * record changed meanwhile — the page shows the server's text next to the fresh data).
 */
export function useAdminAction(keys: readonly QueryKey[]) {
  const queryClient = useQueryClient()
  const office = useOfficeAction()
  const { run: officeRun } = office

  const refresh = useCallback(() => {
    for (const key of keys) void queryClient.invalidateQueries({ queryKey: key })
  }, [keys, queryClient])

  const run = useCallback(async <T>(name: string, action: () => Promise<T>): Promise<T | null> => {
    let conflict = false
    const result = await officeRun(name, async () => {
      try {
        return await action()
      } catch (error) {
        conflict = toApiError(error).status === 409
        throw error
      }
    })
    if (result !== null || conflict) refresh()
    return result
  }, [officeRun, refresh])

  return { run, busy: office.busy, error: office.error, clearError: office.clearError }
}
