import { useEffect } from 'react'
import { SITE_NAME } from '../site'

/** Sets the browser tab title: "Каталог турів — Хвиля". */
export function useDocumentTitle(title: string) {
  useEffect(() => {
    document.title = title ? `${title} — ${SITE_NAME}` : SITE_NAME
  }, [title])
}
