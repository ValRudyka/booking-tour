import { useNavigate } from 'react-router'
import { loginPath } from '../auth/redirect'
import { useAuth } from '../auth/useAuth'

/** Where «Забронювати» leads: the booking wizard (pages/booking, spec 04). */
export function bookingPath(tourId: number, date: string): string {
  return `/booking/${tourId}?${new URLSearchParams({ date })}`
}

/**
 * The one place that decides what «Забронювати» does. Only a signed-in client can book
 * (orders are a client's, backend require_roles): a guest is sent to /login with the booking
 * URL as `redirect` and lands back on it after signing in or registering. The booking route
 * itself is behind RequireAuth too, so a typed URL behaves the same.
 */
export function useStartBooking() {
  const navigate = useNavigate()
  const { user } = useAuth()
  return (tourId: number, date: string) => {
    const target = bookingPath(tourId, date)
    navigate(user ? target : loginPath(target))
  }
}
