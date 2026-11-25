import { useNavigate } from 'react-router'

/** Where «Забронювати» leads. Today: a placeholder page (spec 02, §2). */
export function bookingPath(tourId: number, date: string): string {
  return `/booking/${tourId}?${new URLSearchParams({ date })}`
}

/**
 * The one place that decides what «Забронювати» does. When the checkout page and login exist,
 * this is where a guest is sent to sign in first and brought back to the booking afterwards;
 * the buttons on the tour page do not change.
 */
export function useStartBooking() {
  const navigate = useNavigate()
  return (tourId: number, date: string) => navigate(bookingPath(tourId, date))
}
