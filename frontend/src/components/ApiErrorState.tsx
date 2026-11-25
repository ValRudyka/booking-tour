import { ReloadOutlined, ToolOutlined } from '@ant-design/icons'
import { Alert, Button, Result } from 'antd'
import { useTranslation } from 'react-i18next'
import { ApiError } from '../api/client'

interface Props {
  error: Error
  onRetry: () => void
  /** Heading of the error Alert, e.g. «Не вдалося завантажити тури». */
  title: string
}

/** How a failed request looks everywhere: maintenance mode (the API's 503) as a Result, any other
 * error as an Alert with the API's or a generic Ukrainian message and a retry button. */
export function ApiErrorState({ error, onRetry, title }: Props) {
  const { t } = useTranslation()
  const retry = <Button icon={<ReloadOutlined aria-hidden />} onClick={onRetry}>{t('errors.retry')}</Button>
  if (error instanceof ApiError && error.kind === 'maintenance') {
    return <Result icon={<ToolOutlined aria-hidden />} title={t('errors.maintenanceTitle')}
      subTitle={error.message} extra={retry} />
  }
  return <Alert type="error" showIcon title={title} description={error.message} action={retry} />
}
