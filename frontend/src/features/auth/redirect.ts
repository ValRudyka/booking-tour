import type { UserRole } from '../../api/types'

export const STAFF_ROLES: readonly UserRole[] = ['manager', 'finance', 'admin']
export const CLIENT_HOME = '/cabinet/orders'
export const OFFICE_HOME = '/office'

/**
 * A `?redirect=` value is used only when it is a path inside this site: it starts with one "/"
 * and is not "//host" or "/\host" (both are read as another site). Anything else — a full URL,
 * `javascript:`, an empty value — is ignored, so a link cannot send a user elsewhere after login.
 */
export function safeRedirect(value: string | null | undefined): string | null {
  if (!value || !value.startsWith('/') || value.startsWith('//') || value.startsWith('/\\')) return null
  if (/[\r\n\t]/.test(value)) return null
  return value
}

/** Where a user goes after login when there is no (valid) redirect. */
export function homeFor(role: UserRole): string {
  return STAFF_ROLES.includes(role) ? OFFICE_HOME : CLIENT_HOME
}

/** /login?redirect=<path>, e.g. to come back to a booking after signing in. */
export function loginPath(redirectTo?: string | null): string {
  const target = safeRedirect(redirectTo)
  return target ? `/login?${new URLSearchParams({ redirect: target })}` : '/login'
}
