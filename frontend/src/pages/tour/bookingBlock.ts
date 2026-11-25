import type { TourDetail } from '../../api/types'

/** Why «Забронювати» is disabled (an i18n key under booking.*), or null when it is not. */
export function bookingBlock(tour: TourDetail, date: string | null): 'noSeats' | 'noDates' | null {
  if (tour.free_seats <= 0) return 'noSeats'
  if (date === null) return 'noDates'
  return null
}
