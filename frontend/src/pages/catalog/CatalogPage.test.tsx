import { screen, waitFor, within } from '@testing-library/react'
import type { UserEvent } from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'
import { ApiError } from '../../api/client'
import { lastToursParams, makeTour, mockApi, page } from '../../test/fixtures'
import { renderRoute, searchOf } from '../../test/render'
import { setViewportWidth } from '../../test/setup'

async function chooseOption(user: UserEvent, field: string, option: string) {
  await user.click(screen.getByRole('combobox', { name: field }))
  await user.click(await screen.findByTitle(option))
}

const threeTours = () => page([makeTour(), makeTour(), makeTour()])

describe('CatalogPage', () => {
  afterEach(() => setViewportWidth(1440))

  it('shows the tours from the API with the found count', async () => {
    const spy = mockApi(threeTours)
    renderRoute('/tours')
    expect(await screen.findByText('Знайдено 3 тури')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: /Coral Bay Resort, Хургада/ })).toHaveLength(3)
    expect(lastToursParams(spy)).toEqual({ sort: 'date_asc', page: 1, page_size: 12 })
  })

  it('shows six static skeleton cards while loading', () => {
    mockApi(() => new Promise(() => {}))
    renderRoute('/tours')
    expect(screen.getAllByTestId('tour-card-skeleton')).toHaveLength(6)
    expect(document.querySelector('.ant-skeleton-active')).toBeNull()
  })

  it('reads the filters from the URL and sends them to the API', async () => {
    const spy = mockApi(threeTours)
    renderRoute('/tours?country_id=1&stars=4&stars=5&page=2&sort=price_desc')
    await screen.findByText('Знайдено 3 тури')
    expect(lastToursParams(spy)).toEqual({
      country_id: 1, stars: [4, 5], page: 2, page_size: 12, sort: 'price_desc',
    })
    expect(screen.getByRole('checkbox', { name: '4 зірки' })).toBeChecked()
  })

  it('writes a changed filter to the URL and goes back to page 1', async () => {
    const spy = mockApi(() => page([makeTour()], 30))
    const { router, user } = renderRoute('/tours?page=2&resort_id=10&country_id=1')
    await screen.findByText('Знайдено 30 турів')

    await chooseOption(user, 'Країна', 'Туреччина')
    await waitFor(() => expect(searchOf(router).get('country_id')).toBe('2'))
    expect(searchOf(router).has('page')).toBe(false)
    expect(searchOf(router).has('resort_id')).toBe(false) // the resort belonged to the old country
    await waitFor(() => expect(lastToursParams(spy)).toMatchObject({ country_id: 2, page: 1 }))
  })

  it('keeps the chosen resort when a typed filter is applied after it', async () => {
    mockApi(threeTours)
    const { router, user } = renderRoute('/tours')
    await screen.findByText('Знайдено 3 тури')

    await chooseOption(user, 'Країна', 'Єгипет')
    await chooseOption(user, 'Курорт', 'Хургада')
    await waitFor(() => expect(searchOf(router).get('resort_id')).toBe('10'))
    await user.type(screen.getByRole('spinbutton', { name: 'Ночей від' }), '7')
    await waitFor(() => expect(searchOf(router).get('nights_min')).toBe('7'), { timeout: 2000 })
    expect(searchOf(router).get('country_id')).toBe('1')
    expect(searchOf(router).get('resort_id')).toBe('10')
  })

  it('applies star checkboxes at once and Back restores the previous search', async () => {
    mockApi(threeTours)
    const { router, user } = renderRoute('/tours?stars=4')
    await screen.findByText('Знайдено 3 тури')

    await user.click(screen.getByRole('checkbox', { name: '5 зірок' }))
    expect(searchOf(router).getAll('stars')).toEqual(['4', '5'])

    await router.navigate(-1)
    await waitFor(() => expect(searchOf(router).getAll('stars')).toEqual(['4']))
    await waitFor(() => expect(screen.getByRole('checkbox', { name: '5 зірок' })).not.toBeChecked())
  })

  it('filters by meal plan through the URL', async () => {
    const spy = mockApi(threeTours)
    const { router, user } = renderRoute('/tours?page=2&meal_plan=uai')
    await screen.findByText('Знайдено 3 тури')
    expect(screen.getByRole('group', { name: 'Харчування' })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Ультра все включено' })).toBeChecked()

    await user.click(screen.getByRole('checkbox', { name: 'Все включено' }))
    expect(searchOf(router).getAll('meal_plan')).toEqual(['ai', 'uai'])   // fixed order, light to full
    expect(searchOf(router).has('page')).toBe(false)
    await waitFor(() => expect(lastToursParams(spy)).toMatchObject({ meal_plan: ['ai', 'uai'], page: 1 }))
  })

  it('sorts by title (А–Я)', async () => {
    const spy = mockApi(threeTours)
    const { router, user } = renderRoute('/tours')
    await screen.findByText('Знайдено 3 тури')
    await chooseOption(user, 'Сортування', 'За назвою (А–Я)')
    await waitFor(() => expect(searchOf(router).get('sort')).toBe('title_asc'))
    await waitFor(() => expect(lastToursParams(spy)).toMatchObject({ sort: 'title_asc' }))
  })

  it('searches by name after a short pause in typing', async () => {
    const spy = mockApi(threeTours)
    const { router, user } = renderRoute('/tours')
    await screen.findByText('Знайдено 3 тури')

    await user.type(screen.getByRole('searchbox', { name: 'Пошук за назвою' }), 'Coral')
    expect(searchOf(router).has('q')).toBe(false) // not on every keystroke
    await waitFor(() => expect(searchOf(router).get('q')).toBe('Coral'), { timeout: 2000 })
    await waitFor(() => expect(lastToursParams(spy)).toMatchObject({ q: 'Coral' }))
  })

  it('changes the sort and resets the page', async () => {
    mockApi(threeTours)
    const { router, user } = renderRoute('/tours?page=3')
    await screen.findByText('Знайдено 3 тури')
    await chooseOption(user, 'Сортування', 'Ціна: від дешевших')
    await waitFor(() => expect(searchOf(router).get('sort')).toBe('price_asc'))
    expect(searchOf(router).has('page')).toBe(false)
  })

  it('pages through the results on the server, 12 per page', async () => {
    const spy = mockApi((params) => page([makeTour()], 30, params.page as number))
    const { router, user } = renderRoute('/tours')
    await screen.findByText('Знайдено 30 турів')
    await user.click(screen.getByRole('button', { name: '2' }))
    await waitFor(() => expect(searchOf(router).get('page')).toBe('2'))
    await waitFor(() => expect(lastToursParams(spy)).toMatchObject({ page: 2, page_size: 12 }))
  })

  it('shows the empty state with a reset button that clears the URL', async () => {
    mockApi(() => page([]))
    const { router, user } = renderRoute('/tours?country_id=2&stars=3')
    const message = await screen.findByText('За вашими фільтрами турів не знайдено')
    const empty = message.closest('.ant-empty') as HTMLElement
    await user.click(within(empty).getByRole('button', { name: 'Скинути фільтри' }))
    await waitFor(() => expect(router.state.location.search).toBe(''))
  })

  it('shows an error with a retry button', async () => {
    let calls = 0
    mockApi(() => {
      calls += 1
      if (calls === 1) throw new ApiError('network', null, "Не вдалося з'єднатися з сервером.")
      return threeTours()
    })
    const { user } = renderRoute('/tours')
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Не вдалося завантажити тури')
    expect(alert).toHaveTextContent("Не вдалося з'єднатися з сервером.")

    await user.click(within(alert).getByRole('button', { name: 'Спробувати ще раз' }))
    expect(await screen.findByText('Знайдено 3 тури')).toBeInTheDocument()
  })

  it('explains maintenance mode instead of an error', async () => {
    mockApi(() => {
      throw new ApiError('maintenance', 503, 'Тривають технічні роботи. Спробуйте пізніше.')
    })
    renderRoute('/tours')
    expect(await screen.findByText('Технічні роботи')).toBeInTheDocument()
    expect(screen.getByText('Тривають технічні роботи. Спробуйте пізніше.')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('every filter field has a visible label', async () => {
    mockApi(threeTours)
    renderRoute('/tours')
    await screen.findByText('Знайдено 3 тури')
    for (const name of ['Пошук за назвою', 'Країна', 'Курорт', 'Місто вильоту', 'Транспорт', 'Сортування']) {
      expect(screen.getByLabelText(name)).toBeInTheDocument()
    }
    expect(screen.getByLabelText('Ночей від')).toBeInTheDocument()
    expect(screen.getByLabelText('Ціна до')).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Зірковість готелю' })).toBeInTheDocument()
  })

  it('on mobile edits filters in a Drawer and applies them with one button', async () => {
    setViewportWidth(375)
    mockApi(threeTours)
    const { router, user } = renderRoute('/tours')
    await screen.findByText('Знайдено 3 тури')

    await user.click(screen.getByRole('button', { name: 'Фільтри' }))
    const drawer = await screen.findByRole('dialog')
    await user.click(within(drawer).getByRole('checkbox', { name: '5 зірок' }))
    expect(searchOf(router).has('stars')).toBe(false) // not applied yet

    await user.click(within(drawer).getByRole('button', { name: 'Застосувати' }))
    expect(searchOf(router).getAll('stars')).toEqual(['5'])
    expect(await screen.findByRole('button', { name: 'Фільтри (1)' })).toBeInTheDocument()
  })
})
