import { screen, waitFor, within } from '@testing-library/react'
import dayjs from 'dayjs'
import { describe, expect, it } from 'vitest'
import { TOKEN_KEY } from '../../features/auth/tokenStorage'
import { makeUser, mockServer, type FakeRequest } from '../../test/fixtures'
import { renderRoute } from '../../test/render'
import { kyivToday } from '../../utils/format'

type User = ReturnType<typeof renderRoute>['user']
const client = makeUser()
const DATE = 'DD.MM.YYYY'

function card() {
  return within(document.querySelector('.auth-card') as HTMLElement)
}

async function fill(user: User, values: Partial<Record<'phone' | 'email' | 'password' | 'repeat' | 'last' | 'first' | 'birth', string>> = {}) {
  const v = {
    phone: '+380 50 123 45 67', email: 'olena@example.com', password: 'Strong-pass-1', repeat: 'Strong-pass-1',
    last: 'Коваленко', first: 'Олена', birth: dayjs(kyivToday()).subtract(30, 'year').format(DATE), ...values,
  }
  await screen.findByText('Україна')                 // citizenship preselected once countries load
  if (v.phone) await user.type(screen.getByLabelText('Номер телефону'), v.phone)
  if (v.email) await user.type(screen.getByLabelText('E-mail'), v.email)
  if (v.password) await user.type(screen.getByLabelText('Пароль'), v.password)
  if (v.repeat) await user.type(screen.getByLabelText('Повторіть пароль'), v.repeat)
  if (v.last) await user.type(screen.getByLabelText('Прізвище'), v.last)
  if (v.first) await user.type(screen.getByLabelText("Ім'я"), v.first)
  if (v.birth) await user.type(screen.getByLabelText('Дата народження'), `${v.birth}{Enter}`)
  await user.click(screen.getByRole('checkbox', { name: /даю згоду на обробку персональних даних/ }))
}

const submit = (user: User) => user.click(card().getByRole('button', { name: 'Зареєструватися' }))

function serve(register: (r: FakeRequest) => [number, unknown]) {
  return mockServer({
    'POST /auth/register': register,
    'POST /auth/login': () => [200, { access_token: 'fresh', token_type: 'bearer', user: client }],
    'GET /auth/me': () => [200, client],
  })
}

describe('RegisterPage', () => {
  it('registers, signs in at once and goes back to the redirect', async () => {
    const calls = serve(() => [201, client])
    const { user, router } = renderRoute('/register?redirect=%2Fbooking%2F83%3Fdate%3D2099-06-01')
    const eighteenToday = dayjs(kyivToday()).subtract(18, 'year')
    await fill(user, { birth: eighteenToday.format(DATE) })
    await submit(user)

    await waitFor(() => expect(router.state.location.pathname).toBe('/booking/83'))
    const body = calls.find((c) => c.url === '/auth/register')!.body
    expect(body).toEqual({
      phone: '+380501234567', email: 'olena@example.com', password: 'Strong-pass-1',
      last_name: 'Коваленко', first_name: 'Олена', birth_date: eighteenToday.format('YYYY-MM-DD'),
      citizenship_id: 3, consent: true,
    })
    const login = calls.find((c) => c.url === '/auth/login')!.body as URLSearchParams
    expect(login.get('username')).toBe('+380501234567')
    expect(window.localStorage.getItem(TOKEN_KEY)).toBe('fresh')
  })

  it('refuses a visitor who turns 18 tomorrow (Kyiv date)', async () => {
    const calls = serve(() => [201, client])
    const { user } = renderRoute('/register')
    await fill(user, { birth: dayjs(kyivToday()).subtract(18, 'year').add(1, 'day').format(DATE) })
    await submit(user)
    expect(await screen.findByText('Реєстрація доступна лише з 18 років')).toBeInTheDocument()
    expect(calls.some((c) => c.url === '/auth/register')).toBe(false)
  })

  it('checks that the passwords match and ticks the password requirements', async () => {
    serve(() => [201, client])
    const { user } = renderRoute('/register')
    await screen.findByText('Україна')
    const rules = screen.getByRole('list', { name: 'Вимоги до пароля' })
    expect(within(rules).getByText(/Щонайменше 8 символів/)).toHaveTextContent('(не виконано)')
    await user.type(screen.getByLabelText('Пароль'), 'Strong-pass-1')
    expect(within(rules).getByText(/Щонайменше 8 символів/)).toHaveTextContent('(виконано)')
    expect(within(rules).getByText(/Не більше 128 символів/)).toHaveTextContent('(виконано)')
    await user.type(screen.getByLabelText('Повторіть пароль'), 'Strong-pass-2')
    await user.tab()
    expect(await screen.findByText('Паролі не збігаються')).toBeInTheDocument()
  })

  it('asks for Ukrainian letters from citizens of Ukraine and Latin from others', async () => {
    serve(() => [201, client])
    const { user } = renderRoute('/register')
    await screen.findByText('Україна')
    const last = screen.getByLabelText('Прізвище')
    await user.type(last, 'Kovalenko')
    await user.tab()
    expect(await screen.findByText('Для громадян України — українськими літерами (апостроф і дефіс дозволені)'))
      .toBeInTheDocument()

    await user.click(screen.getByLabelText('Громадянство'))
    await user.click(await screen.findByTitle('Туреччина'))
    await waitFor(() => expect(screen.queryByText(/Для громадян України/)).not.toBeInTheDocument())
  })

  it('shows server errors under their fields: a 422 phone and a taken e-mail', async () => {
    let attempt = 0
    serve(() => {
      attempt += 1
      return attempt === 1
        ? [422, { detail: [{ loc: ['body', 'phone'], type: 'value_error', msg: 'Value error, Телефон у міжнародному форматі, наприклад +380501234567' }] }]
        : [409, { detail: 'Користувач з таким e-mail вже існує' }]
    })
    const { user } = renderRoute('/register')
    await fill(user)
    await submit(user)
    const phone = screen.getByLabelText('Номер телефону')
    expect(await screen.findByText('Телефон у міжнародному форматі, наприклад +380501234567')).toBeInTheDocument()
    await waitFor(() => expect(phone).toHaveFocus())

    await submit(user)
    expect(await screen.findByText('Цей e-mail вже зареєстрований. Увійдіть або вкажіть інший e-mail.')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('turns an unknown backend text into the general message', async () => {
    serve(() => [400, { detail: 'IntegrityError: duplicate key value violates unique constraint' }])
    const { user } = renderRoute('/register')
    await fill(user)
    await submit(user)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Щось пішло не так. Спробуйте ще раз.')
    expect(alert).not.toHaveTextContent('IntegrityError')
  })

  it('sends nothing with errors and focuses the first field with an error', async () => {
    const calls = serve(() => [201, client])
    const { user } = renderRoute('/register')
    await screen.findByText('Україна')
    await submit(user)
    const phone = screen.getByLabelText('Номер телефону')
    await waitFor(() => expect(phone).toHaveFocus())
    expect(screen.getByText('Вкажіть номер телефону')).toBeInTheDocument()
    expect(screen.getByText('Потрібна згода на обробку персональних даних')).toBeInTheDocument()
    expect(calls.some((c) => c.url === '/auth/register')).toBe(false)

    await user.type(phone, '0501')
    expect(await screen.findByText('Номер має бути в міжнародному форматі, наприклад +380501234567')).toBeInTheDocument()
  })
})
