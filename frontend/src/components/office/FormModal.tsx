import { Alert, Form, Modal, type FormInstance } from 'antd'
import type { ReactNode } from 'react'

/**
 * A small ModalForm-like helper for back-office dialogs (spec 09; plain antd Modal + Form): a
 * vertical form with validation on blur and, after the first submit, on change (spec 03 §2a),
 * an optional warning about the consequences, the server's error inside the dialog and an OK
 * button locked while the request runs. `onSubmit` resolves to true to close the dialog.
 */
interface Props<T> {
  open: boolean
  title: string
  okText: string
  cancelText: string
  danger?: boolean
  busy: boolean
  /** The consequences of the action, shown above the fields. */
  warning?: ReactNode
  /** The server's refusal, shown inside the dialog. */
  error?: string | null
  form: FormInstance<T>
  onCancel: () => void
  onSubmit: (values: T) => Promise<boolean>
  children?: ReactNode
}

export function FormModal<T extends object>({
  open, title, okText, cancelText, danger, busy, warning, error, form, onCancel, onSubmit, children,
}: Props<T>) {
  const submit = async () => {
    let values: T
    try {
      values = await form.validateFields()
    } catch {
      return                                    // the fields show what is missing
    }
    if (await onSubmit(values)) onCancel()
  }

  return (
    <Modal open={open} title={title} okText={okText} cancelText={cancelText} onCancel={onCancel}
      onOk={() => void submit()} destroyOnHidden maskClosable={!busy}
      okButtonProps={{ danger, loading: busy, disabled: busy }} cancelButtonProps={{ disabled: busy }}>
      {warning && <Alert type="warning" showIcon role="note" title={warning} className="office-modal-warning" />}
      <Form form={form} layout="vertical" validateTrigger={['onBlur', 'onChange']} preserve={false}
        onFinish={() => void submit()}>
        {children}
      </Form>
      {error && <Alert type="error" showIcon role="alert" title={error} />}
    </Modal>
  )
}
