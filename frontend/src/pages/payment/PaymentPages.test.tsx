import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { OrderWithPrice, PayOut } from '../../api/types'
import { browser, paymentOutcome } from '../../features/payment/orderOutcome'
import { POLLING } from '../../features/payment/paymentPaths'
import {
  makeCheckoutOrder, makeTourDetail, makeUser, mockServer, signIn, TOURISTS, type FakeRequest,
} from '../../test/fixtures'
import { renderRoute } from '../../test/render'

const plain = (text: string | null) => (text ?? '').replace(/[\u00a0\u202f]/g, ' ')
const USER = makeUser()
const TOUR = makeTourDetail({ id: 7 })
const HISTORY = [
  { old_status: null, new_status: 'checkout' as const, changed_by: 501, comment: null, changed_at: '2099-01-01T10:00:00Z' },
  { old_status: 'checkout' as const, new_status: 'awaiting_payment' as const, changed_by: 501, comment: null, changed_at: '2099-01-01T10:05:00Z' },
]
const awaiting = (overrides: Partial<OrderWithPrice> = {}) =>
  makeCheckoutOrder({ status: 'awaiting_payment', tourists: TOURISTS, history: HISTORY, ...overrides })
const paid = (overrides: Partial<OrderWithPrice> = {}) => awaiting({
  status: 'paid', payment_status: 'paid',
  history: [...HISTORY, { old_status: 'awaiting_payment', new_status: 'paid', changed_by: null, comment: null, changed_at: '2099-01-01T10:06:00Z' }],
  ...overrides,
})
const BANK = {
  recipient: 'ТОВ «Демо Тур»', iban: 'UA213223130000026007233566001', edrpou: '12345678', bank_name: 'Демо-банк',
  amount_uah: '63872.76', purpose: 'Оплата туру за замовленням TU-2099-000001, Коваленко Олена',
  pay_until: '2099-01-03T08:05:00Z',
}
const payOut = (overrides: Partial<PayOut> = {}): PayOut => ({
  order_id: 1, order_number: 'TU-2099-000001', order_status: 'awaiting_payment', payment_status: 'awaiting',
  payment: null, checkout_url: null, bank_details: null, message: null, ...overrides,
})

function backend(routes: Record<string, (request: FakeRequest) => [number, unknown]> = {}) {
  signIn(USER)
  return mockServer({
    'GET /auth/me': () => [200, USER],
    'GET /tours/7': () => [200, TOUR],
    ...routes,
  })
}
const count = (calls: FakeRequest[], method: string, url: string) =>
  calls.filter((c) => c.method === method && c.url === url).length

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllEnvs()
  POLLING.intervalMs = 2000
  POLLING.timeoutMs = 30_000
})

