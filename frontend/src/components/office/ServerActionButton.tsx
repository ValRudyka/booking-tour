import { Button, Tooltip, type ButtonProps } from 'antd'
import { useId } from 'react'

/** An action the server decided on (user_actions / admin_actions, spec 13; like staff_actions in
 * spec 09): allowed = a normal button; refused = a disabled button whose reason is shown in a
 * tooltip and read by screen readers through aria-describedby. Never decide this on the client. */
export interface ServerAction {
  allowed: boolean
  reason: string | null
}

interface Props extends Omit<ButtonProps, 'disabled'> {
  info: ServerAction
  /** Disabled for another reason (an action is running). */
  busy?: boolean
}

export function ServerActionButton({ info, busy = false, children, ...rest }: Props) {
  const id = useId()
  if (info.allowed) return <Button {...rest} disabled={busy}>{children}</Button>
  return (
    <>
      <Tooltip title={info.reason}>
        {/* A disabled button gets no mouse events: the wrapper shows the tooltip. */}
        <span className="server-action-refused">
          <Button {...rest} onClick={undefined} disabled aria-describedby={info.reason ? id : undefined}>{children}</Button>
        </span>
      </Tooltip>
      {info.reason && <span id={id} className="visually-hidden">{info.reason}</span>}
    </>
  )
}
