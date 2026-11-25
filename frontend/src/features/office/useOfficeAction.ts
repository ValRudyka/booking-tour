import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useRef, useState } from 'react'
import { ApiError, toApiError } from '../../api/client'
import { officeKeys } from '../../api/office'
import type { ManagerOrder } from '../../api/types'

/**
 * Runs one back-office action at a time (spec 09 §1: the button is locked while the request
 * runs). On success the order card the API answered replaces the cached one and the lists are
 * refreshed. On 409 (another manager took or changed the order meanwhile) the order and the lists
 * are fetched again, so the page shows the new owner and status next to the server's message.
 */
export function useOfficeAction(orderId?: number) {
  const queryClient = useQueryClient()
  const lock = useRef(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<ApiError | null>(null)

  const refresh = useCallback(() => {
    if (orderId !== undefined) void queryClient.invalidateQueries({ queryKey: officeKeys.order(orderId) })
    void queryClient.invalidateQueries({ queryKey: officeKeys.orders })
  }, [orderId, queryClient])

  const run = useCallback(async <T>(name: string, action: () => Promise<T>): Promise<T | null> => {
    if (lock.current) return null
    lock.current = true
    setBusy(name)
    setError(null)
    try {
      const result = await action()
      if (isOrder(result)) queryClient.setQueryData(officeKeys.order(result.id), result)
      else if (orderId !== undefined) void queryClient.invalidateQueries({ queryKey: officeKeys.order(orderId) })
      void queryClient.invalidateQueries({ queryKey: officeKeys.orders })
      return result
    } catch (caught) {
      const apiError = toApiError(caught)
      setError(apiError)
      if (apiError.status === 409) refresh()
      return null
    } finally {
      lock.current = false
      setBusy(null)
    }
  }, [orderId, queryClient, refresh])

  const clearError = useCallback(() => setError(null), [])
  return { run, busy, error, clearError }
}

function isOrder(value: unknown): value is ManagerOrder {
  return typeof value === 'object' && value !== null && 'staff_actions' in value && 'id' in value
}

/** The text to show for a failed action: the server's own Ukrainian text for business refusals
 * (409, and the plain-text 422 of order_processing: «PNR — від 5 до 20 …»), «Недостатньо прав»
 * for 403, otherwise the generic message of ApiError. */
export function actionErrorText(error: ApiError, forbidden: string): string {
  if (error.status === 403) return forbidden
  if (error.kind === 'validation' && error.detail) return error.detail
  return error.message
}
