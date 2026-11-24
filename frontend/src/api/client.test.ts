import { AxiosError, AxiosHeaders, type InternalAxiosRequestConfig } from 'axios'
import { describe, expect, it } from 'vitest'
import { API_URL, ApiError, createApiClient, mediaUrl, toApiError } from './client'
import { shouldRetry } from './queryClient'

function responseError(status: number, data: unknown): AxiosError {
  const config = { headers: new AxiosHeaders() } as InternalAxiosRequestConfig
  return new AxiosError('failed', 'ERR_BAD_RESPONSE', config, null,
    { status, data, statusText: '', headers: {}, config })
}

describe('toApiError', () => {
  it('reports a request without a response as a network error', () => {
    const error = toApiError(new AxiosError('Network Error', 'ERR_NETWORK'))
    expect(error).toMatchObject({ kind: 'network', status: null })
    expect(error.message).toMatch(/з'єднатися з сервером/)
  })

  it('turns the maintenance 503 into its own kind with the API message', () => {
    const error = toApiError(responseError(503, { detail: 'Тривають технічні роботи. Спробуйте пізніше.' }))
    expect(error).toMatchObject({
      kind: 'maintenance', status: 503, message: 'Тривають технічні роботи. Спробуйте пізніше.',
    })
  })

  it('shows the API detail text for business errors', () => {
    expect(toApiError(responseError(404, { detail: 'Тур не знайдено' })))
      .toMatchObject({ kind: 'not_found', message: 'Тур не знайдено' })
    expect(toApiError(responseError(409, { detail: 'Місць немає' })))
      .toMatchObject({ kind: 'client', message: 'Місць немає' })
  })

  it('hides technical validation details', () => {
    const error = toApiError(responseError(422, { detail: [{ loc: ['query', 'page'], msg: 'bad' }] }))
    expect(error).toMatchObject({ kind: 'validation', message: 'Некоректні параметри запиту.' })
  })

  it('gives a generic text for server errors', () => {
    expect(toApiError(responseError(500, 'Internal Server Error')).kind).toBe('server')
  })
})

describe('api client', () => {
  it('sends list parameters as repeated keys, as FastAPI expects', async () => {
    const client = createApiClient()
    let url = ''
    client.defaults.adapter = async (config) => {
      url = client.getUri(config)
      return { data: {}, status: 200, statusText: 'OK', headers: {}, config }
    }
    await client.get('/tours', { params: { stars: [4, 5], page: 1 } })
    expect(url).toBe(`${API_URL}/api/tours?stars=4&stars=5&page=1`)
  })

  it('rejects with ApiError', async () => {
    const client = createApiClient()
    client.defaults.adapter = async () => {
      throw responseError(503, { detail: 'Технічні роботи' })
    }
    await expect(client.get('/tours')).rejects.toBeInstanceOf(ApiError)
  })
})

describe('shouldRetry', () => {
  it('does not retry client errors or maintenance, retries network/server errors twice', () => {
    expect(shouldRetry(0, new ApiError('validation', 422, ''))).toBe(false)
    expect(shouldRetry(0, new ApiError('maintenance', 503, ''))).toBe(false)
    expect(shouldRetry(0, new ApiError('network', null, ''))).toBe(true)
    expect(shouldRetry(1, new ApiError('server', 500, ''))).toBe(true)
    expect(shouldRetry(2, new ApiError('server', 500, ''))).toBe(false)
  })
})

describe('mediaUrl', () => {
  it('prefixes server paths with the API origin', () => {
    expect(mediaUrl('/uploads/tours/1/a.jpg')).toBe(`${API_URL}/uploads/tours/1/a.jpg`)
    expect(mediaUrl(null)).toBeNull()
  })
})
