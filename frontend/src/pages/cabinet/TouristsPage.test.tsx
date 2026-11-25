import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { SavedPassport } from '../../api/types'
import { addMonths, expiryState } from '../../features/booking/bookingRules'
import { makeUser, mockServer, signIn, type FakeRequest } from '../../test/fixtures'
import { renderRoute } from '../../test/render'
import { kyivToday } from '../../utils/format'

const USER = makeUser()
const today = kyivToday()

function saved(overrides: Partial<SavedPassport> = {}): SavedPassport {
  return {
    id: 3, last_name_lat: 'KOVALENKO', first_name_lat: 'OLENA', passport_number: 'FX123456',
    issuing_authority: '1234', expiry_date: '2101-01-01', birth_date: '1988-03-09', ...overrides,
  }
}

type Routes = Record<string, (request: FakeRequest) => [number, unknown]>
function backend(list: SavedPassport[], routes: Routes = {}) {
  signIn(USER)
  let current = list
  const calls = mockServer({
    'GET /auth/me': () => [200, USER],
    'GET /me/passports': () => [200, current],
    ...routes,
  })
  return { calls, set: (next: SavedPassport[]) => { current = next } }
}

const item = (name: string) => screen.getByRole('heading', { name }).closest('.ant-list-item') as HTMLElement

describe('/cabinet/tourists', () => {
  it('explains the page and offers to add a tourist when the list is empty', async () => {
    backend([])
    renderRoute('/cabinet/tourists')
    expect(await screen.findByText('Ще немає збережених туристів')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Додати туриста' })).toBeInTheDocument()
  })

  it('lists tourists with the passport partly hidden and an expiry warning', async () => {
    backend([saved(), saved({ id: 4, last_name_lat: 'KOVALENKO', first_name_lat: 'IVAN', passport_number: 'FX654321',
      expiry_date: addMonths(today, 2), birth_date: null })])
    renderRoute('/cabinet/tourists')
    const olena = within(await screen.findByRole('heading', { name: 'KOVALENKO OLENA' }).then(() => item('KOVALENKO OLENA')))
    expect(olena.getByText('FX****56')).toBeInTheDocument()
    expect(olena.queryByText('FX123456')).not.toBeInTheDocument()
    expect(olena.getByText('09.03.1988')).toBeInTheDocument()
    expect(olena.queryByText('Закінчується термін дії')).not.toBeInTheDocument()
    const ivan = within(item('KOVALENKO IVAN'))
    expect(ivan.getByText('Закінчується термін дії')).toBeInTheDocument()
    expect(ivan.getByText(/не вказано/)).toBeInTheDocument()
  })

  it('adds a tourist in a dialog and checks the fields like the booking', async () => {
    const { calls, set } = backend([], {
      'POST /me/passports': (request) => {
        const created = { id: 9, issuing_authority: null, ...(request.body as object) } as SavedPassport
        set([created])
        return [201, created]
      },
    })
    const { user } = renderRoute('/cabinet/tourists')
    await user.click(await screen.findByRole('button', { name: 'Додати туриста' }))
    const dialog = within(await screen.findByRole('dialog'))
    await user.type(dialog.getByLabelText('Прізвище латиницею'), 'Шевченко')
    await user.click(dialog.getByRole('button', { name: 'Зберегти' }))
    expect(await dialog.findByText('Прізвище та ім\'я — латиницею, як у закордонному паспорті')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'POST')).toBe(false)

    await user.clear(dialog.getByLabelText('Прізвище латиницею'))
    await user.type(dialog.getByLabelText('Прізвище латиницею'), 'SHEVCHENKO')
    await user.type(dialog.getByLabelText('Ім\'я латиницею'), 'TARAS')
    await user.type(dialog.getByLabelText('Дата народження'), '09.03.1988{Enter}')
    await user.type(dialog.getByLabelText('Серія та номер закордонного паспорта'), 'fx 777777')
    await user.type(dialog.getByLabelText('Паспорт дійсний до'), '01.01.2101{Enter}')
    await user.click(dialog.getByRole('button', { name: 'Зберегти' }))

    expect(await screen.findByRole('heading', { name: 'SHEVCHENKO TARAS' })).toBeInTheDocument()
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({
      last_name_lat: 'SHEVCHENKO', first_name_lat: 'TARAS', passport_number: 'FX777777', issuing_authority: null,
      expiry_date: '2101-01-01', birth_date: '1988-03-09',
    })
  })

  it('edits a tourist and shows a server rule under its field', async () => {
    const { calls } = backend([saved()], {
      'PUT /me/passports/3': () => [409, { detail: [{ loc: ['body', 'passport_number'],
        msg: 'Паспорт з таким номером уже збережено', type: 'profile_rule' }] }],
    })
    const { user } = renderRoute('/cabinet/tourists')
    await screen.findByRole('heading', { name: 'KOVALENKO OLENA' })
    await user.click(screen.getByRole('button', { name: 'Редагувати: KOVALENKO OLENA' }))
    const dialog = within(await screen.findByRole('dialog'))
    expect(dialog.getByLabelText('Дата народження')).toHaveValue('09.03.1988')
    expect(dialog.getByLabelText('Орган, що видав')).toHaveValue('1234')
    await user.click(dialog.getByRole('button', { name: 'Зберегти' }))
    expect(await dialog.findByText('Паспорт з таким номером уже збережено')).toBeInTheDocument()
    expect(calls.find((c) => c.method === 'PUT')?.body).toMatchObject({ passport_number: 'FX123456', birth_date: '1988-03-09' })
  })

  it('deletes only after the confirmation', async () => {
    const { calls, set } = backend([saved()], {
      'DELETE /me/passports/3': () => {
        set([])
        return [204, null]
      },
    })
    const { user } = renderRoute('/cabinet/tourists')
    await screen.findByRole('heading', { name: 'KOVALENKO OLENA' })
    await user.click(screen.getByRole('button', { name: 'Видалити: KOVALENKO OLENA' }))
    expect(await screen.findByText('Видалити туриста KOVALENKO OLENA?')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false)
    await user.click(screen.getByRole('button', { name: 'Видалити' }))
    expect(await screen.findByText('Ще немає збережених туристів')).toBeInTheDocument()
    await waitFor(() => expect(calls.filter((c) => c.method === 'DELETE')).toHaveLength(1))
  })

  it('tells expired, soon and fine passports apart', () => {
    expect(expiryState('2026-11-25', '2026-11-25')).toBe('expired')
    expect(expiryState('2027-05-24', '2026-11-25')).toBe('soon')
    expect(expiryState('2027-05-25', '2026-11-25')).toBeNull()
  })
})
