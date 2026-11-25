import { configure, screen, waitFor, within } from '@testing-library/react'
import { beforeAll, describe, expect, it } from 'vitest'
import type { ManagerOrderPage } from '../../api/types'
import { mockServer, signIn, type FakeRequest } from '../../test/fixtures'
import { makeManagerOrder, makeManagerRow, MANAGER, managerPage } from '../../test/officeFixtures'
import { renderRoute, searchOf } from '../../test/render'

type Handler = (request: FakeRequest) => [number, unknown]

function backend(list: Handler = () => [200, managerPage([makeManagerRow()])], extra: Record<string, Handler> = {}) {
  signIn(MANAGER)
  return mockServer({
    'GET /auth/me': () => [200, MANAGER],
    'GET /manager/orders': list,
    ...extra,
  })
}
const listCalls = (calls: FakeRequest[]) => calls.filter((c) => c.method === 'GET' && c.url === '/manager/orders')
const lastParams = (calls: FakeRequest[]) => listCalls(calls).at(-1)?.params

// The office pages are lazy routes: load their code once up front, so the first test does not
// spend its findBy time on the dynamic import while the whole suite runs in parallel.
// The antd Table, Tabs and Descriptions of these pages take more than findBy's 1 s default to
// mount the first time on a loaded machine (like the per-call timeouts of BookingPage.test).
configure({ asyncUtilTimeout: 4000 })
beforeAll(async () => {
  await Promise.all([import('../../layouts/OfficeLayout'), import('./OfficeOrdersPage')])
})

describe('/office/orders (spec 09 §2)', () => {
  it('starts with «Нові», shows the counts and the row', async () => {
    const calls = backend()
    renderRoute('/office/orders')
    expect(await screen.findByRole('tab', { name: 'Нові (3)' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'Мої в роботі (1)' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Усі (7)' })).toBeInTheDocument()
    expect(lastParams(calls)).toEqual({ queue: 'new', sort: 'created_desc', page: 1, page_size: 20 })
    const row = (await screen.findByRole('link', { name: 'TU-2099-000042' })).closest('tr') as HTMLElement
    expect(within(row).getByText('+380501234567')).toBeInTheDocument()
    expect(within(row).getByText('Оплачено')).toBeInTheDocument()
    expect(within(row).getByText('Не призначено')).toBeInTheDocument()
    expect(within(row).getByText('3')).toBeInTheDocument()     // 2 adults + 1 child
    expect(within(row).getByRole('button', { name: 'Взяти в роботу' })).toBeInTheDocument()
  })

  it('puts the tab into the request and the URL, and offers «Взяти» only in «Нові»', async () => {
    const calls = backend()
    const { user, router } = renderRoute('/office/orders')
    await user.click(await screen.findByRole('tab', { name: 'Усі (7)' }))
    await waitFor(() => expect(lastParams(calls)?.queue).toBe('all'))
    expect(searchOf(router).get('queue')).toBe('all')
    await screen.findByRole('link', { name: 'TU-2099-000042' })
    expect(screen.queryByRole('button', { name: 'Взяти в роботу' })).not.toBeInTheDocument()
  })

  it('sends the filters to the API and keeps them in the URL', async () => {
    const calls = backend()
    const { user, router } = renderRoute('/office/orders?queue=mine')
    await user.type(await screen.findByLabelText('Номер заявки'), 'TU-2099')
    await user.type(screen.getByLabelText('Клієнт'), '  Коваленко ')
    await user.click(screen.getByRole('switch', { name: 'Лише прострочені' }))
    await user.click(screen.getByRole('button', { name: /Знайти/ }))
    await waitFor(() => expect(lastParams(calls)).toEqual({
      queue: 'mine', sort: 'created_desc', page: 1, page_size: 20, number: 'TU-2099', client: 'Коваленко', overdue: true,
    }))
    const search = searchOf(router)
    expect([search.get('queue'), search.get('number'), search.get('client'), search.get('overdue')])
      .toEqual(['mine', 'TU-2099', 'Коваленко', 'true'])
    await user.click(screen.getByRole('button', { name: /Скинути/ }))
    await waitFor(() => expect(lastParams(calls)).toEqual({ queue: 'mine', sort: 'created_desc', page: 1, page_size: 20 }))
  })

  it('reads statuses, dates and the page from the URL and drops what is not valid', async () => {
    const calls = backend(() => [200, managerPage([makeManagerRow()], undefined, 45, 2)])
    renderRoute('/office/orders?queue=all&status=in_progress&status=bogus&created_from=2099-01-01&created_to=2099-02-30&start_from=2099-06-01&page=2&sort=start_asc')
    await screen.findByRole('link', { name: 'TU-2099-000042' })
    expect(lastParams(calls)).toEqual({
      queue: 'all', sort: 'start_asc', page: 2, page_size: 20, status: ['in_progress'],
      created_from: '2099-01-01', start_from: '2099-06-01',
    })
    expect(screen.getByRole('listitem', { name: '2' })).toHaveClass('ant-pagination-item-active')
  })

  it('sorts by the departure date through the API', async () => {
    const calls = backend()
    const { user, router } = renderRoute('/office/orders')
    await user.click(await screen.findByRole('columnheader', { name: /Дата виїзду/ }))
    await waitFor(() => expect(lastParams(calls)?.sort).toBe('start_asc'))
    expect(searchOf(router).get('sort')).toBe('start_asc')
  })

  it('takes an order and opens it', async () => {
    backend(undefined, {
      'POST /manager/orders/42/take': () => [200, makeManagerOrder({ status: 'in_progress', manager_id: MANAGER.id })],
      'GET /manager/orders/42': () => [200, makeManagerOrder({ status: 'in_progress', manager_id: MANAGER.id })],
    })
    const { user, router } = renderRoute('/office/orders')
    await user.click(await screen.findByRole('button', { name: 'Взяти в роботу' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/office/orders/42'))
  })

  it('shows the server text when another manager was faster and reloads the list', async () => {
    let page: ManagerOrderPage = managerPage([makeManagerRow()])
    const calls = backend(() => [200, page], {
      'POST /manager/orders/42/take': () => {
        page = managerPage([], { new: 2, mine: 1, all: 7 })
        return [409, { detail: 'Замовлення веде інший менеджер (Коваленко О.). Змінювати його може лише відповідальний менеджер' }]
      },
    })
    const { user, router } = renderRoute('/office/orders')
    await user.click(await screen.findByRole('button', { name: 'Взяти в роботу' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Замовлення веде інший менеджер (Коваленко О.)')
    expect(await screen.findByRole('tab', { name: 'Нові (2)' })).toBeInTheDocument()
    expect(listCalls(calls).length).toBeGreaterThanOrEqual(2)
    expect(router.state.location.pathname).toBe('/office/orders')
  })

  it('shows the API error with a retry', async () => {
    backend(() => [500, { detail: 'boom' }])
    renderRoute('/office/orders')
    expect(await screen.findByText('Не вдалося завантажити заявки')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Спробувати ще раз/ })).toBeInTheDocument()
  })
})
