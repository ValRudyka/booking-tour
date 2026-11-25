import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ClientAction, OrderDetailWithPrice } from '../../api/types'
import { makeOrder, makeUser, mockServer, signIn, type FakeRequest } from '../../test/fixtures'
import { renderRoute } from '../../test/render'

const USER = makeUser()
const plain = (text: string | null) => (text ?? '').replace(/[  ]/g, ' ')

function backend(order: OrderDetailWithPrice, routes: Record<string, (request: FakeRequest) => [number, unknown] | [number, unknown, Record<string, string>]> = {}) {
  signIn(USER)
  return mockServer({
    'GET /auth/me': () => [200, USER],
    [`GET /orders/${order.id}`]: () => [200, order],
    [`GET /orders/${order.id}/documents`]: () => [200, []],
    'GET /orders': () => [200, { items: [], total: 0, page: 1, page_size: 10 }],
    ...routes,
  })
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('/cabinet/orders/:id', () => {
  it('shows 404 for someone else\'s order', async () => {
    signIn(USER)
    mockServer({ 'GET /auth/me': () => [200, USER], 'GET /orders/7': () => [404, { detail: 'Замовлення не знайдено' }] })
    renderRoute('/cabinet/orders/7')
    expect(await screen.findByRole('heading', { level: 1, name: 'Замовлення не знайдено' })).toBeInTheDocument()
  })

  it('shows 404 for a malformed id without asking the API', async () => {
    const calls = backend(makeOrder())
    renderRoute('/cabinet/orders/abc')
    expect(await screen.findByRole('heading', { level: 1, name: 'Замовлення не знайдено' })).toBeInTheDocument()
    expect(calls.some((c) => c.url.startsWith('/orders/'))).toBe(false)
  })

  it('shows the order with its status history in Kyiv time and masked passports', async () => {
    backend(makeOrder())
    renderRoute('/cabinet/orders/42')
    expect(await screen.findByRole('heading', { level: 1, name: 'Замовлення № TU-2099-000042' })).toBeInTheDocument()
    const history = screen.getByRole('heading', { name: 'Історія статусів' }).closest('.ant-card') as HTMLElement
    expect(within(history).getByText('Оплату карткою отримано (Stripe)')).toBeInTheDocument()
    expect(within(history).getByText('01.01.2099, 12:06')).toBeInTheDocument()   // 10:06 UTC = 12:06 in Kyiv
    expect(within(history).getByText('Система')).toBeInTheDocument()
    expect(within(history).getAllByText('Ви')).toHaveLength(2)
    expect(screen.getByText(/FX\*\*\*\*56/)).toBeInTheDocument()
    expect(screen.queryByText(/FX123456/)).not.toBeInTheDocument()
    expect(plain(screen.getByTestId('booking-total').textContent)).toBe('63 872,76 ₴')
  })

  it.each<[ClientAction[], string[]]>([
    [['pay', 'cancel'], ['Оплатити', 'Скасувати замовлення']],
    [['continue_checkout', 'cancel'], ['Продовжити оформлення', 'Скасувати замовлення']],
    [['cancel_request'], ['Скасувати бронювання']],
    [['cancel_request', 'download_documents'], ['Скасувати бронювання']],
    [['review', 'download_documents'], ['Залишити відгук']],
    [['view_review', 'download_documents'], ['Мій відгук']],
    [[], []],
  ])('actions %j show exactly the buttons %j', async (actions, buttons) => {
    backend(makeOrder({ client_actions: actions }))
    renderRoute('/cabinet/orders/42')
    const card = (await screen.findByRole('heading', { name: 'Дії' })).closest('.ant-card') as HTMLElement
    expect(within(card).queryAllByRole('button').map((b) => b.textContent)).toEqual(buttons)
    if (buttons.length === 0) expect(within(card).getByText('Зараз для цього замовлення дій немає.')).toBeInTheDocument()
  })

  it('links to the tour only while it is for sale', async () => {
    backend(makeOrder({ tour_for_sale: false }))
    renderRoute('/cabinet/orders/42')
    await screen.findByText('Тур уже не продається, тому посилання на його сторінку немає.')
    expect(screen.queryByRole('link', { name: 'Coral Bay Resort, Хургада' })).not.toBeInTheDocument()
  })

  it('links to the tour page while it is for sale', async () => {
    backend(makeOrder({ tour_for_sale: true }))
    renderRoute('/cabinet/orders/42')
    expect(await screen.findByRole('link', { name: 'Coral Bay Resort, Хургада' })).toHaveAttribute('href', '/tours/7')
  })

  it('shows a pending bank transfer again, every value copyable', async () => {
    backend(makeOrder({
      status: 'awaiting_payment', payment_status: 'awaiting', client_actions: ['pay', 'cancel'], payments: [],
      pending_transfer: {
        recipient: 'ТОВ «Демо Тур»', iban: 'UA213223130000026007233566001', edrpou: '12345678', bank_name: 'Демо-банк',
        amount_uah: '63872.76', purpose: 'Оплата туру за замовленням TU-2099-000042', pay_until: '2099-01-03T08:05:00Z',
      },
    }))
    const { user, router } = renderRoute('/cabinet/orders/42')
    expect(await screen.findByText('Очікуємо банківський переказ')).toBeInTheDocument()
    expect(screen.getByText('UA213223130000026007233566001')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /^Скопіювати/ }).length).toBeGreaterThanOrEqual(6)
    await user.click(screen.getByRole('button', { name: 'Оплатити' }))
    expect(router.state.location.pathname).toBe('/orders/42/pay')
  })

  it('shows refunds as the API returns them, without failed attempts, and the ФПВ', async () => {
    backend(makeOrder({
      status: 'cancelled', payment_status: 'partially_refunded', client_actions: [], fpv_uah: '3500.00',
      payments: [
        makeOrder().payments[0],
        { id: 2, type: 'refund', method: 'card', status: 'failed', amount_uah: '60372.76', paid_amount: null, received_at: null, created_at: '2099-01-02T09:00:00Z' },
        { id: 3, type: 'refund', method: 'card', status: 'succeeded', amount_uah: '60372.76', paid_amount: null, received_at: '2099-01-02T10:00:00Z', created_at: '2099-01-02T10:00:00Z' },
      ],
    }))
    renderRoute('/cabinet/orders/42')
    const money = (await screen.findByRole('heading', { name: 'Оплата та повернення коштів' })).closest('.ant-card') as HTMLElement
    const refunds = within(money).getByRole('region', { name: 'Повернення коштів' })
    expect(within(refunds).getAllByText('на картку')).toHaveLength(1)
    expect(within(refunds).getByText('Виконано')).toBeInTheDocument()
    expect(within(refunds).queryByText('Не вдалося')).not.toBeInTheDocument()
    expect(plain(within(money).getByText(/ФПВ/).textContent)).toBe('Утримано фактично понесені витрати (ФПВ): 3 500,00 ₴')
    expect(within(money).getByText('Повернено частково')).toBeInTheDocument()
  })

  it('explains what happens to the money while a cancellation request is open', async () => {
    backend(makeOrder({ status: 'cancel_requested', client_actions: [] }))
    renderRoute('/cabinet/orders/42')
    expect(await screen.findByText(/Клопотання про скасування розглядається/)).toBeInTheDocument()
  })

  it('cancels an unpaid order after a confirmation', async () => {
    const order = makeOrder({ status: 'awaiting_payment', payment_status: 'awaiting', client_actions: ['pay', 'cancel'], payments: [] })
    const calls = backend(order, {
      'POST /orders/42/cancel': () => [200, { ...order, status: 'cancelled', client_actions: [] }],
    })
    const { user } = renderRoute('/cabinet/orders/42')
    await user.click(await screen.findByRole('button', { name: 'Скасувати замовлення' }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Скасувати замовлення' }))
    await waitFor(() => expect(calls.filter((c) => c.method === 'POST' && c.url === '/orders/42/cancel')).toHaveLength(1))
    expect(await screen.findByText('Замовлення скасовано')).toBeInTheDocument()
  })
})

describe('cancellation request (form 4.6.1.3)', () => {
  const LIMITS = { evidence: { max_files: 2, max_file_mb: 1, file_types: ['jpg', 'pdf'] }, max_details: 2000 }

  async function openForm(routes: Parameters<typeof backend>[1] = {}) {
    const calls = backend(makeOrder(), { 'GET /orders/42/cancel-request': () => [200, LIMITS], ...routes })
    const view = renderRoute('/cabinet/orders/42')
    await view.user.click(await screen.findByRole('button', { name: 'Скасувати бронювання' }))
    const dialog = await screen.findByRole('dialog')
    await within(dialog).findByLabelText('Причина скасування')
    return { ...view, calls, dialog }
  }

  it('requires a reason and the ФПВ consent, shown under the fields', async () => {
    const { user, calls, dialog } = await openForm()
    await user.click(within(dialog).getByRole('button', { name: 'Надіслати клопотання' }))
    expect(await within(dialog).findByText('Оберіть причину скасування')).toBeInTheDocument()
    expect(within(dialog).getByText('Підтвердіть згоду з умовами утримання ФПВ')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'POST')).toBe(false)
    expect(within(dialog).getByText(/Точну суму ФПВ розраховує фінансовий відділ/)).toBeInTheDocument()
  })

  it('sends the reason, the description, the consent and the files as one multipart request', async () => {
    let body: FormData | null = null
    let current = makeOrder()
    const { user, dialog } = await openForm({
      'GET /orders/42': () => [200, current],
      'POST /orders/42/cancel-request': (request) => {
        body = request.body as FormData
        current = makeOrder({ status: 'cancel_requested', client_actions: [] })
        return [200, current]
      },
    })
    await user.click(within(dialog).getByLabelText('Причина скасування'))
    await user.click(await screen.findByTitle('Хвороба'))
    await user.type(within(dialog).getByLabelText('Детальний опис (необов\'язково)'), 'Перелом ноги')
    const input = dialog.querySelector('input[type=file]') as HTMLInputElement
    await user.upload(input, new File(['%PDF-1.4'], 'dovidka.pdf', { type: 'application/pdf' }))
    await user.click(within(dialog).getByRole('checkbox', { name: /Я розумію/ }))
    await user.click(within(dialog).getByRole('button', { name: 'Надіслати клопотання' }))

    await waitFor(() => expect(body).not.toBeNull())
    const sent = body as unknown as FormData
    expect(sent.get('reason_code')).toBe('illness')
    expect(sent.get('details')).toBe('Перелом ноги')
    expect(sent.get('accept_penalty_policy')).toBe('true')
    expect((sent.getAll('files')[0] as File).name).toBe('dovidka.pdf')
    // The page shows the new status from the answer.
    await waitFor(() => expect(screen.getByRole('heading', { level: 1 }).parentElement).toHaveTextContent('Очікує скасування'))
  })

  it('refuses files of other types or over the size from the API', async () => {
    const { user, dialog } = await openForm()
    const input = dialog.querySelector('input[type=file]') as HTMLInputElement
    // The file input's accept list already hides other extensions; a file whose type does not
    // match its extension is still refused.
    await user.upload(input, new File(['x'], 'photo.pdf', { type: 'image/png' }))
    expect(await within(dialog).findByText('Файл «photo.pdf»: дозволені формати JPG, PDF')).toBeInTheDocument()
    // rc-upload renders a new <input> after every choice.
    const next = dialog.querySelector('input[type=file]') as HTMLInputElement
    await user.upload(next, new File([new Uint8Array(2 * 1024 * 1024)], 'big.pdf', { type: 'application/pdf' }))
    expect(await within(dialog).findByText('Файл «big.pdf» більший за 1 МБ')).toBeInTheDocument()
    expect(within(dialog).queryByText('big.pdf', { selector: 'a, span.ant-upload-list-item-name' })).not.toBeInTheDocument()
  })

  it('shows the server\'s reason when it refuses the request', async () => {
    const { user, dialog } = await openForm({
      'POST /orders/42/cancel-request': () => [422, { detail: 'Файл «a.pdf»: довідка має бути PDF або JPG' }],
    })
    await user.click(within(dialog).getByLabelText('Причина скасування'))
    await user.click(await screen.findByTitle('Інше'))
    await user.click(within(dialog).getByRole('checkbox', { name: /Я розумію/ }))
    await user.click(within(dialog).getByRole('button', { name: 'Надіслати клопотання' }))
    expect(await within(dialog).findByText('Файл «a.pdf»: довідка має бути PDF або JPG')).toBeInTheDocument()
  })
})

