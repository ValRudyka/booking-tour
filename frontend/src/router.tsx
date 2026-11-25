import { createBrowserRouter, Navigate, type RouteObject } from 'react-router'
import { PublicLayout } from './layouts/PublicLayout'
import { CatalogPage } from './pages/catalog/CatalogPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { PlaceholderPage } from './pages/PlaceholderPage'
import { RouteErrorPage } from './pages/RouteErrorPage'
import { BookingPlaceholder } from './pages/BookingPlaceholder'
import { TourDetailsPage } from './pages/tour/TourDetailsPage'

export const routes: RouteObject[] = [
  {
    element: <PublicLayout />,
    errorElement: <RouteErrorPage />,
    children: [
      // No home page yet: the catalog is the start page.
      { index: true, element: <Navigate to="/tours" replace /> },
      { path: 'tours', element: <CatalogPage /> },
      { path: 'tours/:id', element: <TourDetailsPage /> },
      { path: 'booking/:tourId', element: <BookingPlaceholder /> },
      { path: 'about', element: <PlaceholderPage page="about" /> },
      { path: 'login', element: <PlaceholderPage page="login" /> },
      { path: 'register', element: <PlaceholderPage page="register" /> },
      { path: 'terms', element: <PlaceholderPage page="terms" /> },
      { path: 'privacy', element: <PlaceholderPage page="privacy" /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]

export function createAppRouter() {
  return createBrowserRouter(routes)
}
