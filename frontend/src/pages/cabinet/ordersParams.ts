import type { OrderGroup } from '../../api/types'

// «Мої замовлення» state in the URL (?group=&page=), under the API's own parameter names like the
// catalog. Unknown values fall back to the defaults instead of breaking the page.

/** Tab order on the page; «Усі» is the default and comes first. */
export const ORDER_GROUPS: readonly OrderGroup[] = ['all', 'active', 'completed', 'cancelled']

export interface OrdersParams {
  group: OrderGroup
  page: number
}

export function readOrdersParams(search: URLSearchParams): OrdersParams {
  const group = search.get('group')
  const page = search.get('page')
  return {
    group: ORDER_GROUPS.includes(group as OrderGroup) ? group as OrderGroup : 'all',
    page: page && /^\d+$/.test(page) && Number(page) > 0 ? Number(page) : 1,
  }
}

/** Defaults are left out, so the plain /cabinet/orders stays the canonical address. */
export function toOrdersSearch({ group, page }: OrdersParams): URLSearchParams {
  const search = new URLSearchParams()
  if (group !== 'all') search.set('group', group)
  if (page > 1) search.set('page', String(page))
  return search
}
