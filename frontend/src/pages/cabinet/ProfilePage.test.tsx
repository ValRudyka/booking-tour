import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { TOKEN_KEY } from '../../features/auth/tokenStorage'
import { makeUser, mockServer, signIn, type FakeRequest } from '../../test/fixtures'
import { renderRoute } from '../../test/render'

const USER = makeUser()      // Олена Коваленко, a citizen of Ukraine (country 3)

type Routes = Record<string, (request: FakeRequest) => [number, unknown]>
function backend(routes: Routes = {}) {
  signIn(USER)
  return mockServer({ 'GET /auth/me': () => [200, USER], 'GET /orders': () => [200, { items: [], total: 0, page: 1, page_size: 10 }], ...routes })
}

const personal = () => screen.getByRole('heading', { name: 'Особисті дані' }).closest('.ant-card') as HTMLElement
const passwordCard = () => screen.getByRole('heading', { name: 'Зміна пароля' }).closest('.ant-card') as HTMLElement

async function startEditing(user: ReturnType<typeof renderRoute>['user']) {
  await user.click(await screen.findByRole('button', { name: 'Редагувати' }))
  return within(personal())
}

describe('/cabinet/profile: personal data', () => {
  it('shows the data, the phone only for reading, and switches to the form', async () => {
    backend()
    const { user } = renderRoute('/cabinet/profile')
    expect(await screen.findByRole('heading', { level: 1, name: 'Профіль' })).toBeInTheDocument()
    const card = within(personal())
    expect(card.getByText('+380501234567')).toBeInTheDocument()
    expect(card.getByText('14.05.1990')).toBeInTheDocument()
    expect(await card.findByText('Україна')).toBeInTheDocument()

    const form = await startEditing(user)
    expect(form.getByLabelText('Номер телефону')).toHaveAttribute('readonly')
    expect(form.getByLabelText('Прізвище')).toHaveValue('Коваленко')
    await user.click(form.getByRole('button', { name: 'Скасувати' }))
    expect(within(personal()).queryByRole('button', { name: 'Зберегти' })).not.toBeInTheDocument()
  })

  it('saves only the profile fields, says so and updates the header name at once', async () => {
    const calls = backend({
      'PATCH /auth/me': (request) => [200, { ...USER, ...(request.body as object) }],
    })
    const { user } = renderRoute('/cabinet/profile')
    const form = await startEditing(user)
    await user.clear(form.getByLabelText('Ім\'я'))
    await user.type(form.getByLabelText('Ім\'я'), 'Ганна')
    await user.click(form.getByRole('button', { name: 'Зберегти' }))

    expect(await screen.findByText('Дані збережено')).toBeInTheDocument()
    const patch = calls.find((c) => c.method === 'PATCH')!
    expect(patch.body).toEqual({ email: 'olena@example.com', last_name: 'Коваленко', first_name: 'Ганна',
      birth_date: '1990-05-14', citizenship_id: 3 })
    expect(screen.getByRole('button', { name: 'Меню користувача: Ганна К.' })).toBeInTheDocument()
    expect(within(personal()).getByText('Ганна')).toBeInTheDocument()
  })

  it('checks the alphabet against the citizenship before sending', async () => {
    const calls = backend()
    const { user } = renderRoute('/cabinet/profile')
    const form = await startEditing(user)
    await user.clear(form.getByLabelText('Прізвище'))
    await user.type(form.getByLabelText('Прізвище'), 'Kovalenko')
    await user.click(form.getByRole('button', { name: 'Зберегти' }))
    expect(await form.findByText(/Для громадян України/)).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'PATCH')).toBe(false)
  })

  it('puts a server error under its field (422/409 with loc)', async () => {
    backend({
      'PATCH /auth/me': () => [409, { detail: [{ loc: ['body', 'email'], msg: 'Користувач з таким e-mail вже існує',
        type: 'profile_rule' }] }],
    })
    const { user } = renderRoute('/cabinet/profile')
    const form = await startEditing(user)
    await user.clear(form.getByLabelText('E-mail'))
    await user.type(form.getByLabelText('E-mail'), 'taken@example.com')
    await user.click(form.getByRole('button', { name: 'Зберегти' }))
    const field = (await form.findByText('Користувач з таким e-mail вже існує')).closest('.ant-form-item')!
    expect(within(field as HTMLElement).getByLabelText('E-mail')).toBeInTheDocument()
    expect(form.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('asks before leaving with unsaved changes', async () => {
    backend()
    const { user, router } = renderRoute('/cabinet/profile')
    const form = await startEditing(user)
    await user.type(form.getByLabelText('Ім\'я'), 'а')
    await user.click(screen.getByRole('menuitem', { name: /Мої замовлення/ }))

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getAllByText('Зміни не збережено. Вийти без збереження?').length).toBeGreaterThan(0)
    await user.click(within(dialog).getByRole('button', { name: 'Залишитися' }))
    expect(router.state.location.pathname).toBe('/cabinet/profile')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    await user.click(screen.getByRole('menuitem', { name: /Мої замовлення/ }))
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Вийти' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/cabinet/orders'))
  })

  it('leaves without asking when nothing changed', async () => {
    backend()
    const { user, router } = renderRoute('/cabinet/profile')
    await startEditing(user)
    await user.click(screen.getByRole('menuitem', { name: /Мої замовлення/ }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/cabinet/orders'))
  })
})

