import { App } from 'antd'
import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useBlocker } from 'react-router'

/**
 * While `dirty`, leaving the page asks «Зміни не збережено. Вийти без збереження?»: links and
 * Back inside the app through the router's blocker (a dialog), a reload or closing the tab through
 * the browser's own `beforeunload` prompt (browsers show their own text there).
 */
export function useUnsavedChanges(dirty: boolean) {
  const { t } = useTranslation()
  const { modal } = App.useApp()
  const blocker = useBlocker(({ currentLocation, nextLocation }) =>
    dirty && currentLocation.pathname !== nextLocation.pathname)
  const asking = useRef(false)

  useEffect(() => {
    if (blocker.state !== 'blocked' || asking.current) return
    asking.current = true
    modal.confirm({
      title: t('cabinet.profile.unsavedTitle'),
      okText: t('cabinet.profile.unsavedLeave'),
      cancelText: t('cabinet.profile.unsavedStay'),
      onOk: () => { asking.current = false; blocker.proceed() },
      onCancel: () => { asking.current = false; blocker.reset() },
    })
  }, [blocker, modal, t])

  useEffect(() => {
    if (!dirty) return
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])
}
