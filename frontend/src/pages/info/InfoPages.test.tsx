import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { ApiError } from '../../api/client'
import { HelpGuide } from '../../components/HelpGuide'
import { mockApi, page } from '../../test/fixtures'
import { renderRoute, renderWithProviders } from '../../test/render'
import { FAQ_KEYS } from './infoContent'

const CONTACTS = { phone: '+380441234567', email: 'help@tour.local' }

function withContacts(contacts: { phone: string | null; email: string | null }) {
  return mockApi(() => page([]), { '/site/contacts': () => contacts })
}

describe('info pages', () => {
  it.each([
    ['/about', 'Про нас'],
    ['/contacts', 'Контакти'],
    ['/terms', 'Умови бронювання та публічний договір'],
    ['/privacy', 'Політика конфіденційності'],
    ['/faq', 'Часті запитання'],
  ])('%s has one h1 «%s» and the tab title', async (url, title) => {
    withContacts(CONTACTS)
    renderRoute(url)
    expect(await screen.findByRole('heading', { level: 1, name: title })).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
    expect(document.title).toBe(`${title} — Хвиля`)
  })

  it.each(['/terms', '/privacy'])('%s carries the course-project note at the top', (url) => {
    withContacts(CONTACTS)
    renderRoute(url)
    const note = screen.getByRole('alert')
    expect(note).toHaveTextContent('Навчальний проєкт. Цей текст не є юридичним документом.')
    // The note comes before the first section.
    const firstSection = screen.getAllByRole('heading', { level: 2 })[0]
    expect(note.compareDocumentPosition(firstSection) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('the about page has no course-project alert but says it is a course project', () => {
    withContacts(CONTACTS)
    renderRoute('/about')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByText(/Сайт створено як курсовий проєкт/)).toBeInTheDocument()
  })

  it('texts never name the length of a seat hold', () => {
    withContacts(CONTACTS)
    const { unmount } = renderRoute('/terms')
    expect(document.body).not.toHaveTextContent(/\d+\s*(хв|хвилин|годин)/)
    unmount()
    renderRoute('/faq#hold')
    expect(document.body).not.toHaveTextContent(/\d+\s*(хв|хвилин|годин)/)
  })
})

describe('contacts page', () => {
  it('shows the phone and e-mail from the API as tel: and mailto: links', async () => {
    withContacts(CONTACTS)
    renderRoute('/contacts')
    const main = document.getElementById('main') as HTMLElement
    expect(await within(main).findByRole('link', { name: '+380441234567' })).toHaveAttribute('href', 'tel:+380441234567')
    expect(within(main).getByRole('link', { name: 'help@tour.local' })).toHaveAttribute('href', 'mailto:help@tour.local')
  })

  it('hides an empty field', async () => {
    withContacts({ phone: null, email: 'help@tour.local' })
    renderRoute('/contacts')
    const main = document.getElementById('main') as HTMLElement
    expect(await within(main).findByRole('link', { name: 'help@tour.local' })).toBeInTheDocument()
    expect(within(main).queryByText(/Телефон/)).not.toBeInTheDocument()
  })

  it('says so when no contacts are set', async () => {
    withContacts({ phone: null, email: null })
    renderRoute('/contacts')
    expect(await screen.findByText('Контакти служби підтримки ще не вказано. Спробуйте зайти пізніше.')).toBeInTheDocument()
  })

  it('shows the error with a retry when the request fails', async () => {
    mockApi(() => page([]), {
      '/site/contacts': () => { throw new ApiError('server', 500, 'На сервері сталася помилка.') },
    })
    renderRoute('/contacts')
    expect(await screen.findByText('Не вдалося завантажити контакти')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Спробувати ще раз' })).toBeInTheDocument()
  })

  it('links to the matching FAQ questions', async () => {
    withContacts(CONTACTS)
    renderRoute('/contacts')
    expect(await screen.findByRole('link', { name: 'Як скасувати бронювання?' })).toHaveAttribute('href', '/faq#cancel')
    expect(screen.getByRole('link', { name: 'Усі часті запитання' })).toHaveAttribute('href', '/faq')
  })
})

describe('FAQ', () => {
  it('lists every question closed when there is no anchor', () => {
    withContacts(CONTACTS)
    renderRoute('/faq')
    const questions = screen.getAllByRole('button', { expanded: false })
    expect(questions).toHaveLength(FAQ_KEYS.length)
  })

  it('opens and focuses the question named by the anchor', async () => {
    withContacts(CONTACTS)
    renderRoute('/faq#cancel')
    const question = screen.getByRole('button', { name: 'Як скасувати бронювання?' })
    expect(question).toHaveAttribute('aria-expanded', 'true')
    expect(question).toHaveFocus()
    expect(document.getElementById('cancel')).toHaveTextContent('фактично понесених витрат (ФПВ)')
    expect(screen.getByRole('button', { name: 'Як забронювати тур?' })).toHaveAttribute('aria-expanded', 'false')
  })

  it('ignores an unknown anchor', () => {
    withContacts(CONTACTS)
    renderRoute('/faq#nothing')
    expect(screen.getAllByRole('button', { expanded: false })).toHaveLength(FAQ_KEYS.length)
  })

  it('a link to another question on the page opens it too', async () => {
    withContacts(CONTACTS)
    const { user, router } = renderRoute('/faq#book')
    await user.click(screen.getByRole('link', { name: 'утримання місць' }))
    expect(router.state.location.hash).toBe('#hold')
    const hold = screen.getByRole('button', { name: 'Що таке утримання місць і скільки воно триває?' })
    expect(hold).toHaveAttribute('aria-expanded', 'true')
    expect(hold).toHaveFocus()
    // The first question stays open.
    expect(screen.getByRole('button', { name: 'Як забронювати тур?' })).toHaveAttribute('aria-expanded', 'true')
  })

  it('a question opens and closes on click', async () => {
    withContacts(CONTACTS)
    const { user } = renderRoute('/faq')
    const question = screen.getByRole('button', { name: 'Як оплатити бронювання?' })
    await user.click(question)
    expect(question).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText(/Можна платити частинами/)).toBeInTheDocument()
    await user.click(question)
    expect(question).toHaveAttribute('aria-expanded', 'false')
  })
})

describe('links to the info pages', () => {
  it('every footer and header link opens a real page, not the 404', async () => {
    withContacts(CONTACTS)
    const { user, router } = renderRoute('/tours')
    const footer = screen.getByRole('navigation', { name: 'Інформація' })
    const header = screen.getByRole('navigation', { name: 'Головне меню' })
    const links = [...within(header).getAllByRole('link'), ...within(footer).getAllByRole('link')]
    const targets = links.map((link) => link.getAttribute('href'))
    expect(targets).toEqual(['/tours', '/about', '/faq', '/contacts', '/about', '/contacts', '/faq', '/terms', '/privacy'])

    for (const target of new Set(targets)) {
      const link = document.querySelector<HTMLAnchorElement>(`footer a[href="${target}"], header a[href="${target}"]`)
      await user.click(link as HTMLAnchorElement)
      expect(router.state.location.pathname).toBe(target)
      expect(screen.queryByRole('heading', { level: 1, name: 'Сторінку не знайдено' })).not.toBeInTheDocument()
      expect(await screen.findByRole('heading', { level: 1 })).toBeInTheDocument()
    }
  })

  it('«Забули пароль?» links to the FAQ answer about passwords', async () => {
    withContacts(CONTACTS)
    const { user } = renderRoute('/login')
    await user.click(await screen.findByRole('button', { name: 'Забули пароль?' }))
    const panel = document.getElementById('forgot-panel') as HTMLElement
    expect(within(panel).getByRole('link', { name: 'Докладніше про вхід і пароль' })).toHaveAttribute('href', '/faq#password')
  })

  it('HelpGuide can open its link in a new tab (the booking wizard keeps its hold)', async () => {
    renderWithProviders(<HelpGuide content={{
      title: 'Як оформити бронювання', steps: ['Крок'],
      link: { to: '/faq#hold', label: 'Докладніше про утримання місць', newTab: true },
    }} />)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Як це працює?' }))
    const link = await screen.findByRole('link', { name: 'Докладніше про утримання місць' })
    expect(link).toHaveAttribute('href', '/faq#hold')
    expect(link).toHaveAttribute('target', '_blank')
  })
})
