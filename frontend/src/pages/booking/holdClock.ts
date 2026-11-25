import { useEffect, useRef, useState } from 'react'

/** The text changes once a minute, and every second in the last 2 minutes (spec 04, §4). */
export const SECONDS_PHASE_MS = 2 * 60_000

/** How long until the shown text changes: the next whole minute, or the next second at the end. */
function nextChange(left: number): number {
  return left > SECONDS_PHASE_MS
    ? Math.min(left - SECONDS_PHASE_MS, left % 60_000 || 60_000)
    : left % 1000 || 1000
}

/**
 * Milliseconds left until `expiresAt` (the API's hold_expires_at), or null without a hold.
 * The deadline always comes from the server, never from when the page was opened. A timer is set
 * for the next moment the shown text changes, so nothing re-renders in between; `onExpired` is
 * called from that timer once the hold has run out.
 */
export function useHoldRemaining(expiresAt: string | null | undefined, onExpired: () => void): number | null {
  const [now, setNow] = useState(() => Date.now())
  const onExpiredRef = useRef(onExpired)
  useEffect(() => {
    onExpiredRef.current = onExpired
  })
  useEffect(() => {
    if (!expiresAt) return undefined
    const end = Date.parse(expiresAt)
    let timer: ReturnType<typeof setTimeout>
    const schedule = (delay: number) => {
      timer = setTimeout(() => {
        const current = Date.now()
        setNow(current)
        const left = end - current
        if (left <= 0) onExpiredRef.current()
        else schedule(nextChange(left))
      }, delay)
    }
    schedule(0)   // first tick at once: `now` may be from before this hold existed
    return () => clearTimeout(timer)
  }, [expiresAt])
  return expiresAt ? Date.parse(expiresAt) - now : null
}
