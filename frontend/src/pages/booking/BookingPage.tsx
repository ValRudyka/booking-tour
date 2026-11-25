import { useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { Alert, App, Button, Col, Flex, Form, Grid, Result, Row, Skeleton, Steps, Typography } from 'antd'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams, useSearchParams } from 'react-router'
import { ApiError } from '../../api/client'
import {
  cancelOrder, confirmOrder, createOrder, fetchCheckoutOrders, fetchOrder, quoteOrder, updateOrder,
  useInsuranceTypes, useSavedPassports, useTransferTypes,
} from '../../api/orders'
import { useTour } from '../../api/tour'
import type { OrderUpdate, TourDetail, User } from '../../api/types'
import { ApiErrorState } from '../../components/ApiErrorState'
import { BackToCatalogButton } from '../../components/BackToCatalogButton'
import { HelpGuide } from '../../components/HelpGuide'
import { useAuth } from '../../features/auth/useAuth'
import { clearDraft, loadDraft, saveDraft } from '../../features/booking/bookingDraft'
import {
  isHoldExpired, isMaintenance, isSeatsError, isTourUnavailable, serverText, touristIssues,
} from '../../features/booking/bookingErrors'
import { returnDate } from '../../features/booking/bookingRules'
import { payPath, type PayPageState } from '../../features/booking/payHandOff'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { formatDate, nearestBookableDate } from '../../utils/format'
import { BookingSummary } from './BookingSummary'
import {
  draftNeedsNumbers, initialValues, ISO, resizeTourists, toDraft, toTouristsIn, type BookingOrder,
  type BookingValues,
} from './bookingForm'
import { useHoldRemaining } from './holdClock'
import { HoldTimer } from './HoldTimer'
import { StepReview } from './StepReview'
import { StepServices } from './StepServices'
import { StepTourists } from './StepTourists'
import { StepTrip } from './StepTrip'
import './BookingPage.css'

const QUOTE_STALE_MS = 30_000

/** antd's validateFields rejects with {errorFields, ...} when a field is invalid. */
function isFormValidation(error: unknown): boolean {
  return !!error && typeof error === 'object' && 'errorFields' in error
}
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/

/**
 * /booking/:tourId?date=YYYY-MM-DD — the booking wizard (spec docs/frontend/04-booking-page.md,
 * ТЗ 4.5.3). Clients only (RequireAuth in router.tsx; staff get 403).
 *
 * API sequence (backend routers/orders.py):
 *  - step 1, while choosing: POST /orders/quote (price preview; nothing saved, no seats held);
 *  - step 1 «Далі»: POST /orders -> «Оформлення», seats held until hold_expires_at (20 min by
 *    default, never extended); later count changes are a PATCH, a new date cancels and re-creates;
 *  - step 2 «Далі»: PATCH tourists (all passport rules checked by the server);
 *  - step 3: PATCH for each service / promo change;
 *  - step 4: POST /orders/{id}/confirm -> price frozen, «Очікує оплати», then /orders/:id/pay (spec 05).
 */
export function BookingPage() {
  const { tourId: rawId } = useParams()
  const tourId = /^\d+$/.test(rawId ?? '') ? Number(rawId) : null
  const { user } = useAuth()
  const tour = useTour(tourId ?? 0)
  const { t } = useTranslation()
  useDocumentTitle(t('checkout.title'))

  if (tourId === null) return <Unavailable />
  if (tour.isPending || !user) return <Skeleton active={false} paragraph={{ rows: 8 }} />
  if (tour.isError) {
    if (tour.error instanceof ApiError && tour.error.kind === 'not_found') return <Unavailable />
    return <ApiErrorState error={tour.error} onRetry={() => void tour.refetch()} title={t('checkout.states.loadFailed')} />
  }
  return <BookingWizard key={`${user.id}.${tourId}`} tour={tour.data} user={user} refetchTour={tour.refetch} />
}

