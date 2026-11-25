import { createBrowserRouter, Navigate, type RouteObject } from 'react-router'
import { AuthRoot } from './features/auth/AuthProvider'
import { RequireAuth } from './features/auth/RequireAuth'
import { STAFF_ROLES } from './features/auth/redirect'
import { CabinetLayout } from './layouts/CabinetLayout'
import { PublicLayout } from './layouts/PublicLayout'
import { LoginPage } from './pages/auth/LoginPage'
import { RegisterPage } from './pages/auth/RegisterPage'
import { BookingPage } from './pages/booking/BookingPage'
import { OrderDetailsPage } from './pages/cabinet/OrderDetailsPage'
import { OrdersPage } from './pages/cabinet/OrdersPage'
import { ReviewPage } from './pages/cabinet/ReviewPage'
import { CatalogPage } from './pages/catalog/CatalogPage'
import { HomePage } from './pages/home/HomePage'
import { NotFoundPage } from './pages/NotFoundPage'
import { PlaceholderPage } from './pages/PlaceholderPage'
import { PayPage } from './pages/payment/PayPage'
import { PaymentCancelPage, PaymentSuccessPage } from './pages/payment/PaymentResultPages'
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
          { index: true, element: <HomePage /> },
          { path: 'tours', element: <CatalogPage /> },
          { path: 'tours/:id', element: <TourDetailsPage /> },
          { path: 'login', element: <LoginPage /> },
          { path: 'register', element: <RegisterPage /> },
          // Orders are a client's (backend require_roles): staff see 403 here.
          { path: 'booking/:tourId', element: <RequireAuth roles={['client']}><BookingPage /></RequireAuth> },
          // Payment (spec 05): the client's own orders only (someone else's is a 404 from the API).
          { path: 'orders/:id/pay', element: <RequireAuth roles={['client']}><PayPage /></RequireAuth> },
          { path: 'payment/success', element: <RequireAuth roles={['client']}><PaymentSuccessPage /></RequireAuth> },
          { path: 'payment/cancel', element: <RequireAuth roles={['client']}><PaymentCancelPage /></RequireAuth> },
          // The client cabinet (spec 06). Only sections with a backend API are listed.
          {
            path: 'cabinet',
            element: <RequireAuth roles={['client']}><CabinetLayout /></RequireAuth>,
            children: [
              { index: true, element: <Navigate to="orders" replace /> },
              { path: 'orders', element: <OrdersPage /> },
              { path: 'orders/:id', element: <OrderDetailsPage /> },
              { path: 'orders/:id/review', element: <ReviewPage /> },
              // The profile API exists (GET/PATCH /me, passwords, passports); its page is spec 08.
              { path: 'profile', element: <PlaceholderPage page="profile" /> },
            ],
          },
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