describe('/cabinet/profile: password', () => {
  it('refuses a repeat that does not match, nothing is sent', async () => {
    const calls = backend()
    const { user } = renderRoute('/cabinet/profile')
    await screen.findByRole('heading', { name: 'Зміна пароля' })
    const card = within(passwordCard())
    await user.type(card.getByLabelText('Поточний пароль'), 'Old-pass-123')
    await user.type(card.getByLabelText('Новий пароль'), 'New-pass-456')
    await user.type(card.getByLabelText('Повторіть пароль'), 'New-pass-457')
    await user.click(card.getByRole('button', { name: 'Змінити пароль' }))
    expect(await card.findByText('Паролі не збігаються')).toBeInTheDocument()
    expect(calls.some((c) => c.url === '/auth/me/password')).toBe(false)
  })

  it('a wrong current password goes under its field', async () => {
    backend({
      'POST /auth/me/password': () => [422, { detail: [{ loc: ['body', 'current_password'],
        msg: 'Поточний пароль невірний', type: 'profile_rule' }] }],
    })
    const { user } = renderRoute('/cabinet/profile')
    await screen.findByRole('heading', { name: 'Зміна пароля' })
    const card = within(passwordCard())
    await user.type(card.getByLabelText('Поточний пароль'), 'Wrong-pass-1')
    await user.type(card.getByLabelText('Новий пароль'), 'New-pass-456')
    await user.type(card.getByLabelText('Повторіть пароль'), 'New-pass-456')
    await user.click(card.getByRole('button', { name: 'Змінити пароль' }))
    expect(await card.findByText('Поточний пароль невірний')).toBeInTheDocument()
  })

  it('after the change every session has ended: sign-in page with a message, not a 401', async () => {
    const calls = backend({ 'POST /auth/me/password': () => [204, null] })
    const { user, router } = renderRoute('/cabinet/profile')
    await screen.findByRole('heading', { name: 'Зміна пароля' })
    const card = within(passwordCard())
    await user.type(card.getByLabelText('Поточний пароль'), 'Old-pass-123')
    await user.type(card.getByLabelText('Новий пароль'), 'New-pass-456')
    await user.type(card.getByLabelText('Повторіть пароль'), 'New-pass-456')
    await user.click(card.getByRole('button', { name: 'Змінити пароль' }))

    expect(await screen.findByText('Пароль змінено. Увійдіть з новим паролем.')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/login')
    expect(screen.queryByText('Сеанс завершився. Увійдіть знову.')).not.toBeInTheDocument()
    expect(window.localStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(calls.find((c) => c.url === '/auth/me/password')?.body).toEqual(
      { current_password: 'Old-pass-123', new_password: 'New-pass-456' })
  })
})
