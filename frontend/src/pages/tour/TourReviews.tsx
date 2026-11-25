import { Empty, Flex, List, Pagination, Skeleton, Typography } from 'antd'
import { useTranslation } from 'react-i18next'
import { mediaUrl } from '../../api/client'
import { REVIEWS_PAGE_SIZE, useTourReviews } from '../../api/tour'
import type { PublicReview, TourDetail } from '../../api/types'
import { ApiErrorState } from '../../components/ApiErrorState'
import { PhotoViewer } from '../../components/PhotoViewer'
import { StarIcons } from '../../components/StarIcons'
import { formatRating, splitYearMonth } from '../../utils/format'

interface Props {
  tour: TourDetail
  page: number
  onPageChange: (page: number) => void
  /** Only while the tab is open: reviews are loaded lazily (spec §4). */
  active: boolean
}

/** «Відгуки (N)»: published reviews of this tour, newest first, 10 per page from the server. */
export function TourReviews({ tour, page, onPageChange, active }: Props) {
  const { t } = useTranslation()
  const reviews = useTourReviews(tour.id, page, active)

  const summary = (
    <Flex wrap gap={24} className="reviews-summary">
      <div>
        <Typography.Text type="secondary">{t('reviews.hotelScore')}</Typography.Text>
        <div className="reviews-score">
          {tour.hotel.rating_avg !== null ? t('reviews.scoreValue', { rating: formatRating(tour.hotel.rating_avg) }) : '—'}
        </div>
      </div>
      <div>
        <Typography.Text type="secondary">{t('reviews.serviceScore')}</Typography.Text>
        <div className="reviews-score">
          {tour.service_rating_avg !== null && tour.service_rating_avg !== undefined
            ? t('reviews.scoreValue', { rating: formatRating(tour.service_rating_avg) }) : '—'}
        </div>
      </div>
      <div>
        <Typography.Text type="secondary">{t('reviews.summary')}</Typography.Text>
        <div className="reviews-score">{t('reviews.count', { count: tour.reviews_count ?? 0 })}</div>
      </div>
    </Flex>
  )

  if (reviews.isError) {
    return <ApiErrorState error={reviews.error} onRetry={() => void reviews.refetch()} title={t('reviews.loadFailed')} />
  }
  if (reviews.isPending) {
    return <div aria-busy="true"><Skeleton active={false} paragraph={{ rows: 6 }} /></div>
  }
  const data = reviews.data
  if (data.total === 0) {
    return <Empty description={t('reviews.empty')} />
  }
  return (
    <Flex vertical gap={16} aria-busy={reviews.isFetching}>
      {summary}
      <List itemLayout="vertical" dataSource={data.items} rowKey="id"
        renderItem={(review) => <List.Item><ReviewItem review={review} /></List.Item>} />
      {data.total > REVIEWS_PAGE_SIZE && (
        <nav aria-label={t('reviews.pagination')}>
          <Pagination current={page} total={data.total} pageSize={REVIEWS_PAGE_SIZE}
            showSizeChanger={false} align="center" onChange={onPageChange} />
        </nav>
      )}
    </Flex>
  )
}

function ReviewItem({ review }: { review: PublicReview }) {
  const { t } = useTranslation()
  const { year, month } = splitYearMonth(review.trip_month)
  const photos = review.photos.map((photo, n) => ({
    src: mediaUrl(photo.url)!, alt: t('reviews.photoAlt', { author: review.author, n: n + 1 }),
  }))
  const score = (label: string, value: number) => (
    <span className="review-score">
      <span aria-hidden>{label}</span>{' '}
      <StarIcons value={value} outOf={5} label={t('reviews.stars', { label, value })} />
    </span>
  )
  return (
    <article className="review">
      <Flex wrap justify="space-between" gap={8}>
        <h3 className="review-author">{review.author}</h3>
        <Typography.Text type="secondary">
          {t('reviews.trip', { month: `${t(`months.${month}` as 'months.1')} ${year}` })}
        </Typography.Text>
      </Flex>
      <Flex wrap gap={16} className="review-scores">
        {score(t('reviews.hotel'), review.hotel_rating)}
        {score(t('reviews.service'), review.service_rating)}
      </Flex>
      {review.positive && (
        <p className="review-text"><strong>{t('reviews.positive')}:</strong> {review.positive}</p>
      )}
      {review.negative && (
        <p className="review-text"><strong>{t('reviews.negative')}:</strong> {review.negative}</p>
      )}
      {photos.length > 0 && <PhotoViewer photos={photos} variant="thumbs" />}
    </article>
  )
}
