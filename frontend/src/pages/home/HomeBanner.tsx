import { SearchOutlined } from '@ant-design/icons'
import { Button, Card, Col, DatePicker, Form, Row, Select } from 'antd'
import type { Dayjs } from 'dayjs'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { useCities, useCountries } from '../../api/reference'
import { SAND_BG } from '../../theme'
import { catalogUrl } from './homeSearch'

const DATE_FORMAT = 'DD.MM.YYYY' // as in the catalog's filters
const ISO = 'YYYY-MM-DD'

interface FormValues {
  country_id?: number
  dates?: [Dayjs, Dayjs] | null
  departure_city_id?: number
}

/**
 * Banner with the quick search (spec §2). The form only builds a catalog URL with the catalog's
 * own parameters; the search itself happens on /tours. Dates mean the same as the catalog's
 * «Дати виїзду»: tours with a start date inside the range. If a reference list fails to load,
 * its select stays empty and the other fields still work.
 */
export function HomeBanner() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const countries = useCountries()
  const cities = useCities()
  const searchSelect = { optionFilterProp: 'label' } as const

  const search = ({ country_id, dates, departure_city_id }: FormValues) => {
    void navigate(catalogUrl({
      country_id, departure_city_id,
      date_from: dates?.[0]?.format(ISO), date_to: dates?.[1]?.format(ISO),
    }))
  }

  return (
    <section className="home-banner" style={{ background: SAND_BG }} aria-labelledby="home-title">
      <h1 id="home-title" className="home-banner-title">{t('home.title')}</h1>
      <p className="home-banner-subtitle">{t('home.subtitle')}</p>

      <Card className="home-search" styles={{ body: { padding: 16 } }}>
        <Form<FormValues> name="home-search" layout="vertical" onFinish={search}
          aria-label={t('home.searchLabel')} requiredMark={false}>
          <Row gutter={16} align="bottom">
            <Col xs={24} md={12} lg={7}>
              <Form.Item name="country_id" label={t('filters.country')}>
                <Select allowClear showSearch={searchSelect} placeholder={t('filters.anyCountry')}
                  loading={countries.isLoading}
                  options={countries.data?.map((c) => ({ value: c.id, label: c.name_uk }))} />
              </Form.Item>
            </Col>
            <Col xs={24} md={12} lg={7}>
              <Form.Item name="dates" label={t('filters.dates')}>
                <DatePicker.RangePicker format={DATE_FORMAT} style={{ width: '100%' }}
                  placeholder={[t('filters.dateFrom'), t('filters.dateTo')]} />
              </Form.Item>
            </Col>
            <Col xs={24} md={12} lg={6}>
              <Form.Item name="departure_city_id" label={t('filters.departureCity')}>
                <Select allowClear showSearch={searchSelect} placeholder={t('filters.anyCity')}
                  loading={cities.isLoading}
                  options={cities.data?.map((c) => ({ value: c.id, label: c.name_uk }))} />
              </Form.Item>
            </Col>
            <Col xs={24} md={12} lg={4}>
              <Form.Item>
                <Button type="primary" htmlType="submit" block icon={<SearchOutlined aria-hidden />}>
                  {t('home.searchButton')}
                </Button>
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Card>
    </section>
  )
}
