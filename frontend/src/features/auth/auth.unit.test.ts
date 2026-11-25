import dayjs from 'dayjs'
import { describe, expect, it } from 'vitest'
import { ApiError } from '../../api/client'
import { loginErrorText, mapRegisterError } from './authErrors'
import { homeFor, loginPath, safeRedirect } from './redirect'
import { ageOn, isAdult, isValidPhone, nameMatchesCitizenship } from './rules'

const FIELDS = ['phone', 'email', 'password', 'last_name', 'first_name', 'birth_date', 'citizenship_id', 'consent']

describe('safeRedirect', () => {
  it('keeps paths inside the site', () => {
    expect(safeRedirect('/booking/83?date=2026-12-01')).toBe('/booking/83?date=2026-12-01')
    expect(safeRedirect('/cabinet/orders')).toBe('/cabinet/orders')
  })

  it.each(['https://evil.example/', '//evil.example', '/\\evil.example', 'javascript:alert(1)', '', null,
    'cabinet', '/a\nb'])('ignores %s', (value) => {
    expect(safeRedirect(value)).toBeNull()
  })

  it('builds /login?redirect= only for safe paths', () => {
    expect(loginPath('/booking/1?date=2026-12-01')).toBe('/login?redirect=%2Fbooking%2F1%3Fdate%3D2026-12-01')
    expect(loginPath('https://evil.example')).toBe('/login')
  })

  it('sends clients to their orders and staff to the office', () => {
    expect(homeFor('client')).toBe('/cabinet/orders')
    for (const role of ['manager', 'finance', 'admin'] as const) expect(homeFor(role)).toBe('/office')
  })
})

describe('registration rules (the same as the backend)', () => {
  it('accepts international phones with spaces, any country', () => {
    expect(isValidPhone('+380 50 123-45-67')).toBe(true)
    expect(isValidPhone('+48 601 234 567')).toBe(true)
    expect(isValidPhone('0501234567')).toBe(false)       // no +
    expect(isValidPhone('+38050')).toBe(false)           // too short
  })

  it('checks the names alphabet by citizenship', () => {
    expect(nameMatchesCitizenship("Стефанишин-Об'єдко", true)).toBe(true)
    expect(nameMatchesCitizenship('Ївга', true)).toBe(true)
    expect(nameMatchesCitizenship('Shevchenko', true)).toBe(false)
    expect(nameMatchesCitizenship('Ёлкин', true)).toBe(false)          // not a Ukrainian letter
    expect(nameMatchesCitizenship("O'Neil-Smith", false)).toBe(true)
    expect(nameMatchesCitizenship('Шевченко', false)).toBe(false)
  })

  it('counts age like the backend, by the Kyiv date', () => {
    expect(isAdult(dayjs('2008-01-01'), '2026-01-01')).toBe(true)        // 18 today
    expect(isAdult(dayjs('2008-01-02'), '2026-01-01')).toBe(false)       // 17 years 364 days
    expect(ageOn(dayjs('2008-02-29'), '2026-02-28')).toBe(17)
    expect(ageOn(dayjs('2008-02-29'), '2026-03-01')).toBe(18)
  })
})

describe('backend errors -> Ukrainian texts', () => {
  it('puts 422 issues under their fields, in Ukrainian', () => {
    const error = new ApiError('validation', 422, 'x', null, [
      { loc: ['body', 'phone'], type: 'value_error', msg: 'Value error, Телефон у міжнародному форматі, наприклад +380501234567' },
      { loc: ['body', 'password'], type: 'string_too_short', msg: 'String should have at least 8 characters' },
      { loc: ['body', 'email'], type: 'value_error', msg: 'value is not a valid email address: An email address must have an @-sign.' },
      { loc: ['body', 'birth_date'], type: 'missing', msg: 'Field required' },
    ])
    expect(mapRegisterError(error, FIELDS)).toEqual({
      fields: [
        { name: 'phone', errors: ['Телефон у міжнародному форматі, наприклад +380501234567'] },
        { name: 'password', errors: ['Пароль має містити щонайменше 8 символів'] },
        { name: 'email', errors: ['Вкажіть коректний e-mail, наприклад name@example.com'] },
        { name: 'birth_date', errors: ['Вкажіть дату народження'] },
      ],
      alert: null,
    })
  })

  it('maps the known plain texts to fields', () => {
    const taken = new ApiError('client', 409, 'x', 'Користувач з таким e-mail вже існує')
    expect(mapRegisterError(taken, FIELDS).fields).toEqual([
      { name: 'email', errors: ['Цей e-mail вже зареєстрований. Увійдіть або вкажіть інший e-mail.'] }])
    const alphabet = new ApiError('validation', 422, 'x', "Прізвище та ім'я потрібно вводити латиницею")
    expect(mapRegisterError(alphabet, FIELDS).fields.map((f) => f.name)).toEqual(['last_name', 'first_name'])
    const minor = new ApiError('validation', 422, 'x', 'Реєстрація доступна лише з 18 років')
    expect(mapRegisterError(minor, FIELDS).fields).toEqual([
      { name: 'birth_date', errors: ['Реєстрація доступна лише з 18 років'] }])
  })

  it('never shows an unknown backend text: it becomes the generic message', () => {
    const odd = new ApiError('client', 400, 'x', 'Some internal problem: id=5')
    expect(mapRegisterError(odd, FIELDS)).toEqual({ fields: [], alert: 'Щось пішло не так. Спробуйте ще раз.' })
    const unknownField = new ApiError('validation', 422, 'x', null, [{ loc: ['body', 'role'], type: 'extra_forbidden', msg: 'x' }])
    expect(mapRegisterError(unknownField, FIELDS).alert).toBe('Щось пішло не так. Спробуйте ще раз.')
  })

  it('login: one message for wrong data; rate limit, maintenance and network have their own', () => {
    expect(loginErrorText(new ApiError('unauthorized', 401, 'x', 'Невірний логін або пароль')))
      .toBe('Неправильний номер телефону, e-mail або пароль')
    expect(loginErrorText(new ApiError('rate_limited', 429, 'x'))).toBe('Забагато спроб входу. Спробуйте пізніше.')
    expect(loginErrorText(new ApiError('maintenance', 503, 'Тривають технічні роботи. Спробуйте пізніше.')))
      .toBe('Тривають технічні роботи. Спробуйте пізніше.')
    expect(loginErrorText(new ApiError('network', null, 'x'))).toMatch(/з'єднатися з сервером/)
  })
})
