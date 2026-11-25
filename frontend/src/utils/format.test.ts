import { describe, expect, it } from 'vitest'
import {
  formatDate, formatPrice, formatRating, kyivToday, kyivTomorrow, nearestBookableDate,
} from './format'

// Intl uses a narrow no-break space as the uk-UA thousands separator.
const plain = (text: string) => text.replace(/[\u00a0\u202f]/g, ' ')

describe('formatPrice', () => {
  it('groups thousands', () => {
    expect(plain(formatPrice('32000.00'))).toBe('32 000')
    expect(plain(formatPrice('1234567.00'))).toBe('1 234 567')
  })

  it('rounds kopecks half up without float errors', () => {
    expect(plain(formatPrice('32000.50'))).toBe('32 001')
    expect(plain(formatPrice('32000.49'))).toBe('32 000')
    // Too large for a float to hold exactly; as a decimal string it still rounds like the backend.
    expect(plain(formatPrice('10000000000000000.50'))).toBe('10 000 000 000 000 001')
  })
})

describe('formatRating', () => {
  it('uses a decimal comma and one digit', () => {
    expect(formatRating('4.60')).toBe('4,6')
    expect(formatRating('5.00')).toBe('5,0')
  })
})

describe('formatDate', () => {
  it('formats an ISO date as DD.MM.YYYY', () => {
    expect(formatDate('2026-12-01')).toBe('01.12.2026')
  })
})

describe('kyivToday', () => {
  it('uses the Kyiv date, not the visitor\'s', () => {
    // 22:30 UTC on 31 Dec is already 1 Jan in Kyiv (UTC+2 in winter).
    expect(kyivToday(new Date('2026-12-31T22:30:00Z'))).toBe('2027-01-01')
    expect(kyivToday(new Date('2026-12-31T21:30:00Z'))).toBe('2026-12-31')
  })
})

describe('kyivTomorrow', () => {
  it('is the day after the Kyiv date, across a year end', () => {
    // 22:30 UTC on 30 Dec is already 31 Dec in Kyiv, so tomorrow is 1 Jan.
    expect(kyivTomorrow(new Date('2026-12-30T22:30:00Z'))).toBe('2027-01-01')
    expect(kyivTomorrow(new Date('2026-12-30T21:30:00Z'))).toBe('2026-12-31')
  })
})

describe('nearestBookableDate', () => {
  const tomorrow = '2026-12-11'

  it('is the first start date when it is still ahead', () => {
    expect(nearestBookableDate('2026-12-20', '2026-12-31', tomorrow)).toBe('2026-12-20')
  })

  it('is tomorrow once the range of start dates has begun (booking starts tomorrow)', () => {
    expect(nearestBookableDate('2026-12-01', '2026-12-31', tomorrow)).toBe(tomorrow)
  })

  it('is the single date of a one-day range', () => {
    expect(nearestBookableDate('2026-12-15', '2026-12-15', tomorrow)).toBe('2026-12-15')
  })

  it('is null when only today or the past is left', () => {
    expect(nearestBookableDate('2026-12-01', '2026-12-10', tomorrow)).toBeNull()
  })
})
