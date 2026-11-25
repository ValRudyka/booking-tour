import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useRef, useState } from 'react'
import { ApiError, toApiError } from '../../api/client'
import { officeKeys } from '../../api/office'
import { officeTourKeys } from '../../api/officeTours'
import type { ManagerOrder, ManagerTour } from '../../api/types'

interface Handlers {
  /** The request succeeded with this answer (put a returned card into the cache, refresh lists). */
  onResult: (result: unknown) => void
  /** 409: somebody changed the record meanwhile; fetch it and the lists again. */
  onConflict: () => void
}

/**
 * Runs one back-office action at a time (spec 09 §1: the button is locked while the request
 * runs) and keeps the last error for the page. The order and tour pages wrap it with their own
 * cache updates (useOfficeAction, useTourAction).
 */
export function useActionRunner({ onResult, onConflict }: Handlers) {
  const lock = useRef(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<ApiError | null>(null)

  const run = useCallback(async <T>(name: string, action: () => Promise<T>): Promise<T | null> => {
    if (lock.current) return null
    lock.current = true
    setBusy(name)
    setError(null)
    try {
      const result = await action()
      onResult(result)
      return result
    } catch (caught) {
      const apiError = toApiError(caught)
      setError(apiError)
      if (apiError.status === 409) onConflict()
      return null
    } finally {
      lock.current = false
      setBusy(null)
    }
  }, [onResult, onConflict])

  const clearError = useCallback(() => setError(null), [])
  return { run, busy, error, clearError, setError }
}

/**
 * An order action. On success the order card the API answered replaces the cached one and the
 * lists are refreshed. On 409 (another manager took or changed the order meanwhile) the order and
 * the lists are fetched again, so the page shows the new owner and status next to the server's
 * message.
 */
export function useOfficeAction(orderId?: number) {
  const queryClient = useQueryClient()

  const onConflict = useCallback(() => {
    if (orderId !== undefined) void queryClient.invalidateQueries({ queryKey: officeKeys.order(orderId) })
    void queryClient.invalidateQueries({ queryKey: officeKeys.orders })
  }, [orderId, queryClient])

  const onResult = useCallback((result: unknown) => {
    if (isOrder(result)) queryClient.setQueryData(officeKeys.order(result.id), result)
    else if (orderId !== undefined) void queryClient.invalidateQueries({ queryKey: officeKeys.order(orderId) })
    void queryClient.invalidateQueries({ queryKey: officeKeys.orders })
  }, [orderId, queryClient])

  return useActionRunner({ onResult, onConflict })
}

/**
 * A tour action (spec 10): the tour card the API answered goes into the cache, the tour list
 * is refreshed; on 409 (a booking arrived, another manager changed the tour) both are fetched
 * again, so the buttons and locks shown match the server.
 */
export function useTourAction(tourId?: number) {
  const queryClient = useQueryClient()

  const onConflict = useCallback(() => {
    if (tourId !== undefined) void queryClient.invalidateQueries({ queryKey: officeTourKeys.tour(tourId) })
    void queryClient.invalidateQueries({ queryKey: officeTourKeys.tours })
  }, [tourId, queryClient])

  const onResult = useCallback((result: unknown) => {
    if (isTour(result)) queryClient.setQueryData(officeTourKeys.tour(result.id), result)
    else if (tourId !== undefined) void queryClient.invalidateQueries({ queryKey: officeTourKeys.tour(tourId) })
    void queryClient.invalidateQueries({ queryKey: officeTourKeys.tours })
  }, [tourId, queryClient])

  return useActionRunner({ onResult, onConflict })
}

function isOrder(value: unknown): value is ManagerOrder {
  return typeof value === 'object' && value !== null && 'staff_actions' in value && 'id' in value
}

function isTour(value: unknown): value is ManagerTour {
  return typeof value === 'object' && value !== null && 'tour_actions' in value && 'program_days' in value
}

/** The text to show for a failed action: the server's own Ukrainian text for business refusals
 * (409, and the plain-text 422 of order_processing: «PNR — від 5 до 20 …»; the field rules of the
 * tours API, type "tour_rule"), «Недостатньо прав» for 403, otherwise the generic message of
 * ApiError. */
export function actionErrorText(error: ApiError, forbidden: string): string {
  if (error.status === 403) return forbidden
  const rule = error.issues.find((issue) => issue.type === 'tour_rule')
  if (rule) return rule.msg
  if (error.kind === 'validation' && error.detail) return error.detail
  return error.message
}
