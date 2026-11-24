import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import uk from './uk.json'

// Ukrainian only for now; en.json comes in feature/i18n-en. Every UI text goes through a key.
export const defaultNS = 'translation'
export const resources = { uk: { translation: uk } } as const

void i18n.use(initReactI18next).init({
  resources,
  lng: 'uk',
  fallbackLng: 'uk', // i18next 27 no longer falls back to anything by default
  defaultNS,
  interpolation: { escapeValue: false }, // React already escapes
  initAsync: false, // resources are bundled, so init synchronously (also keeps tests simple)
})

export default i18n
