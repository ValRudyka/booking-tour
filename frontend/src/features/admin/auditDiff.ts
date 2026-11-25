import type { TFunction } from 'i18next'
import type { UserRole } from '../../api/types'
import { formatKyivDateTime } from '../../utils/format'

// The audit log's «було / стало» (spec 13 §4): one row per field of the old and new values, in
// readable words instead of raw JSON.

type Json = unknown

export interface DiffRow {
  field: string
  before: Json
  after: Json
  /** The value differs (an entry of "created" has only `after`, "deleted" only `before`). */
  changed: boolean
}

/** Field names the backend never writes (services/audit.py drops them); hidden here as well, so a
 * future mistake on the server still never puts a secret on the screen. */
const SECRET = /password|secret|token|hash|key/i
export const isSecretField = (field: string) => SECRET.test(field)

const ISO_DATETIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?$/
const ROLES = new Set(['client', 'manager', 'finance', 'admin'])

export function diffRows(before: Record<string, Json> | null, after: Record<string, Json> | null): DiffRow[] {
  const keys = [...new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})])]
  return keys.map((field) => {
    const old = before?.[field]
    const next = after?.[field]
    return { field, before: old, after: next, changed: JSON.stringify(old) !== JSON.stringify(next) }
  })
}

/** One value as text: «—» for nothing, Так / Ні, lists joined, ISO times as Kyiv time, role labels. */
export function formatAuditValue(t: TFunction, field: string, value: Json): string {
  if (isSecretField(field)) return t('admin.audit.hidden')
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? t('admin.audit.yes') : t('admin.audit.no')
  if (Array.isArray(value)) return value.length ? value.map((v) => formatAuditValue(t, '', v)).join(', ') : '—'
  if (typeof value === 'string') {
    if (ISO_DATETIME.test(value)) return formatKyivDateTime(value)
    if (field === 'role' && ROLES.has(value)) return t(`userRole.${value as UserRole}`)
    return value
  }
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

/** A field's Ukrainian label, the raw name when there is none. */
export function fieldLabel(t: TFunction, field: string): string {
  const key = `admin.audit.fields.${field}`
  const label = t(key as never) as string
  return label === key ? field : label
}
