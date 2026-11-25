import { configure, screen, waitFor, within } from '@testing-library/react'
import { beforeAll, describe, expect, it } from 'vitest'
import i18n from '../../../i18n'
import { diffRows, formatAuditValue } from '../../../features/admin/auditDiff'
import { mockServer, signIn, type FakeRequest } from '../../../test/fixtures'
import { makeAuditEntry, makeSettings, usersPage } from '../../../test/adminFixtures'
import { ADMIN } from '../../../test/officeFixtures'
import { renderRoute, searchOf } from '../../../test/render'

type Handler = (request: FakeRequest) => [number, unknown]
const ROLE_CHANGE = makeAuditEntry()
const SYSTEM = makeAuditEntry({ id: 902, user_id: null, user_name: null, user_role: null, entity: 'order', entity_id: '55',
  action: 'hold_extended', old_value: { hold_expires_at: '2026-11-24T10:00:00+00:00' },
  new_value: { hold_expires_at: '2026-11-26T10:00:00+00:00', reason: 'bank_transfer' } })

function backend(extra: Record<string, Handler> = {}) {
  signIn(ADMIN)
  return mockServer({
    'GET /auth/me': () => [200, ADMIN],
    'GET /admin/settings': () => [200, makeSettings()],
    'GET /admin/users': () => [200, usersPage([])],
    'GET /admin/audit-log': () => [200, { items: [ROLE_CHANGE, SYSTEM], total: 2, page: 1, page_size: 50 }],
    ...extra,
  })
}
const lastQuery = (calls: FakeRequest[]) => calls.filter((c) => c.url === '/admin/audit-log').at(-1)?.params

configure({ asyncUtilTimeout: 4000 })
beforeAll(async () => {
  await Promise.all([import('../../../layouts/OfficeLayout'), import('./OfficeAuditLogPage')])
})

describe('/office/audit-log (spec 13 §4)', () => {
  it('is read only: rows with author, role, action and object, and no change buttons', async () => {
    const calls = backend()
    renderRoute('/office/audit-log')
    const row = (await screen.findByRole('link', { name: 'Користувач #810' })).closest('tr') as HTMLElement
    expect(row).toHaveTextContent('Адмін Системний')
    expect(row).toHaveTextContent('Адміністратор')
    expect(within(row).getByText('Зміна ролі')).toBeInTheDocument()
    expect(screen.getByText('Система')).toBeInTheDocument()
    expect(lastQuery(calls)).toEqual({ page: 1, page_size: 50 })
    for (const name of [/Редагувати/, /Видалити/, /Змінити/, /Зберегти/]) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument()
    }
    expect(calls.every((c) => c.method === 'GET')).toBe(true)
  })

  it('sends the filters to the API and keeps them in the URL', async () => {
    const calls = backend()
    const { user, router } = renderRoute('/office/audit-log')
    await user.type(await screen.findByLabelText("Id об'єкта"), '810')
    await user.click(screen.getByRole('combobox', { name: 'Дія' }))
    await user.click(await screen.findByTitle('Зміна ролі'))
    await user.click(screen.getByRole('button', { name: /Знайти/ }))
    await waitFor(() => expect(lastQuery(calls)).toEqual({ page: 1, page_size: 50, entity_id: '810', action: 'role_changed' }))
    expect(searchOf(router).get('action')).toBe('role_changed')
  })

  it('details show «було / стало» as a table, the raw JSON only under the spoiler', async () => {
    backend()
    const { user } = renderRoute('/office/audit-log')
    await user.click(await screen.findByRole('button', { name: 'Деталі запису 901' }))
    const drawer = (await screen.findByText('Запис журналу 901')).closest('[role="dialog"]') as HTMLElement
    expect(within(drawer).getByRole('columnheader', { name: 'Було' })).toBeInTheDocument()
    const row = within(drawer).getByText('Роль', { selector: 'td' }).closest('tr') as HTMLElement
    expect(row).toHaveTextContent('Менеджер')
    expect(row).toHaveTextContent('Фінансовий контролер')
    expect(within(drawer).queryByTestId('audit-raw')).not.toBeInTheDocument()
    await user.click(within(drawer).getByRole('button', { name: /Сирі дані/ }))
    expect(await within(drawer).findByTestId('audit-raw')).toHaveTextContent('"role": "finance"')
  })
})

describe('audit before / after formatting', () => {
  const t = i18n.t.bind(i18n)
  it('lists every field of both sides and marks the changed ones', () => {
    expect(diffRows({ a: 1, b: 'x' }, { b: 'y', c: true })).toEqual([
      { field: 'a', before: 1, after: undefined, changed: true },
      { field: 'b', before: 'x', after: 'y', changed: true },
      { field: 'c', before: undefined, after: true, changed: true },
    ])
    expect(diffRows(null, { a: [1] })[0].changed).toBe(true)
    expect(diffRows({ a: [1] }, { a: [1] })[0].changed).toBe(false)
  })

  it('reads values in words and never shows a secret-looking field', () => {
    expect(formatAuditValue(t, 'is_active', false)).toBe('Ні')
    expect(formatAuditValue(t, 'amenities', ['Басейн', 'Wi-Fi'])).toBe('Басейн, Wi-Fi')
    expect(formatAuditValue(t, 'amenities', [])).toBe('—')
    expect(formatAuditValue(t, 'stars', null)).toBe('—')
    expect(formatAuditValue(t, 'role', 'finance')).toBe('Фінансовий контролер')
    expect(formatAuditValue(t, 'sessions_ended_at', '2026-11-24T08:15:00+00:00')).toMatch(/24\.11\.2026/)
    expect(formatAuditValue(t, 'password_hash', '$argon2id$v=19')).toBe('приховано')
    expect(formatAuditValue(t, 'access_token', 'eyJ...')).toBe('приховано')
  })
})
