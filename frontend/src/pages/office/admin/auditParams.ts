import type { AuditLogQuery } from '../../../api/types'
import type { FilterValues } from '../../../components/office/FilterBar'
import { readDate, readPage, readText, writeParams } from '../../../features/office/urlState'

// /office/audit-log state in the URL (spec 13 §4) under the API's parameter names.

export const AUDIT_PAGE_SIZE = 50
/** What the backend writes (audit() call sites); labels in uk.json admin.audit.entity / action. */
export const AUDIT_ENTITIES = ['user', 'settings', 'country', 'city', 'resort', 'hotel', 'insurance_type',
  'transfer_type', 'language', 'promo_code', 'tour', 'tour_image', 'order'] as const
export const AUDIT_ACTIONS = ['created', 'updated', 'deleted', 'archived', 'restored', 'role_changed', 'blocked',
  'unblocked', 'password_reset', 'status_change', 'manager_assigned', 'cancel_requested', 'hold_extended'] as const

export interface AuditState {
  user_id?: number
  entity?: string
  entity_id?: string
  action?: string
  date_from?: string
  date_to?: string
  page: number
  /** The entry whose details are open. */
  entry?: number
}

const positive = (params: URLSearchParams, key: string) => {
  const value = Number(params.get(key))
  return Number.isInteger(value) && value > 0 ? value : undefined
}

export function parseAudit(params: URLSearchParams): AuditState {
  return {
    user_id: positive(params, 'user_id'),
    entity: readText(params, 'entity', 50),
    entity_id: readText(params, 'entity_id', 50),
    action: readText(params, 'action', 50),
    date_from: readDate(params, 'date_from'),
    date_to: readDate(params, 'date_to'),
    page: readPage(params),
    entry: positive(params, 'entry'),
  }
}

export function auditSearch(state: AuditState): URLSearchParams {
  return writeParams({ ...state }, { page: 1 })
}

export function auditQuery(state: AuditState): AuditLogQuery {
  const query: AuditLogQuery = { page: state.page, page_size: AUDIT_PAGE_SIZE }
  for (const key of ['user_id', 'entity', 'entity_id', 'action', 'date_from', 'date_to'] as const) {
    if (state[key] !== undefined) (query as Record<string, unknown>)[key] = state[key]
  }
  return query
}

export function auditFilterValues(state: AuditState): FilterValues {
  return { user_id: state.user_id?.toString(), entity: state.entity, entity_id: state.entity_id, action: state.action,
    date_from: state.date_from, date_to: state.date_to }
}

export function auditFromFilters(values: FilterValues): AuditState {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(values)) if (typeof value === 'string' && value) params.set(key, value)
  return { ...parseAudit(params), page: 1, entry: undefined }
}
