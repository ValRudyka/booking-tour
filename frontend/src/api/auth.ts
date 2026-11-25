import { api } from './client'
import type { RegisterRequest, TokenOut, User } from './types'

/** OAuth2 password flow: a form body; `username` takes a phone number or an e-mail. */
export async function loginRequest(username: string, password: string): Promise<TokenOut> {
  const body = new URLSearchParams({ username, password })
  return (await api.post<TokenOut>('/auth/login', body)).data
}

/** Returns the new user; the backend issues no token here, so the page logs in right after. */
export async function registerRequest(data: RegisterRequest): Promise<User> {
  return (await api.post<User>('/auth/register', data)).data
}

/** Who the stored token belongs to. Used at start-up, so a refused token just means "guest"
 * (no redirect to /login from a public page the visitor is reading). */
export async function fetchMe(): Promise<User> {
  return (await api.get<User>('/auth/me', { skipAuthRedirect: true })).data
}
