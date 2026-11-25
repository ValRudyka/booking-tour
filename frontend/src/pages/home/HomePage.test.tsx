import { screen, within } from '@testing-library/react'
import type { UserEvent } from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { ApiError } from '../../api/client'
import { makeTour, mockApi, page } from '../../test/fixtures'
import { renderRoute, searchOf } from '../../test/render'

async function chooseOption(user: UserEvent, field: string, option: string) {
  await user.click(screen.getByRole('combobox', { name: field }))
  await user.click(await screen.findByTitle(option))
}

type Params = Record<string, unknown>
const isHot = (params: Params) => params.featured === true
const isCount = (params: Params) => params.page_size === 1

/** GET /tours by block: «Гарячі пропозиції», «Найближчі виїзди», the per-country counts. */
function toursApi({ hot = () => page([]), nearest = () => page([]), count = () => page([], 0) }: {
  hot?: (params: Params) => unknown
  nearest?: (params: Params) => unknown
  count?: (params: Params) => unknown
} = {}) {
  return mockApi((params) => (isHot(params) ? hot(params) : isCount(params) ? count(params) : nearest(params)))
}

function section(name: string) {
  return screen.getByRole('region', { name })
}

describe('HomePage', () => {
  it('replaces the old redirect: / is the home page with the site name as the title', async () => {
    toursApi()
    const { router } = renderRoute('/')
    expect(screen.getByRole('heading', { level: 1, name: 'Знайдіть свій тур на море' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/')
    expect(document.title).toBe('Хвиля')
  })

  it('sends an empty search to the plain catalog', async () => {
    toursApi()
    const { router, user } = renderRoute('/')
    await user.click(screen.getByRole('button', { name: 'Знайти тури' }))
    expect(router.state.location.pathname).toBe('/tours')
    expect(router.state.location.search).toBe('')
  })

  it('sends the search to the catalog with the catalog\'s own parameter names', async () => {
    toursApi()
    const { router, user } = renderRoute('/')
    await chooseOption(user, 'Країна', 'Туреччина')
    await chooseOption(user, 'Місто вильоту', 'Київ')
    await user.type(screen.getByPlaceholderText('Від'), '01.06.2099')
    await user.type(screen.getByPlaceholderText('До'), '15.06.2099{Enter}')
    await user.click(screen.getByRole('button', { name: 'Знайти тури' }))

    expect(router.state.location.pathname).toBe('/tours')
    expect(Object.fromEntries(searchOf(router))).toEqual({
      country_id: '2', departure_city_id: '100', date_from: '2099-06-01', date_to: '2099-06-15',
    })
    // The catalog reads the same filters back from that URL.
    expect(await screen.findByRole('heading', { level: 1, name: 'Каталог турів' })).toBeInTheDocument()
  })

  it('shows the nearest departures with free seats and a link to all tours', async () => {
    const spy = toursApi({ nearest: () => page([makeTour({ title_uk: 'Тиждень у Хургаді' }), makeTour()]) })
    renderRoute('/')
    const block = section('Найближчі виїзди')
    expect(await within(block).findByRole('heading', { level: 3, name: 'Тиждень у Хургаді' })).toBeInTheDocument()
    expect(within(block).getAllByRole('link', { name: /Coral Bay Resort|Тиждень/ })).toHaveLength(2)
    expect(within(block).getByRole('link', { name: /Усі тури/ })).toHaveAttribute('href', '/tours')
    expect(spy).toHaveBeenCalledWith('/tours', {
      params: { has_seats: true, sort: 'date_asc', page: 1, page_size: 4 },
    })
  })

  it('shows «Гарячі пропозиції» only when the manager pinned some tours', async () => {
    toursApi({ hot: () => page([makeTour({ title_uk: 'Гарячий тур', is_featured: true })]) })
    renderRoute('/')
    expect(await within(section('Гарячі пропозиції'))
      .findByRole('heading', { level: 3, name: 'Гарячий тур' })).toBeInTheDocument()
  })

  it('hides «Гарячі пропозиції» when there are none', async () => {
    toursApi({ nearest: () => page([makeTour()]) })
    renderRoute('/')
    await within(section('Найближчі виїзди')).findAllByRole('heading', { level: 3 })
    expect(screen.queryByRole('region', { name: 'Гарячі пропозиції' })).not.toBeInTheDocument()
  })

  it('keeps the other blocks working when one block fails', async () => {
    toursApi({
      hot: () => { throw new ApiError('server', 500, 'На сервері сталася помилка.') },
      nearest: () => page([makeTour({ title_uk: 'Тур, що завантажився' })]),
    })
    renderRoute('/')
    const hot = section('Гарячі пропозиції')
    expect(await within(hot).findByText('Не вдалося завантажити тури')).toBeInTheDocument()
    expect(within(hot).getByRole('button', { name: /Спробувати ще раз/ })).toBeInTheDocument()
    expect(await within(section('Найближчі виїзди'))
      .findByRole('heading', { level: 3, name: 'Тур, що завантажився' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Знайти тури' })).toBeEnabled()
  })

  it('shows the maintenance screen once, not in every block', async () => {
    const maintenance = () => { throw new ApiError('maintenance', 503, 'Тривають технічні роботи. Спробуйте пізніше.') }
    toursApi({ hot: maintenance, nearest: maintenance, count: maintenance })
    renderRoute('/')
    expect(await screen.findByText('Технічні роботи')).toBeInTheDocument()
    expect(screen.getAllByText('Технічні роботи')).toHaveLength(1)
    expect(screen.queryByRole('region', { name: 'Гарячі пропозиції' })).not.toBeInTheDocument()
  })
})
