import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router/dom'
import { createQueryClient } from './api/queryClient'
import { AppProviders } from './App'
import './i18n'
import './index.css'
import { createAppRouter } from './router'

const queryClient = createQueryClient()
const router = createAppRouter()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppProviders queryClient={queryClient}>
      <RouterProvider router={router} />
    </AppProviders>
  </StrictMode>,
)
