import { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Card, Checkbox, Descriptions, Drawer, Empty, Form, Input, Select, Space, Table, Tag, Typography, message } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { apiClient } from '../services/api'

const { Title, Text, Paragraph, Link } = Typography

interface SourceSnapshot {
  publisher: string
  source_url: string
  title: string
  published_at: string
  source_modified_at?: string
  retrieved_at: string
  content_sha256: string
  raw_html_sha256?: string
  raw_xml_sha256?: string
  menu_item_sha256?: string
  time_basis?: string
  text: string
}

interface RuleCheck {
  criterion: string
  rule_quote?: string
  evidence_quote: string
  status: string
  reviewed_by: string
  reviewed_at: string
}

interface RuleReview {
  resolution_rules_sha256: string
  source_content_sha256?: string
  rule_document_sha256?: string
  complete: boolean
  reviewed_by: string
  reviewed_at: string
  evidence_verdict?: 'QUALIFIES' | 'DOES_NOT_QUALIFY'
  evidence_reason?: string
}

interface JevSnapshot {
  model?: string
  scores: { yes: number; no: number; ambiguous: number }
}

interface RuleDocumentSnapshot {
  url: string
  raw_sha256: string
  text_sha256: string
  page_count: number
  retrieved_at: string
  text: string
}

interface QuoteSnapshot {
  shares: string
  vwap: string
  cost: string
  fee: string
  gap_per_share: string
  book_age_seconds: number
  book_timestamp: string
  book_hash?: string
  levels_used: Array<{ price: string; shares: string }>
}

interface FactChainRecord {
  schema_version: number
  observed_at: string
  market_slug: string
  category?: string
  market_tags?: string[]
  market_tags_rechecked_at?: string
  market_created_at?: string
  market_rechecked_at?: string
  market_closed?: boolean | null
  market_accepting_orders?: boolean | null
  question?: string
  resolution_rules?: string
  gamma_resolution_rules?: string
  rule_document_url?: string
  rule_document?: RuleDocumentSnapshot
  rule_document_rechecked_at?: string
  source?: SourceSnapshot
  source_rechecked_at?: string
  source_recheck_content_sha256?: string
  rule_review?: RuleReview
  rule_checks?: RuleCheck[]
  jev_evidence?: Array<{ source_url: string; source_title?: string; published_at?: string; time_basis?: string; source_modified_at?: string; observed_at: string; text: string }>
  jev?: JevSnapshot
  evaluated_outcome?: string
  quote?: QuoteSnapshot
  requested_shares?: string
  fee_rate?: string | null
  market_restricted?: boolean
  orderbook_enabled?: boolean
  fees_enabled?: boolean
  min_gap?: string
  discovery_query?: string
  discovery_basis?: string
  status: string
  reason?: string
  candidate_outcome?: string | null
  paper_only: boolean
}

interface FactChainList {
  available: boolean
  malformedCount: number
  records: FactChainRecord[]
}

type RecordKind = 'observations' | 'discovery'

const statusText: Record<string, string> = {
  MARKET_UNAVAILABLE: '市场不可用',
  OUT_OF_SCOPE: '范围外',
  SCOPE_UNVERIFIED: '市场范围待核实',
  SOURCE_UNAVAILABLE: '官方来源不可用',
  SOURCE_TYPE_UNSUPPORTED: '来源类型不满足规则',
  RULE_REVIEW_REQUIRED: '规则待核对',
  EVIDENCE_NOT_QUALIFYING: '证据不符合规则',
  JEV_UNAVAILABLE: 'Jev 不可用',
  JEV_INCONCLUSIVE: 'Jev 未确立结果',
  QUOTE_UNAVAILABLE: '单侧盘口不可用',
  RESTRICTION_UNVERIFIED: '地域限制待核实',
  BELOW_GAP: '价格差不足',
  REVIEW_CANDIDATE: '观察时待复核候选',
  SKIPPED: '已跳过'
}

const formatTime = (value?: string): string => {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

const officialUrl = (value: string): string | undefined => {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && ['www.federalreserve.gov', 'www.whitehouse.gov', 'www.senate.gov'].includes(url.hostname)
      ? value : undefined
  } catch {
    return undefined
  }
}

