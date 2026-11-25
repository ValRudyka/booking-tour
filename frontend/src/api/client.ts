import axios, { AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'
import { getToken } from '../features/auth/tokenStorage'
import i18n from '../i18n'

/** Backend origin, e.g. http://localhost:8000 (frontend/.env.local, see .env.example). */
export const API_URL = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '')

/**
 * The single shape every page gets for a failed request, so the UI can show one clear message
 * instead of digging through axios internals.
 * - network: no response at all (backend down, CORS refused, offline)
 * - maintenance: 503 from the maintenance guard (form 4.6.4.1, field 7)
 * - unauthorized: 401 (wrong login, or a token that expired or was cancelled)
 * - rate_limited: 429 (ready for a login rate limit, feature/auth-rate-limit)
 */
export type ApiErrorKind =
  | 'network' | 'maintenance' | 'not_found' | 'validation' | 'unauthorized' | 'rate_limited'
  | 'client' | 'server'

/** One item of a FastAPI 422 body: where (loc) and what (type); msg is often English. */
export interface FieldIssue {
  loc: (string | number)[]
  type: string
  msg: string
}

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly status: number | null
  /** The backend's plain `detail` text, for mapping known messages (never shown as is). */
  readonly detail: string | null
  /** 422 field issues, for showing errors under the right form fields. */
  readonly issues: FieldIssue[]

  constructor(kind: ApiErrorKind, status: number | null, message: string,
    detail: string | null = null, issues: FieldIssue[] = []) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
    this.detail = detail
    this.issues = issues
  }
}

/** FastAPI errors: {detail: "text"} from HTTPException, {detail: [...]} from validation (422). */
function parseDetail(data: unknown): { text: string | null; issues: FieldIssue[] } {
  if (!data || typeof data !== 'object' || !('detail' in data)) return { text: null, issues: [] }
  const { detail } = data as { detail: unknown }
  if (typeof detail === 'string' && detail.trim()) return { text: detail, issues: [] }
  if (Array.isArray(detail)) {
    const issues = detail.filter((d): d is FieldIssue =>
      !!d && typeof d === 'object' && Array.isArray((d as FieldIssue).loc) && typeof (d as FieldIssue).type === 'string')
    return { text: null, issues }
  }
  return { text: null, issues: [] }
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error
  if (!(error instanceof AxiosError) || !error.response) {
    return new ApiError('network', null, i18n.t('errors.network'))
  }
  const { status, data } = error.response
  const { text, issues } = parseDetail(data)
  if (status === 503) return new ApiError('maintenance', status, text ?? i18n.t('errors.maintenance'), text)
  if (status === 404) return new ApiError('not_found', status, text ?? i18n.t('errors.notFound'), text)
  if (status === 401) return new ApiError('unauthorized', status, i18n.t('errors.unauthorized'), text)
  if (status === 429) return new ApiError('rate_limited', status, i18n.t('errors.rateLimited'), text)
  // 422 details are technical (field paths, pydantic texts): pages map them per field
  // (features/auth/authErrors.ts); the message itself stays generic. Other 4xx keep their issues
  // too: a rule about one field may answer 409 with a loc (an e-mail in use, PATCH /auth/me; a
  // locked tour field, PATCH /manager/tours/{id}).
  if (status === 422) return new ApiError('validation', status, i18n.t('errors.validation'), text, issues)
  if (status >= 500) return new ApiError('server', status, i18n.t('errors.server'), text)
  return new ApiError('client', status, text ?? i18n.t('errors.client'), text, issues)
}

declare module 'axios' {
  interface AxiosRequestConfig {
    /** A 401 here does not end the session with a redirect (the start-up /me check). */
    skipAuthRedirect?: boolean
  }
}

/** Called once for a 401 on a request that carried a token (expired, blocked, or cancelled by an
 * admin password reset). AuthProvider sets it: sign out and go to /login. */
let unauthorizedHandler: (() => void) | null = null
export function onUnauthorized(handler: (() => void) | null) {
  unauthorizedHandler = handler
}

/** Called for a maintenance 503 on a request that carried a token (maintenance switched on while
 * someone is signed in). AuthProvider sets it: check GET /auth/me again, which answers 503 to
 * everyone but an admin, so the protected pages show the maintenance page instead of their
 * errors. A 503 never signs anyone out. */
let maintenanceHandler: (() => void) | null = null
export function onMaintenance(handler: (() => void) | null) {
  maintenanceHandler = handler
}

export function createApiClient(): AxiosInstance {
  const client = axios.create({
    baseURL: `${API_URL}/api`,
    timeout: 15_000,
    // FastAPI reads list parameters as repeated keys: stars=4&stars=5. axios' default would
    // send stars[]=4, which FastAPI silently ignores.
    paramsSerializer: { indexes: null },
  })
  client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    const token = getToken()
    if (token && !config.headers.has('Authorization')) config.headers.set('Authorization', `Bearer ${token}`)
    return config
  })
  client.interceptors.response.use(undefined, (error: unknown) => {
    const apiError = toApiError(error)
    // No refresh token exists, so there is nothing to retry and no loop: a 401 with a token
    // means the session is over. A 401 from the login form itself is just a wrong password.
    if (apiError.kind === 'unauthorized' && error instanceof AxiosError) {
      const sentToken = error.config?.headers?.has?.('Authorization')
      const isLogin = (error.config?.url ?? '').endsWith('/auth/login')
      if (sentToken && !isLogin && !error.config?.skipAuthRedirect) unauthorizedHandler?.()
    }
    // /auth/me itself is the check, and a refused login is shown by the login form.
    if (apiError.kind === 'maintenance' && error instanceof AxiosError) {
      const sentToken = error.config?.headers?.has?.('Authorization')
      const url = error.config?.url ?? ''
      if (sentToken && !url.endsWith('/auth/me') && !url.endsWith('/auth/login')) maintenanceHandler?.()
    }
    return Promise.reject(apiError)
  })
  return client
}

export const api = createApiClient()

/** Public files (tour photos) come as server paths like /uploads/tours/1/a.jpg. */
export function mediaUrl(path: string | null | undefined): string | null {
  if (!path) return null
  if (/^https?:\/\//.test(path)) return path
  return `${API_URL}${path.startsWith('/') ? '' : '/'}${path}`
}
