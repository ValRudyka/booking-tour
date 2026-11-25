import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { makeOrderRow, makeUser, mockServer, orderPage, signIn, type FakeRequest } from '../../test/fixtures'
import { renderRoute, searchOf } from '../../test/render'
import { setViewportWidth } from '../../test/setup'

const USER = makeUser()

function backend(list: (request: FakeRequest) => [number, unknown]) {
  signIn(USER)
  return mockServer({ 'GET /auth/me': () => [200, USER], 'GET /orders': list })
}
const listCalls = (calls: FakeRequest[]) => calls.filter((c) => c.method === 'GET' && c.url === '/orders')

describe('/cabinet/orders', () => {
  it('sends a guest to the login page and back', async () => {
    mockServer({})
    const { router } = renderRoute('/cabinet/orders')
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'))
  })

  it('/cabinet opens the orders list', async () => {
    backend(() => [200, orderPage([])])
    const { router } = renderRoute('/cabinet')
    await waitFor(() => expect(router.state.location.pathname).toBe('/cabinet/orders'))
  })

  it('lists orders with the status tag and only the actions the API allows', async () => {
    backend(() => [200, orderPage([
      makeOrderRow({ id: 1, number: 'TU-1', status: 'awaiting_payment', payment_status: 'awaiting', client_actions: ['pay', 'cancel'] }),
      makeOrderRow({ id: 2, number: 'TU-2', status: 'paid', client_actions: ['cancel_request'] }),
      makeOrderRow({ id: 3, number: 'TU-3', status: 'checkout', client_actions: ['continue_checkout', 'cancel'], tour_id: 7, start_date: '2099-06-10' }),
    ])])
    const { user, router } = renderRoute('/cabinet/orders')
    const rows = await screen.findAllByRole('row')
    const row = (number: string) => rows.find((r) => within(r).queryByRole('link', { name: number }))!
    expect(within(row('TU-1')).getByText('Очікує оплати')).toBeInTheDocument()
    expect(within(row('TU-1')).getByRole('button', { name: 'Оплатити' })).toBeInTheDocument()
    expect(within(row('TU-2')).getByText('Оплачено')).toBeInTheDocument()
    expect(within(row('TU-2')).queryByRole('button', { name: 'Оплатити' })).not.toBeInTheDocument()
    expect(within(row('TU-2')).getByRole('button', { name: 'Деталі замовлення TU-2' })).toBeInTheDocument()

    await user.click(within(row('TU-3')).getByRole('button', { name: 'Продовжити оформлення' }))
    expect(router.state.location.pathname).toBe('/booking/7')
    expect(searchOf(router).get('date')).toBe('2099-06-10')
  })

  it('«Оплатити» leads to the payment page', async () => {
    backend(() => [200, orderPage([makeOrderRow({ id: 5, number: 'TU-5', status: 'awaiting_payment', client_actions: ['pay'] })])])
    const { user, router } = renderRoute('/cabinet/orders')
    await user.click(await screen.findByRole('button', { name: 'Оплатити' }))
    expect(router.state.location.pathname).toBe('/orders/5/pay')
  })

  it('keeps the tab and the page in the URL and asks the server for that group', async () => {
    const calls = backend((request) => [200, orderPage(
      [makeOrderRow({ number: `TU-${String(request.params.group)}` })], 25, Number(request.params.page))])
    const { user, router } = renderRoute('/cabinet/orders?group=completed&page=2')
    expect(await screen.findByRole('link', { name: 'TU-completed' })).toBeInTheDocument()
    expect(listCalls(calls).at(-1)?.params).toMatchObject({ group: 'completed', page: 2, page_size: 10 })

    await user.click(screen.getByText('Скасовані'))
    await waitFor(() => expect(searchOf(router).get('group')).toBe('cancelled'))
    expect(searchOf(router).get('page')).toBeNull()               // a new tab starts on page 1
    await waitFor(() => expect(listCalls(calls).at(-1)?.params).toMatchObject({ group: 'cancelled', page: 1 }))

    await user.click(screen.getByText('Усі'))
    await waitFor(() => expect(router.state.location.search).toBe(''))   // the default is not written
  })

  it('reads an unknown group as «Усі»', async () => {
    const calls = backend(() => [200, orderPage([])])
    renderRoute('/cabinet/orders?group=old&page=-1')
    await screen.findByText('У вас ще немає замовлень')
    expect(listCalls(calls)[0].params).toMatchObject({ group: 'all', page: 1 })
  })

  it('shows the empty state with a link to the catalog', async () => {
    backend(() => [200, orderPage([])])
    const { user, router } = renderRoute('/cabinet/orders')
    expect(await screen.findByText('У вас ще немає замовлень')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'До каталогу' }))
    expect(router.state.location.pathname).toBe('/tours')
  })

  it('an empty tab offers all orders instead', async () => {
    backend(() => [200, orderPage([])])
    const { user, router } = renderRoute('/cabinet/orders?group=cancelled')
    expect(await screen.findByText('У цьому розділі замовлень немає.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Показати всі замовлення' }))
    await waitFor(() => expect(router.state.location.search).toBe(''))
  })

  it('shows cards instead of a table on a phone', async () => {
    setViewportWidth(375)
    try {
      backend(() => [200, orderPage([makeOrderRow({ number: 'TU-9' })])])
      renderRoute('/cabinet/orders')
      expect(await screen.findByRole('link', { name: 'TU-9' })).toBeInTheDocument()
      expect(screen.queryByRole('table')).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Розділи кабінету' })).toBeInTheDocument()
    } finally {
      setViewportWidth(1440)
    }
  })

  it('lists only the cabinet sections that have an API', async () => {
    backend(() => [200, orderPage([])])
    renderRoute('/cabinet/orders')
    const nav = await screen.findByRole('navigation', { name: 'Розділи кабінету' })
    const items = within(nav).getAllByRole('menuitem').map((item) => item.textContent)
    expect(items).toEqual(['Мої замовлення', 'Історія подорожей', 'Збережені туристи', 'Профіль'])
  })
})