describe('/orders/:id/pay', () => {
  it('sends a guest to the login page and back', async () => {
    mockServer({})
    const { router } = renderRoute('/orders/1/pay')
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'))
    expect(new URLSearchParams(router.state.location.search).get('redirect')).toBe('/orders/1/pay')
  })

  it('shows 404 for someone else\'s order', async () => {
    backend({ 'GET /orders/1': () => [404, { detail: 'Замовлення не знайдено' }] })
    renderRoute('/orders/1/pay')
    expect(await screen.findByRole('heading', { level: 1, name: 'Замовлення не знайдено' })).toBeInTheDocument()
  })

  it('pays by card with one request on a double click and leaves for Stripe', async () => {
    const assign = vi.spyOn(browser, 'assign').mockImplementation(() => undefined)
    const calls = backend({
      'GET /orders/1': () => [200, awaiting()],
      'POST /orders/1/pay': () => [200, payOut({ checkout_url: 'https://checkout.stripe.com/c/pay/cs_test_1' })],
    })
    const { user } = renderRoute('/orders/1/pay')
    const button = await screen.findByRole('button', { name: /Оплатити 63\s872,76 ₴/ })
    await user.dblClick(button)
    await waitFor(() => expect(assign).toHaveBeenCalledWith('https://checkout.stripe.com/c/pay/cs_test_1'))
    expect(count(calls, 'POST', '/orders/1/pay')).toBe(1)
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ method: 'card' })
    expect(screen.getByRole('timer')).toHaveTextContent(/Місця утримуються до \d\d:\d\d/)
  })

  it('shows the price change with both amounts before the pay button', async () => {
    backend({ 'GET /orders/1': () => [200, awaiting({ total_uah: '64000.00' })] })
    renderRoute({ pathname: '/orders/1/pay', state: { priceChanged: { shown: '63872.76', frozen: '64000.00' } } })
    const alert = await screen.findByText('Ціну оновлено за курсом на сьогодні')
    expect(plain(alert.closest('.ant-alert')!.textContent)).toContain('сума була 63 872,76 ₴, після підтвердження — 64 000,00 ₴')
    const button = screen.getByRole('button', { name: /Оплатити 64\s000,00 ₴/ })
    expect(alert.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('shows no pay button for a paid order', async () => {
    backend({ 'GET /orders/1': () => [200, paid()] })
    renderRoute('/orders/1/pay')
    expect(await screen.findByRole('heading', { level: 1, name: 'Замовлення вже оплачено' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Оплатити/ })).not.toBeInTheDocument()
  })

  it('gives the bank details with copy buttons', async () => {
    const calls = backend({
      'GET /orders/1': () => [200, awaiting()],
      'POST /orders/1/pay': () => [200, payOut({ bank_details: BANK })],
    })
    const { user } = renderRoute('/orders/1/pay')
    await user.click(await screen.findByRole('radio', { name: 'Банківським переказом' }))
    await user.click(screen.getByRole('button', { name: 'Отримати реквізити' }))
    expect(await screen.findByText(BANK.iban)).toBeInTheDocument()
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ method: 'bank_transfer' })
    expect(screen.getByText(BANK.purpose)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Скопіювати: IBAN' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Скопіювати: Призначення платежу' })).toBeInTheDocument()
    expect(screen.getByText('03.01.2099, 10:05')).toBeInTheDocument()   // pay_until in Kyiv time
    expect(screen.getByText(/Реквізити завжди можна відкрити знову на цій сторінці/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Зрозуміло' }))
    await waitFor(() => expect(screen.queryByText(BANK.iban)).not.toBeInTheDocument())
  })

  it('shows the same details again for a transfer chosen earlier', async () => {
    const calls = backend({
      'GET /orders/1': () => [200, awaiting({
        hold_expires_at: new Date(Date.now() + 47 * 3600_000).toISOString(),
        payments: [{ id: 5, type: 'payment', method: 'bank_transfer', status: 'pending', amount_uah: '63872.76', paid_amount: null, received_at: null, created_at: '2099-01-01T10:06:00Z' }],
      })],
      'POST /orders/1/pay': () => [200, payOut({ bank_details: BANK })],
    })
    renderRoute('/orders/1/pay')
    expect(await screen.findByText(BANK.iban)).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Банківським переказом' })).toBeChecked()
    expect(count(calls, 'POST', '/orders/1/pay')).toBe(1)
    // A 48 h hold shows the date, not thousands of minutes.
    expect(screen.getByRole('timer')).toHaveTextContent(/^Місця утримуються до \d\d\.\d\d\.\d{4}, \d\d:\d\d$/)
  })

  it('goes straight to the success page when a promo code covered everything', async () => {
    let state = awaiting({ total_uah: '0.00', discount_uah: '63872.76' })
    const calls = backend({
      'GET /orders/1': () => [200, state],
      'POST /orders/1/pay': () => {
        state = paid({ total_uah: '0.00' })
        return [200, payOut({ order_status: 'paid', payment_status: 'paid', message: 'Промокод покрив повну вартість — оплата не потрібна' })]
      },
    })
    const { router } = renderRoute('/orders/1/pay')
    expect(await screen.findByRole('heading', { level: 1, name: 'Оплату отримано' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/payment/success')
    expect(screen.queryByRole('radio')).not.toBeInTheDocument()
    expect(count(calls, 'POST', '/orders/1/pay')).toBe(1)
  })

  it('warns neutrally when less than 5 minutes are left', async () => {
    backend({ 'GET /orders/1': () => [200, awaiting({ hold_expires_at: new Date(Date.now() + 4 * 60_000).toISOString() })] })
    renderRoute('/orders/1/pay')
    expect(await screen.findByText('Залишилося менше 5 хвилин утримання місць')).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Карткою онлайн' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Банківським переказом' })).toBeInTheDocument()
  })

  it('shows the expired Result when the hold has run out', async () => {
    backend({ 'GET /orders/1': () => [200, awaiting({ hold_expires_at: new Date(Date.now() - 1000).toISOString() })] })
    renderRoute('/orders/1/pay')
    expect(await screen.findByRole('heading', { level: 1, name: 'Час на оплату минув' })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Забронювати знову' })).toBeInTheDocument()
  })

  it('shows the test card only in a dev build', async () => {
    backend({ 'GET /orders/1': () => [200, awaiting()] })
    const view = renderRoute('/orders/1/pay')
    expect(await screen.findByTestId('test-card')).toHaveTextContent('4242 4242 4242 4242')
    view.unmount()
    vi.stubEnv('DEV', false)
    renderRoute('/orders/1/pay')
    await screen.findByRole('button', { name: /Оплатити/ })
    expect(screen.queryByTestId('test-card')).not.toBeInTheDocument()
  })
})

