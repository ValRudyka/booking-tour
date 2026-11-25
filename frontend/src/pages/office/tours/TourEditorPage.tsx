import { ArrowLeftOutlined } from '@ant-design/icons'
import { Alert, App, Button, Flex, Form, Result, Skeleton, Space, Steps } from 'antd'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { ApiError, toApiError } from '../../../api/client'
import { tourApi, useOfficeTour, useTourRules } from '../../../api/officeTours'
import type { ManagerTour } from '../../../api/types'
import { ApiErrorState } from '../../../components/ApiErrorState'
import { StatusTag } from '../../../components/StatusTag'
import { canEdit, findTourAction, lockReason, type TourStateLike } from '../../../features/office/tourActions'
import { actionErrorText, useTourAction } from '../../../features/office/useOfficeAction'
import { readEnum } from '../../../features/office/urlState'
import { useDocumentTitle } from '../../../hooks/useDocumentTitle'
import { useUnsavedChanges } from '../../../hooks/useUnsavedChanges'
import { OfficeForbidden } from '../OfficeHome'
import { CopyTourModal } from './CopyTourModal'
import { TourActionButtons } from './TourActionButtons'
import { TourBasicsStep } from './TourBasicsStep'
import { TourDatesStep } from './TourDatesStep'
import {
  EMPTY_VALUES, formFieldOf, payloadOf, sameTour, STEP_FIELDS, stepOfField, STEPS, type StepKey, type TourFormValues,
  valuesOf,
} from './tourForm'
import { TourPhotosStep } from './TourPhotosStep'
import { TourProgramStep } from './TourProgramStep'
import { TourSummaryStep } from './TourSummaryStep'
import '../../../layouts/OfficeLayout.css'

/** A new tour exists on the server only after step 3, so it has no photo or summary step yet. */
const NEW_TOUR_STEPS: readonly StepKey[] = ['basics', 'program', 'dates']

/**
 * The tour editor (spec 10 §2): /office/tours/new and /office/tours/:id/edit. One antd Form for
 * all steps (every step stays mounted, hidden, so «Назад» keeps the values and saving validates
 * everything); the step is in the URL (?step=). A new tour is saved as a draft when leaving
 * step 3 (photos need its id); an existing one is saved from the summary step or with
 * «Зберегти» on any step. The API decides what may change: `tour_actions` (an active tour is
 * read-only until unpublished) and `locked_fields` with the server's reason.
 */
export function TourEditorPage() {
  const { id } = useParams()
  const tourId = id === undefined ? undefined : /^\d{1,9}$/.test(id) ? Number(id) : null
  const { t } = useTranslation()
  if (tourId === null) {
    return <Result status="404" title={<h1 className="result-title">{t('office.tours.notFound')}</h1>} />
  }
  return <TourEditor key={tourId ?? 'new'} tourId={tourId} />
}

