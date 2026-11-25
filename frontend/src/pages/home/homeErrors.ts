import { ApiError } from '../../api/client'

/** The API's 503 «технічні роботи»: every block fails the same way at once. */
export function isMaintenance(error: unknown): boolean {
  return error instanceof ApiError && error.kind === 'maintenance'
}
