import { QueryClient } from '@tanstack/react-query'
import { ApiError } from './client'

/** Retrying cannot fix our own bad request (4xx) or maintenance mode (503); it only delays the
 * message. Network errors and other 5xx get two more tries. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && (error.kind === 'maintenance' || error.status !== null && error.status < 500)) {
    return false
  }
  return failureCount < 2
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000, // catalog data changes rarely; avoids refetching on every back/forward
        retry: shouldRetry,
        refetchOnWindowFocus: false,
      },
    },
  })
}
