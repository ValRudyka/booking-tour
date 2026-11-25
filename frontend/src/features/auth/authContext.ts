import { createContext } from 'react'
import type { User } from '../../api/types'

export interface AuthContextValue {
  user: User | null
  /** loading = a stored token is being checked with GET /auth/me (after a reload). */
  status: 'loading' | 'guest' | 'user'
  login: (username: string, password: string) => Promise<User>
  logout: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)

/** Router state of /login after a session ended (a 401 on a signed-in request). */
export interface LoginLocationState {
  sessionExpired?: boolean
  accountCreated?: boolean
}

export const ME_KEY = ['auth', 'me'] as const

/** «Олена К.»: the first name and the initial of the last name. */
export function shortName(user: Pick<User, 'first_name' | 'last_name'>): string {
  return `${user.first_name} ${user.last_name.slice(0, 1)}.`
}
