import { DeleteOutlined } from '@ant-design/icons'
import { App, Button, Col, Empty, Pagination, Row, Skeleton, Space, Typography } from 'antd'
import { useTranslation } from 'react-i18next'
import { useNavigate, useSearchParams } from 'react-router'
import { ApiError } from '../../api/client'
import { FAVORITES_PAGE_SIZE, useFavorites, useToggleFavorite } from '../../api/favorites'
import type { FavoriteTour } from '../../api/types'
import { ApiErrorState } from '../../components/ApiErrorState'
import { TourCard } from '../../components/TourCard'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import './CabinetPages.css'

/** Narrower than the catalog grid: the cabinet menu takes the left column. */
const CARD_COLS = { xs: 24, sm: 12, xl: 8 }

/** /cabinet/favorites (spec 08 §5): the client's «Обране», newest first, server pages in ?page=. */
export function FavoritesPage() {
  const { t } = useTranslation()
  const title = t('favorites.title')
  useDocumentTitle(title)
  const navigate = useNavigate()
  const [search, setSearch] = useSearchParams()
  const page = Math.max(1, Number.parseInt(search.get('page') ?? '1', 10) || 1)
  const favorites = useFavorites(page)
  const data = favorites.data

  return (
    <section aria-labelledby="favorites-title">
      <h1 id="favorites-title" className="cabinet-title">{title}</h1>
      {favorites.isError && !data ? (
        <ApiErrorState error={favorites.error} onRetry={() => void favorites.refetch()} title={title} />
      ) : !data ? (
        <Skeleton active={false} paragraph={{ rows: 6 }} />
      ) : data.total === 0 ? (
        <Empty description={
          <Space orientation="vertical" size={4}>
            <Typography.Text strong>{t('favorites.emptyTitle')}</Typography.Text>
            <Typography.Text>{t('favorites.emptyText')}</Typography.Text>
          </Space>
        }>
          <Button type="primary" onClick={() => navigate('/tours')}>{t('app.toCatalog')}</Button>
        </Empty>
      ) : (
        <>
          <Row gutter={[16, 16]}>
            {data.items.map((tour) => (
              <Col key={tour.id} {...CARD_COLS}>
                <TourCard tour={tour} notForSale={!tour.for_sale} favorite={false}
                  footer={<RemoveButton tour={tour} />} />
              </Col>
            ))}
          </Row>
          {data.total > FAVORITES_PAGE_SIZE && (
            <Pagination className="orders-pagination" current={page} pageSize={FAVORITES_PAGE_SIZE}
              total={data.total} showSizeChanger={false}
              onChange={(next) => setSearch(next > 1 ? { page: String(next) } : {})} />
          )}
        </>
      )}
    </section>
  )
}

function RemoveButton({ tour }: { tour: FavoriteTour }) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const toggle = useToggleFavorite()
  return (
    <Button block icon={<DeleteOutlined aria-hidden />} loading={toggle.isPending}
      aria-label={t('favorites.removeOf', { title: tour.title_uk })}
      onClick={() => toggle.mutate({ tourId: tour.id, add: false }, {
        onSuccess: () => void message.success(t('favorites.removed')),
        onError: (error) => void message.error(error instanceof ApiError ? error.message : t('errors.generic')),
      })}>
      {t('favorites.remove')}
    </Button>
  )
}