describe('trip documents', () => {
  it('downloads a private document with an authorised request and saves it under the server\'s name', async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    URL.createObjectURL = vi.fn(() => 'blob:doc')
    URL.revokeObjectURL = vi.fn()
    const calls = backend(makeOrder({ status: 'documents_ready', client_actions: ['cancel_request', 'download_documents'] }), {
      'GET /orders/42/documents': () => [200, [{ id: 5, doc_type: 'voucher', uploaded_at: '2099-01-02T10:00:00Z' }]],
      'GET /orders/42/documents/5/download': () => [200, new Blob(['%PDF'], { type: 'application/pdf' }),
        { 'content-disposition': 'attachment; filename="voucher-TU-2099-000042-5.pdf"' }],
    })
    const { user } = renderRoute('/cabinet/orders/42')
    await user.click(await screen.findByRole('button', { name: 'Завантажити: Ваучер' }))
    await waitFor(() => expect(click).toHaveBeenCalledTimes(1))
    const request = calls.find((c) => c.url === '/orders/42/documents/5/download')!
    expect(request.authorization).toBe('Bearer test-token')
    const link = click.mock.contexts[0] as HTMLAnchorElement
    expect(link.download).toBe('voucher-TU-2099-000042-5.pdf')
    expect(link.href).toBe('blob:doc')
  })

  it('says when the documents come before the booking is confirmed', async () => {
    backend(makeOrder({ status: 'in_progress', client_actions: ['cancel_request'] }))
    renderRoute('/cabinet/orders/42')
    expect(await screen.findByText(/з'являться тут після підтвердження бронювання/)).toBeInTheDocument()
  })

  it('says the manager is preparing them while the list is empty', async () => {
    backend(makeOrder({ status: 'confirmed', client_actions: ['cancel_request', 'download_documents'] }))
    renderRoute('/cabinet/orders/42')
    expect(await screen.findByText(/Менеджер готує документи/)).toBeInTheDocument()
  })
})
