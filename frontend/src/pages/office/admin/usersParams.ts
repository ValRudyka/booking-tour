import type { AdminUsersQuery, UserRole } from '../../../api/types'
import type { FilterValues } from '../../../components/office/FilterBar'
import { readEnum, readPage, readText, writeParams } from '../../../features/office/urlState'

// /office/users state in the URL (spec 13 §1): tab, filters, page and the open user.

export const USER_TABS = ['staff', 'clients'] as const
export type UserTab = (typeof USER_TABS)[number]
export const STAFF_ROLES = ['manager', 'finance', 'admin'] as const satisfies readonly UserRole[]
export const ACTIVE_VALUES = ['true', 'false'] as const
export const USERS_PAGE_SIZE = 20

export interface UsersState {
  tab: UserTab
  q?: string
  role?: (typeof STAFF_ROLES)[number]
  isActive?: (typeof ACTIVE_VALUES)[number]
  page: number
  /** The user whose card is open. */
  user?: number
}

export function parseUsers(params: URLSearchParams): UsersState {
  const tab = readEnum(params, 'tab', USER_TABS) ?? 'staff'
  const user = Number(params.get('user'))
  return {
    tab,
    q: readText(params, 'q', 100),
    role: tab === 'staff' ? readEnum(params, 'role', STAFF_ROLES) : undefined,
    isActive: readEnum(params, 'is_active', ACTIVE_VALUES),
    page: readPage(params),
    user: Number.isInteger(user) && user > 0 ? user : undefined,
  }
}

export function usersSearch(state: UsersState): URLSearchParams {
  return writeParams({ tab: state.tab, q: state.q, role: state.role, is_active: state.isActive,
    page: state.page, user: state.user }, { tab: 'staff', page: 1 })
}

export function usersQuery(state: UsersState): AdminUsersQuery {
  return {
    staff: state.tab === 'staff', page: state.page, page_size: USERS_PAGE_SIZE,
    ...(state.q ? { q: state.q } : {}),
    ...(state.role ? { role: state.role } : {}),
    ...(state.isActive ? { is_active: state.isActive === 'true' } : {}),
  }
}

export function usersFilterValues(state: UsersState): FilterValues {
  return { q: state.q, role: state.role, is_active: state.isActive }
}

export function usersFromFilters(state: UsersState, values: FilterValues): UsersState {
  const one = (key: string) => (typeof values[key] === 'string' ? values[key] as string : undefined)
  const params = new URLSearchParams()
  for (const key of ['q', 'role', 'is_active']) {
    const value = one(key)
    if (value) params.set(key, value)
  }
  const read = parseUsers(new URLSearchParams([...params, ['tab', state.tab]]))
  return { ...state, q: read.q, role: read.role, isActive: read.isActive, page: 1, user: undefined }
}
