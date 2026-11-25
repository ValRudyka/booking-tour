import type { ManagerOrder, StaffAction, StaffActionInfo } from '../../api/types'

/** One of the order's `staff_actions` (decided by the backend's services/staff_actions.py), or
 * undefined when the API does not list it: then the page shows nothing for it. */
export function findAction(order: ManagerOrder, action: StaffAction): StaffActionInfo | undefined {
  return order.staff_actions.find((a) => a.action === action)
}
