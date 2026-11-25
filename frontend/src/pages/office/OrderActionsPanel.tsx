import { Alert, App, Button, Card, DatePicker, Form, Input, Popconfirm, Select, Typography } from 'antd'
import type { Dayjs } from 'dayjs'
import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { officeActions, useManagers } from '../../api/office'
import type { ManagerOrder, StaffActionInfo } from '../../api/types'
import { findAction } from '../../features/office/staffActions'
import { FormModal } from '../../components/office/FormModal'
import { keysOf, STAFF_ACTIONS, staffActionLabel } from '../../constants/orderLabels'
import { deadlineAllowed, MAX_COMMENT, MAX_TEXT, normalizePnr, PNR_MAX, PNR_PATTERN } from '../../features/office/orderRules'
import { actionErrorText, useOfficeAction } from '../../features/office/useOfficeAction'
import { kyivToday } from '../../utils/format'

type Action = ReturnType<typeof useOfficeAction>
type Dialog = 'confirm' | 'reject' | 'documents_ready' | 'assign'

/** Actions with their own card (documents, comment) are not buttons of this panel. */
const PANEL_ACTIONS = keysOf(STAFF_ACTIONS).filter((a) => a !== 'upload_documents' && a !== 'edit_comment')

/**
 * «Дії» (spec 09 §3): exactly the actions the API lists in `staff_actions`, in a fixed order. An
 * allowed one is a button; a refused one is a disabled button described by the server's reason
 * (e.g. «Замовлення веде інший менеджер …», «Спершу завантажте ваучер»). Nothing here looks at
 * the status: services/staff_actions.py decides.
 */
export function OrderActionsPanel({ order, action }: { order: ManagerOrder; action: Action }) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const baseId = useId()
  const [dialog, setDialog] = useState<Dialog | null>(null)

  const listed = PANEL_ACTIONS.map((name) => findAction(order, name)).filter((a): a is StaffActionInfo => !!a)
  const reasons = [...new Set(listed.filter((a) => !a.allowed && a.reason).map((a) => a.reason as string))]
  const reasonId = (reason: string | null) => reason ? `${baseId}-reason-${reasons.indexOf(reason)}` : undefined
  const busy = action.busy !== null

  const done = (key: 'take' | 'archive') => message.success(t(`office.order.actionDone.${key}`))
  const open = (next: Dialog) => {
    action.clearError()
    setDialog(next)
  }

  const button = (info: StaffActionInfo) => {
    const label = staffActionLabel(t, info.action)
    const common = { disabled: !info.allowed || busy, block: true, 'aria-describedby': info.allowed ? undefined : reasonId(info.reason) }
    switch (info.action) {
      case 'take':
        return (
          <Button type="primary" {...common} loading={action.busy === 'take'}
            onClick={() => void action.run('take', () => officeActions.take(order.id)).then((r) => r && done('take'))}>
            {label}
          </Button>
        )
      case 'archive':
        return (
          <Popconfirm title={t('office.order.archive.confirm')} description={t('office.order.archive.warning')}
            okText={t('office.order.archive.ok')} cancelText={t('office.order.cancel')} disabled={common.disabled}
            onConfirm={() => action.run('archive', () => officeActions.archive(order.id)).then((r) => { if (r) done('archive') })}>
            <Button {...common} loading={action.busy === 'archive'}>{label}</Button>
          </Popconfirm>
        )
      case 'reject':
        return <Button danger {...common} onClick={() => open('reject')}>{label}</Button>
      case 'confirm':
      case 'documents_ready':
        return <Button type="primary" {...common} onClick={() => open(info.action as Dialog)}>{label}</Button>
      default:
        return <Button {...common} onClick={() => open('assign')}>{label}</Button>
    }
  }

  const dialogError = dialog && action.error ? actionErrorText(action.error, t('office.forbiddenTitle')) : null

  return (
    <Card title={<h2 className="office-card-title">{t('office.order.actionsTitle')}</h2>}>
      {reasons.map((reason) => (
        <Alert key={reason} id={reasonId(reason)} type="info" showIcon role="note" title={reason} className="office-reason-alert" />
      ))}
      {listed.length === 0 ? (
        <Typography.Text type="secondary">{t('office.order.noActions')}</Typography.Text>
      ) : (
        <ul className="office-action-list">
          {listed.map((info) => <li key={info.action}>{button(info)}</li>)}
        </ul>
      )}
      {!dialog && action.error && (
        <Alert type="error" showIcon role="alert" className="office-action-error" closable={{ onClose: action.clearError }}
          title={actionErrorText(action.error, t('office.forbiddenTitle'))} />
      )}

      {dialog === 'confirm' && <ConfirmDialog order={order} action={action} error={dialogError} onClose={() => setDialog(null)} />}
      {dialog === 'reject' && <RejectDialog order={order} action={action} error={dialogError} onClose={() => setDialog(null)} />}
      {dialog === 'documents_ready' && (
        <DocumentsReadyDialog order={order} action={action} error={dialogError} onClose={() => setDialog(null)} />
      )}
      {dialog === 'assign' && <AssignDialog order={order} action={action} error={dialogError} onClose={() => setDialog(null)} />}
    </Card>
  )
}

