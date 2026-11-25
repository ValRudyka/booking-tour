import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { API_URL, ApiError } from '../../api/client'
import type { TourDetail } from '../../api/types'
import { HOTEL_FACTS, makeTourDetail, mockApi, page } from '../../test/fixtures'
import { renderRoute } from '../../test/render'
import { setViewportWidth } from '../../test/setup'
import { kyivTomorrow } from '../../utils/format'

const plain = (text: string | null) => (text ?? '').replace(/[  ]/g, ' ')

function serve(tour: TourDetail | (() => TourDetail)) {
  const detail = typeof tour === 'function' ? tour : () => tour
  const current = detail()
  return mockApi(() => page([]), { [`/tours/${current.id}`]: () => detail() })
}

async function openTour(tour: TourDetail, query = '') {
  const view = renderRoute(`/tours/${tour.id}${query}`)
  await screen.findByRole('heading', { level: 1, name: tour.title_uk })
  return view
}

describe('TourDetailsPage', () => {
  afterEach(() => setViewportWidth(1440))

  it('shows the title, price per adult, child price and free seats', async () => {
    const tour = makeTourDetail({ price_from_uah: '32000.00', free_seats: 6 })
    serve(tour)
    await openTour(tour)
    expect(document.title).toMatch(new RegExp(`^${tour.title_uk} — `))
    const panel = screen.getByRole('heading', { name: 'Бронювання' }).closest('.booking-panel') as HTMLElement
    expect(plain(within(panel).getByText(/^від/).textContent)).toBe('від 32 000 ₴')
    expect(within(panel).getByText('за дорослого')).toBeInTheDocument()
    expect(plain(within(panel).getByText(/Дитина до 12 років/).textContent)).toBe('Дитина до 12 років: від 16 000 ₴')
    expect(within(panel).getByText('6')).toBeInTheDocument()
  })

  it('shows the hotel rating and the meal plan in the header and the booking panel', async () => {
    const tour = makeTourDetail({ meal_plan: 'ai' })
    serve(tour)
    await openTour(tour)
    expect(screen.getByText('Рейтинг готелю 4,6 з 5')).toBeInTheDocument()
    // Same label as the catalog filter and card: one dictionary (i18n/labels.ts).
    expect(screen.getAllByText('Все включено')).toHaveLength(2)
  })

  it('shows no meal plan when the tour has none', async () => {
    const tour = makeTourDetail({ meal_plan: null })
    serve(tour)
    await openTour(tour)
    expect(screen.queryByText('Харчування')).not.toBeInTheDocument()
  })

  it('leads the breadcrumb back to the catalog filters', async () => {
    const tour = makeTourDetail()
    serve(tour)
    await openTour(tour)
    const crumbs = screen.getByRole('navigation', { name: 'Навігація' })
    expect(within(crumbs).getByRole('link', { name: 'Каталог' })).toHaveAttribute('href', '/tours')
    expect(within(crumbs).getByRole('link', { name: 'Єгипет' })).toHaveAttribute('href', '/tours?country_id=1')
    expect(within(crumbs).getByRole('link', { name: 'Хургада' }))
      .toHaveAttribute('href', '/tours?country_id=1&resort_id=10')
  })

  it('keeps the catalog filters: card -> tour -> «Каталог» and Back', async () => {
    const tour = makeTourDetail()
    mockApi(() => page([tour]), { [`/tours/${tour.id}`]: () => tour })
    const { router, user } = renderRoute('/tours?country_id=1&stars=5&page=1')
    await user.click(await screen.findByRole('link', { name: new RegExp(tour.title_uk) }))
    await screen.findByRole('heading', { level: 1, name: tour.title_uk })
    expect(screen.getByRole('link', { name: 'Каталог' })).toHaveAttribute('href', '/tours?country_id=1&stars=5&page=1')
    await router.navigate(-1)
    await waitFor(() => expect(router.state.location.search).toBe('?country_id=1&stars=5&page=1'))
  })

  it('shows a placeholder without photos and opens photos from buttons', async () => {
    const without = makeTourDetail({ images: [] })
    serve(without)
    const first = await openTour(without)
    expect(screen.getByRole('img', { name: 'Фото відсутнє' })).toBeInTheDocument()
    first.unmount()

    const withPhotos = makeTourDetail({ images: [
      { id: 1, sort_order: 0, url: '/uploads/tours/1/a.png' },
      { id: 2, sort_order: 1, url: '/uploads/tours/1/b.png' },
    ] })
    serve(withPhotos)
    await openTour(withPhotos)
    const main = screen.getByRole('img', { name: `${withPhotos.title_uk} — фото 1` })
    expect(main).toHaveAttribute('src', `${API_URL}/uploads/tours/1/a.png`)
    expect(screen.getByRole('button', { name: 'Відкрити фото 2 з 2' })).toBeInTheDocument()
  })

  it('opens the tab named in the URL and replaces the history entry on a tab change', async () => {
    const tour = makeTourDetail()
    serve(tour)
    const { router, user } = await openTour(tour, '?tab=program')
    expect(screen.getByText('День 2')).toBeInTheDocument()
    expect(screen.getByText('Відпочинок на пляжі.')).toBeInTheDocument()

    const historyLength = window.history.length
    await user.click(screen.getByRole('tab', { name: 'Готель' }))
    await waitFor(() => expect(router.state.location.search).toBe('?tab=hotel'))
    expect(router.state.historyAction).toBe('REPLACE')
    expect(window.history.length).toBe(historyLength)
  })

  it('lists what is included and not included, with icons, and hides an empty list', async () => {
    const tour = makeTourDetail({ excluded: [] })
    serve(tour)
    await openTour(tour)
    const included = screen.getByRole('heading', { name: 'Що включено' }).closest('section') as HTMLElement
    expect(within(included).getAllByRole('listitem').map((li) => li.textContent?.trim()))
      .toEqual(['Авіапереліт', 'Проживання'])
    expect(included.querySelector('.anticon-check')).not.toBeNull()
    expect(screen.queryByRole('heading', { name: 'Що не включено' })).not.toBeInTheDocument()
  })

  it('shows insurance under "not included" exactly as the API gives it', async () => {
    const tour = makeTourDetail()
    serve(tour)
    await openTour(tour)
    const excluded = screen.getByRole('heading', { name: 'Що не включено' }).closest('section') as HTMLElement
    expect(within(excluded).getByText('Медичне страхування — обирається під час бронювання')).toBeInTheDocument()
    expect(excluded.querySelector('.anticon-close')).not.toBeNull()
  })

  it('hotel tab: a table of the filled facts only, the description below', async () => {
    const tour = makeTourDetail({}, HOTEL_FACTS)
    serve(tour)
    await openTour(tour, '?tab=hotel')
    const table = document.querySelector('.tour-hotel-facts') as HTMLElement
    for (const [label, value] of [['Лінія пляжу', 'Перша лінія'], ['До пляжу', 'На пляжі'],
      ['До аеропорту', '12 км'], ['Заїзд', 'з 14:00'], ['Виїзд', 'до 12:00']]) {
      expect(within(table).getByText(label)).toBeInTheDocument()
      expect(within(table).getByText(value)).toBeInTheDocument()
    }
    expect(within(table).getByText('SPA-центр')).toBeInTheDocument()
    expect(within(table).getByText('Сімейний номер')).toBeInTheDocument()
    expect(screen.getByText('Готель на першій лінії.')).toBeInTheDocument()
  })

  it('hotel tab: no fact rows when the hotel has no facts', async () => {
    const tour = makeTourDetail()
    serve(tour)
    await openTour(tour, '?tab=hotel')
    const table = document.querySelector('.tour-hotel-facts') as HTMLElement
    for (const label of ['Лінія пляжу', 'До пляжу', 'До аеропорту', 'Заїзд', 'Виїзд', 'Зручності', 'Типи номерів']) {
      expect(within(table).queryByText(label)).not.toBeInTheDocument()
    }
    expect(within(table).getByText('Coral Bay Resort')).toBeInTheDocument()
  })

  it('shows the distance to the beach in metres when the hotel is not on it', async () => {
    const tour = makeTourDetail({}, { ...HOTEL_FACTS, distance_to_beach_m: 1200 })
    serve(tour)
    await openTour(tour, '?tab=hotel')
    expect(plain(screen.getByText(/1.200 м/).textContent)).toBe('1 200 м')
  })

  it('books the chosen date through the booking placeholder', async () => {
    const tour = makeTourDetail({ departure_from: '2099-06-01', departure_to: '2099-06-01' })
    serve(tour)
    const { router, user } = await openTour(tour)
    await user.click(screen.getAllByRole('button', { name: 'Забронювати' })[0])
    expect(router.state.location.pathname).toBe(`/booking/${tour.id}`)
    expect(router.state.location.search).toBe('?date=2099-06-01')
  })

  it('offers dates from tomorrow (Kyiv) once the season has begun', async () => {
    const tour = makeTourDetail({ departure_from: '2000-01-01', departure_to: '2099-12-31' })
    serve(tour)
    await openTour(tour)
    const [y, m, d] = kyivTomorrow().split('-')
    expect(screen.getByLabelText('Дата виїзду')).toHaveValue(`${d}.${m}.${y}`)
  })

  it('cannot be booked without seats, and says why', async () => {
    const tour = makeTourDetail({ free_seats: 0 })
    serve(tour)
    await openTour(tour)
    const button = screen.getAllByRole('button', { name: 'Забронювати' })[0]
    expect(button).toBeDisabled()
    expect(button).toHaveAccessibleDescription('Місць немає — бронювання недоступне')
  })

  it('shows 404 for a tour that is not for sale', async () => {
    const spy = mockApi(() => page([]), {
      '/tours/77': () => { throw new ApiError('not_found', 404, 'Тур не знайдено') },
    })
    const { user, router } = renderRoute('/tours/77')
    expect(await screen.findByRole('heading', { level: 1, name: 'Тур не знайдено або він більше не продається' }))
      .toBeInTheDocument()
    expect(spy).toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'До каталогу' }))
    expect(router.state.location.pathname).toBe('/tours')
  })

  it('shows 404 at once for an id that is not a number, without a request', () => {
    const spy = mockApi(() => page([]))
    renderRoute('/tours/abc')
    expect(screen.getByRole('heading', { level: 1, name: 'Тур не знайдено або він більше не продається' }))
      .toBeInTheDocument()
    expect(spy).not.toHaveBeenCalled()
  })

  it('shows an API error with a retry button', async () => {
    let calls = 0
    const tour = makeTourDetail()
    mockApi(() => page([]), { [`/tours/${tour.id}`]: () => {
      calls += 1
      if (calls === 1) throw new ApiError('server', 500, 'На сервері сталася помилка.')
      return tour
    } })
    const { user } = renderRoute(`/tours/${tour.id}`)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Не вдалося завантажити тур')
    await user.click(within(alert).getByRole('button', { name: 'Спробувати ще раз' }))
    expect(await screen.findByRole('heading', { level: 1, name: tour.title_uk })).toBeInTheDocument()
  })

  it('shows the maintenance message', async () => {
    mockApi(() => page([]), { '/tours/5': () => {
      throw new ApiError('maintenance', 503, 'Тривають технічні роботи. Спробуйте пізніше.')
    } })
    renderRoute('/tours/5')
    expect(await screen.findByText('Технічні роботи')).toBeInTheDocument()
  })

  it('on mobile keeps the price and «Забронювати» in a bar at the bottom', async () => {
    setViewportWidth(375)
    const tour = makeTourDetail({ price_from_uah: '32000.00' })
    serve(tour)
    await openTour(tour)
    const bar = screen.getByRole('region', { name: 'Бронювання' })
    expect(plain(within(bar).getByText(/^від/).textContent)).toBe('від 32 000 ₴')
    expect(within(bar).getByRole('button', { name: 'Забронювати' })).toBeEnabled()
  })
})
