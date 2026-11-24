import axios, { AxiosError, type AxiosInstance } from 'axios'
import i18n from '../i18n'

/** Backend origin, e.g. http://localhost:8000 (frontend/.env.local, see .env.example). */
export const API_URL = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '')

/**
 * The single shape every page gets for a failed request, so the UI can show one clear message
 * instead of digging through axios internals.
 * - network: no response at all (backend down, CORS refused, offline)
 * - maintenance: 503 from the maintenance guard (form 4.6.4.1, field 7)
 */
export type ApiErrorKind =
  | 'network' | 'maintenance' | 'not_found' | 'validation' | 'client' | 'server'

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly status: number | null

  constructor(kind: ApiErrorKind, status: number | null, message: string) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
  }
}

/** FastAPI errors: {detail: "text"} from HTTPException, {detail: [...]} from validation (422). */
function detailMessage(data: unknown): string | null {
  if (data && typeof data === 'object' && 'detail' in data) {
    const { detail } = data as { detail: unknown }
    if (typeof detail === 'string' && detail.trim()) return detail
  }
  return null
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error
  if (!(error instanceof AxiosError) || !error.response) {
    return new ApiError('network', null, i18n.t('errors.network'))
  }
  const { status, data } = error.response
  const detail = detailMessage(data)
  if (status === 503) return new ApiError('maintenance', status, detail ?? i18n.t('errors.maintenance'))
  if (status === 404) return new ApiError('not_found', status, detail ?? i18n.t('errors.notFound'))
  // 422 details are technical (field paths, pydantic texts), so the user gets a generic text.
  if (status === 422) return new ApiError('validation', status, i18n.t('errors.validation'))
  if (status >= 500) return new ApiError('server', status, i18n.t('errors.server'))
  return new ApiError('client', status, detail ?? i18n.t('errors.client'))
}

export function createApiClient(): AxiosInstance {
  const client = axios.create({
    baseURL: `${API_URL}/api`,
    timeout: 15_000,
    // FastAPI reads list parameters as repeated keys: stars=4&stars=5. axios' default would
    // send stars[]=4, which FastAPI silently ignores.
    paramsSerializer: { indexes: null },
  })
  client.interceptors.response.use(undefined, (error: unknown) => Promise.reject(toApiError(error)))
  return client
}

export const api = createApiClient()

/** Public files (tour photos) come as server paths like /uploads/tours/1/a.jpg. */
export function mediaUrl(path: string | null | undefined): string | null {
  if (!path) return null
  if (/^https?:\/\//.test(path)) return path
  return `${API_URL}${path.startsWith('/') ? '' : '/'}${path}`
}
