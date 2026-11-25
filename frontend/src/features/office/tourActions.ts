import type { LockedField, ManagerTour, ManagerTourRow, TourAction, TourActionInfo } from '../../api/types'

/** The parts of a tour (list row or full card) that decide its buttons (spec 10). */
export type TourStateLike = Pick<ManagerTourRow | ManagerTour,
  'id' | 'title_uk' | 'status' | 'tour_actions' | 'active_bookings' | 'archive_cancels' | 'for_sale'>

/** One of the tour's `tour_actions` (decided by the backend's services/tour_actions.py), or
 * undefined when the API does not list it: then the page shows nothing for it. */
export function findTourAction(tour: Pick<TourStateLike, 'tour_actions'>, action: TourAction): TourActionInfo | undefined {
  return tour.tour_actions.find((a) => a.action === action)
}

/** Why a form field is locked now (services/tours.py LOCKED_FIELDS), or undefined. */
export function lockReason(locked: LockedField[], field: string): string | undefined {
  return locked.find((item) => item.field === field)?.reason
}

/** The editor may change the tour (a draft); otherwise the form is read-only. */
export function canEdit(tour: Pick<TourStateLike, 'tour_actions'> | undefined): boolean {
  return !tour || findTourAction(tour, 'edit')?.allowed === true
}
