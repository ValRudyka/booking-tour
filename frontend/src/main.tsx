import { Result } from 'antd'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { AppProviders } from './App'
import i18n from './i18n'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppProviders>
      <Result title={i18n.t('app.loading')} />
    </AppProviders>
  </StrictMode>,
)
