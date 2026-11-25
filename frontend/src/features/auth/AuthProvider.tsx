import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router'
import { fetchMe, loginRequest } from '../../api/auth'
import { ApiError, onMaintenance, onUnauthorized } from '../../api/client'
import type { User } from '../../api/types'
import { AuthContext, ME_KEY, type AuthContextValue, type LoginLocationState } from './authContext'
import { clearAllDrafts } from '../booking/bookingDraft'
import { loginPath } from './redirect'
import { clearToken, getToken, onTokenChangeInOtherTab, setToken } from './tokenStorage'

/** How often the maintenance page asks GET /auth/me again by itself. */
export const MAINTENANCE_RECHECK_MS = 60_000

const isMaintenance = (error: unknown) => error instanceof ApiError && error.kind === 'maintenance'

/**
 * Who is signed in. After a reload the user is restored by asking the backend (GET /auth/me),
 * not by trusting the stored token: a blocked user, a changed role or an admin password reset
 * all show up there. A layout route, so it can navigate (see router.tsx).
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  // The page the visitor is on, from the router (not window.location): where to come back to.
  const location = useLocation()
  const here = useRef('')
  useEffect(() => {
    here.current = `${location.pathname}${location.search}`
  }, [location])
  const [token, setTokenState] = useState<string | null>(() => getToken())

  // A stored token the backend refuses after a reload simply means "guest": drop it quietly
  // (no redirect from a public page; a protected page goes to /login through RequireAuth).
  // A 503 (maintenance) is not a refusal: the token stays and the status is 'maintenance', so
  // RequireAuth shows the maintenance page instead of sending staff to /login, where they would
  // log in and come back to the same 503 (the login loop). While it lasts, /auth/me is asked again
  // every minute and when the window gets focus; an admin gets 200 there and is never affected.
  const me = useQuery({
    queryKey: ME_KEY,
    queryFn: async (): Promise<User | null> => {
      try {
        return await fetchMe()
      } catch (error) {
        if (error instanceof ApiError && error.kind === 'unauthorized') {
          clearToken()
          return null
        }
        throw error
      }
    },
    enabled: token !== null,
    retry: false,
    staleTime: Infinity,
    refetchInterval: (query) => (isMaintenance(query.state.error) ? MAINTENANCE_RECHECK_MS : false),
    refetchOnWindowFocus: (query) => (isMaintenance(query.state.error) ? 'always' : false),
  })
  const { refetch: refetchMe } = me

  const forget = useCallback(() => {
    clearToken()
    setTokenState(null)
    queryClient.clear() // no private data stays in the cache after sign-out
  }, [queryClient])

  // A token the backend refuses while in use (expired after 60 min, user blocked, password reset
  // by the admin): sign out and ask to sign in again, then come back to the same page.
  useEffect(() => {
    onUnauthorized(() => {
      const back = here.current
      forget()
      navigate(loginPath(back), { replace: true, state: { sessionExpired: true } satisfies LoginLocationState })
    })
    return () => onUnauthorized(null)
  }, [forget, navigate])

  // Maintenance switched on while signed in: a request answered 503, so check /auth/me again
  // (an in-flight check is not restarted when several requests fail at once).
  useEffect(() => {
    onMaintenance(() => {
      if (getToken() !== null) void queryClient.refetchQueries({ queryKey: ME_KEY }, { cancelRefetch: false })
    })
    return () => onMaintenance(null)
  }, [queryClient])

  const recheck = useCallback(async () => {
    await refetchMe()
  }, [refetchMe])

  // Sign-in or sign-out in another tab.
  useEffect(() => onTokenChangeInOtherTab((next) => {
    setTokenState(next)
    if (next === null) queryClient.clear()
    else void queryClient.invalidateQueries({ queryKey: ME_KEY })
  }), [queryClient])

  const login = useCallback(async (username: string, password: string) => {
    const result = await loginRequest(username, password)
    setToken(result.access_token)
    queryClient.setQueryData(ME_KEY, result.user)
    setTokenState(result.access_token)
    return result.user
  }, [queryClient])

  // Signing out on a protected page must end on the catalog, not on /login. The router normally
  // renders the next page in a transition, so RequireAuth would first see the guest on the old
  // page and redirect. flushSync renders the catalog right away; only then the session is cleared.
  // An explicit sign-out also removes booking drafts (names and birth dates of tourists); an
  // expired session (onUnauthorized above) keeps them, so the client returns to the same step.
  const logout = useCallback(() => {
    void navigate('/tours', { replace: true, flushSync: true })
    clearAllDrafts()
    forget()
  }, [forget, navigate])

  const setUser = useCallback((next: User) => {
    queryClient.setQueryData(ME_KEY, next)
  }, [queryClient])

  // Like logout: render /login first (flushSync), then clear the session. LoginPage does not send
  // a still signed-in user away while `passwordChanged` is in its state.
  const endSessionAfterPasswordChange = useCallback(() => {
    void navigate('/login', { replace: true, flushSync: true,
      state: { passwordChanged: true } satisfies LoginLocationState })
    forget()
  }, [forget, navigate])

  const value = useMemo<AuthContextValue>(() => {
    // The last check decides: a user restored before maintenance began is not shown as signed in.
    const down = token !== null && me.isError && isMaintenance(me.error)
    const user = !down && token !== null && me.data ? me.data : null
    const status = down ? 'maintenance' : user ? 'user' : token !== null && me.isPending ? 'loading' : 'guest'
    return {
      user, status, login, logout, setUser, endSessionAfterPasswordChange, recheck,
      maintenanceMessage: down ? (me.error as ApiError).message : null,
      rechecking: me.isFetching,
    }
  }, [token, me.data, me.isPending, me.isError, me.error, me.isFetching, login, logout, setUser,
    endSessionAfterPasswordChange, recheck])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

/** The root route element: AuthProvider around every page. */
export function AuthRoot() {
  return <AuthProvider><Outlet /></AuthProvider>
}
