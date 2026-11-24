import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { mockApi, page } from './test/fixtures'
import { renderRoute } from './test/render'

describe('routes', () => {
  it('sends / to the catalog', async () => {
    mockApi(() => page([]))
    const { router } = renderRoute('/')
    expect(await screen.findByRole('heading', { level: 1, name: 'Каталог турів' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/tours')
    expect(document.title).toMatch(/^Каталог турів — /)
  })

  it('shows 404 with a way back to the catalog for unknown paths', async () => {
    mockApi(() => page([]))
    const { router, user } = renderRoute('/no-such-page')
    expect(screen.getByRole('heading', { level: 1, name: 'Сторінку не знайдено' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'До каталогу' }))
    expect(router.state.location.pathname).toBe('/tours')
  })

  it('has a placeholder tour page', () => {
    renderRoute('/tours/42')
    expect(screen.getByRole('heading', { level: 1, name: 'Тур №42' })).toBeInTheDocument()
  })
})