const ruleDocumentUrl = (value: string): string | undefined => {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && url.hostname === 'polymarket-upload.s3.us-east-2.amazonaws.com'
      && url.pathname.startsWith('/market_products/') && url.pathname.toLowerCase().endsWith('.pdf')
      ? value : undefined
  } catch {
    return undefined
  }
}

interface SeedFormValues {
  market_slug: string
  category: 'politics' | 'finance'
  source_kind: 'federal_reserve_monetary' | 'white_house_presidential' | 'white_house_briefings' | 'senate_roll_call'
  source_url: string
}

const downloadInput = (name: string, cases: object[]) => {
  const url = URL.createObjectURL(new Blob([JSON.stringify(cases, null, 2)], { type: 'application/json' }))
  const link = document.createElement('a')
  link.href = url
  link.download = name
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
}

const SeedBuilder: React.FC = () => {
  const [form] = Form.useForm<SeedFormValues>()
  const exportSeed = (values: SeedFormValues) => {
    downloadInput(`jev-seed-${values.market_slug}.json`, [{
      market_slug: values.market_slug,
      category: values.category,
      source_kind: values.source_kind,
      source_url: values.source_url.trim()
    }])
    message.success('已导出观察输入；先运行本地只读 CLI，再刷新本页查看来源与规则')
  }

  return <Card title="新建只读观察">
    <Paragraph type="secondary">先选开放的政治或金融二元市场，再提供与其结算条件相关的官方文章或参议院投票 XML。这里只生成输入文件；官方目录、来源时间及市场范围仍由本地 CLI 重新检查。</Paragraph>
    <Form form={form} layout="vertical" onFinish={exportSeed}>
      <Form.Item name="market_slug" label="Polymarket 市场 slug" rules={[{ required: true, pattern: /^[a-z0-9][a-z0-9-]*$/, message: '请填写 URL 中的小写市场 slug' }]}>
        <Input placeholder="例如 another-fed-rate-hike-in-2026" />
      </Form.Item>
      <Form.Item name="category" label="市场类别（须与 Gamma 标签一致）" rules={[{ required: true, message: '请选择市场类别' }]}>
        <Select options={[{ value: 'politics', label: '政治' }, { value: 'finance', label: '金融 / 经济' }]} />
      </Form.Item>
      <Form.Item name="source_kind" label="官方来源" rules={[{ required: true, message: '请选择来源' }]}>
        <Select options={[
          { value: 'federal_reserve_monetary', label: '美联储货币政策 RSS' },
          { value: 'white_house_presidential', label: '白宫 Presidential Actions RSS' },
          { value: 'white_house_briefings', label: '白宫 Briefings & Statements RSS' },
          { value: 'senate_roll_call', label: '美国参议院编号投票 XML' }
        ]} />
      </Form.Item>
      <Form.Item noStyle dependencies={['source_kind']}>
        {({ getFieldValue }) => <Form.Item name="source_url" label="官方来源 URL" rules={[{ required: true, message: '请填写来源 URL' }, {
          validator: async (_, value: string) => {
            const sourceKind = getFieldValue('source_kind')
            const host = sourceKind === 'federal_reserve_monetary' ? 'www.federalreserve.gov' : sourceKind === 'senate_roll_call' ? 'www.senate.gov' : 'www.whitehouse.gov'
            if (value && (!officialUrl(value.trim()) || new URL(value.trim()).hostname !== host)) {
              throw new Error(`URL 必须属于 ${host}`)
            }
            if (value && sourceKind === 'senate_roll_call' && !/^https:\/\/www\.senate\.gov\/legislative\/LIS\/roll_call_votes\/vote(\d{3})([12])\/vote_\1_\2_\d{5}\.xml$/.test(value.trim())) {
              throw new Error('请填写参议院官方编号投票 XML，不能使用可变的确认名单')
            }
          }
        }]}>
          <Input placeholder="https://..." />
        </Form.Item>}
      </Form.Item>
      <Button type="primary" htmlType="submit">导出观察 JSON</Button>
    </Form>
    <Paragraph style={{ marginTop: 12, marginBottom: 0 }}>在项目目录运行：<Text code>python3 scripts/jev_fact_chain.py --input /下载文件的绝对路径</Text></Paragraph>
    <Paragraph style={{ marginTop: 8, marginBottom: 0 }} type="secondary">还不知道市场 slug？可用 <Text code>python3 scripts/jev_fact_chain_discover.py --source-kind federal_reserve_monetary --source-url 官方文章URL --query "Federal Reserve"</Text> 生成关键词线索；线索不代表规则匹配。</Paragraph>
  </Card>
}

