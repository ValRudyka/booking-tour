import { configure, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { AppNotification } from '../api/types'
import { NOTIFICATIONS_REFRESH_MS } from '../api/cabinet'
import { makeUser, mockServer, page, signIn, type FakeRequest } from '../test/fixtures'
import { renderRoute } from '../test/render'

// The first test renders the catalog page cold; on a loaded machine (the whole suite in
// parallel) that takes longer than findBy's 1 s default, like the office tests.
configure({ asyncUtilTimeout: 4000 })

const USER = makeUser()

function note(id: number, overrides: Partial<AppNotification> = {}): AppNotification {
  return {
    id, order_id: 42, title: `Сповіщення ${id}`, body: 'Текст', is_read: false,
    created_at: '2099-01-01T10:00:00Z', ...overrides,
  }
}

/** A fake notifications API that really marks them read. */
function backend(initial: AppNotification[], user = USER) {
  let items = initial
  signIn(user)
  const calls = mockServer({
    'GET /auth/me': () => [200, user],
    'GET /me/notifications': () => [200, {
      items, total: items.length, page: 1, page_size: 10, unread: items.filter((n) => !n.is_read).length,
    }],
    'POST /me/notifications/1/read': () => {
      items = items.map((n) => n.id === 1 ? { ...n, is_read: true } : n)
      return [200, items[0]]
    },
    'POST /me/notifications/read-all': () => {
      items = items.map((n) => ({ ...n, is_read: true }))
      return [200, { marked: 2 }]
    },
    'GET /orders/42': () => [404, { detail: 'Замовлення не знайдено' }],
    'GET /tours': () => [200, page([])],
  })
  return calls
}
const posts = (calls: FakeRequest[]) => calls.filter((c) => c.method === 'POST').map((c) => c.url)

describe('notification bell', () => {
  it('shows the unread count; opening one marks it read, updates the count and opens its order', async () => {
    const calls = backend([note(1), note(2), note(3, { is_read: true, order_id: null })])
    const { user, router } = renderRoute('/tours')
    const bell = await screen.findByRole('button', { name: 'Сповіщення: 2 непрочитані' })
    await user.click(bell)
    const popover = await screen.findByRole('tooltip')
    expect(within(popover).getAllByRole('listitem')).toHaveLength(3)
    await user.click(within(popover).getByRole('button', { name: /Сповіщення 1/ }))

    expect(posts(calls)).toEqual(['/me/notifications/1/read'])
    await waitFor(() => expect(router.state.location.pathname).toBe('/cabinet/orders/42'))
    expect(await screen.findByRole('button', { name: 'Сповіщення: 1 непрочитане' })).toBeInTheDocument()
  })

  it('«Позначити всі прочитаними» clears the count', async () => {
    const calls = backend([note(1), note(2)])
    const { user } = renderRoute('/tours')
    await user.click(await screen.findByRole('button', { name: 'Сповіщення: 2 непрочитані' }))
    await user.click(await screen.findByRole('button', { name: 'Позначити всі прочитаними' }))
    expect(await screen.findByRole('button', { name: 'Сповіщення' })).toBeInTheDocument()
    expect(posts(calls)).toEqual(['/me/notifications/read-all'])
  })

  it('a read notification without an order only closes the list', async () => {
    const calls = backend([note(3, { is_read: true, order_id: null })])
    const { user, router } = renderRoute('/tours')
    await user.click(await screen.findByRole('button', { name: 'Сповіщення' }))
    await user.click(within(await screen.findByRole('tooltip')).getByRole('button', { name: /Сповіщення 3/ }))
    expect(posts(calls)).toEqual([])
    expect(router.state.location.pathname).toBe('/tours')
  })

  it('is shown to clients only', async () => {
    backend([], makeUser({ role: 'manager' }))
    renderRoute('/tours')
    await screen.findByRole('button', { name: /Меню користувача/ })
    expect(screen.queryByRole('button', { name: /^Сповіщення/ })).not.toBeInTheDocument()
  })

  it('a new notification about an order reads that order again', async () => {
    let items: AppNotification[] = []
    signIn(USER)
    const calls = mockServer({
      'GET /auth/me': () => [200, USER],
      'GET /me/notifications': () => [200, { items, total: items.length, page: 1, page_size: 10, unread: items.length }],
      'GET /orders/42': () => [404, { detail: 'Замовлення не знайдено' }],
    })
    const { queryClient } = renderRoute('/cabinet/orders/42')
    await screen.findByRole('heading', { level: 1, name: 'Замовлення не знайдено' })
    const reads = () => calls.filter((c) => c.url === '/orders/42').length
    const before = reads()
    items = [note(7)]                                  // what the next minute's refresh brings
    await queryClient.invalidateQueries({ queryKey: ['notifications'] })
    await waitFor(() => expect(reads()).toBe(before + 1))
  })

  it('is refreshed every minute (no WebSocket)', () => {
    expect(NOTIFICATIONS_REFRESH_MS).toBe(60_000)
  })
})
