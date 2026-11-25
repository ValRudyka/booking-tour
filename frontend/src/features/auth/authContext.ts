import { createContext } from 'react'
import type { User } from '../../api/types'

export interface AuthContextValue {
  user: User | null
  /** loading = a stored token is being checked with GET /auth/me (after a reload).
   * maintenance = GET /auth/me answered 503 (maintenance mode, form 4.6.4.1 field 7): the token is
   * kept and nobody is signed out; protected pages show the maintenance page. */
  status: 'loading' | 'guest' | 'user' | 'maintenance'
  /** The API's maintenance text while status is 'maintenance', else null. */
  maintenanceMessage: string | null
  /** Ask GET /auth/me again (the maintenance page's «Спробувати ще раз»). */
  recheck: () => Promise<void>
  /** A recheck is running. */
  rechecking: boolean
  login: (username: string, password: string) => Promise<User>
  logout: () => void
  /** The profile was saved: the header and every page show the new data at once. */
  setUser: (user: User) => void
  /** The client changed the password: the backend has ended every session (this one too), so
   * sign out and ask to sign in with the new password. Booking drafts are kept, as after an
   * expired session. */
  endSessionAfterPasswordChange: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)

/** Router state of /login after a session ended (a 401 on a signed-in request). */
export interface LoginLocationState {
  sessionExpired?: boolean
  accountCreated?: boolean
  /** Came from the password change: «Пароль змінено. Увійдіть з новим паролем.» */
  passwordChanged?: boolean
}

export const ME_KEY = ['auth', 'me'] as const

/** «Олена К.»: the first name and the initial of the last name. */
export function shortName(user: Pick<User, 'first_name' | 'last_name'>): string {
  return `${user.first_name} ${user.last_name.slice(0, 1)}.`
}
