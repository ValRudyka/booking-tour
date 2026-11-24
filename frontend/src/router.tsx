import { Typography } from 'antd'
import { createBrowserRouter, Navigate, type RouteObject } from 'react-router'
import { useTranslation } from 'react-i18next'
import { useDocumentTitle } from './hooks/useDocumentTitle'
import { PublicLayout } from './layouts/PublicLayout'
import { NotFoundPage } from './pages/NotFoundPage'
import { PlaceholderPage } from './pages/PlaceholderPage'
import { RouteErrorPage } from './pages/RouteErrorPage'
import { TourDetailsPlaceholder } from './pages/TourDetailsPlaceholder'

/** Stand-in for /tours until the catalog page lands (next commit). */
function CatalogStub() {
  const { t } = useTranslation()
  useDocumentTitle(t('catalog.title'))
  return <Typography.Title level={1}>{t('catalog.title')}</Typography.Title>
}

export const routes: RouteObject[] = [
  {
    element: <PublicLayout />,
    errorElement: <RouteErrorPage />,
    children: [
      // No home page yet: the catalog is the start page.
      { index: true, element: <Navigate to="/tours" replace /> },
      { path: 'tours', element: <CatalogStub /> },
      { path: 'tours/:id', element: <TourDetailsPlaceholder /> },
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
