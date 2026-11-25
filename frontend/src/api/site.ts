import { useQuery } from '@tanstack/react-query'
import { api } from './client'
import type { SiteContacts } from './types'

/** Support contacts from the admin's settings (form 4.6.4.1, fields 8–9): footer, «Забули пароль?». */
export function useSiteContacts() {
  return useQuery({
    queryKey: ['site', 'contacts'],
    queryFn: async () => (await api.get<SiteContacts>('/site/contacts')).data,
    staleTime: 10 * 60_000,
  })
}
