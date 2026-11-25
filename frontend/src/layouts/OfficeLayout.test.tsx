import { configure, screen, waitFor, within } from '@testing-library/react'
import { beforeAll, describe, expect, it } from 'vitest'
import type { User } from '../api/types'
import { makeUser, mockServer, signIn } from '../test/fixtures'
import { ADMIN, FINANCE, MANAGER, managerPage } from '../test/officeFixtures'
import { renderRoute } from '../test/render'

function backend(user: User, extra: Parameters<typeof mockServer>[0] = {}) {
  signIn(user)
  return mockServer({
    'GET /auth/me': () => [200, user],
    'GET /manager/orders': () => [200, managerPage([])],
    ...extra,
  })
}

const menuItems = () => within(screen.getByRole('navigation', { name: 'Розділи робочого кабінету' }))
  .getAllByRole('menuitem').map((item) => item.textContent)

// The office pages are lazy routes: load their code once up front, so the first test does not
// spend its findBy time on the dynamic import while the whole suite runs in parallel.
// The antd Table, Tabs and Descriptions of these pages take more than findBy's 1 s default to
// mount the first time on a loaded machine (like the per-call timeouts of BookingPage.test).
configure({ asyncUtilTimeout: 4000 })
beforeAll(async () => {
  await import('./OfficeLayout')
})

describe('back office layout (spec 09 §1)', () => {
  it('builds the manager menu from the role and opens «Заявки» at /office', async () => {
    backend(MANAGER)
    const { router } = renderRoute('/office')
    await waitFor(() => expect(router.state.location.pathname).toBe('/office/orders'))
    expect(await screen.findByRole('heading', { level: 1, name: 'Заявки' })).toBeInTheDocument()
    expect(menuItems()).toEqual(['Заявки', 'Тури', 'Відгуки', 'Промокоди'])
    expect(screen.queryByText('Транзакції')).not.toBeInTheDocument()
    expect(screen.getByTestId('office-user')).toHaveTextContent('Іван П., Менеджер')
    expect(screen.getByRole('button', { name: /На сайт/ })).toBeInTheDocument()
  })

  it('shows finance its own menu without «Заявки» and starts at «Транзакції»', async () => {
    backend(FINANCE)
    const { router } = renderRoute('/office')
    await waitFor(() => expect(router.state.location.pathname).toBe('/office/transactions'))
    expect(await screen.findByRole('heading', { level: 1, name: 'Транзакції' })).toBeInTheDocument()
    expect(menuItems()).toEqual(['Транзакції', 'Повернення'])
    expect(screen.queryByText('Заявки')).not.toBeInTheDocument()
  })

  it('starts the admin at «Користувачі»', async () => {
    backend(ADMIN)
    const { router } = renderRoute('/office')
    await waitFor(() => expect(router.state.location.pathname).toBe('/office/users'))
    expect(menuItems()).toEqual(['Користувачі', 'Довідники', 'Налаштування', 'Журнал аудиту'])
  })

  it('answers 403 to a client', async () => {
    backend(makeUser())
    renderRoute('/office')
    expect(await screen.findByRole('heading', { level: 1, name: 'Немає доступу до цієї сторінки' })).toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Розділи робочого кабінету' })).not.toBeInTheDocument()
  })

  it('answers 403 inside the office to a role the page is not for', async () => {
    const calls = backend(FINANCE)
    renderRoute('/office/orders')
    expect(await screen.findByRole('heading', { level: 1, name: 'Недостатньо прав' })).toBeInTheDocument()
    expect(calls.some((c) => c.url === '/manager/orders')).toBe(false)
  })

  it('sends a guest to the login page and back', async () => {
    mockServer({})
    const { router } = renderRoute('/office/orders?queue=mine')
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'))
    expect(new URLSearchParams(router.state.location.search).get('redirect')).toBe('/office/orders?queue=mine')
  })

  it('leads a manager from a notification to the office order page', async () => {
    backend(MANAGER, {
      'GET /me/notifications': () => [200, {
        items: [{ id: 1, order_id: 42, title: 'Вам передано замовлення TU-2099-000042', body: 'Текст', is_read: true, created_at: '2099-01-01T10:00:00Z' }],
        total: 1, page: 1, page_size: 10, unread: 0,
      }],
      'GET /manager/orders/42': () => [404, { detail: 'Замовлення не знайдено' }],
    })
    const { user, router } = renderRoute('/office/orders')
    await user.click(await screen.findByRole('button', { name: 'Сповіщення' }))
    await user.click(await screen.findByText('Вам передано замовлення TU-2099-000042'))
    await waitFor(() => expect(router.state.location.pathname).toBe('/office/orders/42'))
  })

  it('signs out to the public site', async () => {
    backend(MANAGER)
    const { user, router } = renderRoute('/office/orders')
    await user.click(await screen.findByRole('button', { name: /Вийти/ }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/tours'))
  })
})
