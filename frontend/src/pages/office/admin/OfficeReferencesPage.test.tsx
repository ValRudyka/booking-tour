import { configure, screen, waitFor, within } from '@testing-library/react'
import { beforeAll, describe, expect, it } from 'vitest'
import { mockServer, signIn, type FakeRequest } from '../../../test/fixtures'
import {
  makeCountry, makeHotelAdmin, makeResort, makeServiceType, makeSettings, refAllowed, refRefused,
} from '../../../test/adminFixtures'
import { ADMIN } from '../../../test/officeFixtures'
import { renderRoute, searchOf } from '../../../test/render'

type Handler = (request: FakeRequest) => [number, unknown]
const TURKEY = makeCountry()
const EGYPT = makeCountry({ id: 2, iso_code: 'EG', name_uk: 'Єгипет', name_en: 'Egypt' })
const OLD = makeCountry({ id: 3, iso_code: 'CY', name_uk: 'Кіпр', name_en: 'Cyprus', is_archived: true,
  admin_actions: [refAllowed('edit'), refAllowed('restore'), refAllowed('delete')] })
const KEMER = makeResort()
const HURGHADA = makeResort({ id: 12, country_id: 2, name_uk: 'Хургада', name_en: 'Hurghada' })

function backend(extra: Record<string, Handler> = {}) {
  signIn(ADMIN)
  return mockServer({
    'GET /auth/me': () => [200, ADMIN],
    'GET /admin/settings': () => [200, makeSettings()],
    'GET /admin/countries': () => [200, [TURKEY, EGYPT, OLD]],
    'GET /admin/resorts': () => [200, [KEMER, HURGHADA]],
    'GET /admin/hotels': () => [200, [makeHotelAdmin()]],
    'GET /admin/insurance-types': () => [200, [makeServiceType()]],
    ...extra,
  })
}

async function dialogTitled(title: string): Promise<HTMLElement> {
  const heading = await screen.findByText(title, { selector: '.ant-modal-title, .ant-drawer-title' })
  return heading.closest('[role="dialog"]') as HTMLElement
}
const rowOf = async (text: string) => (await screen.findByText(text, { selector: 'td' })).closest('tr') as HTMLElement

configure({ asyncUtilTimeout: 4000 })
beforeAll(async () => {
  await Promise.all([import('../../../layouts/OfficeLayout'), import('./OfficeReferencesPage')])
})

describe('/office/references (spec 13 §2)', () => {
  it('hides archived records until «Показати архівні» is on', async () => {
    backend()
    const { user, router } = renderRoute('/office/references')
    expect(await screen.findByRole('heading', { level: 1, name: 'Довідники' })).toBeInTheDocument()
    expect(await rowOf('Туреччина')).toBeInTheDocument()
    expect(screen.queryByText('Кіпр', { selector: 'td' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('switch', { name: 'Показати архівні' }))
    await user.click(screen.getByRole('button', { name: /Знайти/ }))
    const old = await rowOf('Кіпр')
    expect(within(old).getByText('В архіві')).toBeInTheDocument()
    expect(within(old).getByRole('button', { name: 'Відновити' })).toBeEnabled()
    expect(searchOf(router).get('archived')).toBe('true')
  })

  it('archives only after the confirmation that explains the consequences', async () => {
    const calls = backend({ 'POST /admin/countries/2/archive': () => [200, { ...EGYPT, is_archived: true }] })
    const { user } = renderRoute('/office/references')
    await user.click(within(await rowOf('Єгипет')).getByRole('button', { name: 'В архів' }))
    const confirm = await dialogTitled('Перенести «Єгипет» в архів?')
    expect(within(confirm).getByText(/залишиться в наявних турах і замовленнях/)).toBeInTheDocument()
    expect(within(confirm).getByText(/зникнуть її курорти, готелі й міста вильоту/)).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'POST')).toBe(false)
    await user.click(within(confirm).getByRole('button', { name: 'В архів' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url === '/admin/countries/2/archive')).toBe(true))
  })

  it('shows the server reason when archiving is refused (a published tour uses the hotel)', async () => {
    const reason = 'Використовується в 1 опублікованому турі — спершу зніміть його з продажу'
    backend({ 'GET /admin/hotels': () => [200, [makeHotelAdmin({ admin_actions: [refAllowed('edit'), refRefused('archive', reason)] })]] })
    renderRoute('/office/references?tab=hotels')
    const archive = within(await rowOf('Sea Breeze')).getByRole('button', { name: 'В архів' })
    expect(archive).toBeDisabled()
    expect(archive).toHaveAccessibleDescription(reason)
  })

  it('shows a 409 from the server in the dialog', async () => {
    backend({ 'POST /admin/countries/1/archive': () => [409, { detail: 'Використовується в опублікованих турах (2) — спершу зніміть їх з продажу' }] })
    const { user } = renderRoute('/office/references')
    await user.click(within(await rowOf('Туреччина')).getByRole('button', { name: 'В архів' }))
    const confirm = await dialogTitled('Перенести «Туреччина» в архів?')
    await user.click(within(confirm).getByRole('button', { name: 'В архів' }))
    expect(await within(confirm).findByText(/опублікованих турах \(2\)/)).toBeInTheDocument()
  })

  it('the hotel form offers the resorts of the chosen country only', async () => {
    const calls = backend({ 'POST /admin/hotels': () => [201, makeHotelAdmin({ id: 22, name: 'Nile View', resort_id: 12 })] })
    const { user } = renderRoute('/office/references?tab=hotels')
    await user.click(await screen.findByRole('button', { name: /Додати готель/ }))
    const drawer = await dialogTitled('Додати готель')
    const resort = within(drawer).getByRole('combobox', { name: 'Курорт' })
    expect(resort).toBeDisabled()
    await user.click(within(drawer).getByRole('combobox', { name: 'Країна' }))
    await user.click(await screen.findByTitle('Єгипет'))
    await waitFor(() => expect(resort).toBeEnabled())
    await user.click(resort)
    expect(await screen.findByTitle('Хургада')).toBeInTheDocument()
    expect(screen.queryByTitle('Кемер')).not.toBeInTheDocument()
    await user.click(screen.getByTitle('Хургада'))
    await user.type(within(drawer).getByLabelText('Назва готелю'), 'Nile View')
    await user.click(within(drawer).getByRole('button', { name: 'Додати' }))
    await waitFor(() => expect(calls.find((c) => c.method === 'POST')?.body).toMatchObject({
      resort_id: 12, name: 'Nile View', stars: null, amenities: [], room_types: [], check_in: null,
    }))
  })

  it('the default insurance cannot be archived and says why', async () => {
    backend()
    renderRoute('/office/references?tab=insurance-types')
    const row = await rowOf('Базове')
    expect(within(row).getByText('Типовий')).toBeInTheDocument()
    expect(within(row).getByRole('button', { name: 'В архів' })).toHaveAccessibleDescription(/Типовий запис не архівується/)
  })
})
