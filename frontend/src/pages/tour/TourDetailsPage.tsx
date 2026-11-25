import { Breadcrumb, Button, Col, Flex, Grid, Result, Row, Skeleton, Tabs, Tag, Typography } from 'antd'
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useParams } from 'react-router'
import { ApiError, mediaUrl } from '../../api/client'
import { useTour } from '../../api/tour'
import type { TourDetail } from '../../api/types'
import { ApiErrorState } from '../../components/ApiErrorState'
import { BackToCatalogButton } from '../../components/BackToCatalogButton'
import { PhotoPlaceholder } from '../../components/PhotoPlaceholder'
import { PhotoViewer } from '../../components/PhotoViewer'
import { StarIcons } from '../../components/StarIcons'
import type { TourLinkState } from '../../components/TourCard'
import { useStartBooking } from '../../features/booking/startBooking'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { mealLabel } from '../../i18n/labels'
import { formatRating, nearestBookableDate } from '../../utils/format'
import { BookingPanel, MobileBookingBar } from './BookingPanel'
import { TourReviews } from './TourReviews'
import { DescriptionTab, HotelTab, ProgramTab } from './TourSections'
import { parseTourId, type TourTab, useTourTab } from './tourParams'
import './TourDetailsPage.css'

/** /tours/:id — the tour page (spec docs/frontend/02-tour-details-page.md). */
export function TourDetailsPage() {
  const { id } = useParams()
  const tourId = parseTourId(id)
  if (tourId === null) return <TourNotFound />
  return <TourDetails key={tourId} tourId={tourId} />
}

function TourNotFound() {
  const { t } = useTranslation()
  useDocumentTitle(t('tourPage.notFoundTitle'))
  return (
    <Result status="404" title={<h1 className="result-title">{t('tourPage.notFoundTitle')}</h1>}
      subTitle={t('tourPage.notFoundText')} extra={<BackToCatalogButton />} />
  )
}

function TourDetailsSkeleton() {
  return (
    <div aria-busy="true" data-testid="tour-skeleton">
      <Skeleton active={false} title={{ width: '60%' }} paragraph={{ rows: 1 }} />
      <Row gutter={[24, 24]}>
        <Col xs={24} lg={16}>
          <Skeleton.Node active={false} style={{ width: '100%', height: 360 }} />
          <Skeleton active={false} paragraph={{ rows: 5 }} />
        </Col>
        <Col xs={24} lg={8}><Skeleton active={false} paragraph={{ rows: 7 }} /></Col>
      </Row>
    </div>
  )
}

function TourDetails({ tourId }: { tourId: number }) {
  const { t } = useTranslation()
  const tour = useTour(tourId)
  useDocumentTitle(tour.data?.title_uk ?? t('app.loading'))

  if (tour.isPending) return <TourDetailsSkeleton />
  if (tour.isError) {
    if (tour.error instanceof ApiError && tour.error.kind === 'not_found') return <TourNotFound />
    return <ApiErrorState error={tour.error} onRetry={() => void tour.refetch()} title={t('tourPage.loadFailed')} />
  }
  return <TourContent tour={tour.data} />
}

