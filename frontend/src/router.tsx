import { createBrowserRouter, type RouteObject } from 'react-router'
import { AuthRoot } from './features/auth/AuthProvider'
import { RequireAuth } from './features/auth/RequireAuth'
import { STAFF_ROLES } from './features/auth/redirect'
import { PublicLayout } from './layouts/PublicLayout'
import { LoginPage } from './pages/auth/LoginPage'
import { RegisterPage } from './pages/auth/RegisterPage'
import { BookingPage } from './pages/booking/BookingPage'
import { CatalogPage } from './pages/catalog/CatalogPage'
import { HomePage } from './pages/home/HomePage'
import { AboutPage } from './pages/info/AboutPage'
import { ContactsPage } from './pages/info/ContactsPage'
import { FaqPage } from './pages/info/FaqPage'
import { PrivacyPage, TermsPage } from './pages/info/LegalPages'
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
          { path: 'cabinet', element: <RequireAuth roles={['client']}><PlaceholderPage page="cabinet" /></RequireAuth> },
          { path: 'cabinet/orders', element: <RequireAuth roles={['client']}><PlaceholderPage page="cabinetOrders" /></RequireAuth> },
          // The back office comes in feature/frontend-backoffice.
          { path: 'office', element: <RequireAuth roles={STAFF_ROLES}><PlaceholderPage page="office" /></RequireAuth> },
          // Static information pages (spec 14): texts in i18n, contacts from the admin's settings.
          { path: 'about', element: <AboutPage /> },
          { path: 'contacts', element: <ContactsPage /> },
          { path: 'terms', element: <TermsPage /> },
          { path: 'privacy', element: <PrivacyPage /> },
          { path: 'faq', element: <FaqPage /> },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
]

export function createAppRouter() {
  return createBrowserRouter(routes)
}
