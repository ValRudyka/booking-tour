import { configure, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import type { ManagerOrder, StaffActionInfo } from '../../api/types'
import { mockServer, signIn, type FakeRequest } from '../../test/fixtures'
import {
  allowed, DOCUMENT_RULES, makeManagerOrder, MANAGER, managerPage, refused,
} from '../../test/officeFixtures'
import { renderRoute } from '../../test/render'

type Handler = (request: FakeRequest) => [number, unknown] | [number, unknown, Record<string, string>]

function backend(order: ManagerOrder, extra: Record<string, Handler> = {}) {
  signIn(MANAGER)
  return mockServer({
    'GET /auth/me': () => [200, MANAGER],
    [`GET /manager/orders/${order.id}`]: () => [200, order],
    'GET /manager/orders': () => [200, managerPage([])],
    'GET /manager/orders/document-rules': () => [200, DOCUMENT_RULES],
    'GET /manager/managers': () => [200, [{ id: MANAGER.id, name: 'Петренко Іван' }, { id: 702, name: 'Коваленко Олена' }]],
    ...extra,
  })
}
const posts = (calls: FakeRequest[]) => calls.filter((c) => c.method !== 'GET')
const actionsCard = async () => (await screen.findByRole('heading', { name: 'Дії' })).closest('.ant-card') as HTMLElement
const OTHER = 'Замовлення веде інший менеджер (Коваленко О.). Змінювати його може лише відповідальний менеджер'

// The office pages are lazy routes: load their code once up front, so the first test does not
// spend its findBy time on the dynamic import while the whole suite runs in parallel.
// The antd Table, Tabs and Descriptions of these pages take more than findBy's 1 s default to
// mount the first time on a loaded machine (like the per-call timeouts of BookingPage.test).
configure({ asyncUtilTimeout: 4000 })
beforeAll(async () => {
  await Promise.all([import('../../layouts/OfficeLayout'), import('./OfficeOrderPage')])
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('/office/orders/:id (spec 09 §3)', () => {
  it('shows the order, full passport data, payments and the history', async () => {
    backend(makeManagerOrder())
    renderRoute('/office/orders/42')
    expect(await screen.findByRole('heading', { level: 1, name: 'Заявка № TU-2099-000042' })).toBeInTheDocument()
    expect(screen.getByTestId('responsible')).toHaveTextContent('Відповідальний: не призначено')
    expect(screen.getByText('FX123456')).toBeInTheDocument()           // not masked for the manager
    expect(screen.getByText('Coral Bay Resort')).toBeInTheDocument()
    expect(screen.getByTestId('order-total').textContent?.replace(/\s/g, ' ')).toBe('63 872,76 ₴')
    const history = screen.getByRole('heading', { name: 'Історія статусів' }).closest('.ant-card') as HTMLElement
    expect(within(history).getByText('Система')).toBeInTheDocument()
    expect(within(history).getByText('Коваленко О.')).toBeInTheDocument()
    expect(within(history).getByText('01.01.2099, 12:06')).toBeInTheDocument()   // Kyiv time
  })

  it.each<[StaffActionInfo[], string[]]>([
    [[allowed('take'), allowed('assign'), allowed('edit_comment')], ['Взяти в роботу', 'Передати іншому менеджеру']],
    [[allowed('confirm'), allowed('reject'), allowed('assign')], ['Підтвердити (PNR)', 'Відхилити', 'Передати іншому менеджеру']],
    [[allowed('upload_documents'), refused('documents_ready', 'Спершу завантажте ваучер')], ['Документи готові']],
    [[allowed('archive')], ['Архівувати']],
    [[allowed('edit_comment')], []],
  ])('staff_actions %j give exactly the buttons %j', async (actions, buttons) => {
    backend(makeManagerOrder({ staff_actions: actions }))
    renderRoute('/office/orders/42')
    const card = await actionsCard()
    expect(within(card).queryAllByRole('button').map((b) => b.textContent)).toEqual(buttons)
    if (buttons.length === 0) expect(within(card).getByText('Зараз для цієї заявки дій немає.')).toBeInTheDocument()
  })

  it('disables refused actions and explains them with the server reason', async () => {
    backend(makeManagerOrder({
      status: 'in_progress', manager_id: 702, manager_name: 'Коваленко О.',
      staff_actions: [refused('confirm', OTHER), refused('reject', OTHER), refused('assign', OTHER), refused('edit_comment', OTHER)],
    }))
    renderRoute('/office/orders/42')
    const card = await actionsCard()
    const confirm = within(card).getByRole('button', { name: 'Підтвердити (PNR)' })
    expect(confirm).toBeDisabled()
    expect(within(card).getByRole('button', { name: 'Відхилити' })).toBeDisabled()
    expect(within(card).getAllByText(OTHER)).toHaveLength(1)            // one explanation for all
    expect(confirm).toHaveAccessibleDescription(OTHER)
    expect(screen.queryByRole('textbox', { name: 'Внутрішній коментар' })).not.toBeInTheDocument()
  })

  it('takes the order: one request, the new card replaces the old one', async () => {
    let order = makeManagerOrder()
    const calls = backend(order, {
      'GET /manager/orders/42': () => [200, order],
      'POST /manager/orders/42/take': () => {
        order = makeManagerOrder({
          status: 'in_progress', manager_id: MANAGER.id, manager_name: 'Петренко І.',
          staff_actions: [allowed('confirm'), allowed('reject'), allowed('assign'), allowed('edit_comment')],
        })
        return [200, order]
      },
    })
    const { user } = renderRoute('/office/orders/42')
    const take = within(await actionsCard()).getByRole('button', { name: 'Взяти в роботу' })
    await user.dblClick(take)
    expect(await screen.findByTestId('responsible')).toHaveTextContent('Відповідальний: Петренко І.')
    expect(await screen.findByRole('button', { name: 'Підтвердити (PNR)' })).toBeEnabled()
    expect(posts(calls).map((c) => c.url)).toEqual(['/manager/orders/42/take'])
  })

  it('shows the 409 text and reloads the order when another manager took it first', async () => {
    let order = makeManagerOrder()
    const calls = backend(order, {
      'GET /manager/orders/42': () => [200, order],
      'POST /manager/orders/42/take': () => {
        order = makeManagerOrder({
          status: 'in_progress', manager_id: 702, manager_name: 'Коваленко О.',
          staff_actions: [refused('confirm', OTHER), refused('reject', OTHER), refused('assign', OTHER)],
        })
        return [409, { detail: OTHER }]
      },
    })
    const { user } = renderRoute('/office/orders/42')
    await user.click(within(await actionsCard()).getByRole('button', { name: 'Взяти в роботу' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(OTHER)
    expect(await screen.findByTestId('responsible')).toHaveTextContent('Відповідальний: Коваленко О.')
    expect(calls.filter((c) => c.url === '/manager/orders/42' && c.method === 'GET').length).toBeGreaterThanOrEqual(2)
  })

  it('requires a reason to reject and sends it with the message to the client', async () => {
    const order = makeManagerOrder({ status: 'in_progress', manager_id: MANAGER.id, staff_actions: [allowed('confirm'), allowed('reject')] })
    const calls = backend(order, {
      'POST /manager/orders/42/reject': () => [200, { ...order, status: 'rejected', reject_reason: 'Немає місць', staff_actions: [] }],
    })
    const { user } = renderRoute('/office/orders/42')
    await user.click(within(await actionsCard()).getByRole('button', { name: 'Відхилити' }))
    const dialog = await screen.findByRole('dialog', { name: 'Відхилити заявку' })
    expect(within(dialog).getByText(/фінансовий відділ — завдання повернути кошти в повному обсязі/)).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Відхилити заявку' }))
    expect(await within(dialog).findByText('Вкажіть причину відхилення')).toBeInTheDocument()
    expect(posts(calls)).toHaveLength(0)
    await user.type(within(dialog).getByLabelText('Причина відхилення'), '   ')
    await user.click(within(dialog).getByRole('button', { name: 'Відхилити заявку' }))
    expect(posts(calls)).toHaveLength(0)
    await user.clear(within(dialog).getByLabelText('Причина відхилення'))
    await user.type(within(dialog).getByLabelText('Причина відхилення'), ' Немає місць ')
    await user.type(within(dialog).getByLabelText('Повідомлення клієнту'), 'Запропонуємо інший готель')
    await user.click(within(dialog).getByRole('button', { name: 'Відхилити заявку' }))
    await waitFor(() => expect(posts(calls)).toHaveLength(1))
    expect(posts(calls)[0].body).toEqual({ reject_reason: 'Немає місць', client_message: 'Запропонуємо інший готель' })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('confirms with an upper-case PNR and the deadline, and shows a server refusal inside the dialog', async () => {
    const order = makeManagerOrder({ status: 'in_progress', manager_id: MANAGER.id, staff_actions: [allowed('confirm'), allowed('reject')] })
    const calls = backend(order, {
      'POST /manager/orders/42/confirm': () => [422, { detail: 'Дедлайн оплати туроператору має бути не пізніше дати початку туру' }],
    })
    const { user } = renderRoute('/office/orders/42')
    await user.click(within(await actionsCard()).getByRole('button', { name: 'Підтвердити (PNR)' }))
    const dialog = await screen.findByRole('dialog', { name: 'Підтвердити бронювання' })
    const pnr = within(dialog).getByLabelText('GDS номер (PNR)')
    await user.type(pnr, 'ab-1')
    await user.click(within(dialog).getByRole('button', { name: 'Підтвердити' }))
    expect(await within(dialog).findByText('PNR — від 5 до 20 латинських літер і цифр')).toBeInTheDocument()
    await user.clear(pnr)
    await user.type(pnr, 'abc123')
    expect(pnr).toHaveValue('ABC123')
    await user.click(within(dialog).getByLabelText('Дедлайн оплати туроператору'))
    await user.keyboard('15.01.2099{Enter}')
    await user.click(within(dialog).getByRole('button', { name: 'Підтвердити' }))
    await waitFor(() => expect(posts(calls)).toHaveLength(1))
    expect(posts(calls)[0].body).toEqual({ pnr: 'ABC123', operator_deadline: '2099-01-15', client_message: null })
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Дедлайн оплати туроператору має бути не пізніше дати початку туру')
  })

  it('archives only after the confirmation with the consequences', async () => {
    const order = makeManagerOrder({ status: 'completed', manager_id: MANAGER.id, staff_actions: [allowed('archive')] })
    const calls = backend(order, {
      'POST /manager/orders/42/archive': () => [200, { ...order, status: 'archived', staff_actions: [] }],
    })
    const { user } = renderRoute('/office/orders/42')
    await user.click(within(await actionsCard()).getByRole('button', { name: 'Архівувати' }))
    expect(await screen.findByText(/Повернути заявку з архіву не можна/)).toBeInTheDocument()
    expect(posts(calls)).toHaveLength(0)
    const popover = document.querySelector('.ant-popover') as HTMLElement
    await user.click(within(popover).getByRole('button', { name: 'Архівувати' }))
    await waitFor(() => expect(posts(calls).map((c) => c.url)).toEqual(['/manager/orders/42/archive']))
  })

  it('uploads a document with its type and offers delete only where the API allows', async () => {
    const order = makeManagerOrder({
      status: 'confirmed', manager_id: MANAGER.id,
      staff_actions: [allowed('upload_documents'), refused('documents_ready', 'Спершу завантажте ваучер')],
      documents: [
        { id: 5, doc_type: 'air_ticket', uploaded_at: '2099-01-02T08:00:00Z', uploaded_by: MANAGER.id, can_delete: true },
        { id: 6, doc_type: 'cancel_evidence', uploaded_at: '2099-01-02T09:00:00Z', uploaded_by: 501, can_delete: false },
      ],
    })
    const calls = backend(order, {
      'POST /manager/orders/42/documents': () => [201, [{ id: 7, doc_type: 'voucher', uploaded_at: '2099-01-03T08:00:00Z', uploaded_by: MANAGER.id }]],
    })
    const { user } = renderRoute('/office/orders/42')
    const card = (await screen.findByRole('heading', { name: 'Документи' })).closest('.ant-card') as HTMLElement
    expect(within(card).getByRole('button', { name: 'Видалити «Авіаквиток»' })).toBeInTheDocument()
    expect(within(card).queryByRole('button', { name: /Видалити «Довідка/ })).not.toBeInTheDocument()
    expect(await within(card).findByText(/Можна додати ще 8/)).toBeInTheDocument()

    await user.click(within(card).getByRole('button', { name: 'Завантажити' }))
    expect(await within(card).findByText('Оберіть тип документа')).toBeInTheDocument()
    await user.click(within(card).getByRole('combobox', { name: 'Тип документа' }))
    await user.click(await screen.findByTitle('Ваучер'))
    const file = new File(['%PDF-1.4'], 'voucher.pdf', { type: 'application/pdf' })
    await user.upload(card.querySelector('input[type="file"]') as HTMLInputElement, file)
    await user.click(within(card).getByRole('button', { name: 'Завантажити' }))
    await waitFor(() => expect(posts(calls)).toHaveLength(1))
    const form = posts(calls)[0].body as FormData
    expect(form.get('doc_type')).toBe('voucher')
    expect((form.getAll('files')[0] as File).name).toBe('voucher.pdf')
  })

  it('refuses a file of the wrong type before sending', async () => {
    const order = makeManagerOrder({ status: 'confirmed', manager_id: MANAGER.id, staff_actions: [allowed('upload_documents')] })
    const calls = backend(order)
    const { user } = renderRoute('/office/orders/42')
    const card = (await screen.findByRole('heading', { name: 'Документи' })).closest('.ant-card') as HTMLElement
    await within(card).findByRole('button', { name: 'Обрати файли' })
    const input = card.querySelector('input[type="file"]') as HTMLInputElement
    // The extension passes the input's accept list, the browser's MIME type does not.
    await user.upload(input, new File(['x'], 'notes.pdf', { type: 'application/msword' }))
    expect(await within(card).findByText('Файл «notes.pdf»: дозволені формати JPG, PDF, PNG')).toBeInTheDocument()
    expect(posts(calls)).toHaveLength(0)
  })

  it('shows the client\'s cancellation request', async () => {
    backend(makeManagerOrder({
      status: 'cancel_requested', cancel_reason_code: 'illness', cancel_reason: 'Довідка з лікарні',
      staff_actions: [allowed('assign'), allowed('edit_comment')],
    }))
    renderRoute('/office/orders/42')
    const alert = await screen.findByRole('status')
    expect(alert).toHaveTextContent('Клієнт просить скасувати бронювання')
    expect(alert).toHaveTextContent('Причина: Хвороба')
    expect(alert).toHaveTextContent('Пояснення клієнта: Довідка з лікарні')
  })

  it('saves the internal comment', async () => {
    const order = makeManagerOrder({ staff_actions: [allowed('take'), allowed('edit_comment')] })
    const calls = backend(order, {
      'PATCH /manager/orders/42': () => [200, { ...order, internal_comment: 'Клієнт VIP' }],
    })
    const { user } = renderRoute('/office/orders/42')
    await user.type(await screen.findByRole('textbox', { name: 'Внутрішній коментар' }), ' Клієнт VIP ')
    await user.click(screen.getByRole('button', { name: 'Зберегти коментар' }))
    await waitFor(() => expect(posts(calls)[0]?.body).toEqual({ internal_comment: 'Клієнт VIP' }))
  })

  it('answers 404 for an unknown id', async () => {
    backend(makeManagerOrder(), { 'GET /manager/orders/7': () => [404, { detail: 'Замовлення не знайдено' }] })
    renderRoute('/office/orders/7')
    expect(await screen.findByRole('heading', { level: 1, name: 'Заявку не знайдено' })).toBeInTheDocument()
  })

  it('answers 404 for a malformed id without asking the API', async () => {
    const calls = backend(makeManagerOrder())
    renderRoute('/office/orders/abc')
    expect(await screen.findByRole('heading', { level: 1, name: 'Заявку не знайдено' })).toBeInTheDocument()
    expect(calls.some((c) => c.url.startsWith('/manager/orders/a'))).toBe(false)
  })
})
