import { focusManager } from '@tanstack/react-query'
import { act, configure, screen, waitFor, within } from '@testing-library/react'
import { AxiosError } from 'axios'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { api, onUnauthorized } from '../../api/client'
import { makeUser, mockServer, signIn } from '../../test/fixtures'
import { ADMIN, MANAGER, managerPage } from '../../test/officeFixtures'
import { renderRoute } from '../../test/render'
import { TOKEN_KEY } from './tokenStorage'

// Maintenance mode (form 4.6.4.1, field 7): the backend answers 503 to everyone except admins,
// /auth/me and /auth/login included. A 503 must never send anyone to /login (the staff login loop).
const DOWN = 'Тривають технічні роботи. Спробуйте пізніше.'
const down = (): [number, unknown] => [503, { detail: DOWN }]

const maintenanceHeading = () => screen.findByRole('heading', { level: 1, name: 'Технічні роботи' })

// The office pages are lazy routes and their antd Table mounts slowly on a loaded machine
// (as in OfficeLayout.test).
configure({ asyncUtilTimeout: 4000 })
beforeAll(async () => {
  await Promise.all([import('../../layouts/OfficeLayout'), import('../../pages/office/OfficeOrdersPage')])
})
afterEach(() => focusManager.setFocused(undefined))

describe('maintenance mode', () => {
  it('a 503 on a signed-in request does not end the session', async () => {
    window.localStorage.setItem(TOKEN_KEY, 'test-token')
    mockServer({ 'GET /manager/orders': down })
    const onLogout = vi.fn()
    onUnauthorized(onLogout)
    const error = await api.get('/manager/orders').catch((e: unknown) => e)
    onUnauthorized(null)
    expect(error).toMatchObject({ kind: 'maintenance', message: DOWN })
    expect(error).not.toBeInstanceOf(AxiosError)
    expect(onLogout).not.toHaveBeenCalled()
  })

  it('shows a manager the maintenance page after a reload instead of sending them to /login', async () => {
    signIn(MANAGER)
    const calls = mockServer({ 'GET /auth/me': down })
    const { router } = renderRoute('/office/orders')
    expect(await maintenanceHeading()).toBeInTheDocument()
    expect(screen.getByText(DOWN)).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/office/orders')
    expect(window.localStorage.getItem(TOKEN_KEY)).toBe('test-token')
    expect(calls.some((c) => c.url === '/manager/orders')).toBe(false)
  })

  it('shows a client the maintenance page on a cabinet page', async () => {
    signIn(makeUser())
    mockServer({ 'GET /auth/me': down })
    const { router } = renderRoute('/cabinet/orders')
    expect(await maintenanceHeading()).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/cabinet/orders')
  })

  it('switches a manager already in the office to the maintenance page', async () => {
    signIn(MANAGER)
    let on = false
    mockServer({
      'GET /auth/me': () => (on ? down() : [200, MANAGER]),
      'GET /manager/orders': () => (on ? down() : [200, managerPage([])]),
    })
    const { router, user } = renderRoute('/office/orders')
    expect(await screen.findByRole('heading', { level: 1, name: 'Заявки' })).toBeInTheDocument()
    on = true
    await user.click(screen.getByRole('tab', { name: /Усі/ }))
    expect(await maintenanceHeading()).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/office/orders')
  })

  it('does not affect an admin', async () => {
    signIn(ADMIN)
    // /auth/me and /admin/... stay open for an admin; the bell's endpoint does not.
    mockServer({ 'GET /auth/me': () => [200, ADMIN], 'GET /me/notifications': down })
    const { router } = renderRoute('/office')
    await waitFor(() => expect(router.state.location.pathname).toBe('/office/users'))
    expect(await screen.findByRole('heading', { level: 1, name: 'Користувачі' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Технічні роботи' })).not.toBeInTheDocument()
  })

  it('comes back by itself on the next check once maintenance is off', async () => {
    signIn(MANAGER)
    let on = true
    mockServer({
      'GET /auth/me': () => (on ? down() : [200, MANAGER]),
      'GET /manager/orders': () => [200, managerPage([])],
    })
    const { router } = renderRoute('/office/orders')
    expect(await maintenanceHeading()).toBeInTheDocument()
    on = false
    // The window gets focus again (also checked every minute, MAINTENANCE_RECHECK_MS).
    act(() => {
      focusManager.setFocused(false)
      focusManager.setFocused(true)
    })
    expect(await screen.findByRole('heading', { level: 1, name: 'Заявки' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/office/orders')
  })

  it('«Спробувати ще раз» checks again', async () => {
    signIn(MANAGER)
    let on = true
    mockServer({
      'GET /auth/me': () => (on ? down() : [200, MANAGER]),
      'GET /manager/orders': () => [200, managerPage([])],
    })
    const { user } = renderRoute('/office/orders')
    expect(await maintenanceHeading()).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Спробувати ще раз/ }))
    expect(await maintenanceHeading()).toBeInTheDocument() // still on
    on = false
    await user.click(screen.getByRole('button', { name: /Спробувати ще раз/ }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Заявки' })).toBeInTheDocument()
  })

  it('a refused login shows the message on the login page and stays there', async () => {
    mockServer({ 'POST /auth/login': down })
    const { router, user } = renderRoute('/login?redirect=%2Foffice%2Forders')
    await user.type(await screen.findByLabelText(/Номер телефону або e-mail/), 'ivan@example.com')
    await user.type(screen.getByLabelText(/Пароль/), 'Some-pass-11')
    // The form's «Увійти» (the header has a button with the same name).
    await user.click(within(document.querySelector('.auth-card') as HTMLElement).getByRole('button', { name: 'Увійти' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(DOWN)
    expect(router.state.location.pathname).toBe('/login')
    expect(window.localStorage.getItem(TOKEN_KEY)).toBeNull()
  })
})
