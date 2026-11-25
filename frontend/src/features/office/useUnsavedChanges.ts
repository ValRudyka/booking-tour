import { App } from 'antd'
import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useBlocker } from 'react-router'

/**
 * Asks before leaving a page with unsaved changes (spec 10): links and back/forward inside the
 * app go through React Router's `useBlocker` (a Modal «Вийти без збереження?»), closing or
 * reloading the tab through `beforeunload` (the browser's own question; its text cannot be set).
 *
 * `allowNext()` lets the next navigation through without asking: the page calls it right before
 * it navigates itself after a successful save (the state update that clears `dirty` would come
 * too late for that navigation).
 */
export function useUnsavedChanges(dirty: boolean) {
  const { t } = useTranslation()
  const { modal } = App.useApp()
  const skip = useRef(false)
  const asking = useRef(false)   // one question at a time (StrictMode runs effects twice)
  const blocker = useBlocker(({ currentLocation, nextLocation }) => {
    if (skip.current) {
      skip.current = false
      return false
    }
    // Moving between the editor's own steps (?step=) is not leaving the page.
    return dirty && currentLocation.pathname !== nextLocation.pathname
  })

  useEffect(() => {
    if (blocker.state !== 'blocked' || asking.current) return
    asking.current = true
    modal.confirm({
      title: t('office.tours.unsaved.title'),
      content: t('office.tours.unsaved.text'),
      okText: t('office.tours.unsaved.leave'),
      okButtonProps: { danger: true },
      cancelText: t('office.tours.unsaved.stay'),
      onOk: () => { asking.current = false; blocker.proceed() },
      onCancel: () => { asking.current = false; blocker.reset() },
    })
  }, [blocker, modal, t])

  useEffect(() => {
    if (!dirty) return
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''   // older browsers need it set to show the question
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [dirty])

  return { allowNext: () => { skip.current = true } }
}
