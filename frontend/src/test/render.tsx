import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { createQueryClient } from '../api/queryClient'
import { AppProviders } from '../App'
import { routes } from '../router'

/** Renders the real routes at `url` with the app's providers; retries are off in tests. */
export function renderRoute(url: string) {
  const queryClient = createQueryClient()
  queryClient.setDefaultOptions({ queries: { ...queryClient.getDefaultOptions().queries, retry: false } })
  const router = createMemoryRouter(routes, { initialEntries: [url] })
  const user = userEvent.setup()
  const view = render(
    <AppProviders queryClient={queryClient}>
      <RouterProvider router={router} />
    </AppProviders>,
  )
  return { ...view, router, user, queryClient }
}

/** The current URL's query string as a plain object of arrays (order-independent checks). */
export function searchOf(router: ReturnType<typeof createMemoryRouter>): URLSearchParams {
  return new URLSearchParams(router.state.location.search)
}

/** Renders one component inside the app's providers and a router (for links). */
export function renderWithProviders(ui: React.ReactElement) {
  const router = createMemoryRouter([{ path: '*', element: ui }], { initialEntries: ['/'] })
  const queryClient = createQueryClient()
  return render(
    <AppProviders queryClient={queryClient}>
      <RouterProvider router={router} />
    </AppProviders>,
  )
}
