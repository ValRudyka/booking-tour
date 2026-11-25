import { ArrowDownOutlined, ArrowUpOutlined, DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Form, Input, Space, Typography } from 'antd'
import type { FormInstance } from 'antd'
import { useTranslation } from 'react-i18next'
import type { TourRules } from '../../../api/types'
import type { TourFormValues } from './tourForm'

/**
 * Step 2 «Програма» (form 4.6.2.1, field 17): days in order. The day number is the position
 * (1, 2, 3…), so adding, removing or moving a day renumbers them; payloadOf() sends exactly that.
 * A tour of N nights has at most N + 1 days (the server's rule, shown as a hint).
 */
export function TourProgramStep({ form, rules }: { form: FormInstance<TourFormValues>; rules: TourRules }) {
  const { t } = useTranslation()
  const nights = Form.useWatch('nights', form)
  const maxDays = typeof nights === 'number' ? nights + 1 : undefined

  return (
    <Form.List name="program_days" rules={[{
      validator: async (_, days?: unknown[]) => {
        if (maxDays !== undefined && (days?.length ?? 0) > maxDays) {
          throw new Error(t('office.tours.rule.programLength', { max: maxDays }))
        }
      },
    }]}>
      {(items, { add, remove, move }, { errors }) => (
        <Space orientation="vertical" size={12} className="office-full-width">
          <Typography.Paragraph type="secondary">
            {maxDays !== undefined ? t('office.tours.form.programHint', { max: maxDays }) : t('office.tours.form.programHintNoNights')}
          </Typography.Paragraph>
          {items.length === 0 && <Alert type="info" showIcon role="note" title={t('office.tours.form.programEmpty')} />}
          {items.map((item, index) => {
            const day = index + 1
            return (
              <Card key={item.key} size="small" title={<h3 className="office-card-subtitle">{t('office.tours.form.day', { n: day })}</h3>}
                extra={(
                  <Space size={4}>
                    <Button size="small" icon={<ArrowUpOutlined aria-hidden />} disabled={index === 0 || undefined}
                      onClick={() => move(index, index - 1)} aria-label={t('office.tours.form.dayUp', { n: day })} />
                    <Button size="small" icon={<ArrowDownOutlined aria-hidden />} disabled={index === items.length - 1 || undefined}
                      onClick={() => move(index, index + 1)} aria-label={t('office.tours.form.dayDown', { n: day })} />
                    <Button size="small" danger icon={<DeleteOutlined aria-hidden />} onClick={() => remove(index)}
                      aria-label={t('office.tours.form.dayRemove', { n: day })} />
                  </Space>
                )}>
                <Form.Item name={[item.name, 'description']} label={t('office.tours.form.dayText', { n: day })}
                  rules={[{ required: true, whitespace: true, message: t('office.tours.rule.dayText') },
                    { max: rules.max_day_text, message: t('office.tours.rule.dayTextMax', { max: rules.max_day_text }) }]}>
                  <Input.TextArea rows={3} maxLength={rules.max_day_text} showCount className="office-textarea" />
                </Form.Item>
              </Card>
            )
          })}
          <Form.ErrorList errors={errors} />
          <Button icon={<PlusOutlined aria-hidden />} onClick={() => add({ description: '' })}
            disabled={(maxDays !== undefined && items.length >= maxDays) || undefined}>
            {t('office.tours.form.addDay')}
          </Button>
        </Space>
      )}
    </Form.List>
  )
}
