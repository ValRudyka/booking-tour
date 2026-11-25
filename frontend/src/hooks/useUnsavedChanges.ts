import { App } from 'antd'
import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useBlocker } from 'react-router'

/** The dialog's texts (already translated); the profile's are the default. */
export interface UnsavedTexts {
  title: string
  content?: string
  leave: string
  stay: string
}

/**
 * While `dirty`, leaving the page asks «Зміни не збережено. Вийти без збереження?»: links and
 * Back inside the app through the router's blocker (a dialog), a reload or closing the tab through
 * the browser's own `beforeunload` prompt (browsers show their own text there). Moving inside the
 * page (another ?step= of the tour editor) is not leaving.
 *
 * `allowNext()` lets the next navigation through without asking: a page calls it right before it
 * navigates itself after a successful save (the state update that clears `dirty` would come too
 * late for that navigation).
 */
export function useUnsavedChanges(dirty: boolean, texts?: UnsavedTexts) {
  const { t } = useTranslation()
  const { modal } = App.useApp()
  const skip = useRef(false)
  const blocker = useBlocker(({ currentLocation, nextLocation }) => {
    if (skip.current) {
      skip.current = false
      return false
    }
    return dirty && currentLocation.pathname !== nextLocation.pathname
  })
  const asking = useRef(false)   // one question at a time (StrictMode runs effects twice)
  const dialog = texts ?? {
    title: t('cabinet.profile.unsavedTitle'), leave: t('cabinet.profile.unsavedLeave'), stay: t('cabinet.profile.unsavedStay'),
  }
  const key = JSON.stringify(dialog)

  useEffect(() => {
    if (blocker.state !== 'blocked' || asking.current) return
    asking.current = true
    const { title, content, leave, stay } = JSON.parse(key) as UnsavedTexts
    modal.confirm({
      title,
      content,
      okText: leave,
      cancelText: stay,
      onOk: () => { asking.current = false; blocker.proceed() },
      onCancel: () => { asking.current = false; blocker.reset() },
    })
  }, [blocker, modal, key])

  useEffect(() => {
    if (!dirty) return
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  return { allowNext: () => { skip.current = true } }
}
