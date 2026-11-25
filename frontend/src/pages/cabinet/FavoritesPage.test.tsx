import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { FavoriteTour } from '../../api/types'
import { makeTour, makeTourDetail, makeUser, mockServer, page, signIn, type FakeRequest } from '../../test/fixtures'
import { renderRoute } from '../../test/render'

const USER = makeUser()

function favorite(overrides: Partial<FavoriteTour> = {}): FavoriteTour {
  return { ...makeTour(), for_sale: true, added_at: '2099-01-01T10:00:00Z', ...overrides }
}

type Routes = Record<string, (request: FakeRequest) => [number, unknown]>

describe('/cabinet/favorites', () => {
  it('shows the cards; a tour no longer for sale is marked, muted and not a link', async () => {
    signIn(USER)
    const sale = favorite({ title_uk: 'Тур у продажу' })
    const gone = favorite({ title_uk: 'Тур поза продажем', for_sale: false })
    mockServer({
      'GET /auth/me': () => [200, USER],
      'GET /me/favorites': () => [200, { items: [sale, gone], total: 2, page: 1, page_size: 12 }],
    })
    renderRoute('/cabinet/favorites')
    const saleCard = (await screen.findByRole('heading', { name: 'Тур у продажу' })).closest('.tour-card-wrap') as HTMLElement
    expect(within(saleCard).getByRole('link')).toHaveAttribute('href', `/tours/${sale.id}`)
    const goneCard = screen.getByRole('heading', { name: 'Тур поза продажем' }).closest('.tour-card-wrap') as HTMLElement
    expect(within(goneCard).getByText('Не продається')).toBeInTheDocument()
    expect(within(goneCard).queryByRole('link')).not.toBeInTheDocument()
    expect(goneCard.querySelector('.tour-card-muted')).not.toBeNull()
    // The page has its own remove buttons, no hearts.
    expect(within(goneCard).getByRole('button', { name: 'Прибрати з обраного: Тур поза продажем' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Додати в обране/ })).not.toBeInTheDocument()
  })

  it('removes a tour', async () => {
    signIn(USER)
    let items = [favorite({ title_uk: 'Тур у продажу' })]
    const calls = mockServer({
      'GET /auth/me': () => [200, USER],
      'GET /me/favorites': () => [200, { items, total: items.length, page: 1, page_size: 12 }],
      'GET /me/favorites/ids': () => [200, items.map((t) => t.id)],
      [`DELETE /me/favorites/${items[0].id}`]: () => {
        items = []
        return [204, null]
      },
    })
    const { user } = renderRoute('/cabinet/favorites')
    await user.click(await screen.findByRole('button', { name: 'Прибрати з обраного: Тур у продажу' }))
    expect(await screen.findByText('В обраному поки порожньо')).toBeInTheDocument()
    expect(calls.filter((c) => c.method === 'DELETE')).toHaveLength(1)
  })
})

describe('«В обране» on the catalog cards and the tour page', () => {
  const tour = makeTour({ title_uk: 'Сонячний тур' })

  function catalog(routes: Routes = {}) {
    return mockServer({ 'GET /tours': () => [200, page([tour])], ...routes })
  }

  it('a client adds and removes a tour with the heart', async () => {
    signIn(USER)
    let ids: number[] = []
    const calls = catalog({
      'GET /auth/me': () => [200, USER],
      'GET /me/favorites/ids': () => [200, ids],
      [`PUT /me/favorites/${tour.id}`]: () => {
        ids = [tour.id]
        return [204, null]
      },
      [`DELETE /me/favorites/${tour.id}`]: () => {
        ids = []
        return [204, null]
      },
    })
    const { user } = renderRoute('/tours')
    const heart = await screen.findByRole('button', { name: 'Додати в обране: Сонячний тур' })
    expect(heart).toHaveAttribute('aria-pressed', 'false')
    await user.click(heart)
    const pressed = await screen.findByRole('button', { name: 'Прибрати з обраного: Сонячний тур' })
    expect(pressed).toHaveAttribute('aria-pressed', 'true')
    await user.click(pressed)
    expect(await screen.findByRole('button', { name: 'Додати в обране: Сонячний тур' })).toBeInTheDocument()
    await waitFor(() => expect(calls.filter((c) => c.method === 'PUT' || c.method === 'DELETE').map((c) => c.method))
      .toEqual(['PUT', 'DELETE']))
  })

  it('a guest is sent to sign in and back to the same page', async () => {
    catalog()
    const { user, router } = renderRoute('/tours?country_id=1')
    await user.click(await screen.findByRole('button', { name: 'Додати в обране: Сонячний тур' }))
    expect(router.state.location.pathname).toBe('/login')
    expect(new URLSearchParams(router.state.location.search).get('redirect')).toBe('/tours?country_id=1')
  })

  it('staff see no heart (the API is for clients only)', async () => {
    const manager = makeUser({ id: 7, role: 'manager' })
    signIn(manager)
    const calls = catalog({ 'GET /auth/me': () => [200, manager] })
    renderRoute('/tours')
    expect(await screen.findByRole('heading', { name: 'Сонячний тур' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /обране/ })).not.toBeInTheDocument()
    expect(calls.some((c) => c.url.startsWith('/me/favorites'))).toBe(false)
  })

  it('the tour page has «В обране» under «Забронювати»', async () => {
    signIn(USER)
    const detail = makeTourDetail({ id: 77, title_uk: 'Тур зі сторінкою' })
    mockServer({
      'GET /auth/me': () => [200, USER],
      'GET /tours/77': () => [200, detail],
      'GET /tours/77/reviews': () => [200, { items: [], total: 0, page: 1, page_size: 10 }],
      'GET /me/favorites/ids': () => [200, [77]],
    })
    renderRoute('/tours/77')
    const buttons = await screen.findAllByRole('button', { name: 'Прибрати з обраного: Тур зі сторінкою' })
    expect(buttons[0]).toHaveTextContent('В обраному')
  })
})
