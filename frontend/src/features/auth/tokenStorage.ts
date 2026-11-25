/**
 * Where the access token lives: localStorage, so the sign-in survives a reload and is shared by
 * tabs. Trade-off: a script injected into the page (XSS) could read it; React escapes all output,
 * the app has no third-party scripts or dangerouslySetInnerHTML, and the token lives 60 minutes.
 * An httpOnly cookie would need cookie auth and CSRF protection in the backend.
 * The backend issues no refresh token (POST /api/auth/login returns only access_token).
 */
export const TOKEN_KEY = 'tour.auth.token'

export function getToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY)
  } catch {
    return null // storage blocked (private mode settings): behave as a guest
  }
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY)
}

/** Another tab signed in or out: `token` is the new value (null = signed out). */
export function onTokenChangeInOtherTab(listener: (token: string | null) => void): () => void {
  const handler = (event: StorageEvent) => {
    if (event.key === TOKEN_KEY || event.key === null) listener(getToken())
  }
  window.addEventListener('storage', handler)
  return () => window.removeEventListener('storage', handler)
}