function TourContent({ tour }: { tour: TourDetail }) {
  const { t } = useTranslation()
  const location = useLocation()
  const screens = Grid.useBreakpoint()
  const isDesktop = Boolean(screens.lg)
  const { tab, setTab, reviewsPage, setReviewsPage } = useTourTab()
  const tabsRef = useRef<HTMLDivElement>(null)
  const startBooking = useStartBooking()
  const firstDate = nearestBookableDate(tour.departure_from, tour.departure_to)
  const [date, setDate] = useState<string | null>(firstDate)
  const book = () => { if (date) startBooking(tour.id, date) }

  // «Каталог» returns to the filters the visitor came from (passed by TourCard), else /tours.
  const catalogSearch = (location.state as TourLinkState | null)?.catalogSearch ?? ''
  const photos = tour.images.map((image, n) => ({
    src: mediaUrl(image.url)!, alt: t('tourPage.photoAlt', { title: tour.title_uk, n: n + 1 }),
  }))

  const tabs: { key: TourTab; label: string; children: React.ReactNode }[] = [
    { key: 'description', label: t('tourPage.tabDescription'), children: <DescriptionTab tour={tour} /> },
    { key: 'program', label: t('tourPage.tabProgram'), children: <ProgramTab tour={tour} /> },
    { key: 'hotel', label: t('tourPage.tabHotel'), children: <HotelTab tour={tour} /> },
    {
      key: 'reviews', label: t('tourPage.tabReviews', { count: tour.reviews_count ?? 0 }),
      children: <TourReviews tour={tour} page={reviewsPage} onPageChange={setReviewsPage}
        active={tab === 'reviews'} />,
    },
  ]
  const openReviews = () => {
    setTab('reviews')
    tabsRef.current?.scrollIntoView({ block: 'start' })
  }
  const panel = (
    <BookingPanel tour={tour} firstDate={firstDate} date={date} onDateChange={setDate} onBook={book} />
  )

  return (
    <div className={isDesktop ? undefined : 'tour-page-mobile'}>
      <nav aria-label={t('tourPage.breadcrumb')}>
        <Breadcrumb items={[
          { title: <Link to={`/tours${catalogSearch}`}>{t('tourPage.catalog')}</Link> },
          { title: <Link to={`/tours?country_id=${tour.country.id}`}>{tour.country.name_uk}</Link> },
          { title: <Link to={`/tours?country_id=${tour.country.id}&resort_id=${tour.resort.id}`}>{tour.resort.name_uk}</Link> },
          { title: <span aria-current="page">{tour.title_uk}</span> },
        ]} />
      </nav>

      <Typography.Title level={1} className="tour-title">{tour.title_uk}</Typography.Title>
      <TourHeaderLine tour={tour} onOpenReviews={openReviews} />

      <Row gutter={[24, 24]} className="tour-body">
        <Col xs={24} lg={16}>
          <section aria-label={t('tourPage.gallery')} className="tour-gallery">
            {photos.length > 0 ? <PhotoViewer photos={photos} variant="gallery" /> : <PhotoPlaceholder height={360} />}
          </section>
          {!isDesktop && <div className="tour-panel-mobile">{panel}</div>}
          <div ref={tabsRef}>
            <Tabs activeKey={tab} onChange={(key) => setTab(key as TourTab)} items={tabs}
              aria-label={t('tourPage.tabs')} className="tour-tabs" />
          </div>
        </Col>
        {isDesktop && <Col lg={8}><div className="tour-panel-sticky">{panel}</div></Col>}
      </Row>

      {!isDesktop && <MobileBookingBar tour={tour} date={date} onBook={book} />}
    </div>
  )
}

/** Hotel, stars, meal plan, «Рейтинг готелю … · N відгуків про тур». The rating covers every
 * published review of the hotel; the count only this tour's (they are different numbers). */
function TourHeaderLine({ tour, onOpenReviews }: { tour: TourDetail; onOpenReviews: () => void }) {
  const { t } = useTranslation()
  const { hotel } = tour
  return (
    <Flex wrap align="center" gap={8} className="tour-header-line">
      <Typography.Text strong>{hotel.name}</Typography.Text>
      {hotel.stars ? <StarIcons value={hotel.stars} label={t('tour.stars', { count: hotel.stars })} /> : null}
      {tour.meal_plan && <Tag>{mealLabel(t, tour.meal_plan)}</Tag>}
      <Typography.Text>
        {hotel.rating_avg !== null ? t('tourPage.hotelRating', { rating: formatRating(hotel.rating_avg) })
          : t('tour.noReviews')}
      </Typography.Text>
      {(tour.reviews_count ?? 0) > 0 && (
        <>
          <span aria-hidden>·</span>
          <Button type="link" className="tour-reviews-link" onClick={onOpenReviews}>
            {t('tourPage.reviewsLink', { count: tour.reviews_count ?? 0 })}
          </Button>
        </>
      )}
    </Flex>
  )
}
