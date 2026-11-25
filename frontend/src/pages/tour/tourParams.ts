import { useSearchParams } from 'react-router'

export const TOUR_TABS = ['description', 'program', 'hotel', 'reviews'] as const
export type TourTab = (typeof TOUR_TABS)[number]
export const DEFAULT_TAB: TourTab = 'description'

/** /tours/:id must be a positive whole number; anything else is a 404 without a request. */
export function parseTourId(raw: string | undefined): number | null {
  if (!raw || !/^\d{1,9}$/.test(raw)) return null
  const id = Number(raw)
  return id > 0 ? id : null
}

export function readTab(params: URLSearchParams): TourTab {
  return TOUR_TABS.find((tab) => tab === params.get('tab')) ?? DEFAULT_TAB
}

export function readReviewsPage(params: URLSearchParams): number {
  const raw = params.get('reviews_page')
  return raw && /^\d{1,6}$/.test(raw) && Number(raw) > 0 ? Number(raw) : 1
}

/**
 * The open tab lives in the URL (?tab=reviews), so a link can open the reviews directly. Tab
 * changes REPLACE the history entry: Back from the tour page goes straight to the catalog
 * instead of stepping through every tab the visitor clicked.
 */
export function useTourTab() {
  const [params, setParams] = useSearchParams()
  const tab = readTab(params)
  const reviewsPage = readReviewsPage(params)

  const write = (next: { tab: TourTab; reviewsPage?: number }) => {
    const out = new URLSearchParams()
    if (next.tab !== DEFAULT_TAB) out.set('tab', next.tab)
    if (next.tab === 'reviews' && next.reviewsPage && next.reviewsPage > 1) {
      out.set('reviews_page', String(next.reviewsPage))
    }
    setParams(out, { replace: true, preventScrollReset: true })
  }
  return {
    tab,
    reviewsPage,
    setTab: (next: TourTab) => write({ tab: next }),
    setReviewsPage: (page: number) => write({ tab: 'reviews', reviewsPage: page }),
  }
}