describe('/payment/success', () => {
  it('checks first, then shows success once the webhook has marked the order paid', async () => {
    POLLING.intervalMs = 30
    let reads = 0
    backend({ 'GET /orders/1': () => [200, ++reads < 3 ? awaiting() : paid()] })
    renderRoute('/payment/success?order_id=1&session_id=cs_test_1')
    expect(await screen.findByRole('heading', { level: 1, name: 'Перевіряємо оплату…' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { level: 1, name: 'Оплату отримано' })).toBeInTheDocument()
    expect(screen.getByText(/TU-2099-000001 оплачено/)).toBeInTheDocument()
    expect(document.title).toMatch(/^Оплату отримано — /)
    expect(screen.getByRole('button', { name: 'Мої замовлення' })).toBeInTheDocument()
  })

  it('says «processing», not an error, when the time runs out', async () => {
    POLLING.intervalMs = 30
    POLLING.timeoutMs = 200
    backend({ 'GET /orders/1': () => [200, awaiting()] })
    renderRoute('/payment/success?order_id=1')
    expect(await screen.findByRole('heading', { level: 1, name: 'Оплата обробляється' })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('explains a late payment that was refunded automatically', async () => {
    backend({
      'GET /orders/1': () => [200, awaiting({
        status: 'cancelled', payment_status: 'refunded',
        history: [...HISTORY, { old_status: 'awaiting_payment', new_status: 'cancelled', changed_by: null, comment: 'Час на оплату минув', changed_at: '2099-01-01T10:25:00Z' }],
      })],
    })
    renderRoute('/payment/success?order_id=1')
    expect(await screen.findByRole('heading', { level: 1, name: 'Оплата надійшла запізно' })).toBeInTheDocument()
    expect(screen.getByText(/кошти автоматично повернено на картку/)).toBeInTheDocument()
  })
})

describe('/payment/cancel', () => {
  it('offers to try again while the order can be paid', async () => {
    backend({ 'GET /orders/1': () => [200, awaiting()] })
    const { user, router } = renderRoute('/payment/cancel?order_id=1')
    expect(await screen.findByRole('heading', { level: 1, name: 'Оплату не завершено. Гроші не списано.' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Спробувати ще раз' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/orders/1/pay'))
  })

  it('has no retry for an order that can no longer be paid', async () => {
    backend({ 'GET /orders/1': () => [200, awaiting({ hold_expires_at: new Date(Date.now() - 1000).toISOString() })] })
    renderRoute('/payment/cancel?order_id=1')
    const result = (await screen.findByRole('heading', { level: 1, name: 'Оплату не завершено. Гроші не списано.' })).closest('.ant-result') as HTMLElement
    expect(within(result).getByText('Оплатити це замовлення вже не можна.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Спробувати ще раз' })).not.toBeInTheDocument()
  })
})

describe('paymentOutcome', () => {
  it('reads where the order stands', () => {
    const now = Date.now()
    expect(paymentOutcome(awaiting(), now)).toBe('payable')
    expect(paymentOutcome(awaiting({ hold_expires_at: new Date(now - 1).toISOString() }), now)).toBe('expired')
    expect(paymentOutcome(awaiting({ hold_expires_at: new Date(now - 1).toISOString(), payment_status: 'partially_paid' }), now)).toBe('payable')
    expect(paymentOutcome(paid(), now)).toBe('paid')
    expect(paymentOutcome(paid({ status: 'in_progress' }), now)).toBe('paid')
    expect(paymentOutcome(makeCheckoutOrder(), now)).toBe('checkout')
    expect(paymentOutcome(awaiting({ status: 'cancelled' }), now)).toBe('cancelled')
    expect(paymentOutcome(awaiting({ status: 'cancelled', payment_status: 'refunded' }), now)).toBe('late_refund')
    // Cancelled after it had been paid (a cancellation request): not a late payment.
    expect(paymentOutcome(paid({ status: 'cancelled', payment_status: 'partially_refunded' }), now)).toBe('cancelled')
  })
})
