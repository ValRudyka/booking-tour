import { configure, screen, waitFor, within } from '@testing-library/react'
import { beforeAll, describe, expect, it } from 'vitest'
import { mockServer, signIn, type FakeRequest } from '../../../test/fixtures'
import { ADMIN_ROW, makeAdminUser, makeSettings, usersPage, userAllowed, userRefused } from '../../../test/adminFixtures'
import { ADMIN } from '../../../test/officeFixtures'
import { renderRoute, searchOf } from '../../../test/render'

type Handler = (request: FakeRequest) => [number, unknown]
const MANAGER_ROW = makeAdminUser()

function backend(extra: Record<string, Handler> = {}) {
  signIn(ADMIN)
  return mockServer({
    'GET /auth/me': () => [200, ADMIN],
    'GET /admin/settings': () => [200, makeSettings()],
    'GET /admin/users': () => [200, usersPage([ADMIN_ROW, MANAGER_ROW])],
    [`GET /admin/users/${ADMIN.id}`]: () => [200, ADMIN_ROW],
    [`GET /admin/users/${MANAGER_ROW.id}`]: () => [200, MANAGER_ROW],
    ...extra,
  })
}
// antd gives every dialog the same aria-labelledby id under test, so a Modal opened over the
// Drawer is found by its title text instead of its accessible name.
async function dialogTitled(title: string): Promise<HTMLElement> {
  const heading = await screen.findByText(title, { selector: '.ant-modal-title' })
  return heading.closest('[role="dialog"]') as HTMLElement
}
const lastList = (calls: FakeRequest[]) => calls.filter((c) => c.method === 'GET' && c.url === '/admin/users').at(-1)?.params

configure({ asyncUtilTimeout: 4000 })
beforeAll(async () => {
  await Promise.all([import('../../../layouts/OfficeLayout'), import('./OfficeUsersPage')])
})

