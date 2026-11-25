import { Card, Typography } from 'antd'
import type { ReactNode } from 'react'
import './auth.css'

/** The narrow centred card of the auth pages (~420 px; full width on a phone). */
export function AuthCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="auth-page">
      <Card className="auth-card">
        <Typography.Title level={1} className="auth-title">{title}</Typography.Title>
        {children}
      </Card>
    </div>
  )
}
