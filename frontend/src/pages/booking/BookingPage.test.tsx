import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { OrderWithPrice, ServiceOption } from '../../api/types'
import { draftKey, saveDraft, type BookingDraft } from '../../features/booking/bookingDraft'
import {
  makeCheckoutOrder, makePrice, makeTourDetail, makeUser, mockServer, signIn, TOURISTS, type FakeRequest,
} from '../../test/fixtures'
import { renderRoute } from '../../test/render'

// Intl uses a narrow no-break space as the uk-UA thousands separator.
const plain = (text: string | null) => (text ?? '').replace(/[\u00a0\u202f]/g, ' ')

const USER = makeUser()
const TOUR = makeTourDetail({ id: 7, departure_from: '2099-06-01', departure_to: '2099-06-30', nights: 7, free_seats: 10 })
const URL = '/booking/7?date=2099-06-10'
const INSURANCE: ServiceOption[] = [
  { id: 1, name_uk: 'Базове', price_uah: '350.00', is_default: true },
  { id: 2, name_uk: 'Розширене', price_uah: '700.00', is_default: false },
]
const makeOrder = (overrides: Partial<OrderWithPrice> = {}) =>
  makeCheckoutOrder({ tour_title_uk: TOUR.title_uk, hotel_name: TOUR.hotel.name, ...overrides })
const TRANSFER: ServiceOption[] = [{ id: 5, name_uk: 'Груповий', price_uah: '0.00', is_default: true }]

/** The backend for the wizard: the tour, references, no saved passports, no unfinished orders. */
function backend(routes: Record<string, (request: FakeRequest) => [number, unknown]> = {}) {
  signIn(USER)
  return mockServer({
    'GET /auth/me': () => [200, USER],
    'GET /tours/7': () => [200, TOUR],
    'GET /orders': () => [200, { items: [], total: 0, page: 1, page_size: 50 }],
    'GET /reference/insurance-types': () => [200, INSURANCE],
    'GET /reference/transfer-types': () => [200, TRANSFER],
    'GET /me/passports': () => [200, []],
    'POST /orders/quote': () => [200, makePrice({ total_uah: '12345.67' })],
    ...routes,
  })
}

/** A booking in progress: the draft points at order 1 and the server still holds it. */
function inProgress(step: number, order: OrderWithPrice, extra: Partial<BookingDraft> = {}) {
  saveDraft(USER.id, 7, {
    step, date: order.start_date, adults: order.adults, children: order.children, orderId: order.id,
    tourists: [], insurance_type_id: order.insurance_type_id, transfer_type_id: order.transfer_type_id,
    promo: '', wishes: '', ...extra,
  })
}

const count = (calls: FakeRequest[], method: string, url: string) =>
  calls.filter((c) => c.method === method && c.url === url).length

const card = (title: string) => screen.getByRole('heading', { name: title }).closest('.booking-tourist') as HTMLElement