describe('/office/users (spec 13 §1)', () => {
  it('lists the staff tab with the server filters, then the clients tab', async () => {
    const calls = backend()
    const { user, router } = renderRoute('/office/users')
    expect(await screen.findByRole('heading', { level: 1, name: 'Користувачі' })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Коваль Олена' })).toBeInTheDocument()
    expect(lastList(calls)).toEqual({ staff: true, page: 1, page_size: 20 })
    await user.type(screen.getByLabelText('Пошук'), 'Коваль')
    await user.click(screen.getByRole('button', { name: /Знайти/ }))
    await waitFor(() => expect(lastList(calls)).toEqual({ staff: true, page: 1, page_size: 20, q: 'Коваль' }))
    expect(searchOf(router).get('q')).toBe('Коваль')
    await user.click(screen.getByRole('tab', { name: 'Клієнти' }))
    await waitFor(() => expect(lastList(calls)).toEqual({ staff: false, page: 1, page_size: 20 }))
    expect(screen.queryByRole('button', { name: /Додати співробітника/ })).not.toBeInTheDocument()
  })

  it('shows the rules for yourself as disabled buttons with the server reason', async () => {
    backend()
    const { user } = renderRoute(`/office/users?user=${ADMIN.id}`)
    const drawer = await screen.findByRole('dialog')
    const block = await within(drawer).findByRole('button', { name: 'Заблокувати' })
    expect(block).toBeDisabled()
    expect(block).toHaveAccessibleDescription('Не можна заблокувати себе')
    expect(within(drawer).getByRole('button', { name: 'Змінити роль' })).toBeDisabled()
    expect(within(drawer).getByRole('button', { name: 'Скинути пароль' })).toHaveAccessibleDescription(/Змінити пароль/)
    expect(within(drawer).getByRole('button', { name: 'Редагувати' })).toBeEnabled()
    await user.click(within(drawer).getByRole('button', { name: 'Редагувати' }))
    expect(await dialogTitled('Дані співробітника')).toBeInTheDocument()
  })

  it('blocks only after the confirmation that sessions end', async () => {
    const blocked = makeAdminUser({ is_active: false, user_actions: [userAllowed('unblock')] })
    const calls = backend({ [`PATCH /admin/users/${MANAGER_ROW.id}`]: () => [200, blocked] })
    const { user } = renderRoute(`/office/users?user=${MANAGER_ROW.id}`)
    const drawer = await screen.findByRole('dialog')
    await user.click(await within(drawer).findByRole('button', { name: 'Заблокувати' }))
    const confirm = await dialogTitled('Заблокувати Коваль Олена?')
    expect(within(confirm).getByText(/відкриті сесії буде завершено/)).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'PATCH')).toBe(false)
    await user.click(within(confirm).getByRole('button', { name: 'Заблокувати' }))
    await waitFor(() => expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({ is_active: false }))
  })

  it('changes the role with the chosen staff role', async () => {
    const calls = backend({ [`PATCH /admin/users/${MANAGER_ROW.id}`]: () => [200, makeAdminUser({ role: 'finance' })] })
    const { user } = renderRoute(`/office/users?user=${MANAGER_ROW.id}`)
    const drawer = await screen.findByRole('dialog')
    await user.click(await within(drawer).findByRole('button', { name: 'Змінити роль' }))
    const dialog = await dialogTitled('Зміна ролі')
    expect(within(dialog).getByText(/Права доступу зміняться одразу/)).toBeInTheDocument()
    await user.click(within(dialog).getByRole('combobox', { name: 'Роль' }))
    await user.click(await screen.findByTitle('Фінансовий контролер'))
    await user.click(within(dialog).getByRole('button', { name: 'Змінити роль' }))
    await waitFor(() => expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({ role: 'finance' }))
  })

  it('shows a refusal of the last admin rule from the server too', async () => {
    const last = makeAdminUser({ id: 811, role: 'admin', user_actions: [userRefused('block', 'Це останній активний адміністратор — його не можна заблокувати або змінити йому роль')] })
    backend({ 'GET /admin/users/811': () => [200, last] })
    renderRoute('/office/users?user=811')
    const block = await within(await screen.findByRole('dialog')).findByRole('button', { name: 'Заблокувати' })
    expect(block).toBeDisabled()
    expect(block).toHaveAccessibleDescription(/останній активний адміністратор/)
  })

  it('creates an employee and shows the temporary password once, with the note', async () => {
    const created = { ...makeAdminUser({ id: 812, last_name: 'Бойко', first_name: 'Марія' }), temporary_password: 'Tmp7kQ2xWm9Lp4Rz' }
    const calls = backend({ 'POST /admin/users': () => [201, created] })
    const { user } = renderRoute('/office/users')
    await user.click(await screen.findByRole('button', { name: /Додати співробітника/ }))
    const dialog = await dialogTitled('Новий співробітник')
    await user.click(within(dialog).getByRole('combobox', { name: 'Роль' }))
    await user.click(await screen.findByTitle('Менеджер'))
    await user.type(within(dialog).getByLabelText('Прізвище'), 'Бойко')
    await user.type(within(dialog).getByLabelText("Ім'я"), 'Марія')
    await user.type(within(dialog).getByLabelText('Номер телефону'), '+380 67 111 22 44')
    await user.type(within(dialog).getByLabelText('E-mail'), 'maria@tour.ua')
    await user.click(within(dialog).getByRole('button', { name: 'Створити' }))
    await waitFor(() => expect(calls.find((c) => c.method === 'POST')?.body).toEqual({
      role: 'manager', last_name: 'Бойко', first_name: 'Марія', phone: '+380671112244', email: 'maria@tour.ua',
    }))
    const shown = await dialogTitled('Співробітника створено')
    expect(within(shown).getByTestId('temporary-password')).toHaveTextContent('Tmp7kQ2xWm9Lp4Rz')
    expect(within(shown).getByText('Передайте співробітнику безпечним способом; він змінить пароль після входу.')).toBeInTheDocument()
    expect(within(shown).getByRole('button', { name: 'Копіювати пароль' })).toBeInTheDocument()
    await user.click(within(shown).getByRole('button', { name: 'Готово' }))
    await waitFor(() => expect(screen.queryByText('Tmp7kQ2xWm9Lp4Rz')).not.toBeInTheDocument())
  })

  it('puts a taken phone refusal into the dialog', async () => {
    backend({ 'POST /admin/users': () => [409, { detail: 'Користувач з таким телефоном уже зареєстрований' }] })
    const { user } = renderRoute('/office/users')
    await user.click(await screen.findByRole('button', { name: /Додати співробітника/ }))
    const dialog = await dialogTitled('Новий співробітник')
    await user.click(within(dialog).getByRole('combobox', { name: 'Роль' }))
    await user.click(await screen.findByTitle('Менеджер'))
    await user.type(within(dialog).getByLabelText('Прізвище'), 'Бойко')
    await user.type(within(dialog).getByLabelText("Ім'я"), 'Марія')
    await user.type(within(dialog).getByLabelText('Номер телефону'), '+380671112244')
    await user.type(within(dialog).getByLabelText('E-mail'), 'maria@tour.ua')
    await user.click(within(dialog).getByRole('button', { name: 'Створити' }))
    expect(await within(dialog).findByText('Користувач з таким телефоном уже зареєстрований')).toBeInTheDocument()
  })
})

describe('staff password change (office user menu)', () => {
  it('changes the password and sends the user to sign in again', async () => {
    const calls = backend({ 'POST /auth/me/password': () => [204, null] })
    const { user, router } = renderRoute('/office/users')
    await user.click(await screen.findByRole('button', { name: 'Меню користувача' }))
    await user.click(await screen.findByRole('menuitem', { name: /Змінити пароль/ }))
    const dialog = await dialogTitled('Зміна пароля')
    await user.type(within(dialog).getByLabelText('Поточний пароль'), 'Old-pass-1')
    await user.type(within(dialog).getByLabelText('Новий пароль'), 'New-pass-22')
    await user.type(within(dialog).getByLabelText('Повторіть пароль'), 'New-pass-22')
    await user.click(within(dialog).getByRole('button', { name: 'Змінити пароль' }))
    await waitFor(() => expect(calls.find((c) => c.url === '/auth/me/password')?.body)
      .toEqual({ current_password: 'Old-pass-1', new_password: 'New-pass-22' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'))
  })
})
