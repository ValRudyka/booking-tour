import { configure, screen, waitFor, within } from '@testing-library/react'
import { beforeAll, describe, expect, it } from 'vitest'
import type { ManagerTourRow } from '../../../api/types'
import { mockServer, RESORTS, signIn, type FakeRequest } from '../../../test/fixtures'
import {
  DRAFT_ACTIONS, HOTELS, makeManagerTour, makeTourRow, MANAGER, TOUR_RULES, tourAllowed, tourPage, tourRefused,
} from '../../../test/officeFixtures'
import { renderRoute, searchOf } from '../../../test/render'

type Handler = (request: FakeRequest) => [number, unknown]

function backend(rows: ManagerTourRow[] = [makeTourRow()], extra: Record<string, Handler> = {}) {
  signIn(MANAGER)
  return mockServer({
    'GET /auth/me': () => [200, MANAGER],
    'GET /manager/tours': () => [200, tourPage(rows)],
    'GET /reference/resorts': (r) => [200, RESORTS.filter((x) => x.country_id === r.params.country_id)],
    'GET /reference/hotels': (r) => [200, HOTELS.filter((x) => x.resort_id === r.params.resort_id)],
    'GET /manager/tours/rules': () => [200, TOUR_RULES],
    ...extra,
  })
}
const listParams = (calls: FakeRequest[]) => calls.filter((c) => c.method === 'GET' && c.url === '/manager/tours').at(-1)?.params

// Lazy office pages: load their code once, and give the first antd Table mount time (spec 09 tests).
configure({ asyncUtilTimeout: 4000 })
beforeAll(async () => {
  await Promise.all([import('../../../layouts/OfficeLayout'), import('./OfficeToursPage'), import('./TourEditorPage')])
})

async function rowOf(title: string) {
  return (await screen.findByRole('link', { name: title })).closest('tr') as HTMLElement
}

describe('/office/tours (spec 10 §1)', () => {
  it('shows the columns and only the actions the API lists', async () => {
    backend()
    renderRoute('/office/tours')
    const row = await rowOf('Coral Bay, Хургада')
    expect(within(row).getByText('Єгипет')).toBeInTheDocument()
    expect(within(row).getByText('Coral Bay Resort')).toBeInTheDocument()
    expect(within(row).getByText('01.06.2099')).toBeInTheDocument()
    expect(within(row).getByText('від 850,00 EUR')).toBeInTheDocument()
    expect(within(row).getByText('16 / 20')).toBeInTheDocument()
    expect(within(row).getByText('Опублікований')).toBeInTheDocument()
    expect(within(row).getByRole('button', { name: 'Зняти з публікації: Coral Bay, Хургада' })).toBeEnabled()
    expect(within(row).queryByRole('button', { name: /^Опублікувати/ })).not.toBeInTheDocument()
    // edit refused for an active tour: the editor opens read-only
    expect(within(row).getByRole('button', { name: 'Переглянути: Coral Bay, Хургада' })).toBeInTheDocument()
    const site = within(row).getByRole('link', { name: /На сайті/ })
    expect(site).toHaveAttribute('href', '/tours/7')
    expect(site).toHaveAttribute('target', '_blank')
  })

  it('shows a refused action disabled with the server reason', async () => {
    const reason = '1 бронювань частково оплачено переказом — спершу фінансовий контролер має завершити оплату або повернути кошти'
    backend([makeTourRow({ tour_actions: [tourAllowed('unpublish'), tourRefused('archive', reason), tourAllowed('copy')] })])
    renderRoute('/office/tours')
    const row = await rowOf('Coral Bay, Хургада')
    const archive = within(row).getByRole('button', { name: 'В архів: Coral Bay, Хургада' })
    expect(archive).toBeDisabled()
    expect(archive).toHaveAccessibleDescription(reason)
  })

  it('sends the filters to the API and keeps them in the URL; the resort list follows the country', async () => {
    const calls = backend()
    const { user, router } = renderRoute('/office/tours')
    await rowOf('Coral Bay, Хургада')
    await user.type(screen.getByRole('textbox', { name: 'Назва' }), 'Хург')
    await user.click(screen.getByRole('combobox', { name: 'Країна' }))
    await user.click(await screen.findByTitle('Єгипет'))
    await user.click(screen.getByRole('combobox', { name: 'Курорт' }))
    await user.click(await screen.findByTitle('Хургада'))
    await user.click(screen.getByRole('button', { name: /Знайти/ }))
    await waitFor(() => expect(listParams(calls)).toEqual({ sort: 'updated_desc', page: 1, page_size: 20, q: 'Хург', country_id: 1, resort_id: 10 }))
    expect(searchOf(router).get('country_id')).toBe('1')
    expect(searchOf(router).get('resort_id')).toBe('10')
  })

  it('asks before archiving and names the bookings that will be cancelled', async () => {
    const calls = backend([makeTourRow({ archive_cancels: 3 })], {
      'POST /manager/tours/7/archive': () => [200, makeManagerTour({ status: 'archived', tour_actions: [tourAllowed('restore'), tourAllowed('copy')] })],
    })
    const { user } = renderRoute('/office/tours')
    const row = await rowOf('Coral Bay, Хургада')
    await user.click(within(row).getByRole('button', { name: 'В архів: Coral Bay, Хургада' }))
    expect(await screen.findByText(/3 неоплачені бронювання буде скасовано/)).toBeInTheDocument()
    expect(calls.some((c) => c.url.endsWith('/archive'))).toBe(false)     // nothing sent before the answer
    await user.click(screen.getByRole('button', { name: 'В архів' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url === '/manager/tours/7/archive')).toBe(true))
  })

  it('names the active bookings that stay payable when unpublishing', async () => {
    backend([makeTourRow({ active_bookings: 2 })])
    const { user } = renderRoute('/office/tours')
    const row = await rowOf('Coral Bay, Хургада')
    await user.click(within(row).getByRole('button', { name: 'Зняти з публікації: Coral Bay, Хургада' }))
    expect(await screen.findByText(/2 активні бронювання залишаться: клієнти зможуть оплатити їх/)).toBeInTheDocument()
  })

  it('copies with new dates and opens the new draft', async () => {
    const copy = makeManagerTour({ id: 8, title_uk: 'Копія — Coral Bay, Хургада', departure_from: '2099-09-01', departure_to: '2099-09-10', tour_actions: DRAFT_ACTIONS })
    const calls = backend([makeTourRow()], {
      'POST /manager/tours/7/copy': () => [201, copy],
      'GET /manager/tours/8': () => [200, copy],
    })
    const { user, router } = renderRoute('/office/tours')
    const row = await rowOf('Coral Bay, Хургада')
    await user.click(within(row).getByRole('button', { name: 'Копіювати: Coral Bay, Хургада' }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Створити копію' }))
    expect(await within(dialog).findByText('Оберіть дати заїздів')).toBeInTheDocument()   // no dates: nothing sent
    const [from, to] = within(dialog).getAllByRole('textbox')
    await user.type(from, '01.09.2099')
    await user.type(to, '10.09.2099{Enter}')
    await user.click(within(dialog).getByRole('button', { name: 'Створити копію' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/office/tours/8/edit'))
    const sent = calls.find((c) => c.method === 'POST' && c.url === '/manager/tours/7/copy')
    expect(sent?.body).toEqual({ departure_from: '2099-09-01', departure_to: '2099-09-10' })
    expect(await screen.findByRole('heading', { name: 'Копія — Coral Bay, Хургада' })).toBeInTheDocument()
    expect(screen.getAllByText('Чернетка').length).toBeGreaterThan(0)
  })
})
