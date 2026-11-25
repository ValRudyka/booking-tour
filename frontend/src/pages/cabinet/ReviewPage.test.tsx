import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { MyReview, OrderReview } from '../../api/types'
import { makeOrder, makeUser, mockServer, signIn, type FakeRequest } from '../../test/fixtures'
import { renderRoute } from '../../test/render'

const USER = makeUser()
const ORDER = makeOrder({ status: 'completed', client_actions: ['review', 'download_documents'] })

function state(overrides: Partial<OrderReview> = {}): OrderReview {
  return {
    can_write: true, premoderation: true, max_text: 2000, review: null,
    photos: { max_files: 2, max_file_mb: 5, file_types: ['jpg', 'png'] }, ...overrides,
  }
}

function review(overrides: Partial<MyReview> = {}): MyReview {
  return {
    id: 9, order_id: 42, tour_id: 7, tour_title_uk: ORDER.tour_title_uk, hotel_name: ORDER.hotel_name,
    hotel_rating: 4, service_rating: 5, positive: 'Чудове море', negative: null, photos: [],
    name_display: 'short', author: 'Олена К.', status: 'pending', reject_reason: null, can_resubmit: false,
    submitted_at: '2099-07-01T09:00:00Z', moderated_at: null, created_at: '2099-07-01T09:00:00Z', ...overrides,
  }
}

type Routes = Record<string, (request: FakeRequest) => [number, unknown]>
function backend(reviewState: OrderReview, routes: Routes = {}) {
  signIn(USER)
  return mockServer({
    'GET /auth/me': () => [200, USER],
    'GET /orders/42': () => [200, ORDER],
    'GET /orders/42/review': () => [200, reviewState],
    'GET /orders/42/documents': () => [200, []],
    'GET /orders': () => [200, { items: [], total: 0, page: 1, page_size: 10 }],
    ...routes,
  })
}

const png = (name: string) => new File(['png'], name, { type: 'image/png' })
const posts = (calls: FakeRequest[]) => calls.filter((c) => c.method === 'POST' || c.method === 'PATCH')

afterEach(() => {
  vi.restoreAllMocks()
})

async function rate(user: ReturnType<typeof renderRoute>['user'], group: string, value: number) {
  const radios = within(screen.getByRole('radiogroup', { name: group })).getAllByRole('radio')
  await user.click(radios[value - 1])
}

