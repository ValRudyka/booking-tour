import { Collapse } from 'antd'
import { useEffect, useState } from 'react'
import { Trans, useTranslation } from 'react-i18next'
import { useLocation } from 'react-router'
import { FAQ_KEYS, isFaqKey } from './infoContent'
import { InfoPage } from './InfoPage'
import { RICH_TEXT } from './richText'

/**
 * /faq: questions in a Collapse; several may be open. The URL hash names a question
 * (`/faq#cancel`): it opens, scrolls into view and gets the focus — on the first visit and on
 * every later link to it, also from another answer on this page. The item's `id` is set on
 * its root element (@rc-component/collapse passes it through); the header is the button.
 */
export function FaqPage() {
  const { t } = useTranslation()
  const location = useLocation()
  const anchor = location.hash.slice(1)
  const [open, setOpen] = useState<string[]>(() => (isFaqKey(anchor) ? [anchor] : []))

  // A new navigation to a question opens it as well; adjusting state while rendering (React
  // docs, "Adjusting some state when a prop changes") avoids a render with it still closed.
  const [seenKey, setSeenKey] = useState(location.key)
  if (seenKey !== location.key) {
    setSeenKey(location.key)
    if (isFaqKey(anchor) && !open.includes(anchor)) setOpen([...open, anchor])
  }

  useEffect(() => {
    if (!isFaqKey(anchor)) return
    const header = document.getElementById(anchor)?.querySelector<HTMLElement>('.ant-collapse-header')
    header?.scrollIntoView({ block: 'start' })
    header?.focus({ preventScroll: true })
  }, [anchor, location.key])

  return (
    <InfoPage title={t('info.faq.title')}
      lead={<Trans i18nKey="info.faq.lead" components={RICH_TEXT} />}>
      <Collapse className="faq-collapse" activeKey={open} onChange={(keys) => setOpen(keys.map(String))}
        items={FAQ_KEYS.map((key) => ({
          key,
          id: key,
          label: t(`info.faq.items.${key}.q`),
          children: <Trans i18nKey={`info.faq.items.${key}.a`} components={RICH_TEXT} />,
        }))} />
    </InfoPage>
  )
}
