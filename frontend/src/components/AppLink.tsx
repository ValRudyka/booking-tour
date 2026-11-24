import { theme } from 'antd'
import { Link, type LinkProps } from 'react-router'

/** A router link (no page reload) in antd's link colour. */
export function AppLink({ style, ...props }: LinkProps) {
  const { token } = theme.useToken()
  return <Link style={{ color: token.colorLink, ...style }} {...props} />
}
