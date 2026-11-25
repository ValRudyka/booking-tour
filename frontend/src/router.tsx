import { createBrowserRouter, Navigate, type RouteObject } from 'react-router'
import { AuthRoot } from './features/auth/AuthProvider'
import { RequireAuth } from './features/auth/RequireAuth'
import { STAFF_ROLES } from './features/auth/redirect'
import { PublicLayout } from './layouts/PublicLayout'
import { BookingPlaceholder } from './pages/BookingPlaceholder'
import { CatalogPage } from './pages/catalog/CatalogPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { PlaceholderPage } from './pages/PlaceholderPage'
import { RouteErrorPage } from './pages/RouteErrorPage'
import { TourDetailsPage } from './pages/tour/TourDetailsPage'
export const routes: RouteObject[] = [
  {
    // AuthProvider wraps every page (it needs the router to send a user to /login).
    element: <AuthRoot />,
    errorElement: <RouteErrorPage />,
    children: [
      {
        element: <PublicLayout />,
        children: [
          // No home page yet: the catalog is the start page.
          { index: true, element: <Navigate to="/tours" replace /> },
          { path: 'tours', element: <CatalogPage /> },
          { path: 'tours/:id', element: <TourDetailsPage /> },
          { path: 'login', element: <PlaceholderPage page="login" /> },  // the page comes in the next commit
          { path: 'register', element: <PlaceholderPage page="register" /> },
          // Orders are a client's (backend require_roles): staff see 403 here.
          { path: 'booking/:tourId', element: <RequireAuth roles={['client']}><BookingPlaceholder /></RequireAuth> },
          { path: 'cabinet', element: <RequireAuth roles={['client']}><PlaceholderPage page="cabinet" /></RequireAuth> },
          { path: 'cabinet/orders', element: <RequireAuth roles={['client']}><PlaceholderPage page="cabinetOrders" /></RequireAuth> },
          // The back office comes in feature/frontend-backoffice.
          { path: 'office', element: <RequireAuth roles={STAFF_ROLES}><PlaceholderPage page="office" /></RequireAuth> },
          { path: 'about', element: <PlaceholderPage page="about" /> },
          { path: 'terms', element: <PlaceholderPage page="terms" /> },
          { path: 'privacy', element: <PlaceholderPage page="privacy" /> },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
]
export function createAppRouter() {
  return createBrowserRouter(routes)
}
