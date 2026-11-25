import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'
import '../i18n'

// Vitest runs without globals, so React Testing Library cannot register its own cleanup.
afterEach(() => cleanup())

// jsdom has no matchMedia; antd's Grid/responsive observer needs it. Desktop width by default,
// tests can override it with setViewportWidth().
let viewportWidth = 1440
export function setViewportWidth(width: number) {
  viewportWidth = width
}
function matches(query: string): boolean {
  const min = query.match(/min-width:\s*(\d+)px/)
  const max = query.match(/max-width:\s*(\d+(?:\.\d+)?)px/)
  return (!min || viewportWidth >= Number(min[1])) && (!max || viewportWidth <= Number(max[1]))
}
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: matches(query),
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }),
})

// jsdom has no ResizeObserver; antd 6 (Select, Pagination, ...) uses it without a polyfill.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
window.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver

// jsdom does not implement scrolling.
window.scrollTo = vi.fn() as unknown as typeof window.scrollTo
Element.prototype.scrollIntoView = vi.fn()