describe('booking wizard /booking/:tourId', () => {
  it('sends a guest to the login page and back to this booking', async () => {
    mockServer({})
    const { router } = renderRoute(URL)
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'))
    expect(new URLSearchParams(router.state.location.search).get('redirect')).toBe(URL)
  })

  it('shows 403 to staff', async () => {
    const manager = makeUser({ role: 'manager' })
    signIn(manager)
    mockServer({ 'GET /auth/me': () => [200, manager] })
    renderRoute(URL)
    expect(await screen.findByRole('heading', { level: 1, name: 'Немає доступу до цієї сторінки' })).toBeInTheDocument()
  })

  it('takes the date from the tour page and the total from the server', async () => {
    const calls = backend()
    renderRoute(URL)
    expect(await screen.findByRole('heading', { level: 1, name: 'Оформлення бронювання' })).toBeInTheDocument()
    expect(screen.getByLabelText('Дата заїзду')).toHaveValue('10.06.2099')
    // "12345.67" cannot come from any arithmetic on the tour's prices: it is the quote's answer.
    await waitFor(() => expect(plain(screen.getByTestId('booking-total').textContent)).toBe('12 345,67 ₴'))
    expect(calls.find((c) => c.url === '/orders/quote')?.body).toEqual(
      { tour_id: 7, start_date: '2099-06-10', adults: 1, children: 0 })
  })

  it('creates one order on a double click and starts the hold', async () => {
    const calls = backend({ 'POST /orders': () => [201, makeOrder({ adults: 1, tourists: [] })] })
    const { user } = renderRoute(URL)
    const next = await screen.findByRole('button', { name: 'Далі' })
    await user.dblClick(next)
    expect(await screen.findByRole('heading', { name: 'Дорослий 1' })).toBeInTheDocument()
    expect(count(calls, 'POST', '/orders')).toBe(1)
    expect(screen.getByRole('timer')).toHaveTextContent(/Місця утримуються до \d\d:\d\d \(залишилось 15 хв\)/)
  })

  it('shows the 409 about seats from the server on step 1', async () => {
    backend({ 'POST /orders': () => [409, { detail: 'Недостатньо вільних місць: залишилось 1' }] })
    const { user } = renderRoute(URL)
    await user.click(await screen.findByRole('button', { name: 'Далі' }))
    expect(await screen.findByText('Недостатньо вільних місць: залишилось 1')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Дорослий 1' })).not.toBeInTheDocument()
  })

  it('does not pass step 2 with empty fields', async () => {
    const calls = backend({ 'GET /orders/1': () => [200, makeOrder()] })
    inProgress(1, makeOrder())
    const { user } = renderRoute(URL)
    await user.click(await screen.findByRole('button', { name: 'Далі' }))
    expect((await screen.findAllByText('Заповніть це поле')).length).toBeGreaterThan(0)
    expect(count(calls, 'PATCH', '/orders/1')).toBe(0)
  })

  it('checks the passport against the return date like the backend', async () => {
    backend({ 'GET /orders/1': () => [200, makeOrder({ tourists: [{ ...TOURISTS[0], passport_expiry: '2099-12-01' }, TOURISTS[1]] })] })
    inProgress(1, makeOrder())
    const { user } = renderRoute(URL)
    await user.click(await screen.findByRole('button', { name: 'Далі' }))
    // Return 17.06.2099 + 6 months = 17.12.2099 (form 4.6.1.2, field 3.5).
    expect(await within(card('Дорослий 1')).findByText(
      'Паспорт має діяти щонайменше 6 місяців після повернення — до 17.12.2099')).toBeInTheDocument()
  })

  it('puts a 422 about tourist 2 under that tourist\'s field', async () => {
    const message = 'Паспорт туриста KOVALENKO IVAN має діяти щонайменше 6 місяців після повернення — до 17.12.2099'
    backend({
      'GET /orders/1': () => [200, makeOrder({ tourists: TOURISTS })],
      'PATCH /orders/1': () => [422, { detail: [{ loc: ['body', 'tourists', 1, 'passport_expiry'], msg: message, type: 'checkout_rule' }] }],
    })
    inProgress(1, makeOrder())
    const { user } = renderRoute(URL)
    await user.click(await screen.findByRole('button', { name: 'Далі' }))
    expect(await within(card('Дорослий 2')).findByText(message)).toBeInTheDocument()
    expect(within(card('Дорослий 1')).queryByText(message)).not.toBeInTheDocument()
  })

  it('keeps the data when going back and forth', async () => {
    const withTourists = makeOrder({ tourists: TOURISTS })
    const calls = backend({ 'GET /orders/1': () => [200, withTourists], 'PATCH /orders/1': () => [200, withTourists] })
    inProgress(1, withTourists)
    const { user } = renderRoute(URL)
    const lastName = await within(await waitFor(() => card('Дорослий 2'))).findByLabelText('Прізвище латиницею')
    await user.clear(lastName)
    await user.type(lastName, 'Shevchenko')
    await user.click(screen.getByRole('button', { name: 'Далі' }))
    expect(await screen.findByText('Медичне страхування')).toBeVisible()
    expect(calls.find((c) => c.method === 'PATCH')?.body).toMatchObject({
      tourists: [{ last_name_lat: 'KOVALENKO' }, { last_name_lat: 'Shevchenko', passport_number: 'FX654321' }],
    })
    await user.click(screen.getByRole('button', { name: 'Назад' }))
    await user.click(screen.getByRole('button', { name: 'Назад' }))
    expect(screen.getByLabelText('Дорослі (від 12 років)')).toHaveValue('2')
    await user.click(screen.getByRole('button', { name: 'Далі' }))   // same numbers: no request
    expect(within(card('Дорослий 2')).getByLabelText('Прізвище латиницею')).toHaveValue('Shevchenko')
    expect(count(calls, 'POST', '/orders')).toBe(0)
  })

  it('never writes passport numbers to sessionStorage', async () => {
    const withTourists = makeOrder({ tourists: TOURISTS })
    backend({ 'GET /orders/1': () => [200, withTourists] })
    inProgress(1, withTourists)
    const { user } = renderRoute(URL)
    const number = await within(await waitFor(() => card('Дорослий 1'))).findByLabelText('Серія та номер закордонного паспорта')
    await user.clear(number)
    await user.type(number, 'ab 777888')
    expect(number).toHaveValue('AB777888')
    const stored = window.sessionStorage.getItem(draftKey(USER.id, 7)) ?? ''
    expect(stored).toContain('KOVALENKO')
    expect(stored).not.toMatch(/AB777888|FX123456|passport_number/)
  })

  it('applies a promo code and shows the server\'s reason for a refused one', async () => {
    const withTourists = makeOrder({ tourists: TOURISTS })
    const withPromo = makeOrder({
      tourists: TOURISTS, promo_code: 'SUMMER10',
      price: makePrice({ promo_code: 'SUMMER10', discount_uah: '6387.28', total_uah: '57485.48' }),
    })
    backend({
      'GET /orders/1': () => [200, withTourists],
      'PATCH /orders/1': (request) => ((request.body as { promo_code?: string }).promo_code === 'SUMMER10'
        ? [200, withPromo] : [422, { detail: 'Промокод не знайдено' }]),
    })
    inProgress(2, withTourists)
    const { user } = renderRoute(URL)
    const promo = await screen.findByLabelText('Промокод')
    await user.type(promo, 'NOPE')
    await user.click(screen.getByRole('button', { name: 'Застосувати' }))
    expect(await screen.findByText('Промокод не знайдено')).toBeInTheDocument()
    await user.clear(promo)
    await user.type(promo, 'SUMMER10')
    await user.click(screen.getByRole('button', { name: 'Застосувати' }))
    expect(plain((await screen.findByText(/Промокод SUMMER10 застосовано/)).textContent))
      .toBe('Промокод SUMMER10 застосовано: знижка 6 387,28 ₴')
    expect(plain(screen.getByTestId('booking-total').textContent)).toBe('57 485,48 ₴')
  })

  it('shows a Result when the hold runs out and starts again', async () => {
    const soon = makeOrder({ tourists: TOURISTS, hold_expires_at: new Date(Date.now() + 1500).toISOString() })
    backend({ 'GET /orders/1': () => [200, soon] })
    inProgress(1, soon)
    const { user } = renderRoute(URL)
    expect(await screen.findByRole('heading', { level: 1, name: 'Час утримання місць минув' }, { timeout: 4000 }))
      .toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Почати знову' }))
    expect(await screen.findByLabelText('Дата заїзду')).toBeVisible()
    expect(JSON.parse(window.sessionStorage.getItem(draftKey(USER.id, 7))!).orderId).toBeNull()
  })

  it('warns on step 4 when less than 5 minutes are left', async () => {
    const short = makeOrder({ tourists: TOURISTS, hold_expires_at: new Date(Date.now() + 4 * 60_000).toISOString() })
    backend({ 'GET /orders/1': () => [200, short] })
    inProgress(3, short)
    renderRoute(URL)
    expect(await screen.findByText('Залишилося менше 5 хвилин утримання місць')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Почати знову' }).length).toBe(1)
  })

  it('confirms once on a double click and hands a price change to the payment page', async () => {
    const withTourists = makeOrder({ tourists: TOURISTS })
    const calls = backend({
      'GET /orders/1': () => [200, withTourists],
      'POST /orders/1/confirm': () => [200, makeOrder({
        tourists: TOURISTS, status: 'awaiting_payment', total_uah: '64000.00', price: makePrice({ total_uah: '64000.00' }),
      })],
    })
    inProgress(3, withTourists)
    const { user, router } = renderRoute(URL)
    expect(await screen.findByText(/паспорт FX\*{4}56,/)).toBeInTheDocument()   // passports partly hidden
    const confirm = screen.getByRole('button', { name: 'Підтвердити й перейти до оплати' })
    await user.click(confirm)
    expect(await screen.findByText('Потрібна згода з Договором публічної оферти')).toBeInTheDocument()
    await user.click(screen.getByRole('checkbox'))
    await user.dblClick(confirm)
    await waitFor(() => expect(router.state.location.pathname).toBe('/orders/1/pay'))
    expect(count(calls, 'POST', '/orders/1/confirm')).toBe(1)
    expect(router.state.location.state).toEqual({ priceChanged: { shown: '63872.76', frozen: '64000.00' } })
    expect(window.sessionStorage.getItem(draftKey(USER.id, 7))).toBeNull()
  })

  it('resumes an unfinished order of the same tour only', async () => {
    const other = { ...makeOrder({ id: 9, tour_id: 99 }) }
    const same = makeOrder({ id: 3, number: 'TU-2099-000003' })
    const calls = backend({
      'GET /orders': () => [200, { items: [other, same], total: 2, page: 1, page_size: 50 }],
      'GET /orders/3': () => [200, same],
    })
    renderRoute(URL)
    expect(await screen.findByText('Продовжуємо ваше незавершене бронювання №TU-2099-000003 на 10.06.2099.'))
      .toBeInTheDocument()
    expect(count(calls, 'GET', '/orders/9')).toBe(0)
  })

  it('starts fresh when the only unfinished order is for another tour', async () => {
    const calls = backend({
      'GET /orders': () => [200, { items: [makeOrder({ id: 9, tour_id: 99 })], total: 1, page: 1, page_size: 50 }],
    })
    renderRoute(URL)
    expect(await screen.findByLabelText('Дата заїзду')).toBeVisible()
    expect(screen.queryByRole('timer')).not.toBeInTheDocument()
    expect(count(calls, 'GET', '/orders/9')).toBe(0)
  })

  it('shows a Result for a tour that is no longer for sale', async () => {
    backend({ 'GET /tours/7': () => [404, { detail: 'Тур не знайдено' }] })
    renderRoute(URL)
    expect(await screen.findByRole('heading', { level: 1, name: 'Тур недоступний для бронювання' })).toBeInTheDocument()
  })
})
