import { configure, screen, waitFor, within } from '@testing-library/react'
import { beforeAll, describe, expect, it } from 'vitest'
import type { ManagerTour } from '../../../api/types'
import { mockServer, RESORTS, signIn, type FakeRequest } from '../../../test/fixtures'
import {
  ACTIVE_ACTIONS, HOTELS, makeManagerTour, MANAGER, TOUR_RULES, tourPage,
} from '../../../test/officeFixtures'
import { renderRoute } from '../../../test/render'

type Handler = (request: FakeRequest) => [number, unknown]

function backend(tour: ManagerTour | null = makeManagerTour(), extra: Record<string, Handler> = {}) {
  signIn(MANAGER)
  return mockServer({
    'GET /auth/me': () => [200, MANAGER],
    'GET /manager/tours': () => [200, tourPage([])],
    'GET /manager/tours/rules': () => [200, TOUR_RULES],
    'GET /reference/resorts': (r) => [200, RESORTS.filter((x) => x.country_id === r.params.country_id)],
    'GET /reference/hotels': (r) => [200, HOTELS.filter((x) => x.resort_id === r.params.resort_id)],
    ...(tour ? { [`GET /manager/tours/${tour.id}`]: () => [200, tour] as [number, unknown] } : {}),
    ...extra,
  })
}
const sent = (calls: FakeRequest[], method: string, url: string) => calls.filter((c) => c.method === method && c.url === url)

configure({ asyncUtilTimeout: 4000 })
beforeAll(async () => {
  await Promise.all([import('../../../layouts/OfficeLayout'), import('./TourEditorPage'), import('./OfficeToursPage')])
})

