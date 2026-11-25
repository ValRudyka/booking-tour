import { FilterOutlined } from '@ant-design/icons'
import { Button, Card, Col, Drawer, Empty, Flex, Grid, Pagination, Row, Select, Typography } from 'antd'
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useTours } from '../../api/catalog'
import { ApiErrorState } from '../../components/ApiErrorState'
import { TourCard } from '../../components/TourCard'
import { TourCardSkeleton } from '../../components/TourCardSkeleton'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { CatalogFilters, SEARCH_DEBOUNCE_MS } from './CatalogFilters'
import {
  countActiveFilters, EMPTY_FILTERS, type CatalogSort, PAGE_SIZE, SORTS, toApiParams, type CatalogFilters as Filters,
} from './catalogParams'
import { useCatalogParams } from './useCatalogParams'
import './CatalogPage.css'

const SKELETON_COUNT = 6
const CARD_COLS = { xs: 24, md: 12, xl: 8 } as const // 3 cards, then 2, then 1 per row

/** /tours — the public tour catalog (spec 01-catalog-page.md, ТЗ 4.4 step 2). */
export function CatalogPage() {
  const { t } = useTranslation()
  useDocumentTitle(t('catalog.title'))
  const { state, setFilters, replaceFilters, setSort, setPage, reset } = useCatalogParams()
  const tours = useTours(toApiParams(state))
  const queryClient = useQueryClient()
  const screens = Grid.useBreakpoint()
  const isDesktop = Boolean(screens.lg)
  const sortId = useId()

  // Mobile: filters are edited in a Drawer on a draft and applied with one button.
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [draft, setDraft] = useState<Filters>(state.filters)
  const openDrawer = () => {
    setDraft(state.filters)
    setDrawerOpen(true)
  }
  const patchDraft = (patch: Partial<Filters>) => setDraft((current) => {
    const next = { ...current, ...patch }
    if ('country_id' in patch && patch.country_id !== current.country_id) next.resort_id = undefined
    return next
  })

  const data = tours.data
  const lastPage = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1
  // An old link may point past the last page (fewer tours now): go to the last one.
  useEffect(() => {
    if (data && data.items.length === 0 && data.total > 0 && state.page > lastPage) {
      setPage(lastPage, true)
    }
  }, [data, lastPage, state.page, setPage])

  const changePage = (page: number) => {
    setPage(page)
    window.scrollTo(0, 0)
  }

  const resetButton = <Button onClick={reset}>{t('filters.reset')}</Button>
  const activeCount = countActiveFilters(state.filters)

  return (
    <>
      <Typography.Title level={1} className="catalog-title">{t('catalog.title')}</Typography.Title>

      <Row gutter={[24, 24]} wrap={!isDesktop}>
        {isDesktop && (
          <Col flex="280px">
            <Card title={<h2 className="catalog-filters-title">{t('filters.title')}</h2>}
              extra={activeCount > 0 ? resetButton : undefined} size="small">
              <CatalogFilters value={state.filters} onChange={setFilters}
                debounceMs={SEARCH_DEBOUNCE_MS} idPrefix="filter" />
            </Card>
          </Col>
        )}

        <Col flex="auto" style={{ minWidth: 0 }}>
          <section aria-label={t('catalog.results')} aria-busy={tours.isFetching}>
            <Flex justify="space-between" align="center" wrap gap={12} className="catalog-toolbar">
              <Flex align="center" gap={12} wrap>
                {!isDesktop && (
                  <Button icon={<FilterOutlined aria-hidden />} onClick={openDrawer}>
                    {activeCount > 0 ? t('filters.openWithCount', { count: activeCount }) : t('filters.open')}
                  </Button>
                )}
                <Typography.Text strong aria-live="polite">
                  {data ? t('catalog.found', { count: data.total }) : ' '}
                </Typography.Text>
              </Flex>
              <Flex align="center" gap={8}>
                <label htmlFor={sortId}>{t('catalog.sort')}</label>
                <Select id={sortId} value={state.sort} onChange={(sort: CatalogSort) => setSort(sort)}
                  style={{ minWidth: 220 }}
                  options={SORTS.map((sort) => ({ value: sort, label: t(`catalog.sortOptions.${sort}`) }))} />
              </Flex>
            </Flex>

            <CatalogResults
              isPending={tours.isPending}
              error={tours.isError ? tours.error : null}
              // Retry everything on screen: when the API was down, the filter lists failed too.
              onRetry={() => void queryClient.refetchQueries({ type: 'active' })}
              items={data?.items ?? []}
              total={data?.total ?? 0}
              resetButton={resetButton}
            />

            {data && data.total > PAGE_SIZE && (
              <nav aria-label={t('catalog.pagination')} className="catalog-pagination">
                <Pagination current={state.page} total={data.total} pageSize={PAGE_SIZE}
                  showSizeChanger={false} onChange={changePage} align="center" />
              </nav>
            )}
          </section>
        </Col>
      </Row>

      {!isDesktop && (
        <Drawer title={t('filters.title')} placement="left" size={340} open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          footer={(
            <Flex gap={8} justify="flex-end">
              <Button onClick={() => setDraft(EMPTY_FILTERS)}>{t('filters.reset')}</Button>
              <Button type="primary" onClick={() => {
                replaceFilters(draft)
                setDrawerOpen(false)
              }}>
                {t('filters.apply')}
              </Button>
            </Flex>
          )}>
          <CatalogFilters value={draft} onChange={patchDraft} debounceMs={0} idPrefix="drawer-filter" />
        </Drawer>
      )}
    </>
  )
}

interface ResultsProps {
  isPending: boolean
  error: Error | null
  onRetry: () => void
  items: NonNullable<ReturnType<typeof useTours>['data']>['items']
  total: number
  resetButton: React.ReactNode
}

function CatalogResults({ isPending, error, onRetry, items, total, resetButton }: ResultsProps) {
  const { t } = useTranslation()

  if (error) {
    return <ApiErrorState error={error} onRetry={onRetry} title={t('errors.loadFailed')} />
  }
  if (isPending) {
    return (
      <Row gutter={[16, 16]}>
        {Array.from({ length: SKELETON_COUNT }, (_, index) => (
          <Col key={index} {...CARD_COLS}><TourCardSkeleton /></Col>
        ))}
      </Row>
    )
  }
  if (total === 0) {
    return <Empty description={t('catalog.empty')} className="catalog-empty">{resetButton}</Empty>
  }
  return (
    <Row gutter={[16, 16]}>
      {items.map((tour) => (
        <Col key={tour.id} {...CARD_COLS}><TourCard tour={tour} /></Col>
      ))}
    </Row>
  )
}
