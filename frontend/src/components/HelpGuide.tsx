import { QuestionCircleOutlined } from '@ant-design/icons'
import { Button, FloatButton, Modal, Steps } from 'antd'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import './HelpGuide.css'

export interface HelpGuideContent {
  title: string
  steps: string[]
  /** A link to the related page, e.g. from «Як увійти» to the registration. */
  link?: { to: string; label: string }
}

/**
 * «Як це працює?»: a round button in the bottom right corner that opens a short numbered guide.
 * The Modal opens only on a click; Esc, ×, «Зрозуміло» or a click outside close it, and antd
 * returns the focus to the button. No animation (theme motion: false). Reusable: the booking
 * page will get its own content.
 */
export function HelpGuide({ content }: { content: HelpGuideContent }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  return (
    <>
      <FloatButton icon={<QuestionCircleOutlined aria-hidden />} tooltip={t('help.button')}
        aria-label={t('help.button')} className="help-guide-button" onClick={() => setOpen(true)} />
      <Modal open={open} title={content.title} onCancel={() => setOpen(false)}
        focusable={{ focusTriggerAfterClose: true }}
        footer={[
          content.link && (
            <Link key="link" to={content.link.to} className="help-guide-link">{content.link.label}</Link>
          ),
          <Button key="ok" type="primary" onClick={() => setOpen(false)}>{t('help.close')}</Button>,
        ]}>
        {/* A numbered list, not progress: every step "wait", no current step. */}
        <Steps orientation="vertical" size="small" current={-1}
          items={content.steps.map((step) => ({ title: step, status: 'wait' as const }))} />
      </Modal>
    </>
  )
}
