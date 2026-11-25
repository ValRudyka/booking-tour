import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { mockApi, page, signIn } from './test/fixtures'
import { renderRoute } from './test/render'

describe('routes', () => {
  it('opens the home page at /', async () => {
    mockApi(() => page([]))
    const { router } = renderRoute('/')
    expect(await screen.findByRole('heading', { level: 1, name: 'Знайдіть свій тур на море' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/')
  })

  it('opens the catalog at /tours', async () => {
    mockApi(() => page([]))
    renderRoute('/tours')
    expect(await screen.findByRole('heading', { level: 1, name: 'Каталог турів' })).toBeInTheDocument()
    expect(document.title).toMatch(/^Каталог турів — /)
  })

  it('shows 404 with a way back to the catalog for unknown paths', async () => {
    mockApi(() => page([]))
    const { router, user } = renderRoute('/no-such-page')
    expect(screen.getByRole('heading', { level: 1, name: 'Сторінку не знайдено' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'До каталогу' }))
    expect(router.state.location.pathname).toBe('/tours')
  })

  it('has a placeholder booking page for a signed-in client until the checkout exists', async () => {
    mockApi(() => page([]), signIn())
    renderRoute('/booking/42?date=2099-06-10')
    expect(await screen.findByRole('heading', { level: 1, name: 'Бронювання туру №42' })).toBeInTheDocument()
    expect(screen.getByText(/10\.06\.2099/)).toBeInTheDocument()
  })
})