interface ReviewFormValues {
  reviewed_by: string
  complete: boolean
  evidence_verdict: 'QUALIFIES' | 'DOES_NOT_QUALIFY'
  evidence_reason: string
  checks: Array<{ criterion: string; rule_quote: string; evidence_quote: string; status: 'CONFIRMED' | 'EXCLUDED' }>
}

const RuleReviewBuilder: React.FC<{ record: FactChainRecord }> = ({ record }) => {
  const [form] = Form.useForm<ReviewFormValues>()
  if (!record.source || !record.resolution_rules || !record.category) return null
  if (record.rule_document_url && !record.rule_document) {
    return <Alert type="warning" showIcon message="外部完整规则尚未取得，不能导出完整审核" />
  }

  const source = record.source
  const exportReview = async (values: ReviewFormValues) => {
    if (values.evidence_verdict === 'QUALIFIES' && values.checks.some(check => check.status !== 'CONFIRMED')) {
      message.error('标为符合规则时，每项条件都必须是“事实满足此规则”')
      return
    }
    if (values.evidence_verdict === 'DOES_NOT_QUALIFY' && !values.checks.some(check => check.status === 'EXCLUDED')) {
      message.error('标为不符合规则时，至少一项条件必须说明排除原因')
      return
    }
    if (!window.crypto?.subtle) {
      message.error('当前浏览器无法计算规则 SHA-256，请使用安全上下文打开页面')
      return
    }
    const bytes = new TextEncoder().encode(record.resolution_rules)
    const digest = await window.crypto.subtle.digest('SHA-256', bytes)
    const resolutionRulesSha256 = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('')
    const reviewedAt = new Date().toISOString()
    const caseInput = [{
      market_slug: record.market_slug,
      category: record.category,
      source_kind: source.publisher,
      source_url: source.source_url,
      rule_review: {
        resolution_rules_sha256: resolutionRulesSha256,
        source_content_sha256: source.content_sha256,
        ...(record.rule_document ? { rule_document_sha256: record.rule_document.raw_sha256 } : {}),
        complete: values.evidence_verdict === 'QUALIFIES' && values.complete,
        reviewed_by: values.reviewed_by.trim(),
        reviewed_at: reviewedAt,
        evidence_verdict: values.evidence_verdict,
        evidence_reason: values.evidence_reason.trim()
      },
      rule_checks: values.checks.map(check => ({
        criterion: check.criterion.trim(),
        rule_quote: check.rule_quote.trim(),
        evidence_quote: check.evidence_quote.trim(),
        status: check.status,
        reviewed_by: values.reviewed_by.trim(),
        reviewed_at: reviewedAt
      }))
    }]
    downloadInput(`jev-review-${record.market_slug}.json`, caseInput)
    message.success('已导出核对输入；仍须在本地运行只读 CLI，系统会重新校验来源和规则')
  }

  return <Card size="small" title="人工逐项核对并导出输入">
    <Alert type="warning" showIcon style={{ marginBottom: 16 }} message="请阅读完整结算规则及官方原文" description="逐项摘录规则原文及对应事实；特别核对生效时间、排除条款和最早可结算时间。不符合规则的事实应标为排除，CLI 会记录并在 Jev 前停止。" />
    {record.rule_document && <Alert type="warning" showIcon style={{ marginBottom: 16 }} message="此市场另有完整规则 PDF" description="请打开原 PDF 逐页核对，页面抽取文本仅用于查找和版本绑定；确认页内图表、脚注和文字均已覆盖后才能勾选完整审核。" />}
    <Paragraph type="secondary">下载后在项目目录运行：<Text code>python3 scripts/jev_fact_chain.py --input /下载文件的绝对路径</Text>。结果会写入只读审计快照；本页刷新后可查看后续阶段。</Paragraph>
    <Form form={form} layout="vertical" initialValues={{ checks: [{}], complete: false }} onFinish={values => void exportReview(values)}>
      <Form.Item name="reviewed_by" label="核对人" rules={[{ required: true, whitespace: true, message: '请填写核对人' }]}>
        <Input maxLength={100} />
      </Form.Item>
      <Form.List name="checks" rules={[{ validator: async (_, checks) => {
        if (!checks?.length) throw new Error('至少需要一项结算条件')
      } }]}>
        {(fields, { add, remove }, { errors }) => <>
          {fields.map((field, index) => <Card size="small" key={field.key} title={`结算条件 ${index + 1}`} extra={fields.length > 1 ? <Button type="link" onClick={() => remove(field.name)}>删除</Button> : null} style={{ marginBottom: 12 }}>
            <Form.Item name={[field.name, 'criterion']} label="规则条件及核对结论" rules={[{ required: true, whitespace: true, message: '请逐项填写规则条件' }]}>
              <Input.TextArea rows={2} maxLength={1000} />
            </Form.Item>
            <Form.Item name={[field.name, 'rule_quote']} label="当前结算规则原文片段" rules={[{ required: true, whitespace: true, message: '请摘录规则原文' }, {
              validator: async (_, quote: string) => {
                if (quote && !record.resolution_rules?.toLocaleLowerCase().includes(quote.trim().toLocaleLowerCase())) {
                  throw new Error('片段不在当前结算规则中')
                }
              }
            }]}>
              <Input.TextArea rows={2} maxLength={2000} />
            </Form.Item>
            <Form.Item name={[field.name, 'evidence_quote']} label="官方原文片段" rules={[{ required: true, whitespace: true, message: '请填写官方原文片段' }, {
              validator: async (_, quote: string) => {
                if (quote && !source.text.toLocaleLowerCase().includes(quote.trim().toLocaleLowerCase())) {
                  throw new Error('片段不在已保存的官方原文中')
                }
              }
            }]}>
              <Input.TextArea rows={2} maxLength={2000} />
            </Form.Item>
            <Form.Item name={[field.name, 'status']} label="此事实与该规则的关系" rules={[{ required: true, message: '请选择核对结果' }]}>
              <Select options={[
                { value: 'CONFIRMED', label: '事实满足此规则' },
                { value: 'EXCLUDED', label: '规则排除此事实' }
              ]} />
            </Form.Item>
          </Card>)}
          <Form.ErrorList errors={errors} />
          <Button onClick={() => add()} style={{ marginBottom: 16 }}>添加结算条件</Button>
        </>}
      </Form.List>
      <Form.Item name="evidence_verdict" label="这份官方来源能否用于确认结算结果？" rules={[{ required: true, message: '请选择整体结论' }]}>
        <Select options={[
          { value: 'QUALIFIES', label: '符合规则，允许进入 Jev 判读' },
          { value: 'DOES_NOT_QUALIFY', label: '不符合规则，只保存排除审计' }
        ]} />
      </Form.Item>
      <Form.Item name="evidence_reason" label="整体结论依据（包含日期与排除条款）" rules={[{ required: true, whitespace: true, message: '请说明为何符合或被排除' }]}>
        <Input.TextArea rows={2} maxLength={2000} />
      </Form.Item>
      <Form.Item shouldUpdate={(previous, current) => previous.evidence_verdict !== current.evidence_verdict}>
        {({ getFieldValue }) => <Form.Item name="complete" valuePropName="checked" rules={[{ validator: async (_, checked) => {
          if (getFieldValue('evidence_verdict') === 'QUALIFIES' && !checked) {
            throw new Error('进入 Jev 前必须确认已逐条覆盖完整结算规则')
          }
        } }]}>
          <Checkbox disabled={getFieldValue('evidence_verdict') !== 'QUALIFIES'}>只有证据符合规则时，才确认已逐条覆盖上方完整结算规则</Checkbox>
        </Form.Item>}
      </Form.Item>
      <Button type="primary" htmlType="submit">导出只读核对 JSON</Button>
    </Form>
  </Card>
}