function TourEditor({ tourId }: { tourId: number | undefined }) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const navigate = useNavigate()
  const isNew = tourId === undefined
  const tour = useOfficeTour(tourId)
  const rules = useTourRules()
  const [searchParams, setSearchParams] = useSearchParams()
  const steps = isNew ? NEW_TOUR_STEPS : STEPS
  const step: StepKey = readEnum(searchParams, 'step', steps) ?? 'basics'
  const stepIndex = steps.indexOf(step)

  const [form] = Form.useForm<TourFormValues>()
  // Every value of the form, re-read on each change (the summary step shows them).
  const watched = Form.useWatch((all: TourFormValues) => all, { form, preserve: true })
  const [submitted, setSubmitted] = useState(false)
  // The field to scroll to and focus once its step is shown (set by validation and server errors).
  const pendingFocus = useRef<(string | number)[] | null>(null)
  const [focusTick, setFocusTick] = useState(0)
  const [fieldErrorShown, setFieldErrorShown] = useState(false)
  const [copying, setCopying] = useState<TourStateLike | null>(null)
  const action = useTourAction(tourId)
  const saved: ManagerTour | undefined = tour.data
  const editable = canEdit(saved)
  // Each saved version of the tour (see the effect below) is the baseline of «unsaved changes».
  const loaded = saved ? `${saved.id}:${saved.updated_at}` : null
  // eslint-disable-next-line react-hooks/exhaustive-deps -- `loaded` stands for `saved`
  const baseline = useMemo(() => (saved ? valuesOf(saved) : EMPTY_VALUES), [loaded])
  const [changes, setChanges] = useState<{ version: string | null; dirty: boolean }>({ version: null, dirty: false })
  const dirty = changes.version === loaded && changes.dirty
  const setDirty = (value: boolean) => setChanges({ version: loaded, dirty: value })
  const unsaved = useUnsavedChanges(dirty, {
    title: t('office.tours.unsaved.title'), content: t('office.tours.unsaved.text'),
    leave: t('office.tours.unsaved.leave'), stay: t('office.tours.unsaved.stay'),
  })
  useDocumentTitle(isNew ? t('office.tours.newTitle') : saved ? saved.title_uk : t('office.tours.title'))

  // Load the saved tour into the form, again after each save (the server's normalised values:
  // the auto title, upper-case flights) — but not after a photo change, which does not touch
  // the tour row (same updated_at), so the manager's edits on other steps stay.
  useEffect(() => {
    if (!saved) return
    form.resetFields()
    form.setFieldsValue(baseline)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `baseline` changes with `loaded`
  }, [baseline, form])

  useEffect(() => {
    if (!pendingFocus.current) return
    form.scrollToField(pendingFocus.current, { block: 'center', focus: true })
    pendingFocus.current = null
  }, [focusTick, form, step])

  const focusLater = (name: (string | number)[]) => {
    pendingFocus.current = name
    setFocusTick((n) => n + 1)
  }

  const goTo = useCallback((next: StepKey) => {
    const params = new URLSearchParams(searchParams)
    if (next === 'basics') params.delete('step')
    else params.set('step', next)
    setSearchParams(params)
  }, [searchParams, setSearchParams])

  const onValuesChange = (changed: Partial<TourFormValues>) => {
    // Resort depends on the country, hotel on the resort (form 4.6.2.1 fields 3–5).
    if ('country_id' in changed) form.setFieldsValue({ resort_id: undefined, hotel_id: undefined })
    else if ('resort_id' in changed) form.setFieldsValue({ hotel_id: undefined })
    if ('transport_type' in changed) {
      if (changed.transport_type !== 'air') form.setFieldsValue({ flight_out: '', flight_back: '' })
      if (changed.transport_type === 'none') form.setFieldsValue({ departure_city_id: null })
    }
    setDirty(!sameTour(form.getFieldsValue(true), baseline))
  }

  /** Validates the given fields (all when omitted); on errors opens the first one's step. */
  const validate = async (names?: (keyof TourFormValues)[]): Promise<boolean> => {
    setSubmitted(true)
    try {
      await (names ? form.validateFields(names, { recursive: true }) : form.validateFields())
      return true
    } catch (caught) {
      const first = (caught as { errorFields?: { name: (string | number)[] }[] }).errorFields?.[0]?.name
      if (first) {
        const target = stepOfField(String(first[0]))
        if (target && target !== step) goTo(target)
        focusLater(first)
      }
      return false
    }
  }

  /** The server's field errors (`loc`) go under their fields, on their step (spec 03 §2a). */
  const showServerErrors = (error: ApiError): boolean => {
    const fields = error.issues.filter((issue) => issue.type === 'tour_rule' && issue.loc[0] === 'body' && issue.loc.length > 1)
    const known = fields.filter((issue) => issue.loc[1] !== 'program_days' || issue.loc.length > 2)
    if (known.length === 0) return false
    form.setFields(known.map((issue) => {
      const [, field, ...rest] = issue.loc
      return { name: [formFieldOf(String(field)), ...rest] as never, errors: [issue.msg] }
    }))
    const first = known[0].loc
    const target = stepOfField(String(first[1]))
    if (target && target !== step) goTo(target)
    focusLater([formFieldOf(String(first[1])), ...first.slice(2)])
    return true
  }

  const send = async <T,>(name: string, request: () => Promise<T>): Promise<T | null> => {
    setFieldErrorShown(false)
    return action.run(name, async () => {
      try {
        return await request()
      } catch (caught) {
        setFieldErrorShown(showServerErrors(toApiError(caught)))
        throw caught
      }
    })
  }

  const save = async (publish: boolean) => {
    if (!(await validate())) return
    const body = payloadOf(form.getFieldsValue(true))
    if (isNew) {
      const created = await send('save', () => tourApi.create(body))
      if (!created) return
      void message.success(t('office.tours.done.created'))
      setDirty(false)
      unsaved.allowNext()
      navigate(`/office/tours/${created.id}/edit?step=photos`, { replace: true })
      return
    }
    const updated = await send('save', () => tourApi.update(tourId, body))
    if (!updated) return
    if (!publish) {
      void message.success(t('office.tours.done.saved'))
      return
    }
    const published = await send('publish', () => tourApi.publish(tourId))
    if (published) void message.success(t('office.tours.done.publish', { title: published.title_uk }))
  }

  const next = async () => {
    // A read-only tour (active, archived) is only looked through: nothing to validate.
    if (editable && !(await validate(STEP_FIELDS[step]))) return
    if (isNew && step === 'dates') {
      await save(false)
      return
    }
    goTo(steps[stepIndex + 1])
  }

  if (!isNew && tour.error instanceof ApiError && tour.error.status === 403) return <OfficeForbidden />
  if (!isNew && tour.error instanceof ApiError && tour.error.status === 404) {
    return <Result status="404" title={<h1 className="result-title">{t('office.tours.notFound')}</h1>}
      extra={<Link to="/office/tours">{t('office.tours.back')}</Link>} />
  }
  if ((!isNew && tour.isError && !saved) || rules.isError) {
    return <ApiErrorState error={(tour.error ?? rules.error)!} title={t('office.tours.loadFailed')}
      onRetry={() => { void tour.refetch(); void rules.refetch() }} />
  }
  if ((!isNew && !saved) || !rules.data) return <Skeleton active paragraph={{ rows: 10 }} />

  const locked = (field: string) => (saved ? lockReason(saved.locked_fields, field) : undefined)
  const editReason = saved ? findTourAction(saved, 'edit')?.reason : undefined
  const busy = action.busy !== null
  const showActionError = action.error && !fieldErrorShown

  return (
    <Flex vertical gap={16}>
      <Link to="/office/tours" className="office-back"><ArrowLeftOutlined aria-hidden /> {t('office.tours.back')}</Link>
      <Flex justify="space-between" align="center" wrap gap={12}>
        <Space wrap align="center">
          <h1 className="office-page-title">{isNew ? t('office.tours.newTitle') : saved!.title_uk}</h1>
          {saved && <StatusTag kind="tour" status={saved.status} />}
        </Space>
        {saved && <TourActionButtons tour={saved} action={action} onCopy={setCopying} size="middle" />}
      </Flex>
      {saved && !editable && editReason && <Alert type="info" showIcon role="note" title={editReason} />}
      {saved && editable && saved.locked_fields.length > 0 && (
        <Alert type="warning" showIcon role="note" title={t('office.tours.lockedTitle')} description={saved.locked_fields[0].reason} />
      )}
      {showActionError && (
        <Alert type="error" showIcon role="alert" closable={{ onClose: action.clearError }}
          title={actionErrorText(action.error!, t('office.forbiddenTitle'))} />
      )}

      <Steps current={stepIndex} onChange={(index) => goTo(steps[index])} size="small" className="office-steps"
        items={steps.map((key) => ({ title: t(`office.tours.step.${key}`) }))} />

      <Form<TourFormValues> form={form} layout="vertical" disabled={!editable} initialValues={EMPTY_VALUES}
        validateTrigger={submitted ? ['onBlur', 'onChange'] : 'onBlur'} onValuesChange={onValuesChange}
        className="office-tour-form" aria-label={t('office.tours.formLabel')}>
        <section hidden={step !== 'basics'} aria-label={t('office.tours.step.basics')}>
          <TourBasicsStep form={form} rules={rules.data} locked={locked} savedHotel={saved?.hotel} />
        </section>
        <section hidden={step !== 'program'} aria-label={t('office.tours.step.program')}>
          <TourProgramStep form={form} rules={rules.data} />
        </section>
        <section hidden={step !== 'dates'} aria-label={t('office.tours.step.dates')}>
          <TourDatesStep rules={rules.data} locked={locked} tour={saved} />
        </section>
      </Form>
      {step === 'photos' && saved && <TourPhotosStep tour={saved} rules={rules.data} editable={editable} />}
      {step === 'summary' && (
        <Flex vertical gap={12}>
          {saved && findTourAction(saved, 'publish') && !findTourAction(saved, 'publish')!.allowed && (
            <Alert type="warning" showIcon role="note" title={t('office.tours.summary.cannotPublish')}
              description={findTourAction(saved, 'publish')!.reason} />
          )}
          <TourSummaryStep values={{ ...EMPTY_VALUES, ...watched }} tour={saved} />
        </Flex>
      )}

      <Flex justify="space-between" wrap gap={12} className="office-steps-footer">
        <Button onClick={() => goTo(steps[stepIndex - 1])} disabled={stepIndex === 0 || busy}>{t('office.tours.prev')}</Button>
        <Space wrap>
          {!isNew && editable && step !== 'summary' && (
            <Button onClick={() => void save(false)} loading={action.busy === 'save'} disabled={busy || !dirty}>
              {t('office.tours.save')}
            </Button>
          )}
          {step === 'summary' && editable && (
            <>
              <Button onClick={() => void save(false)} loading={action.busy === 'save'} disabled={busy}>
                {t('office.tours.saveDraft')}
              </Button>
              {saved && findTourAction(saved, 'publish') && (
                <Button type="primary" onClick={() => void save(true)} loading={action.busy === 'publish'} disabled={busy}>
                  {t('office.tours.saveAndPublish')}
                </Button>
              )}
            </>
          )}
          {(stepIndex < steps.length - 1 || (isNew && step === 'dates')) && (
            <Button type="primary" onClick={() => void next()} loading={isNew && step === 'dates' && action.busy === 'save'} disabled={busy}>
              {isNew && step === 'dates' ? t('office.tours.createAndNext') : t('office.tours.next')}
            </Button>
          )}
        </Space>
      </Flex>
      <CopyTourModal tour={copying} action={action} onClose={() => setCopying(null)} />
    </Flex>
  )
}