interface DialogProps {
  order: ManagerOrder
  action: Action
  error: string | null
  onClose: () => void
}

const optional = (value: string | undefined) => value?.trim() || null

function ClientMessageField() {
  const { t } = useTranslation()
  return (
    <Form.Item name="client_message" label={t('office.order.clientMessage')} extra={t('office.order.clientMessageHint')}>
      <Input.TextArea rows={3} maxLength={MAX_TEXT} showCount />
    </Form.Item>
  )
}

/** «Підтвердити (PNR)» (ТЗ 4.5.4 step 4.2, form 4.6.2.2 fields 3–4, 7). */
function ConfirmDialog({ order, action, error, onClose }: DialogProps) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const [form] = Form.useForm<{ pnr: string; deadline: Dayjs; client_message?: string }>()
  const today = kyivToday()
  return (
    <FormModal open title={t('office.order.confirm.title')} okText={t('office.order.confirm.submit')}
      cancelText={t('office.order.cancel')} busy={action.busy === 'confirm'} error={error} form={form} onCancel={onClose}
      warning={t('office.order.confirm.note')}
      onSubmit={async (values) => {
        const result = await action.run('confirm', () => officeActions.confirm(order.id, {
          pnr: normalizePnr(values.pnr), operator_deadline: values.deadline.format('YYYY-MM-DD'),
          client_message: optional(values.client_message),
        }))
        if (result) message.success(t('office.order.actionDone.confirm'))
        return result !== null
      }}>
      <Form.Item name="pnr" label={t('office.order.confirm.pnr')} extra={t('office.order.confirm.pnrHint')}
        normalize={(value: string) => value.toUpperCase()}
        rules={[
          { required: true, whitespace: true, message: t('office.order.confirm.pnrRequired') },
          { pattern: PNR_PATTERN, message: t('office.order.confirm.pnrFormat') },
        ]}>
        <Input maxLength={PNR_MAX} autoComplete="off" spellCheck={false} />
      </Form.Item>
      <Form.Item name="deadline" label={t('office.order.confirm.deadline')} extra={t('office.order.confirm.deadlineHint')}
        rules={[{ required: true, message: t('office.order.confirm.deadlineRequired') }]}>
        <DatePicker format="DD.MM.YYYY" className="office-full-width"
          disabledDate={(day) => !deadlineAllowed(day.format('YYYY-MM-DD'), today, order.start_date)} />
      </Form.Item>
      <ClientMessageField />
    </FormModal>
  )
}

/** «Відхилити» with a required reason (ТЗ 4.5.4 step 4.1). */
function RejectDialog({ order, action, error, onClose }: DialogProps) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const [form] = Form.useForm<{ reject_reason: string; client_message?: string }>()
  return (
    <FormModal open danger title={t('office.order.reject.title')} okText={t('office.order.reject.submit')}
      cancelText={t('office.order.cancel')} busy={action.busy === 'reject'} error={error} form={form} onCancel={onClose}
      warning={t('office.order.reject.warning')}
      onSubmit={async (values) => {
        const result = await action.run('reject', () => officeActions.reject(order.id, {
          reject_reason: values.reject_reason.trim(), client_message: optional(values.client_message),
        }))
        if (result) message.success(t('office.order.actionDone.reject'))
        return result !== null
      }}>
      <Form.Item name="reject_reason" label={t('office.order.reject.reason')}
        rules={[{ required: true, whitespace: true, message: t('office.order.reject.reasonRequired') }]}>
        <Input.TextArea rows={3} maxLength={MAX_TEXT} showCount />
      </Form.Item>
      <ClientMessageField />
    </FormModal>
  )
}

