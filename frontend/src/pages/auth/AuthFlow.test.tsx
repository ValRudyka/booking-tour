import { act, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { TOKEN_KEY } from '../../features/auth/tokenStorage'
import { makeUser, mockServer, page } from '../../test/fixtures'
import { renderRoute } from '../../test/render'
import { setViewportWidth } from '../../test/setup'

const client = makeUser({ role: 'client', first_name: 'Олена', last_name: 'Коваленко' })
const manager = makeUser({ id: 7, role: 'manager', first_name: 'Іван', last_name: 'Петренко' })

function storeToken() {
  window.localStorage.setItem(TOKEN_KEY, 'stored-token')
}

describe('auth state', () => {
  afterEach(() => setViewportWidth(1440))

  it('restores the signed-in user after a reload by asking GET /auth/me', async () => {
    storeToken()
    const calls = mockServer({ 'GET /auth/me': () => [200, client] })
    renderRoute('/tours')
    expect(await screen.findByRole('button', { name: 'Меню користувача: Олена К.' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Увійти' })).not.toBeInTheDocument()
    expect(calls.find((c) => c.url === '/auth/me')?.authorization).toBe('Bearer stored-token')
  })

  it('a stored token the backend refuses just means "guest" on a public page', async () => {
    storeToken()
    mockServer({ 'GET /auth/me': () => [401, { detail: 'Не вдалося підтвердити облікові дані' }] })
    const { router } = renderRoute('/tours')
    expect(await screen.findByRole('button', { name: 'Увійти' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/tours')
    await waitFor(() => expect(window.localStorage.getItem(TOKEN_KEY)).toBeNull())
  })

  it('logout clears the token and the header shows the guest buttons again', async () => {
    storeToken()
    mockServer({ 'GET /auth/me': () => [200, client] })
    const { user, router } = renderRoute('/tours')
    await user.click(await screen.findByRole('button', { name: 'Меню користувача: Олена К.' }))
    await user.click(await screen.findByText('Вийти'))
    expect(await screen.findByRole('button', { name: 'Увійти' })).toBeInTheDocument()
    expect(window.localStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(router.state.location.pathname).toBe('/tours')
  })

  it('logging out on a protected page goes to the catalog, not to /login', async () => {
    storeToken()
    mockServer({ 'GET /auth/me': () => [200, client] })
    const { user, router } = renderRoute('/cabinet/orders')
    await user.click(await screen.findByRole('button', { name: 'Меню користувача: Олена К.' }))
    await user.click(await screen.findByText('Вийти'))
    await waitFor(() => expect(router.state.location.pathname).toBe('/tours'))
    expect(window.localStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(await screen.findByRole('button', { name: 'Увійти' })).toBeInTheDocument()
  })

  it('shows «Робочий кабінет» to staff and the account pages to clients', async () => {
    storeToken()
    mockServer({ 'GET /auth/me': () => [200, manager] })
    const { user } = renderRoute('/tours')
    await user.click(await screen.findByRole('button', { name: 'Меню користувача: Іван П.' }))
    expect(await screen.findByText('Робочий кабінет')).toBeInTheDocument()
    expect(screen.queryByText('Мої замовлення')).not.toBeInTheDocument()
  })

  it('a 401 while signed in ends the session: /login with the message and a way back', async () => {
    storeToken()
    let expired = false
    mockServer({
      'GET /auth/me': () => [200, client],
      'GET /tours': () => expired ? [401, { detail: 'Не вдалося підтвердити облікові дані' }] : [200, page([])],
    })
    const { router } = renderRoute('/tours?country_id=1')
    await screen.findByRole('button', { name: 'Меню користувача: Олена К.' })
    expired = true
    await act(() => router.navigate('/tours?country_id=2'))
    expect(await screen.findByText('Сеанс завершився. Увійдіть знову.')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/login')
    expect(new URLSearchParams(router.state.location.search).get('redirect')).toBe('/tours?country_id=2')
    expect(window.localStorage.getItem(TOKEN_KEY)).toBeNull()
  })

  it('signing out in another tab signs out here too', async () => {
    storeToken()
    mockServer({ 'GET /auth/me': () => [200, client] })
    renderRoute('/tours')
    await screen.findByRole('button', { name: 'Меню користувача: Олена К.' })
    window.localStorage.removeItem(TOKEN_KEY)
    act(() => { window.dispatchEvent(new StorageEvent('storage', { key: TOKEN_KEY, newValue: null })) })
    expect(await screen.findByRole('button', { name: 'Увійти' })).toBeInTheDocument()
  })
})

describe('RequireAuth', () => {
  it('sends a guest to /login with the page as redirect', async () => {
    mockServer({})
    const { router } = renderRoute('/cabinet/orders')
    await screen.findByRole('heading', { level: 1, name: 'Вхід' })
    expect(router.state.location.search).toBe('?redirect=%2Fcabinet%2Forders')
  })

  it('shows 403 for a signed-in user with another role', async () => {
    storeToken()
    mockServer({ 'GET /auth/me': () => [200, manager] })
    renderRoute('/cabinet/orders')
    expect(await screen.findByRole('heading', { level: 1, name: 'Немає доступу до цієї сторінки' })).toBeInTheDocument()
  })

  it('a manager cannot open the booking page (orders are a client\'s)', async () => {
    storeToken()
    mockServer({ 'GET /auth/me': () => [200, manager] })
    renderRoute('/booking/83?date=2099-06-01')
    expect(await screen.findByRole('heading', { level: 1, name: 'Немає доступу до цієї сторінки' })).toBeInTheDocument()
  })
})

/** The form's «Увійти» (the header has a button with the same name). */
function submitButton() {
  return within(document.querySelector('.auth-card') as HTMLElement).getByRole('button', { name: 'Увійти' })
}

describe('LoginPage', () => {
  function serveLogin(result: () => [number, unknown]) {
    return mockServer({ 'POST /auth/login': result, 'GET /auth/me': () => [200, client] })
  }

  async function fillAndSubmit(user: ReturnType<typeof renderRoute>['user'], login = '+380501234567', password = 'Strong-pass-1') {
    await user.type(screen.getByLabelText('Номер телефону або e-mail'), login)
    await user.type(screen.getByLabelText('Пароль'), password)
    await user.click(submitButton())
  }

  it('signs in and goes back to the redirect (a booking)', async () => {
    const calls = serveLogin(() => [200, { access_token: 'new-token', token_type: 'bearer', user: client }])
    const { user, router } = renderRoute('/login?redirect=%2Fbooking%2F83%3Fdate%3D2099-06-01')
    await screen.findByRole('heading', { level: 1, name: 'Вхід' })
    await fillAndSubmit(user)
    await waitFor(() => expect(router.state.location.pathname).toBe('/booking/83'))
    expect(router.state.location.search).toBe('?date=2099-06-01')
    expect(window.localStorage.getItem(TOKEN_KEY)).toBe('new-token')
    const form = calls.find((c) => c.url === '/auth/login')!.body as URLSearchParams
    expect([form.get('username'), form.get('password')]).toEqual(['+380501234567', 'Strong-pass-1'])
  })

  it('ignores an external redirect and goes to the default page', async () => {
    serveLogin(() => [200, { access_token: 't', token_type: 'bearer', user: client }])
    const { user, router } = renderRoute('/login?redirect=https%3A%2F%2Fevil.example')
    await screen.findByRole('heading', { level: 1, name: 'Вхід' })
    await fillAndSubmit(user)
    await waitFor(() => expect(router.state.location.pathname).toBe('/cabinet/orders'))
  })

  it('sends staff to the office', async () => {
    serveLogin(() => [200, { access_token: 't', token_type: 'bearer', user: manager }])
    const { user, router } = renderRoute('/login')
    await screen.findByRole('heading', { level: 1, name: 'Вхід' })
    await fillAndSubmit(user, 'manager@tour.local')
    await waitFor(() => expect(router.state.location.pathname).toBe('/office'))
  })

  it('shows one general message for wrong data, in an alert', async () => {
    serveLogin(() => [401, { detail: 'Невірний логін або пароль' }])
    const { user, router } = renderRoute('/login')
    await screen.findByRole('heading', { level: 1, name: 'Вхід' })
    await fillAndSubmit(user)
    expect(await screen.findByRole('alert')).toHaveTextContent('Неправильний номер телефону, e-mail або пароль')
    expect(router.state.location.pathname).toBe('/login')
  })

  it.each([
    [429, { detail: 'Too Many Requests' }, 'Забагато спроб входу. Спробуйте пізніше.'],
    [503, { detail: 'Тривають технічні роботи. Спробуйте пізніше.' }, 'Тривають технічні роботи. Спробуйте пізніше.'],
    [500, { detail: 'Traceback…' }, 'На сервері сталася помилка'],
  ])('shows a clear text for %s', async (status, body, text) => {
    serveLogin(() => [status, body])
    const { user } = renderRoute('/login')
    await screen.findByRole('heading', { level: 1, name: 'Вхід' })
    await fillAndSubmit(user)
    expect(await screen.findByRole('alert')).toHaveTextContent(text)
  })

  it('a signed-in user who opens /login is sent on at once', async () => {
    storeToken()
    mockServer({ 'GET /auth/me': () => [200, client] })
    const { router } = renderRoute('/login?redirect=%2Ftours%2F5')
    await waitFor(() => expect(router.state.location.pathname).toBe('/tours/5'))
  })

  it('checks fields on leaving them, sends nothing with errors and focuses the first error', async () => {
    const calls = serveLogin(() => [200, {}])
    const { user } = renderRoute('/login')
    const login = await screen.findByLabelText('Номер телефону або e-mail')
    await user.click(login)
    await user.tab()
    expect(await screen.findByText('Вкажіть номер телефону або e-mail')).toBeInTheDocument()
    expect(login).toHaveAttribute('aria-invalid', 'true')
    expect(login.getAttribute('aria-describedby')).toContain('username_help')

    await user.click(submitButton())
    await waitFor(() => expect(login).toHaveFocus())
    expect(calls.some((c) => c.url === '/auth/login')).toBe(false)

    // After the first submit the error disappears while typing the fix.
    await user.type(login, '+380501234567')
    await waitFor(() => expect(screen.queryByText('Вкажіть номер телефону або e-mail')).not.toBeInTheDocument())
  })

  it('«Забули пароль?» shows the support contacts from the site settings', async () => {
    mockServer({ 'GET /site/contacts': () => [200, { phone: '+380441234567', email: 'help@tour.local' }] })
    const { user } = renderRoute('/login')
    await user.click(await screen.findByRole('button', { name: 'Забули пароль?' }))
    const panel = document.getElementById('forgot-panel') as HTMLElement
    expect(panel).toHaveTextContent('адміністратор скине пароль')
    expect(within(panel).getByRole('link', { name: '+380441234567' })).toHaveAttribute('href', 'tel:+380441234567')
    expect(within(panel).getByRole('link', { name: 'help@tour.local' })).toHaveAttribute('href', 'mailto:help@tour.local')
  })
})

describe('HelpGuide', () => {
  it('opens on click with the login guide, closes on Esc and gives the focus back', async () => {
    mockServer({})
    const { user, router } = renderRoute('/login')
    const button = await screen.findByRole('button', { name: 'Як це працює?' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()     // never opens by itself
    await user.click(button)
    const dialog = await screen.findByRole('dialog', { name: 'Як увійти' })
    expect(within(dialog).getByText(/телефону або e-mail/)).toBeInTheDocument()
    expect(within(dialog).getByText(/служби підтримки/)).toBeInTheDocument()
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await waitFor(() => expect(button).toHaveFocus())

    await user.click(button)
    await user.click(within(await screen.findByRole('dialog')).getByRole('link', { name: 'Перейти до реєстрації' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/register'))
  })

  it('the registration page has its own guide with a link to the login', async () => {
    mockServer({})
    const { user } = renderRoute('/register')
    await user.click(await screen.findByRole('button', { name: 'Як це працює?' }))
    const dialog = await screen.findByRole('dialog', { name: 'Як зареєструватися' })
    expect(within(dialog).getByText(/від 8 до 128 символів/)).toBeInTheDocument()
    expect(within(dialog).getByText(/громадяни інших держав — латинськими/)).toBeInTheDocument()
    expect(within(dialog).getByRole('link', { name: 'Перейти до входу' })).toBeInTheDocument()
  })
})