describe('/cabinet/orders/:id/review', () => {
  it('requires both ratings: errors under the fields, nothing sent', async () => {
    const calls = backend(state())
    const { user } = renderRoute('/cabinet/orders/42/review')
    await user.click(await screen.findByRole('button', { name: 'Опублікувати відгук' }))
    expect(await screen.findAllByText('Поставте оцінку від 1 до 5')).toHaveLength(2)

    await rate(user, 'Оцінка готелю / проживання', 4)
    await user.click(screen.getByRole('button', { name: 'Опублікувати відгук' }))
    expect(await screen.findAllByText('Поставте оцінку від 1 до 5')).toHaveLength(1)
    expect(posts(calls)).toHaveLength(0)
  })

  it('names every star in Ukrainian', async () => {
    backend(state())
    renderRoute('/cabinet/orders/42/review')
    const group = await screen.findByRole('radiogroup', { name: 'Оцінка сервісу компанії' })
    expect(within(group).getAllByRole('radio').map((r) => r.getAttribute('aria-label')))
      .toEqual(['1 з 5', '2 з 5', '3 з 5', '4 з 5', '5 з 5'])
  })

  it('sends the ratings, texts, name choice and photos in one multipart request', async () => {
    let body: FormData | null = null
    let current = state()
    backend(state(), {
      'GET /orders/42/review': () => [200, current],
      'POST /orders/42/review': (request) => {
        body = request.body as FormData
        current = state({ can_write: false, review: review() })
        return [201, review()]
      },
    })
    const { user } = renderRoute('/cabinet/orders/42/review')
    await screen.findByRole('radiogroup', { name: 'Оцінка готелю / проживання' })
    await rate(user, 'Оцінка готелю / проживання', 4)
    await rate(user, 'Оцінка сервісу компанії', 5)
    await user.type(screen.getByLabelText('Позитивні враження (необов\'язково)'), 'Чудове море')
    await user.click(screen.getByRole('radio', { name: 'Анонімно' }))
    await user.upload(document.querySelector('input[type=file]') as HTMLInputElement, png('beach.png'))
    await user.click(screen.getByRole('button', { name: 'Опублікувати відгук' }))

    await waitFor(() => expect(body).not.toBeNull())
    const sent = body as unknown as FormData
    expect([sent.get('hotel_rating'), sent.get('service_rating')]).toEqual(['4', '5'])
    expect(sent.get('positive')).toBe('Чудове море')
    expect(sent.get('name_display')).toBe('anonymous')
    expect((sent.getAll('photos') as File[]).map((f) => f.name)).toEqual(['beach.png'])
    // The review replaces the form, with its moderation status.
    expect(await screen.findByText('На модерації')).toBeInTheDocument()
  })

  it('does not add photos beyond the limit from the API', async () => {
    backend(state())
    const { user } = renderRoute('/cabinet/orders/42/review')
    await screen.findByRole('radiogroup', { name: 'Оцінка готелю / проживання' })
    await user.upload(document.querySelector('input[type=file]') as HTMLInputElement, [png('1.png'), png('2.png'), png('3.png')])
    expect(await screen.findByText('Можна додати не більше 2 файлів')).toBeInTheDocument()
    expect(document.querySelectorAll('.ant-upload-list-item')).toHaveLength(2)
    // At the limit the «Додати фото» button is gone.
    expect(screen.queryByText('Додати фото')).not.toBeInTheDocument()
  })

  it('tells about premoderation, or that the review is published at once', async () => {
    backend(state({ premoderation: false }))
    renderRoute('/cabinet/orders/42/review')
    expect(await screen.findByText('Відгук буде опубліковано на сайті одразу.')).toBeInTheDocument()
  })

  it('shows the existing review and its status instead of the form', async () => {
    backend(state({ can_write: false, review: review({ status: 'published' }) }))
    renderRoute('/cabinet/orders/42/review')
    expect(await screen.findByText('Опубліковано')).toBeInTheDocument()
    expect(screen.getByText('Відгук опубліковано на сторінці туру.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Опублікувати відгук' })).not.toBeInTheDocument()
    expect(screen.getByRole('img', { name: '4 з 5' })).toBeInTheDocument()
  })

  it('loads a private photo with the token', async () => {
    URL.createObjectURL = vi.fn(() => 'blob:photo')
    URL.revokeObjectURL = vi.fn()
    const calls = backend(state({ can_write: false, review: review({ photos: [{ id: 3, url: '/api/reviews/9/photos/3' }] }) }), {
      'GET /reviews/9/photos/3': () => [200, new Blob(['png'], { type: 'image/png' })],
    })
    renderRoute('/cabinet/orders/42/review')
    await waitFor(() => expect(screen.getByRole('img', { name: 'Ваше фото 1' })).toHaveAttribute('src', 'blob:photo'))
    expect(calls.find((c) => c.url === '/reviews/9/photos/3')?.authorization).toBe('Bearer test-token')
  })

  it('a rejected review shows the reason and allows one correction with PATCH', async () => {
    let body: FormData | null = null
    let current = state({
      can_write: false,
      review: review({ status: 'rejected', reject_reason: 'Лайка', can_resubmit: true, photos: [{ id: 3, url: '/api/reviews/9/photos/3' }] }),
    })
    const calls = backend(current, {
      'GET /orders/42/review': () => [200, current],
      'GET /reviews/9/photos/3': () => [200, new Blob(['png'], { type: 'image/png' })],
      'PATCH /me/reviews/9': (request) => {
        body = request.body as FormData
        current = state({ can_write: false, review: review({ status: 'pending' }) })
        return [200, current.review]
      },
    })
    const { user } = renderRoute('/cabinet/orders/42/review')
    expect(await screen.findByText('Причина відхилення: Лайка')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Виправити й подати знову' }))
    expect(screen.getByText(/Повторно подати відгук можна лише один раз/)).toBeInTheDocument()
    // The form starts from the review as it was.
    expect(screen.getByLabelText('Позитивні враження (необов\'язково)')).toHaveValue('Чудове море')
    await user.click(screen.getByRole('radio', { name: 'Замінити фото (поточні буде видалено)' }))
    await user.click(screen.getByRole('button', { name: 'Подати відгук знову' }))

    await waitFor(() => expect(body).not.toBeNull())
    const sent = body as unknown as FormData
    expect([sent.get('hotel_rating'), sent.get('service_rating')]).toEqual(['4', '5'])
    expect(sent.get('clear_photos')).toBe('true')                // replace with nothing = remove them
    expect(posts(calls).map((c) => `${c.method} ${c.url}`)).toEqual(['PATCH /me/reviews/9'])
    expect(await screen.findByText('На модерації')).toBeInTheDocument()
  })

  it('keeps the old photos on a correction unless asked to replace them', async () => {
    let body: FormData | null = null
    backend(state({
      can_write: false,
      review: review({ status: 'rejected', reject_reason: 'Лайка', can_resubmit: true, photos: [{ id: 3, url: '/api/reviews/9/photos/3' }] }),
    }), {
      'GET /reviews/9/photos/3': () => [200, new Blob(['png'], { type: 'image/png' })],
      'PATCH /me/reviews/9': (request) => {
        body = request.body as FormData
        return [200, review({ status: 'pending' })]
      },
    })
    const { user } = renderRoute('/cabinet/orders/42/review')
    await user.click(await screen.findByRole('button', { name: 'Виправити й подати знову' }))
    expect(document.querySelector('input[type=file]')).toBeNull()   // «Залишити поточні фото»
    await user.click(screen.getByRole('button', { name: 'Подати відгук знову' }))
    await waitFor(() => expect(body).not.toBeNull())
    const sent = body as unknown as FormData
    expect(sent.get('clear_photos')).toBeNull()
    expect(sent.getAll('photos')).toHaveLength(0)
  })

  it('a review rejected again cannot be sent once more', async () => {
    backend(state({ can_write: false, review: review({ status: 'rejected', reject_reason: 'Реклама', can_resubmit: false }) }))
    renderRoute('/cabinet/orders/42/review')
    expect(await screen.findByText('Відгук відхилено повторно, тому подати його знову не можна.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Виправити й подати знову' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Подати/ })).not.toBeInTheDocument()
  })

  it('explains when no review can be written yet', async () => {
    backend(state({ can_write: false }))
    renderRoute('/cabinet/orders/42/review')
    expect(await screen.findByRole('heading', { level: 1, name: 'Відгук поки що залишити не можна' })).toBeInTheDocument()
  })
})
