import { Button, Collapse, Descriptions, Drawer, Flex, Table, Tag, Typography } from 'antd'
import type { TableColumnsType } from 'antd'
import type { TFunction } from 'i18next'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router'
import { useAdminUsers, useAuditLog } from '../../../api/admin'
import { ApiError } from '../../../api/client'
import type { AuditEntry } from '../../../api/types'
import { ApiErrorState } from '../../../components/ApiErrorState'
import { FilterBar, type FilterField } from '../../../components/office/FilterBar'
import { roleLabel } from '../../../constants/orderLabels'
import { diffRows, fieldLabel, formatAuditValue, isSecretField, type DiffRow } from '../../../features/admin/auditDiff'
import { useDocumentTitle } from '../../../hooks/useDocumentTitle'
import { formatKyivDateTime } from '../../../utils/format'
import { OfficeForbidden } from '../OfficeHome'
import {
  AUDIT_ACTIONS, AUDIT_ENTITIES, AUDIT_PAGE_SIZE, auditFilterValues, auditFromFilters, auditQuery, auditSearch,
  parseAudit, type AuditState,
} from './auditParams'
import '../../../layouts/OfficeLayout.css'
import './admin.css'

const REFERENCE_TAB: Record<string, string> = {
  country: 'countries', city: 'cities', resort: 'resorts', hotel: 'hotels',
  insurance_type: 'insurance-types', transfer_type: 'transfer-types',
}

/** A label from uk.json, the raw code when the backend writes something new. */
function label(t: TFunction, group: 'entity' | 'action', code: string): string {
  const key = `admin.audit.${group}.${code}`
  const text = t(key as never) as string
  return text === key ? code : text
}

/** Where an entry's object can be opened in the admin's office, if anywhere. */
function objectPath(entry: AuditEntry): string | null {
  if (entry.entity === 'user') return `/office/users?user=${entry.entity_id}`
  if (entry.entity === 'settings') return '/office/settings'
  if (entry.entity === 'language') return '/office/settings'
  const tab = REFERENCE_TAB[entry.entity]
  return tab ? `/office/references?tab=${tab}&archived=true` : null
}

/**
 * «Журнал аудиту» (spec 13 §4, ТЗ 5.9, 7): read only — the database refuses to change or delete
 * entries (an append-only trigger), so the page has no edit or delete buttons. Filters go to the
 * API in the URL (Kyiv days); an entry opens in a Drawer with a «поле — було — стало» table and
 * the raw JSON collapsed. The backend never writes passwords, tokens, keys or passport data
 * (services/audit.py); fields named like a secret are hidden here as well.
 * Not shown: IP and result (not stored), export (no endpoint) — CLAUDE.md backlog.
 */