function Unavailable() {
  const { t } = useTranslation()
  return (
    <Result status="warning" title={<h1 className="result-title">{t('checkout.states.unavailableTitle')}</h1>}
      subTitle={t('checkout.states.unavailableText')} extra={<BackToCatalogButton />} />
  )
}

type Phase = 'restoring' | 'ready' | 'expired' | 'unavailable'
interface ActionError { error: unknown; retry?: () => void }

function BookingWizard({ tour, user, refetchTour }: {
  tour: TourDetail
  user: User
  refetchTour: () => Promise<{ data?: TourDetail }>
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { modal } = App.useApp()
  const [params] = useSearchParams()
  const screens = Grid.useBreakpoint()
  const compact = !screens.md
  const [form] = Form.useForm<BookingValues>()

  const [phase, setPhase] = useState<Phase>('restoring')
  const [step, setStep] = useState(0)
  const [order, setOrder] = useState<BookingOrder | null>(null)
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(false)   // a double click must not send a second request
  // A new step starts at its top: «Далі» sits at the bottom of a long form (many tourists), and
  // without this the next step would open half scrolled. Not on the first render (restore).
  const stepsRef = useRef<HTMLDivElement>(null)
  const shownStep = useRef<number | null>(null)
  useEffect(() => {
    if (shownStep.current !== null && shownStep.current !== step) stepsRef.current?.scrollIntoView({ block: 'start' })
    shownStep.current = step
  }, [step])
  const [actionError, setActionError] = useState<ActionError | null>(null)
  const [promoError, setPromoError] = useState<string | null>(null)
  const [resumed, setResumed] = useState<{ number: string; date: string } | null>(null)
  const [reenterNumbers, setReenterNumbers] = useState(false)

  const insurance = useInsuranceTypes()
  const transfer = useTransferTypes()
  const passports = useSavedPassports()

  // Bookable start dates: from tomorrow (Kyiv) within the tour's range, as the backend checks.
  const firstDate = nearestBookableDate(tour.departure_from, tour.departure_to)
  const lastDate = tour.departure_to
  const bookable = (date: string | null | undefined): date is string =>
    !!date && DATE_RE.test(date) && firstDate !== null && date >= firstDate && date <= lastDate

  // ---------- the draft (sessionStorage, no passport numbers)
  const persist = useCallback((nextStep: number, nextOrder: BookingOrder | null) => {
    saveDraft(user.id, tour.id, toDraft(form.getFieldsValue(true) as BookingValues, nextStep, nextOrder?.id ?? null))
  }, [form, user.id, tour.id])
  useEffect(() => {
    if (phase === 'ready' || phase === 'expired') persist(step, order)
  }, [phase, step, order, persist])

  // ---------- restore: the order on the server, the draft, or a fresh start
  useEffect(() => {
    let cancelled = false
    const urlDate = params.get('date')
    void (async () => {
      const draft = loadDraft(user.id, tour.id)
      let restored: BookingOrder | null = null
      let resumedHere = false
      try {
        if (draft?.orderId) {
          restored = await fetchOrder(draft.orderId)
        } else {
          // Resume an unfinished booking of THIS tour only (lost draft: another tab, closed tab).
          const page = await fetchCheckoutOrders()
          const found = page.items.find((o) => o.tour_id === tour.id && o.hold_expires_at
            && Date.parse(o.hold_expires_at) > Date.now())
          if (found) {
            restored = await fetchOrder(found.id)
            resumedHere = true
          }
        }
      } catch (error) {
        // 404 (not this client's order any more) or a failed lookup: start without it.
        if (isMaintenance(error)) setActionError({ error })
        restored = null
      }
      if (cancelled) return
      const held = restored?.status === 'checkout' && !!restored.hold_expires_at
        && Date.parse(restored.hold_expires_at) > Date.now()
      if (restored?.status === 'awaiting_payment') {
        clearDraft(user.id, tour.id)
        void navigate(payPath(restored.id), { replace: true })
        return
      }
      const startDate = bookable(urlDate) ? urlDate : bookable(draft?.date) ? draft.date : firstDate
      if (held && restored) {
        form.setFieldsValue(initialValues(restored, draft, null))
        setOrder(restored)
        setReenterNumbers(draftNeedsNumbers(draft, restored))
        setStep(resumedHere ? 1 : Math.max(1, Math.min(draft?.step ?? 1, 3)))
        if (resumedHere) setResumed({ number: restored.number, date: restored.start_date })
        setPhase('ready')
        return
      }
      form.setFieldsValue(initialValues(null, draft, startDate))
      setReenterNumbers(draftNeedsNumbers(draft, null))
      // The order of the draft ran out while the client was away (or was cancelled by the System).
      const ranOut = !!draft?.orderId && restored?.status === 'cancelled' && !!restored.hold_expires_at
        && Date.parse(restored.hold_expires_at) <= Date.now()
      if (ranOut || (restored?.status === 'checkout' && !held)) {
        setPhase('expired')
        return
      }
      setPhase(tour.free_seats > 0 && firstDate !== null ? 'ready' : 'unavailable')
    })()
    return () => { cancelled = true }
    // Runs once per mounted wizard: the key in BookingPage changes with the user and the tour, and
    // re-running it on later changes would restore over what the client is typing.
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ---------- price: the quote before the order exists, the order's price after
  const date = Form.useWatch('date', form)
  const adults = Form.useWatch('adults', form) ?? 1
  const children = Form.useWatch('children', form) ?? 0
  const dateIso = date ? date.format(ISO) : null
  const quoteBody = { tour_id: tour.id, start_date: dateIso ?? '', adults, children }
  const quote = useQuery({
    queryKey: ['quote', quoteBody],
    queryFn: () => quoteOrder(quoteBody),
    enabled: phase === 'ready' && order === null && bookable(dateIso) && adults >= 1 && children >= 0,
    staleTime: QUOTE_STALE_MS,
    placeholderData: keepPreviousData,
    retry: false,
  })
  const price = order ? order.price : (quote.isError ? null : quote.data ?? null)

  // ---------- the hold
  const expire = useCallback(() => {
    setOrder(null)
    setStep(0)
    setPhase('expired')
  }, [])
  const remaining = useHoldRemaining(order?.hold_expires_at, expire)

  /**
   * Every action of the wizard goes through here, one at a time. The lock is taken synchronously,
   * before the form validation or a dialog, so a double click cannot start a second request (the
   * backend has no idempotency key: two POST /orders would hold seats twice). Common errors are
   * handled here, the rest by `onError` (true = handled).
   */
  const run = (action: () => Promise<void>, onError?: (error: unknown) => boolean) => {
    if (busyRef.current) return
    busyRef.current = true
    setBusy(true)
    setActionError(null)
    void (async () => {
      try {
        await action()
      } catch (error) {
        if (isFormValidation(error)) return   // the form already shows the field errors
        if (isHoldExpired(error)) expire()
        else if (isTourUnavailable(error)) setPhase('unavailable')
        else if (!onError?.(error)) {
          const retryable = error instanceof ApiError && ['network', 'server', 'maintenance'].includes(error.kind)
          setActionError({ error, retry: retryable ? () => run(action, onError) : undefined })
        }
      } finally {
        busyRef.current = false
        setBusy(false)
      }
    })()
  }

  const afterSeatsChange = () => queryClient.invalidateQueries({ queryKey: ['tour', tour.id] })

  // ---------- step 1 -> 2
  const nextFromTrip = () => run(async () => {
    const values = await form.validateFields(['date', 'adults', 'children'])
    const startDate = values.date!.format(ISO)
    const nextAdults = values.adults ?? 1
    const nextChildren = values.children ?? 0
    let current = order
    if (current && current.start_date !== startDate) {
      const ok = await modal.confirm({
        title: t('checkout.trip.dateChangeTitle'), content: t('checkout.trip.dateChangeText', { number: current.number }),
        okText: t('checkout.trip.dateChangeYes'), cancelText: t('checkout.trip.dateChangeNo'),
      })
      if (!ok) return
      await cancelOrder(current.id)   // the date of an order cannot be changed (PATCH has no date)
      current = null
      setOrder(null)
    }
    if (!current) {
      const known = (list: { id: number }[] | undefined, id: number | null | undefined) =>
        id != null && list?.some((o) => o.id === id) ? id : null
      current = await createOrder({
        tour_id: tour.id, start_date: startDate, adults: nextAdults, children: nextChildren,
        // Services chosen before a restart are kept if they are still offered.
        insurance_type_id: known(insurance.data, form.getFieldValue('insurance_type_id')),
        transfer_type_id: known(transfer.data, form.getFieldValue('transfer_type_id')),
        wishes: (form.getFieldValue('wishes') as string | undefined)?.trim() || null,
      })
      void afterSeatsChange()
    } else if (current.adults !== nextAdults || current.children !== nextChildren) {
      // Stored tourists must match the numbers, so they are cleared and sent again on step 2.
      const body: OrderUpdate = { adults: nextAdults, children: nextChildren }
      if (current.tourists.length) body.tourists = []
      current = await updateOrder(current.id, body)
      void afterSeatsChange()
    }
    form.setFieldsValue({
      tourists: resizeTourists(form.getFieldValue('tourists'), nextAdults + nextChildren),
      insurance_type_id: current.insurance_type_id, transfer_type_id: current.transfer_type_id,
    })
    setOrder(current)
    setStep(1)
  }, (error) => {
    if (isSeatsError(error)) {
      form.setFields([{ name: 'adults', errors: [serverText(error)] }])
      void refetchTour()
      return true
    }
    return false
  })

  const showTouristIssues = (error: unknown): boolean => {
    const issues = touristIssues(error)
    if (!issues.length) return false
    setStep(1)
    form.setFields(issues.map((issue) => ({ name: ['tourists', issue.index, issue.field], errors: [issue.message] })))
    return true
  }

  // ---------- step 2 -> 3
  const nextFromTourists = () => run(async () => {
    if (!order) return
    await form.validateFields([['tourists']], { recursive: true })
    const updated = await updateOrder(order.id, { tourists: toTouristsIn(form.getFieldValue('tourists') ?? []) })
    setOrder(updated)
    setReenterNumbers(false)
    setStep(2)
  }, showTouristIssues)

  // ---------- step 3: services and promo code (each choice is saved at once)
  const patchOrder = (body: OrderUpdate, onError?: (error: unknown) => boolean) => run(async () => {
    if (order) setOrder(await updateOrder(order.id, body))
  }, onError)
  const onInsurance = (id: number) => patchOrder({ insurance_type_id: id }, () => {
    form.setFieldValue('insurance_type_id', order?.insurance_type_id)
    return false
  })
  const onTransfer = (id: number) => patchOrder({ transfer_type_id: id }, () => {
    form.setFieldValue('transfer_type_id', order?.transfer_type_id)
    return false
  })
  const onApplyPromo = () => {
    const code = ((form.getFieldValue('promo') as string | undefined) ?? '').trim()
    if (!code) {
      setPromoError(t('checkout.rules.required'))
      return
    }
    setPromoError(null)
    patchOrder({ promo_code: code }, (error) => {
      // A refused code: the backend's reason (not found, inactive, expired, minimum, limit).
      if (error instanceof ApiError && error.status === 422) {
        setPromoError(serverText(error))
        return true
      }
      return false
    })
  }
  const onRemovePromo = () => {
    form.setFieldValue('promo', '')
    setPromoError(null)
    patchOrder({ promo_code: null })
  }
  const nextFromServices = () => run(async () => {
    if (!order) return
    await form.validateFields(['wishes'])
    const wishes = ((form.getFieldValue('wishes') as string | undefined) ?? '').trim() || null
    if (wishes !== order.wishes) setOrder(await updateOrder(order.id, { wishes }))
    setStep(3)
  })

  // ---------- step 4: confirm and hand over to the payment page (spec 05)
  const confirm = () => run(async () => {
    if (!order) return
    await form.validateFields(['accept'])
    const shown = price?.total_uah ?? order.total_uah
    let frozen: string
    try {
      frozen = (await confirmOrder(order.id)).total_uah
    } catch (error) {
      // A second confirm (another tab, a retried request) answers 409: if the order is already
      // waiting for payment, simply go on to the payment page.
      if (error instanceof ApiError && error.status === 409 && !isHoldExpired(error)) {
        const current = await fetchOrder(order.id)
        if (current.status === 'awaiting_payment') {
          clearDraft(user.id, tour.id)
          void navigate(payPath(order.id))
          return
        }
      }
      throw error
    }
    clearDraft(user.id, tour.id)
    const state: PayPageState = frozen !== shown ? { priceChanged: { shown, frozen } } : {}
    void navigate(payPath(order.id), { state })
  }, showTouristIssues)

  // ---------- cancel / restart
  const cancelBooking = () => run(async () => {
    if (!order) return
    const ok = await modal.confirm({
      title: t('checkout.cancelConfirm'), okText: t('checkout.cancelYes'), cancelText: t('checkout.cancelNo'),
      okButtonProps: { danger: true },
    })
    if (!ok) return
    await cancelOrder(order.id)
    clearDraft(user.id, tour.id)
    void afterSeatsChange()
    void navigate('/tours')
  })

  /** «Почати знову»: a new hold from step 1; what the client typed stays (except what never was stored). */
  const restart = async () => {
    const { data } = await refetchTour()
    setOrder(null)
    setStep(0)
    setResumed(null)
    setPhase(data && data.free_seats > 0 ? 'ready' : 'unavailable')
  }
  const restartFromReview = () => run(async () => {
    if (!order) return
    const ok = await modal.confirm({
      title: t('checkout.review.restartConfirm'), okText: t('checkout.hold.restart'), cancelText: t('checkout.cancelNo'),
    })
    if (!ok) return
    await cancelOrder(order.id)
    await restart()
  })

  const help = (
    <HelpGuide content={{
      title: t('help.bookingTitle'),
      steps: (['1', '2', '3', '4', '5'] as const).map((n) => t(`help.bookingSteps.${n}`)),
      // A new tab: the wizard and its seat hold stay open.
      link: { to: '/faq#hold', label: t('help.toHoldFaq'), newTab: true },
    }} />
  )

  if (phase === 'restoring') return <Skeleton active={false} paragraph={{ rows: 8 }} />
  if (phase === 'unavailable') return <Unavailable />
  if (phase === 'expired') {
    return (
      <>
        <Result status="warning" title={<h1 className="result-title">{t('checkout.hold.expiredTitle')}</h1>}
          subTitle={t('checkout.hold.expiredText')}
          extra={[
            <Button key="restart" type="primary" onClick={() => void restart()}>{t('checkout.hold.restart')}</Button>,
            <BackToCatalogButton key="catalog" />,
          ]} />
        {help}
      </>
    )
  }

  const startDate = order?.start_date ?? dateIso
  const endDate = order?.end_date ?? (startDate ? returnDate(startDate, tour.nights) : null)
  const available = tour.free_seats + (order ? order.adults + order.children : 0)
  const summary = (
    <BookingSummary tour={tour} startDate={startDate} endDate={endDate} compact={compact}
      adults={order?.adults ?? adults} childCount={order?.children ?? children} price={price} />
  )
  const steps = [
    { key: 'trip', title: t('checkout.steps.trip') },
    { key: 'tourists', title: t('checkout.steps.tourists') },
    { key: 'services', title: t('checkout.steps.services') },
    { key: 'review', title: t('checkout.steps.review') },
  ]
  const next = [nextFromTrip, nextFromTourists, nextFromServices, confirm][step]

  return (
    <div className="booking-page">
      <Typography.Title level={1} className="booking-title">{t('checkout.title')}</Typography.Title>
      <Typography.Paragraph className="booking-subtitle">
        {tour.title_uk}
        {order && <> · {t('checkout.orderNumber', { number: order.number })}</>}
      </Typography.Paragraph>
      <div ref={stepsRef}>
        <Steps current={step} items={steps} size="small" className="booking-steps" />
      </div>

      {order?.hold_expires_at && remaining !== null && remaining > 0 && (
        <HoldTimer expiresAt={order.hold_expires_at} remaining={remaining} />
      )}
      {resumed && (
        <Alert type="info" showIcon className="booking-block" closable={{ onClose: () => setResumed(null) }}
          title={t('checkout.resumed', { number: resumed.number, date: formatDate(resumed.date) })} />
      )}

      <Row gutter={[24, 24]}>
        <Col xs={24} md={14} lg={16}>
          <Form form={form} layout="vertical" requiredMark={false} className="booking-form"
            onValuesChange={() => persist(step, order)}>
            <div hidden={step !== 0}>
              {firstDate && (
                <StepTrip tour={tour} firstDate={firstDate} lastDate={lastDate} available={available}
                  hasOrder={order !== null} />
              )}
            </div>
            <div hidden={step !== 1}>
              {order && step >= 1 && (
                <StepTourists form={form} adults={order.adults} startDate={order.start_date}
                  endDate={order.end_date} user={user} passports={passports.data ?? []}
                  reenterNumbers={reenterNumbers} />
              )}
            </div>
            <div hidden={step !== 2}>
              {order && (
                <StepServices insurance={insurance.data} transfer={transfer.data} price={price}
                  appliedPromo={order.promo_code} promoError={promoError} busy={busy}
                  onInsurance={onInsurance} onTransfer={onTransfer} onApplyPromo={onApplyPromo}
                  onRemovePromo={onRemovePromo} />
              )}
            </div>
            <div hidden={step !== 3}>
              {order && step === 3 && (
                <StepReview tour={tour} order={order} price={price} insurance={insurance.data}
                  transfer={transfer.data} remaining={remaining} busy={busy}
                  onRestart={restartFromReview} />
              )}
            </div>

            {actionError && (
              isMaintenance(actionError.error) && actionError.error instanceof Error ? (
                <ApiErrorState error={actionError.error} onRetry={() => actionError.retry?.()}
                  title={t('checkout.states.actionFailed')} />
              ) : (
                <Alert type="error" showIcon className="booking-block" title={t('checkout.states.actionFailed')}
                  description={serverText(actionError.error)}
                  action={actionError.retry && (
                    <Button onClick={actionError.retry}>{t('errors.retry')}</Button>
                  )} />
              )
            )}

            {compact && summary}

            <Flex justify="space-between" wrap gap={8} className="booking-actions">
              <Flex gap={8} wrap>
                {step > 0 && (
                  <Button disabled={busy} onClick={() => { setActionError(null); setStep(step - 1) }}>
                    {t('checkout.back')}
                  </Button>
                )}
                {order && (
                  <Button type="link" danger disabled={busy} onClick={cancelBooking}>
                    {t('checkout.cancel')}
                  </Button>
                )}
              </Flex>
              <Button type="primary" loading={busy} onClick={next}>
                {step === 3 ? t('checkout.confirm') : t('checkout.next')}
              </Button>
            </Flex>
          </Form>
        </Col>
        {!compact && <Col md={10} lg={8}><div className="booking-summary-sticky">{summary}</div></Col>}
      </Row>
      {help}
    </div>
  )
}