/** «Документи готові»: the client is told the documents can be downloaded. */
function DocumentsReadyDialog({ order, action, error, onClose }: DialogProps) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const [form] = Form.useForm<{ client_message?: string }>()
  return (
    <FormModal open title={t('office.order.documentsReady.title')} okText={t('office.order.documentsReady.submit')}
      cancelText={t('office.order.cancel')} busy={action.busy === 'documents_ready'} error={error} form={form}
      onCancel={onClose} warning={t('office.order.documentsReady.note')}
      onSubmit={async (values) => {
        const result = await action.run('documents_ready',
          () => officeActions.documentsReady(order.id, optional(values.client_message)))
        if (result) message.success(t('office.order.actionDone.documents_ready'))
        return result !== null
      }}>
      <ClientMessageField />
    </FormModal>
  )
}

/** Hand-over to another manager (form 4.6.2.2, field 8). */
function AssignDialog({ order, action, error, onClose }: DialogProps) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const managers = useManagers(true)
  const [form] = Form.useForm<{ manager_id: number }>()
  const options = (managers.data ?? []).filter((m) => m.id !== order.manager_id).map((m) => ({ value: m.id, label: m.name }))
  return (
    <FormModal open title={t('office.order.assign.title')} okText={t('office.order.assign.submit')}
      cancelText={t('office.order.cancel')} busy={action.busy === 'assign'} error={error} form={form} onCancel={onClose}
      warning={t('office.order.assign.warning')}
      onSubmit={async (values) => {
        const result = await action.run('assign', () => officeActions.assign(order.id, values.manager_id))
        if (result) message.success(t('office.order.actionDone.assign'))
        return result !== null
      }}>
      {managers.isError && <Alert type="error" showIcon title={t('office.order.assign.loadFailed')} />}
      <Form.Item name="manager_id" label={t('office.order.assign.manager')}
        rules={[{ required: true, message: t('office.order.assign.managerRequired') }]}>
        <Select options={options} loading={managers.isPending} showSearch={{ optionFilterProp: 'label' }} />
      </Form.Item>
    </FormModal>
  )
}

/** «Внутрішній коментар» (form 4.6.2.2, field 6): managers only, editable by the responsible one. */
export function CommentCard({ order }: { order: ManagerOrder }) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const action = useOfficeAction(order.id)       // its errors show in this card
  const edit = findAction(order, 'edit_comment')
  const [text, setText] = useState(order.internal_comment ?? '')
  const changed = text.trim() !== (order.internal_comment ?? '')
  const save = async () => {
    const result = await action.run('comment', () => officeActions.comment(order.id, text.trim() || null))
    if (result) message.success(t('office.order.actionDone.comment'))
  }
  return (
    <Card title={<h2 className="office-card-title">{t('office.order.commentTitle')}</h2>}>
      <Typography.Paragraph type="secondary">{t('office.order.commentHint')}</Typography.Paragraph>
      {edit?.allowed ? (
        <>
          <Input.TextArea rows={4} maxLength={MAX_COMMENT} showCount value={text} aria-label={t('office.order.commentTitle')}
            onChange={(event) => setText(event.target.value)} />
          <Button className="office-comment-save" disabled={!changed || action.busy !== null}
            loading={action.busy === 'comment'} onClick={() => void save()}>
            {t('office.order.commentSave')}
          </Button>
          {action.error && (
            <Alert type="error" showIcon role="alert" className="office-block"
              title={actionErrorText(action.error, t('office.forbiddenTitle'))} />
          )}
        </>
      ) : (
        <>
          <Typography.Paragraph className="office-pre">{order.internal_comment ?? t('office.order.commentEmpty')}</Typography.Paragraph>
          {edit?.reason && <Typography.Text className="office-reason">{edit.reason}</Typography.Text>}
        </>
      )}
    </Card>
  )
}
