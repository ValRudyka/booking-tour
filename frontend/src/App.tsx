import { App as AntdApp, ConfigProvider } from 'antd'
import ukUA from 'antd/locale/uk_UA'
import dayjs from 'dayjs'
import 'dayjs/locale/uk'
import type { ReactNode } from 'react'
import { antdTheme } from './theme'

// antd's DatePicker formats dates with dayjs, so its locale is set next to antd's own.
dayjs.locale('uk')

/** Providers shared by the app and the tests. */
export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <ConfigProvider theme={antdTheme} locale={ukUA}>
      <AntdApp>{children}</AntdApp>
    </ConfigProvider>
  )
}