export function OfficeAuditLogPage() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const state = useMemo(() => parseAudit(searchParams), [searchParams])
  const log = useAuditLog(auditQuery(state))
  const staff = useAdminUsers({ staff: true, page: 1, page_size: 100 })
  useDocumentTitle(t('admin.audit.title'))

  const go = (next: AuditState) => setSearchParams(auditSearch(next))
  const fields: FilterField[] = [
    { kind: 'dateRange', name: 'period', label: t('admin.audit.period'), from: 'date_from', to: 'date_to' },
    {
      kind: 'select', name: 'user_id', label: t('admin.audit.user'),
      options: (staff.data?.items ?? []).map((u) => ({ value: String(u.id), label: `${u.last_name} ${u.first_name} (${roleLabel(t, u.role)})` })),
    },
    { kind: 'select', name: 'action', label: t('admin.audit.actionFilter'), options: AUDIT_ACTIONS.map((a) => ({ value: a, label: label(t, 'action', a) })) },
    { kind: 'select', name: 'entity', label: t('admin.audit.entityFilter'), options: AUDIT_ENTITIES.map((e) => ({ value: e, label: label(t, 'entity', e) })) },
    { kind: 'text', name: 'entity_id', label: t('admin.audit.entityId'), maxLength: 50 },
  ]

  const columns: TableColumnsType<AuditEntry> = [
    { title: t('admin.audit.col.time'), dataIndex: 'created_at', width: 170, render: (value: string) => formatKyivDateTime(value) },
    {
      title: t('admin.audit.col.user'), key: 'user', width: 200,
      render: (_, entry) => entry.user_id === null ? <Typography.Text type="secondary">{t('admin.audit.system')}</Typography.Text>
        : entry.user_name ?? `#${entry.user_id}`,
    },
    { title: t('admin.audit.col.role'), key: 'role', width: 160, render: (_, entry) => (entry.user_role ? roleLabel(t, entry.user_role) : '—') },
    { title: t('admin.audit.col.action'), key: 'action', width: 190, render: (_, entry) => <Tag>{label(t, 'action', entry.action)}</Tag> },
    {
      title: t('admin.audit.col.object'), key: 'object', width: 220,
      render: (_, entry) => {
        const text = `${label(t, 'entity', entry.entity)} #${entry.entity_id}`
        const path = objectPath(entry)
        return path ? <Link to={path}>{text}</Link> : text
      },
    },
    {
      title: t('admin.audit.col.details'), key: 'details', width: 130,
      render: (_, entry) => (
        <Button size="small" onClick={() => go({ ...state, entry: entry.id })}
          aria-label={t('admin.audit.openDetails', { id: entry.id })}>
          {t('admin.audit.details')}
        </Button>
      ),
    },
  ]

  if (log.error instanceof ApiError && log.error.status === 403) return <OfficeForbidden />
  const open = log.data?.items.find((entry) => entry.id === state.entry) ?? null

  return (
    <Flex vertical gap={16}>
      <h1 className="office-page-title">{t('admin.audit.title')}</h1>
      <Typography.Paragraph type="secondary" className="admin-intro">{t('admin.audit.intro')}</Typography.Paragraph>
      <FilterBar fields={fields} values={auditFilterValues(state)} onApply={(values) => go(auditFromFilters(values))} />
      {log.isError && !log.data ? (
        <ApiErrorState error={log.error} onRetry={() => void log.refetch()} title={t('admin.audit.loadFailed')} />
      ) : (
        <Table<AuditEntry> rowKey="id" columns={columns} dataSource={log.data?.items ?? []}
          loading={log.isFetching && !log.data} scroll={{ x: 1100 }} locale={{ emptyText: t('admin.audit.empty') }}
          onChange={(pagination) => go({ ...state, page: pagination.current ?? 1, entry: undefined })}
          pagination={{
            current: state.page, pageSize: AUDIT_PAGE_SIZE, total: log.data?.total ?? 0, showSizeChanger: false,
            showTotal: (total, [from, to]) => t('admin.pagination', { from, to, total }),
          }} />
      )}
      <EntryDrawer entry={open} onClose={() => go({ ...state, entry: undefined })} />
    </Flex>
  )
}

function EntryDrawer({ entry, onClose }: { entry: AuditEntry | null; onClose: () => void }) {
  const { t } = useTranslation()
  const rows = entry ? diffRows(entry.old_value, entry.new_value) : []
  const raw = entry && JSON.stringify(
    { old_value: hideSecrets(entry.old_value), new_value: hideSecrets(entry.new_value) }, null, 2)
  const columns: TableColumnsType<DiffRow> = [
    { title: t('admin.audit.diff.field'), key: 'field', width: '30%', render: (_, row) => fieldLabel(t, row.field) },
    { title: t('admin.audit.diff.before'), key: 'before', render: (_, row) => formatAuditValue(t, row.field, row.before) },
    { title: t('admin.audit.diff.after'), key: 'after', render: (_, row) => formatAuditValue(t, row.field, row.after) },
  ]
  return (
    <Drawer open={entry !== null} onClose={onClose} size={640} destroyOnHidden
      title={entry ? t('admin.audit.entryTitle', { id: entry.id }) : ''}>
      {entry && (
        <Flex vertical gap={16}>
          <Descriptions size="small" column={1} bordered items={[
            { key: 'time', label: t('admin.audit.col.time'), children: formatKyivDateTime(entry.created_at) },
            { key: 'user', label: t('admin.audit.col.user'), children: entry.user_id === null ? t('admin.audit.system')
              : `${entry.user_name ?? `#${entry.user_id}`}${entry.user_role ? `, ${roleLabel(t, entry.user_role)}` : ''}` },
            { key: 'action', label: t('admin.audit.col.action'), children: label(t, 'action', entry.action) },
            { key: 'object', label: t('admin.audit.col.object'), children: `${label(t, 'entity', entry.entity)} #${entry.entity_id}` },
          ]} />
          <h2 className="admin-card-title">{t('admin.audit.diff.title')}</h2>
          <Table<DiffRow> rowKey="field" size="small" pagination={false} columns={columns} dataSource={rows}
            rowClassName={(row) => (row.changed && entry.old_value && entry.new_value ? 'admin-diff-changed' : '')}
            locale={{ emptyText: t('admin.audit.diff.empty') }} />
          <Collapse items={[{
            key: 'raw', label: t('admin.audit.raw'),
            children: <pre className="admin-json" data-testid="audit-raw">{raw}</pre>,
          }]} />
        </Flex>
      )}
    </Drawer>
  )
}

function hideSecrets(values: Record<string, unknown> | null): Record<string, unknown> | null {
  if (!values) return values
  return Object.fromEntries(Object.entries(values).map(([k, v]) => [k, isSecretField(k) ? '***' : v]))
}
