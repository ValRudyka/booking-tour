import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { API_URL, ApiError } from '../../api/client'
import type { ReviewPage, TourDetail } from '../../api/types'
import { makeReview, makeTourDetail, mockApi, page, reviewPage } from '../../test/fixtures'
import { renderRoute, searchOf } from '../../test/render'

function serve(tour: TourDetail, reviews: (params: Record<string, unknown>) => ReviewPage) {
  return mockApi(() => page([]), {
    [`/tours/${tour.id}`]: () => tour,
    [`/tours/${tour.id}/reviews`]: reviews,
  })
}

const reviewCalls = (spy: ReturnType<typeof mockApi>, tourId: number) =>
  spy.mock.calls.filter(([url]) => url === `/tours/${tourId}/reviews`)

describe('Reviews tab', () => {
  it('loads no reviews until the tab is opened, then loads them', async () => {
    const tour = makeTourDetail({ reviews_count: 1 })
    const spy = serve(tour, () => reviewPage([makeReview()]))
    const { user, router } = renderRoute(`/tours/${tour.id}`)
    await screen.findByRole('heading', { level: 1, name: tour.title_uk })
    expect(reviewCalls(spy, tour.id)).toHaveLength(0)

    await user.click(screen.getByRole('tab', { name: 'Відгуки (1)' }))
    expect(await screen.findByRole('heading', { name: 'Олена К.' })).toBeInTheDocument()
    expect(reviewCalls(spy, tour.id)).toHaveLength(1)
    expect(searchOf(router).get('tab')).toBe('reviews')
  })

  it('?tab=reviews opens the reviews: author, trip month, ratings, texts and photos', async () => {
    const tour = makeTourDetail({ reviews_count: 2, service_rating_avg: '4.50' })
    serve(tour, () => reviewPage([
      makeReview({ author: 'Олена К.', trip_month: '2026-10', hotel_rating: 5, service_rating: 4,
        positive: 'Чудовий готель.', negative: 'Слабкий Wi-Fi.',
        photos: [{ id: 7, url: '/api/reviews/3/photos/7' }] }),
      makeReview({ author: 'Анонімний мандрівник', trip_month: '2026-09' }),
    ]))
    renderRoute(`/tours/${tour.id}?tab=reviews`)

    const first = (await screen.findByRole('heading', { name: 'Олена К.' })).closest('article') as HTMLElement
    expect(within(first).getByText('Поїздка: жовтень 2026')).toBeInTheDocument()
    expect(within(first).getByRole('img', { name: 'Готель: 5 з 5' })).toBeInTheDocument()
    expect(within(first).getByRole('img', { name: 'Сервіс: 4 з 5' })).toBeInTheDocument()
    expect(within(first).getByText('Чудовий готель.')).toBeInTheDocument()
    expect(within(first).getByText('Слабкий Wi-Fi.')).toBeInTheDocument()
    expect(within(first).getByRole('img', { name: 'Фото до відгуку: Олена К., 1' }))
      .toHaveAttribute('src', `${API_URL}/api/reviews/3/photos/7`)
    expect(screen.getByRole('heading', { name: 'Анонімний мандрівник' })).toBeInTheDocument()
    // Summary: the hotel's rating and this tour's service rating and count.
    expect(screen.getByText('4,6 з 5')).toBeInTheDocument()
    expect(screen.getByText('4,5 з 5')).toBeInTheDocument()
    expect(screen.getByText('2 відгуки')).toBeInTheDocument()
  })

  it('shows the empty state', async () => {
    const tour = makeTourDetail({ reviews_count: 0 })
    serve(tour, () => reviewPage([]))
    renderRoute(`/tours/${tour.id}?tab=reviews`)
    expect(await screen.findByText('Ще немає відгуків. Відгук можуть залишити туристи після завершення поїздки.'))
      .toBeInTheDocument()
  })

  it('pages through reviews on the server', async () => {
    const tour = makeTourDetail({ reviews_count: 12 })
    const spy = serve(tour, (params) => reviewPage(
      [makeReview({ author: params.page === 2 ? 'Друга сторінка' : 'Перша сторінка' })], 12, params.page as number))
    const { user, router } = renderRoute(`/tours/${tour.id}?tab=reviews`)
    await screen.findByRole('heading', { name: 'Перша сторінка' })
    await user.click(screen.getByRole('button', { name: '2' }))
    expect(await screen.findByRole('heading', { name: 'Друга сторінка' })).toBeInTheDocument()
    expect(searchOf(router).get('reviews_page')).toBe('2')
    expect(reviewCalls(spy, tour.id).at(-1)?.[1]).toMatchObject({ params: { page: 2, page_size: 10 } })
  })

  it('a reviews error stays inside the tab; the rest of the page works', async () => {
    const tour = makeTourDetail({ reviews_count: 3, price_from_uah: '32000.00' })
    serve(tour, () => { throw new ApiError('server', 500, 'На сервері сталася помилка.') })
    renderRoute(`/tours/${tour.id}?tab=reviews`)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Не вдалося завантажити відгуки')
    expect(screen.getByRole('heading', { level: 1, name: tour.title_uk })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Забронювати' })[0]).toBeEnabled()
  })

  it('the header link «N відгуків про тур» opens the reviews tab', async () => {
    const tour = makeTourDetail({ reviews_count: 3 })
    serve(tour, () => reviewPage([makeReview()]))
    const { user, router } = renderRoute(`/tours/${tour.id}`)
    await screen.findByRole('heading', { level: 1, name: tour.title_uk })
    expect(screen.getByText('Рейтинг готелю 4,6 з 5')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '3 відгуки про тур' }))
    await waitFor(() => expect(searchOf(router).get('tab')).toBe('reviews'))
    expect(await screen.findByRole('heading', { name: 'Олена К.' })).toBeInTheDocument()
  })

  it('has no header link when the tour has no reviews', async () => {
    const tour = makeTourDetail({ reviews_count: 0 })
    serve(tour, () => reviewPage([]))
    renderRoute(`/tours/${tour.id}`)
    await screen.findByRole('heading', { level: 1, name: tour.title_uk })
    expect(screen.queryByRole('button', { name: /відгук/ })).not.toBeInTheDocument()
  })
})