describe('tour editor (spec 10 §2)', () => {
  it('resort depends on the country, hotel on the resort; changing the country clears both', async () => {
    backend(null)
    const { user } = renderRoute('/office/tours/new')
    const country = await screen.findByRole('combobox', { name: 'Країна' })
    expect(screen.getByRole('combobox', { name: 'Курорт' })).toBeDisabled()
    expect(screen.getByRole('combobox', { name: 'Готель' })).toBeDisabled()
    await user.click(country)
    await user.click(await screen.findByTitle('Єгипет'))
    await user.click(screen.getByRole('combobox', { name: 'Курорт' }))
    await user.click(await screen.findByTitle('Хургада'))
    await user.click(screen.getByRole('combobox', { name: 'Готель' }))
    expect(await screen.findByTitle('Sunrise Garden ****')).toBeInTheDocument()
    expect(screen.queryByTitle(/Antalya Palace/)).not.toBeInTheDocument()   // another resort's hotel
    await user.click(screen.getByTitle('Coral Bay Resort *****'))
    // The title placeholder shows the automatic «Готель, Курорт».
    expect(screen.getByRole('textbox', { name: 'Назва туру українською' })).toHaveAttribute('placeholder', 'Coral Bay Resort, Хургада')

    await user.click(screen.getByRole('combobox', { name: 'Країна' }))
    await user.click(await screen.findByTitle('Туреччина'))
    const form = screen.getByRole('form', { name: 'Форма туру' })
    await waitFor(() => expect(within(form).queryByTitle('Хургада')).not.toBeInTheDocument())
    expect(within(form).queryByTitle(/Coral Bay Resort/)).not.toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Готель' })).toBeDisabled()
  })

  it('renumbers program days when adding, removing and moving them', async () => {
    const tour = makeManagerTour()
    const calls = backend(tour, { [`PATCH /manager/tours/${tour.id}`]: () => [200, tour] })
    const { user } = renderRoute('/office/tours/7/edit?step=program')
    expect(await screen.findByRole('heading', { name: 'День 2' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Додати день' }))
    await user.type(screen.getByRole('textbox', { name: 'Маршрут дня 3' }), 'Виліт')
    await user.click(screen.getByRole('button', { name: 'Перемістити день 3 вище' }))
    await user.click(screen.getByRole('button', { name: 'Видалити день 1' }))
    expect(screen.queryByRole('heading', { name: 'День 3' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Зберегти' }))
    await waitFor(() => expect(sent(calls, 'PATCH', '/manager/tours/7')).toHaveLength(1))
    expect((sent(calls, 'PATCH', '/manager/tours/7')[0].body as { program_days: unknown }).program_days).toEqual([
      { day_number: 1, description: 'Виліт' }, { day_number: 2, description: 'Пляж' }])
  })

  it('does not accept a past date, price 0 or 0 seats', async () => {
    const calls = backend(null, { 'POST /manager/tours': () => [201, makeManagerTour()] })
    const { user } = renderRoute('/office/tours/new?step=dates')
    const [from, to] = await screen.findAllByPlaceholderText(/^(Від|До)$/)
    await user.type(from, '01.01.2020')
    await user.type(to, '05.01.2020{Enter}')
    const price = screen.getByRole('spinbutton', { name: 'Ціна за дорослого' })
    await user.type(price, '0')
    await user.type(screen.getByRole('spinbutton', { name: 'Жорсткий блок місць' }), '0')
    await user.click(screen.getByRole('button', { name: 'Зберегти чернетку й додати фото' }))
    expect(await screen.findByText(/Оберіть дати заїздів|Дата заїзду не може бути в минулому/)).toBeInTheDocument()
    expect(screen.getByText('Базова вартість має бути більшою за 0')).toBeInTheDocument()
    expect(screen.getByText('Жорсткий блок місць — не менше 1')).toBeInTheDocument()
    expect(sent(calls, 'POST', '/manager/tours')).toHaveLength(0)
  })

  it('«Зберегти як чернетку» saves only; «Зберегти й опублікувати» saves and publishes', async () => {
    const tour = makeManagerTour()
    const published = makeManagerTour({ status: 'active', tour_actions: ACTIVE_ACTIONS, for_sale: true })
    const calls = backend(tour, {
      'PATCH /manager/tours/7': () => [200, tour],
      'POST /manager/tours/7/publish': () => [200, published],
    })
    const { user } = renderRoute('/office/tours/7/edit?step=summary')
    await user.click(await screen.findByRole('button', { name: 'Зберегти як чернетку' }))
    await waitFor(() => expect(sent(calls, 'PATCH', '/manager/tours/7')).toHaveLength(1))
    expect(sent(calls, 'POST', '/manager/tours/7/publish')).toHaveLength(0)

    await user.click(screen.getByRole('button', { name: 'Зберегти й опублікувати' }))
    await waitFor(() => expect(sent(calls, 'POST', '/manager/tours/7/publish')).toHaveLength(1))
    expect(sent(calls, 'PATCH', '/manager/tours/7')).toHaveLength(2)
    expect(await screen.findByText('Опублікований')).toBeInTheDocument()
  })

  it('shows locked fields disabled with the server reason and the server field errors under their fields', async () => {
    const reason = '2 активних бронювань: дочекайтеся оплати або закінчення утримання'
    const tour = makeManagerTour({
      locked_fields: ['title_uk', 'title_en', 'hotel_id', 'departure_from', 'departure_to', 'nights', 'transport_type',
        'departure_city_id', 'meal_plan'].map((field) => ({ field, reason })),
      seats_held: 4,
    })
    backend(tour, {
      'PATCH /manager/tours/7': () => [422, { detail: [{ loc: ['body', 'seats_total'], msg: 'Квота не може бути меншою за 4: продано 0, утримано в активних бронюваннях 4', type: 'tour_rule' }] }],
    })
    const { user, router } = renderRoute('/office/tours/7/edit')
    const title = await screen.findByRole('textbox', { name: 'Назва туру англійською' })
    expect(title).toBeDisabled()
    expect(screen.getByRole('combobox', { name: 'Готель' })).toBeDisabled()
    expect(screen.getAllByText(reason).length).toBeGreaterThan(3)
    // Prices and the description stay editable.
    expect(screen.getByRole('textbox', { name: 'Детальний опис' })).toBeEnabled()
    await user.type(screen.getByRole('textbox', { name: 'Детальний опис' }), ' і сонце')
    await user.click(screen.getByRole('button', { name: 'Зберегти' }))
    // The server's rule about the quota opens step 3 and stands under the field.
    await waitFor(() => expect(router.state.location.search).toBe('?step=dates'))
    const error = await screen.findByText('Квота не може бути меншою за 4: продано 0, утримано в активних бронюваннях 4')
    await waitFor(() => expect(error.closest('section')).not.toHaveAttribute('hidden'))
    expect(screen.getByRole('spinbutton', { name: 'Тривалість (ночей)' })).toBeDisabled()
    expect(screen.getByRole('spinbutton', { name: 'Ціна за дорослого' })).toBeEnabled()
  })

  it('opens an active tour read-only with the reason and the unpublish button', async () => {
    backend(makeManagerTour({ status: 'active', tour_actions: ACTIVE_ACTIONS, for_sale: true }))
    renderRoute('/office/tours/7/edit')
    expect(await screen.findByText('Редагувати можна лише чернетку — спершу зніміть тур з публікації')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Назва туру англійською' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Зняти з публікації: Coral Bay, Хургада' })).toBeEnabled()
    expect(screen.queryByRole('button', { name: 'Зберегти' })).not.toBeInTheDocument()
  })

  it('asks before leaving with unsaved changes', async () => {
    backend(makeManagerTour())
    const { user, router } = renderRoute('/office/tours/7/edit')
    await user.type(await screen.findByRole('textbox', { name: 'Детальний опис' }), ' нове')
    await user.click(screen.getByRole('link', { name: /До списку турів/ }))
    expect(await screen.findByRole('dialog', { name: 'Вийти без збереження?' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/office/tours/7/edit')
    await user.click(screen.getByRole('button', { name: 'Залишитися' }))
    expect(router.state.location.pathname).toBe('/office/tours/7/edit')
    // Moving between steps is not leaving.
    await user.click(screen.getByRole('button', { name: 'Далі' }))
    await waitFor(() => expect(router.state.location.search).toBe('?step=program'))
    await user.click(screen.getByRole('link', { name: /До списку турів/ }))
    await user.click(await screen.findByRole('button', { name: 'Вийти без збереження' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/office/tours'))
  })
})
