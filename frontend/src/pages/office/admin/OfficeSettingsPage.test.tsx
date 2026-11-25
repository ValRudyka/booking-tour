import { configure, screen, waitFor, within } from '@testing-library/react'
import { beforeAll, describe, expect, it } from 'vitest'
import type { AdminSettings } from '../../../api/types'
import { mockServer, signIn, type FakeRequest } from '../../../test/fixtures'
import { makeSettings, refAllowed, refRefused } from '../../../test/adminFixtures'
import { ADMIN } from '../../../test/officeFixtures'
import { renderRoute } from '../../../test/render'

type Handler = (request: FakeRequest) => [number, unknown]
const LANGUAGES = [
  { code: 'uk', name: 'Українська', is_enabled: true, admin_actions: [refAllowed('edit'),
    refRefused('disable', 'Українська — основна мова сайту, її не можна вимкнути'),
    refRefused('delete', 'Українська — основна мова сайту, її не можна видалити')] },
]
const GATEWAY = { gateway: 'mock', stripe_key_configured: false, stripe_key_mode: null, webhook_secret_configured: false,
  stripe_api_version: '2026-01-28', how_to_change: 'Ключі задаються в backend/.env' }

function backend(extra: Record<string, Handler> = {}) {
  signIn(ADMIN)
  let settings: AdminSettings = makeSettings()
  const calls = mockServer({
    'GET /auth/me': () => [200, ADMIN],
    'GET /admin/settings': () => [200, settings],
    'PUT /admin/settings': (request) => {
      settings = { ...settings, ...(request.body as Partial<AdminSettings>) }
      return [200, settings]
    },
    'GET /admin/languages': () => [200, LANGUAGES],
    'GET /admin/payment-gateway': () => [200, GATEWAY],
    ...extra,
  })
  return calls
}
const puts = (calls: FakeRequest[]) => calls.filter((c) => c.method === 'PUT').map((c) => c.body)

configure({ asyncUtilTimeout: 4000 })
beforeAll(async () => {
  await Promise.all([import('../../../layouts/OfficeLayout'), import('./OfficeSettingsPage')])
})

describe('/office/settings (spec 13 §3)', () => {
  it('turns maintenance mode on only after the warning; then the office shows the Alert', async () => {
    const calls = backend()
    const { user } = renderRoute('/office/settings')
    const toggle = await screen.findByRole('switch', { name: 'Технічні роботи' })
    expect(screen.queryByText('Увімкнено режим технічних робіт')).not.toBeInTheDocument()
    await user.click(toggle)
    const confirm = await screen.findByText('Клієнти не зможуть користуватися сайтом. Адміністратори матимуть доступ.')
    const dialog = confirm.closest('[role="dialog"]') as HTMLElement
    expect(within(dialog).getByText(/Менеджери й фінансисти також не зможуть працювати/)).toBeInTheDocument()
    expect(puts(calls)).toEqual([])
    await user.click(within(dialog).getByRole('button', { name: 'Увімкнути' }))
    await waitFor(() => expect(puts(calls)).toEqual([{ maintenance_mode: true }]))
    expect(await screen.findByText('Увімкнено режим технічних робіт')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Вимкнути в налаштуваннях' })).toBeInTheDocument()
    // Off at once, and the Alert goes away.
    await user.click(screen.getByRole('switch', { name: 'Технічні роботи' }))
    await waitFor(() => expect(puts(calls).at(-1)).toEqual({ maintenance_mode: false }))
    await waitFor(() => expect(screen.queryByText('Увімкнено режим технічних робіт')).not.toBeInTheDocument())
  })

  it('cancelling the warning keeps maintenance mode off', async () => {
    const calls = backend()
    const { user } = renderRoute('/office/settings')
    await user.click(await screen.findByRole('switch', { name: 'Технічні роботи' }))
    const dialog = (await screen.findByText(/Клієнти не зможуть/)).closest('[role="dialog"]') as HTMLElement
    await user.click(within(dialog).getByRole('button', { name: 'Скасувати' }))
    expect(puts(calls)).toEqual([])
    expect(screen.getByRole('switch', { name: 'Технічні роботи' })).not.toBeChecked()
  })

  it('a group saves only its own changed fields, with descriptions and limits shown', async () => {
    const calls = backend()
    const { user } = renderRoute('/office/settings')
    const timeout = await screen.findByLabelText('Час утримання місць, хв')
    expect(screen.getByText(/Скільки хвилин місця тримаються/)).toBeInTheDocument()
    expect(screen.getByText('Від 5 до 120')).toBeInTheDocument()
    expect(screen.getByText(/Змінено .*Адмін Системний/)).toBeInTheDocument()
    const save = screen.getByRole('button', { name: 'Зберегти: Бронювання й оплата' })
    expect(save).toBeDisabled()
    await user.clear(timeout)
    await user.type(timeout, '30')
    await waitFor(() => expect(save).toBeEnabled())
    expect(screen.getByRole('button', { name: 'Зберегти: Контакти сайту' })).toBeDisabled()
    await user.click(save)
    await waitFor(() => expect(puts(calls)).toEqual([{ booking_timeout_min: 30 }]))
    expect(await screen.findByText('Збережено')).toBeInTheDocument()
  })

  it('saves the contact address and shows the review limits from .env read-only', async () => {
    const calls = backend()
    const { user } = renderRoute('/office/settings')
    await user.type(await screen.findByLabelText('Адреса офісу'), 'Київ, вул. Морська, 1')
    await user.click(screen.getByRole('button', { name: 'Зберегти: Контакти сайту' }))
    await waitFor(() => expect(puts(calls)).toEqual([{ support_address: 'Київ, вул. Морська, 1' }]))
    expect(screen.getByText('Фото у відгуку, не більше')).toBeInTheDocument()
    expect(screen.getByText('5 МБ')).toBeInTheDocument()
  })

  it('shows a refusal of the server in the group', async () => {
    backend({ 'PUT /admin/settings': () => [422, { detail: '«Таймаут бронювання, хв»: ціле число від 5 до 120' }] })
    const { user } = renderRoute('/office/settings')
    const timeout = await screen.findByLabelText('Час утримання місць, хв')
    await user.clear(timeout)
    await user.type(timeout, '30')
    await user.click(screen.getByRole('button', { name: 'Зберегти: Бронювання й оплата' }))
    expect(await screen.findByText('«Таймаут бронювання, хв»: ціле число від 5 до 120')).toBeInTheDocument()
  })

  it('warns before leaving with unsaved changes', async () => {
    backend({ 'GET /admin/users': () => [200, { items: [], total: 0, page: 1, page_size: 20 }] })
    const { user, router } = renderRoute('/office/settings')
    await user.type(await screen.findByLabelText('Адреса офісу'), 'Львів')
    await user.click(screen.getByRole('menuitem', { name: /Користувачі/ }))
    expect((await screen.findAllByText('Зміни не збережено. Вийти без збереження?')).length).toBeGreaterThan(0)
    expect(router.state.location.pathname).toBe('/office/settings')
  })

  it('the base language cannot be turned off and says why; the gateway shows no keys', async () => {
    backend()
    renderRoute('/office/settings')
    const disable = await screen.findByRole('button', { name: 'Вимкнути' })
    expect(disable).toBeDisabled()
    expect(disable).toHaveAccessibleDescription(/основна мова сайту/)
    expect(screen.getByText('Тестовий без мережі (mock)')).toBeInTheDocument()
  })
})