const JevFactChain: React.FC = () => {
  const [data, setData] = useState<FactChainList | null>(null)
  const [kind, setKind] = useState<RecordKind>('observations')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<FactChainRecord | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await apiClient.get<{ code: number; data: FactChainList | null; msg: string }>('/jev-fact-chain/list', { params: { kind } })
      if (response.data.code !== 0 || !response.data.data) {
        throw new Error(response.data.msg || '读取 Jev 事实链失败')
      }
      setData(response.data.data)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '读取 Jev 事实链失败')
    } finally {
      setLoading(false)
    }
  }, [kind])

  useEffect(() => { void load() }, [load])

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Card extra={<Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>刷新</Button>}>
        <Title level={2} style={{ marginTop: 0 }}>Jev 事实链研究</Title>
        <Paragraph>政治与金融市场的只读核验：官方来源 → 结算规则逐项核对 → Jev 判读 → 单侧盘口复核。</Paragraph>
        <Tag color="blue">Shadow / 不下单</Tag>
        <Text type="secondary">仅展示已保存的快照；模型分数不是已校准的胜率，候选不代表可成交利润。</Text>
      </Card>

      {error && <Alert type="error" showIcon message={error} />}
      {data && !data.available && <Alert type="warning" showIcon message="尚无事实链快照" description="运行只读 Jev 事实链 CLI 并让后端读取同一快照文件后，记录会显示在这里。" />}
      {data && data.malformedCount > 0 && <Alert type="warning" showIcon message={`${data.malformedCount} 条损坏快照已跳过`} />}

      <SeedBuilder />

      <Card title={kind === 'observations' ? '核验记录' : '关键词线索'} extra={<Select<RecordKind>
        value={kind}
        disabled={loading}
        onChange={value => { setSelected(null); setData(null); setKind(value) }}
        options={[{ value: 'observations', label: '核验记录' }, { value: 'discovery', label: '关键词线索（未核对）' }]}
        style={{ width: 190 }}
      />}>
        {kind === 'discovery' && <Alert type="warning" showIcon message="关键词线索不是事实或交易信号" description="市场与官方文章的关系、完整结算规则及可交易性尚未核对；此列表不代表 Jev 判读或 edge。" style={{ marginBottom: 16 }} />}
        <Table<FactChainRecord>
          loading={loading}
          dataSource={data?.records || []}
          rowKey={record => `${record.market_slug}-${record.observed_at}`}
          locale={{ emptyText: <Empty description={kind === 'observations' ? '暂无核验记录' : '暂无关键词线索'} /> }}
          pagination={{ pageSize: 10 }}
          scroll={{ x: 900 }}
          columns={[
            { title: '观察时间', dataIndex: 'observed_at', width: 185, render: formatTime },
            { title: '市场', dataIndex: 'question', ellipsis: true, render: (_: unknown, record) => record.question || record.market_slug },
            { title: '类别', dataIndex: 'category', width: 90, render: (value: string) => value || '—' },
            { title: '状态', dataIndex: 'status', width: 190, render: (value: string, record) => <><Tag color={value === 'REVIEW_CANDIDATE' ? 'orange' : 'default'}>{statusText[value] || value}</Tag>{record.discovery_basis && <Tag>关键词线索</Tag>}</> },
            { title: '候选方向', dataIndex: 'candidate_outcome', width: 110, render: (value?: string) => value || '—' },
            { title: '详情', width: 90, render: (_: unknown, record) => <Button type="link" onClick={() => setSelected(record)}>查看链路</Button> }
          ]}
        />
      </Card>

      <Drawer title={selected?.question || selected?.market_slug} open={selected !== null} onClose={() => setSelected(null)} width={760}>
        {selected && <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Alert type={selected.status === 'REVIEW_CANDIDATE' ? 'warning' : 'info'} showIcon message={statusText[selected.status] || selected.status} description={selected.discovery_basis && selected.status === 'RULE_REVIEW_REQUIRED' ? '关键词关联和完整结算规则均尚未核对。' : selected.reason || '只读研究快照，非交易指令。'} />
          {selected.discovery_basis && <Alert type="warning" showIcon message="关键词搜索仅供发现" description={`搜索词：${selected.discovery_query || '未记录'}。市场与官方事实是否相关、是否满足完整结算规则，均尚未经核对；不得据此调用 Jev 或判断 edge。`} />}

          <Card size="small" title="1 · 市场范围与官方事实来源">
            <Descriptions column={1} size="small">
              <Descriptions.Item label="Gamma 市场标签">{selected.market_tags?.length ? selected.market_tags.join('、') : '未核实'}</Descriptions.Item>
            </Descriptions>
            {selected.source ? <>
              <Descriptions column={1} size="small">
                <Descriptions.Item label="来源">{selected.source.publisher}</Descriptions.Item>
                <Descriptions.Item label="标题">{selected.source.title}</Descriptions.Item>
                <Descriptions.Item label={selected.source.time_basis === 'vote_date' ? '投票时间' : '发布时间'}>{formatTime(selected.source.published_at)}</Descriptions.Item>
                {selected.source.source_modified_at && <Descriptions.Item label="官网最后修改时间">{formatTime(selected.source.source_modified_at)}</Descriptions.Item>}
                <Descriptions.Item label="抓取时间">{formatTime(selected.source.retrieved_at)}</Descriptions.Item>
                {selected.source_rechecked_at && <Descriptions.Item label="Jev 后来源复核时间">{formatTime(selected.source_rechecked_at)}</Descriptions.Item>}
                <Descriptions.Item label="原文">{officialUrl(selected.source.source_url) ? <Link href={selected.source.source_url} target="_blank" rel="noopener noreferrer">打开官方记录</Link> : '链接未通过白名单'}</Descriptions.Item>
                <Descriptions.Item label={selected.source.raw_html_sha256 || selected.source.raw_xml_sha256 ? '核对文本 SHA-256' : '旧版内容 SHA-256'}><Text code copyable>{selected.source.content_sha256}</Text></Descriptions.Item>
                {selected.source_recheck_content_sha256 && <Descriptions.Item label="复核时文本 SHA-256"><Text code copyable>{selected.source_recheck_content_sha256}</Text></Descriptions.Item>}
                {selected.source.raw_html_sha256 && <Descriptions.Item label="原始 HTML SHA-256"><Text code copyable>{selected.source.raw_html_sha256}</Text></Descriptions.Item>}
                {selected.source.raw_xml_sha256 && <Descriptions.Item label="原始投票 XML SHA-256"><Text code copyable>{selected.source.raw_xml_sha256}</Text></Descriptions.Item>}
                {selected.source.menu_item_sha256 && <Descriptions.Item label="官方目录条目 SHA-256"><Text code copyable>{selected.source.menu_item_sha256}</Text></Descriptions.Item>}
              </Descriptions>
              <Paragraph ellipsis={{ rows: 5, expandable: true, symbol: '展开原文快照' }}>{selected.source.text}</Paragraph>
            </> : <Text type="secondary">未取得可核对的官方来源。</Text>}
          </Card>

          <Card size="small" title="2 · 结算规则逐项核对">
            <Paragraph><Text strong>Gamma 市场创建时间：</Text>{formatTime(selected.market_created_at)}</Paragraph>
            <Paragraph><Text strong>Gamma 市场说明：</Text>{selected.gamma_resolution_rules || selected.resolution_rules || '未获取'}</Paragraph>
            {selected.rule_document ? <>
              <Descriptions column={1} size="small">
                <Descriptions.Item label="外部完整规则 PDF">{ruleDocumentUrl(selected.rule_document.url) ? <Link href={selected.rule_document.url} target="_blank" rel="noopener noreferrer">打开原始规则文件</Link> : '链接未通过白名单'}</Descriptions.Item>
                <Descriptions.Item label="页数 / 抓取时间">{selected.rule_document.page_count} 页 · {formatTime(selected.rule_document.retrieved_at)}</Descriptions.Item>
                <Descriptions.Item label="原始 PDF SHA-256"><Text code copyable>{selected.rule_document.raw_sha256}</Text></Descriptions.Item>
                <Descriptions.Item label="抽取文本 SHA-256"><Text code copyable>{selected.rule_document.text_sha256}</Text></Descriptions.Item>
                {selected.rule_document_rechecked_at && <Descriptions.Item label="Jev 后规则文件复核时间">{formatTime(selected.rule_document_rechecked_at)}</Descriptions.Item>}
              </Descriptions>
              <Paragraph ellipsis={{ rows: 6, expandable: true, symbol: '展开规则 PDF 文本' }}>{selected.rule_document.text}</Paragraph>
            </> : selected.rule_document_url ? <Alert type="warning" showIcon message="外部完整规则文件未取得或未通过校验" style={{ marginBottom: 8 }} /> : null}
            {selected.rule_review && <Descriptions column={1} size="small">
              <Descriptions.Item label="完整规则核对">{selected.rule_review.complete ? '人工确认已逐条覆盖' : '未完成'}</Descriptions.Item>
              <Descriptions.Item label="规则版本 SHA-256"><Text code copyable>{selected.rule_review.resolution_rules_sha256}</Text></Descriptions.Item>
              {selected.rule_document && <Descriptions.Item label="审核绑定的 PDF SHA-256"><Text code copyable>{selected.rule_review.rule_document_sha256 || '未绑定，不能进入 Jev'}</Text></Descriptions.Item>}
              <Descriptions.Item label={selected.source?.raw_html_sha256 || selected.source?.raw_xml_sha256 ? '核对时来源文本 SHA-256' : '核对时旧版文章 SHA-256'}><Text code copyable>{selected.rule_review.source_content_sha256 || '未绑定，需重新核对'}</Text></Descriptions.Item>
              <Descriptions.Item label="核对人 / 时间">{selected.rule_review.reviewed_by} · {formatTime(selected.rule_review.reviewed_at)}</Descriptions.Item>
              <Descriptions.Item label="证据结论">{selected.rule_review.evidence_verdict || '未确认'} · {selected.rule_review.evidence_reason || '—'}</Descriptions.Item>
            </Descriptions>}
            {selected.rule_review && !selected.rule_review.source_content_sha256 && <Alert type="warning" showIcon message="旧快照未绑定官方来源版本，须重新核对后才能进入 Jev" style={{ marginBottom: 8 }} />}
            {selected.rule_checks?.length ? selected.rule_checks.map((check, index) => (
              <Card size="small" key={`${check.criterion}-${index}`} style={{ marginBottom: 8 }}>
                <Space direction="vertical">
                  <Text strong>{index + 1}. {check.criterion}</Text>
                  <Tag color={check.status === 'CONFIRMED' ? 'green' : 'orange'}>{check.status}</Tag>
                  <Text>规则原文：{check.rule_quote || '未记录'}</Text>
                  <Text>证据原文：{check.evidence_quote}</Text>
                  <Text type="secondary">核对人：{check.reviewed_by || '未记录'} · {formatTime(check.reviewed_at)}</Text>
                </Space>
              </Card>
            )) : <Text type="secondary">尚无逐项核对记录；不得进入 Jev 判读。</Text>}
          </Card>

          <RuleReviewBuilder key={`${selected.market_slug}-${selected.observed_at}`} record={selected} />

          <Card size="small" title="3 · Jev 判读">
            {selected.jev_evidence?.map((evidence, index) => <Descriptions key={`${evidence.source_url}-${index}`} column={1} size="small">
              <Descriptions.Item label="送入 Jev 的来源">{officialUrl(evidence.source_url) ? <Link href={evidence.source_url} target="_blank" rel="noopener noreferrer">打开官方记录</Link> : '链接未通过白名单'}</Descriptions.Item>
              {evidence.source_title && <Descriptions.Item label="送入 Jev 的官方标题">{evidence.source_title}</Descriptions.Item>}
              {evidence.published_at && <Descriptions.Item label={evidence.time_basis === 'vote_date' ? '送入 Jev 的投票时间' : '送入 Jev 的发布时间'}>{formatTime(evidence.published_at)}</Descriptions.Item>}
              {evidence.source_modified_at && <Descriptions.Item label="送入 Jev 的官网修改时间">{formatTime(evidence.source_modified_at)}</Descriptions.Item>}
              <Descriptions.Item label="送入 Jev 的事实观测时间">{formatTime(evidence.observed_at)}</Descriptions.Item>
              <Descriptions.Item label="送入 Jev 的官方事实文本">{evidence.text}</Descriptions.Item>
            </Descriptions>)}
            {selected.jev ? <Descriptions column={1} size="small">
              <Descriptions.Item label="模型">{selected.jev.model || '未知'}</Descriptions.Item>
              <Descriptions.Item label="Yes">{selected.jev.scores.yes}</Descriptions.Item>
              <Descriptions.Item label="No">{selected.jev.scores.no}</Descriptions.Item>
              <Descriptions.Item label="歧义">{selected.jev.scores.ambiguous}</Descriptions.Item>
              <Descriptions.Item label="待复核方向">{selected.evaluated_outcome || '无'}</Descriptions.Item>
            </Descriptions> : <Text type="secondary">前置门禁未通过或尚未判读。</Text>}
          </Card>

          <Card size="small" title="4 · 单侧盘口与费用">
            <Descriptions column={1} size="small">
              <Descriptions.Item label="Gamma 报价前复核时间">{formatTime(selected.market_rechecked_at)}</Descriptions.Item>
              {selected.market_tags_rechecked_at && <Descriptions.Item label="Gamma 范围标签复核时间">{formatTime(selected.market_tags_rechecked_at)}</Descriptions.Item>}
              <Descriptions.Item label="市场接单状态">{selected.market_closed === true ? '已关闭' : selected.market_accepting_orders === true ? '接单中' : selected.market_accepting_orders === false ? '不接单' : '未确认'}</Descriptions.Item>
              <Descriptions.Item label="盘口启用">{selected.orderbook_enabled === true ? '是' : '未确认'}</Descriptions.Item>
              <Descriptions.Item label="市场地域限制">{selected.market_restricted === false ? '无' : selected.market_restricted === true ? '有，须独立核实可交易性' : '未知'}</Descriptions.Item>
              <Descriptions.Item label="费用启用 / 费率">{selected.fees_enabled === true ? '是' : selected.fees_enabled === false ? '否' : '未知'} / {selected.fee_rate ?? '未知'}</Descriptions.Item>
            </Descriptions>
            {selected.quote ? <>
              <Alert type="warning" showIcon message="这是观察时的历史盘口，不是当前可执行报价" description="盘口时间戳和 30 秒新鲜度只针对抓取当时；查看页面时须重新运行只读核验，且候选仍需独立复核。" style={{ marginBottom: 8 }} />
              <Descriptions column={1} size="small">
                <Descriptions.Item label="方向">{selected.evaluated_outcome}</Descriptions.Item>
                <Descriptions.Item label="份额 / VWAP">{selected.quote.shares} / ${selected.quote.vwap}</Descriptions.Item>
                <Descriptions.Item label="总成本 / 费用">${selected.quote.cost} / ${selected.quote.fee}</Descriptions.Item>
                <Descriptions.Item label="若兑付 $1 的单位净差">${selected.quote.gap_per_share}</Descriptions.Item>
                <Descriptions.Item label="盘口年龄">{selected.quote.book_age_seconds} 秒</Descriptions.Item>
                <Descriptions.Item label="盘口时间戳 / 哈希">{selected.quote.book_timestamp} / {selected.quote.book_hash || '—'}</Descriptions.Item>
              </Descriptions>
              {selected.status === 'RESTRICTION_UNVERIFIED' && <Alert type="warning" showIcon message="仅为只读报价；地域限制未核实，不生成候选。" style={{ marginBottom: 8 }} />}
              <Text type="secondary">逐档买入：{selected.quote.levels_used.map(level => `${level.shares} 份 @ $${level.price}`).join('，')}</Text>
            </> : <Text type="secondary">没有通过时效、深度、最小单量或费用检查的单侧报价。</Text>}
          </Card>
        </Space>}
      </Drawer>
    </Space>
  )
}

export default JevFactChain
