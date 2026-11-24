import { useEffect, useMemo, useRef } from 'react'

/** Calls `callback` once the calls stop for `delayMs`; with delayMs = 0 it calls at once.
 * A pending call is dropped when the component unmounts. */
export function useDebouncedCallback<A extends unknown[]>(callback: (...args: A) => void, delayMs: number) {
  const callbackRef = useRef(callback)
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  useEffect(() => {
    callbackRef.current = callback
  })
  useEffect(() => () => clearTimeout(timerRef.current), [])

  return useMemo(() => {
    const debounced = (...args: A) => {
      clearTimeout(timerRef.current)
      if (delayMs <= 0) {
        callbackRef.current(...args)
        return
      }
      timerRef.current = setTimeout(() => callbackRef.current(...args), delayMs)
    }
    /** Runs the pending call now (e.g. Enter in the search field). */
    debounced.flush = (...args: A) => {
      clearTimeout(timerRef.current)
      callbackRef.current(...args)
    }
    debounced.cancel = () => clearTimeout(timerRef.current)
    return debounced
  }, [delayMs])
}
