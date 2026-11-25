import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { makeTour } from '../test/fixtures'
import { renderWithProviders } from '../test/render'
import { API_URL } from '../api/client'
import { kyivTomorrow } from '../utils/format'
import { TourCard } from './TourCard'

const text = (element: HTMLElement) => element.textContent!.replace(/[  ]/g, ' ')

describe('TourCard', () => {
  it('shows the "from" price formatted for Ukrainian', () => {
    renderWithProviders(<TourCard tour={makeTour({ price_from_uah: '32000.00' })} />)
    expect(text(screen.getByText(/^від/))).toBe('від 32 000 ₴')
  })

  it('shows the hotel rating with a decimal comma', () => {
    renderWithProviders(<TourCard tour={makeTour()} />)
    expect(screen.getByText('Рейтинг готелю 4,6 з 5')).toBeInTheDocument()
  })

  it('says there are no reviews yet when the rating is null', () => {
    const tour = makeTour()
    renderWithProviders(<TourCard tour={{ ...tour, hotel: { ...tour.hotel, rating_avg: null } }} />)
    expect(screen.getByText('Ще немає відгуків')).toBeInTheDocument()
  })

  it('shows a neutral placeholder without a photo', () => {
    renderWithProviders(<TourCard tour={makeTour({ image_url: null })} />)
    expect(screen.getByRole('img', { name: 'Фото відсутнє' })).toBeInTheDocument()
  })

  it('loads the photo from the API server', () => {
    const tour = makeTour({ image_url: '/uploads/tours/3/abc.jpg' })
    renderWithProviders(<TourCard tour={tour} />)
    expect(screen.getByRole('img', { name: tour.title_uk })).toHaveAttribute('src', `${API_URL}/uploads/tours/3/abc.jpg`)
  })

  it('shows hotel, stars, nights, date and departure city', () => {
    renderWithProviders(<TourCard tour={makeTour({ departure_from: '2099-06-01' })} />)
    expect(screen.getByText('Coral Bay Resort')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: '5 зірок' })).toBeInTheDocument()
    expect(screen.getByText('7 ночей')).toBeInTheDocument()
    expect(screen.getByText(/Найближчий виїзд 01\.06\.2099/)).toBeInTheDocument()
    expect(screen.getByText('Виліт: Київ')).toBeInTheDocument()
  })

  it('warns when few seats are left, in correct Ukrainian plural', () => {
    renderWithProviders(<TourCard tour={makeTour({ free_seats: 3 })} />)
    expect(screen.getByText('Залишилось 3 місця')).toBeInTheDocument()
  })

  it('shows no seats tag when there are plenty', () => {
    renderWithProviders(<TourCard tour={makeTour({ free_seats: 10 })} />)
    expect(screen.queryByText(/Залишилось/)).not.toBeInTheDocument()
    expect(screen.queryByText('Місць немає')).not.toBeInTheDocument()
  })

  it('marks a sold-out tour', () => {
    renderWithProviders(<TourCard tour={makeTour({ free_seats: 0 })} />)
    expect(screen.getByText('Місць немає')).toBeInTheDocument()
  })

  it('shows the meal plan as a tag, and nothing when it is not stated', () => {
    const { unmount } = renderWithProviders(<TourCard tour={makeTour({ meal_plan: 'uai' })} />)
    expect(screen.getByText('Ультра все включено')).toBeInTheDocument()
    unmount()
    renderWithProviders(<TourCard tour={makeTour({ meal_plan: null })} />)
    expect(screen.queryByText(/включено|Сніданок|пансіон|Без харчування/)).not.toBeInTheDocument()
  })

  it('shows tomorrow as the nearest departure once the range has begun', () => {
    // Starts long ago, ends far ahead: the nearest bookable date is tomorrow (Kyiv), never today.
    renderWithProviders(<TourCard tour={makeTour({ departure_from: '2000-01-01', departure_to: '2099-12-31' })} />)
    const [y, m, d] = kyivTomorrow().split('-')
    expect(screen.getByText(`Найближчий виїзд ${d}.${m}.${y}`)).toBeInTheDocument()
  })

  it('is one link to the tour page', () => {
    const tour = makeTour()
    renderWithProviders(<TourCard tour={tour} />)
    expect(screen.getByRole('link')).toHaveAttribute('href', `/tours/${tour.id}`)
  })
})
