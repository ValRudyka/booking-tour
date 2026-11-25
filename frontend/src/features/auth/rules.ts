// Client-side checks for the auth forms. They only help: the backend checks the same rules again
// (backend/app/schemas/auth.py and services/users.py). Keep them in step with it.
import dayjs, { type Dayjs } from 'dayjs'
import { kyivToday } from '../../utils/format'

/** backend PHONE_RE after removing spaces, "-", "(" and ")": + and 10–15 digits, any country. */
const PHONE_RE = /^\+\d{10,15}$/
export const PASSWORD_MIN = 8
export const PASSWORD_MAX = 128
export const NAME_MAX = 100
export const ADULT_AGE = 18
/** Ukrainian letters, apostrophes, hyphen, space (backend CYRILLIC_NAME). */
const UKRAINIAN_NAME = /^[А-ЩЬЮЯҐЄІЇа-щьюяґєії'’ʼ\- ]+$/
/** Latin letters, apostrophes, hyphen, space (backend LATIN_NAME). */
const LATIN_NAME = /^[A-Za-z'’\- ]+$/
/** A quick syntax check; the backend's e-mail validator has the final word. */
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

export function normalizePhone(value: string): string {
  return value.replace(/[\s\-()]/g, '')
}

export function isValidPhone(value: string): boolean {
  return PHONE_RE.test(normalizePhone(value))
}

export function isValidEmail(value: string): boolean {
  return EMAIL_RE.test(value.trim())
}

/** Ukrainian citizens write their names in Ukrainian, everyone else in Latin letters (ТЗ 4.5.1). */
export function nameMatchesCitizenship(name: string, isUkrainian: boolean): boolean {
  return (isUkrainian ? UKRAINIAN_NAME : LATIN_NAME).test(name.trim())
}

/** Full years on `day` (YYYY-MM-DD), like the backend's age_on(). */
export function ageOn(birthDate: Dayjs, day: string): number {
  const today = dayjs(day, 'YYYY-MM-DD')
  const beforeBirthday = today.month() < birthDate.month()
    || (today.month() === birthDate.month() && today.date() < birthDate.date())
  return today.year() - birthDate.year() - (beforeBirthday ? 1 : 0)
}

/** 18+ by the Kyiv date (the backend's clock.today()), whatever the visitor's time zone. */
export function isAdult(birthDate: Dayjs, today: string = kyivToday()): boolean {
  return ageOn(birthDate, today) >= ADULT_AGE
}
