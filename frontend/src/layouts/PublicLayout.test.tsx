import { screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { renderRoute } from '../test/render'
import { setViewportWidth } from '../test/setup'

describe('PublicLayout', () => {
  afterEach(() => setViewportWidth(1440))

  it('shows the navigation and auth buttons in the header on desktop', () => {
    renderRoute('/about')
    const nav = screen.getByRole('navigation', { name: 'Головне меню' })
    expect(within(nav).getByRole('link', { name: 'Тури' })).toHaveAttribute('href', '/tours')
    expect(screen.getByRole('button', { name: 'Увійти' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Умови' })).toHaveAttribute('href', '/terms')
  })

  it('hides the menu in a Drawer on mobile', async () => {
    setViewportWidth(375)
    const { user, router } = renderRoute('/about')
    expect(screen.queryByRole('navigation', { name: 'Головне меню' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Меню' }))
    const drawer = await screen.findByRole('dialog')
    await user.click(within(drawer).getByRole('button', { name: 'Реєстрація' }))
    expect(router.state.location.pathname).toBe('/register')
  })
})