describe('«Історія подорожей» (spec 08 §4)', () => {
  const trip = (number: string, overrides: Parameters<typeof makeOrderRow>[0] = {}) => makeOrderRow({
    id: Number(number.replace(/\D/g, '')), number, status: 'completed', country_name: 'Туреччина',
    resort_name: 'Анталія', client_actions: ['download_documents'], ...overrides,
  })

  it('is the «Завершені» tab: /cabinet/history redirects there and the menu item is selected', async () => {
    const calls = backend(() => [200, orderPage([trip('TU-1')])])
    const { router } = renderRoute('/cabinet/history')
    expect(await screen.findByRole('link', { name: 'TU-1' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/cabinet/orders')
    expect(searchOf(router).get('group')).toBe('completed')
    expect(listCalls(calls).at(-1)?.params).toMatchObject({ group: 'completed' })
    const nav = screen.getByRole('navigation', { name: 'Розділи кабінету' })
    const selected = nav.querySelectorAll('.ant-menu-item-selected')
    expect([...selected].map((item) => item.textContent)).toEqual(['Історія подорожей'])
    expect(screen.getByText('Туреччина, Анталія')).toBeInTheDocument()
  })

  it('shows the right review state for every trip', async () => {
    backend(() => [200, orderPage([
      trip('TU-1', { client_actions: ['review', 'download_documents'] }),
      trip('TU-2', { client_actions: ['view_review', 'download_documents'], review_status: 'pending' }),
      trip('TU-3', { client_actions: ['view_review', 'download_documents'], review_status: 'published' }),
      trip('TU-4', { client_actions: ['view_review', 'download_documents'], review_status: 'rejected', review_can_resubmit: true }),
      trip('TU-5', { client_actions: ['view_review', 'download_documents'], review_status: 'rejected' }),
    ])])
    const { user, router } = renderRoute('/cabinet/orders?group=completed')
    const row = async (number: string) => within((await screen.findByRole('link', { name: number })).closest('tr') as HTMLElement)

    expect((await row('TU-1')).getByRole('button', { name: 'Залишити відгук (замовлення TU-1)' })).toBeInTheDocument()
    expect((await row('TU-2')).getByText('На модерації')).toBeInTheDocument()
    expect((await row('TU-3')).getByText('Опубліковано')).toBeInTheDocument()
    expect((await row('TU-5')).getByText('Відхилено')).toBeInTheDocument()
    expect((await row('TU-5')).queryByRole('button', { name: /виправити/ })).not.toBeInTheDocument()
    await user.click((await row('TU-4')).getByRole('button', { name: 'Відгук відхилено — виправити (замовлення TU-4)' }))
    expect(router.state.location.pathname).toBe('/cabinet/orders/4/review')
  })

  it('has its own empty state with a link to the catalog', async () => {
    backend(() => [200, orderPage([])])
    const { user, router } = renderRoute('/cabinet/orders?group=completed')
    expect(await screen.findByText("Тут з'являться ваші завершені подорожі")).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'До каталогу' }))
    expect(router.state.location.pathname).toBe('/tours')
  })
})
