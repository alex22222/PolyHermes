import { useEffect, useState } from 'react'
import { Card, Table, Tag, Tabs, message, Space, Button, Tooltip, Radio, Typography } from 'antd'
import { useTranslation } from 'react-i18next'
import { useMediaQuery } from 'react-responsive'
import { ReloadOutlined } from '@ant-design/icons'
import { apiService } from '../services/api'
import type { BridgeTradeRecord, BridgeWebhookLog } from '../types'
import { formatUSDC } from '../utils'

type RecordStatus = '' | 'SUCCESS' | 'PENDING' | 'FAILED'
type WebhookLogStatus = '' | 'SUCCESS' | 'FAILED' | 'PENDING'

const BridgeTradeRecordList: React.FC = () => {
  const { t, i18n } = useTranslation()
  const isMobile = useMediaQuery({ maxWidth: 768 })

  const [activeTab, setActiveTab] = useState('records')

  // 交易记录
  const [records, setRecords] = useState<BridgeTradeRecord[]>([])
  const [recordsLoading, setRecordsLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState<RecordStatus>('')
  const [recordsPagination, setRecordsPagination] = useState({
    current: 1,
    pageSize: 20,
    total: 0
  })

  // Webhook 日志
  const [webhookLogs, setWebhookLogs] = useState<BridgeWebhookLog[]>([])
  const [webhookLogsLoading, setWebhookLogsLoading] = useState(false)
  const [webhookStatusFilter, setWebhookStatusFilter] = useState<WebhookLogStatus>('')
  const [webhookLogsPagination, setWebhookLogsPagination] = useState({
    current: 1,
    pageSize: 20,
    total: 0
  })

  useEffect(() => {
    if (activeTab === 'records') {
      fetchRecords()
    } else if (activeTab === 'webhookLogs') {
      fetchWebhookLogs()
    }
  }, [activeTab, recordsPagination.current, recordsPagination.pageSize, statusFilter, webhookLogsPagination.current, webhookLogsPagination.pageSize, webhookStatusFilter])

  const fetchRecords = async () => {
    setRecordsLoading(true)
    try {
      const response = await apiService.bridgeTradeRecords.list({
        page: recordsPagination.current,
        size: recordsPagination.pageSize,
        status: statusFilter || undefined
      })
      if (response.data.code === 0 && response.data.data) {
        setRecords(response.data.data.list || [])
        setRecordsPagination((prev) => ({
          ...prev,
          total: response.data.data?.total || 0
        }))
      } else {
        message.error(response.data.msg || t('bridgeTradeRecord.fetchFailed') || '获取桥接交易记录失败')
      }
    } catch (error: any) {
      message.error(error.message || t('bridgeTradeRecord.fetchFailed') || '获取桥接交易记录失败')
    } finally {
      setRecordsLoading(false)
    }
  }

  const fetchWebhookLogs = async () => {
    setWebhookLogsLoading(true)
    try {
      const response = await apiService.bridgeWebhookLogs.list({
        page: webhookLogsPagination.current,
        size: webhookLogsPagination.pageSize,
        status: webhookStatusFilter || undefined
      })
      if (response.data.code === 0 && response.data.data) {
        setWebhookLogs(response.data.data.list || [])
        setWebhookLogsPagination((prev) => ({
          ...prev,
          total: response.data.data?.total || 0
        }))
      } else {
        message.error(response.data.msg || t('bridgeWebhookLog.fetchFailed') || '获取 Webhook 日志失败')
      }
    } catch (error: any) {
      message.error(error.message || t('bridgeWebhookLog.fetchFailed') || '获取 Webhook 日志失败')
    } finally {
      setWebhookLogsLoading(false)
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'SUCCESS':
        return 'success'
      case 'PENDING':
        return 'processing'
      case 'FAILED':
        return 'error'
      default:
        return 'default'
    }
  }

  const getSideColor = (side: string) => {
    return side === 'BUY' ? 'green' : 'red'
  }

  /**
   * 对 Bridge 错误信息进行友好分类
   */
  const classifyError = (errorMessage?: string) => {
    if (!errorMessage) return { key: 'unknown', label: t('bridgeTradeRecord.errorType.unknown') || '未知' }
    const lower = errorMessage.toLowerCase()
    if (lower.includes('could not enter trade amount')) {
      return { key: 'enter_amount', label: t('bridgeTradeRecord.errorType.enterAmount') || '无法输入金额' }
    }
    if (lower.includes('could not select outcome')) {
      return { key: 'select_outcome', label: t('bridgeTradeRecord.errorType.selectOutcome') || '无法选择结果' }
    }
    if (lower.includes('bestscore') || lower.includes('referenceerror') || lower.includes('selector')) {
      return { key: 'selector_error', label: t('bridgeTradeRecord.errorType.selectorError') || '选择器错误' }
    }
    if (lower.includes('could not open sell dialog')) {
      return { key: 'open_sell', label: t('bridgeTradeRecord.errorType.openSell') || '无法打开卖出' }
    }
    if (lower.includes('sell post-submit verification failed') || lower.includes('live portfolio quantity did not decrease')) {
      return { key: 'sell_verify_failed', label: t('bridgeTradeRecord.errorType.sellVerifyFailed') || '卖出后验证失败' }
    }
    if (lower.includes('live portfolio insufficient position')) {
      return { key: 'live_position_insufficient', label: t('bridgeTradeRecord.errorType.livePositionInsufficient') || '真实持仓不足' }
    }
    if (lower.includes('success_position_mismatch')) {
      return { key: 'success_position_mismatch', label: t('bridgeTradeRecord.errorType.successPositionMismatch') || '成功记录与持仓不一致' }
    }
    if (lower.includes('unexpected_portfolio_position')) {
      return { key: 'unexpected_portfolio_position', label: t('bridgeTradeRecord.errorType.unexpectedPortfolioPosition') || '异常真实持仓' }
    }
    if (lower.includes('could not resolve polymtrade event')) {
      return { key: 'resolve_event', label: t('bridgeTradeRecord.errorType.resolveEvent') || '事件解析失败' }
    }
    if (lower.includes('insufficient position')) {
      return { key: 'insufficient_position', label: t('bridgeTradeRecord.errorType.insufficientPosition') || '仓位不足' }
    }
    if (lower.includes('could not click')) {
      return { key: 'click_button', label: t('bridgeTradeRecord.errorType.clickButton') || '按钮点击失败' }
    }
    if (
      lower.includes('execution context was destroyed') ||
      lower.includes('target page, context or browser has been closed') ||
      lower.includes('interrupted by another navigation')
    ) {
      return { key: 'navigation_race', label: t('bridgeTradeRecord.errorType.navigationRace') || '导航/重启竞态' }
    }
    if (lower.includes('duplicate short-cycle market buy skipped')) {
      return { key: 'duplicate_short_cycle_buy', label: t('bridgeTradeRecord.errorType.duplicateShortCycleBuy') || '短周期重复买入已跳过' }
    }
    if (lower.includes('network/deposit modal') || lower.includes('insufficient usdc balance') || lower.includes('needs a deposit')) {
      return { key: 'insufficient_balance', label: t('bridgeTradeRecord.errorType.insufficientBalance') || '余额不足' }
    }
    return { key: 'other', label: t('bridgeTradeRecord.errorType.other') || '其他' }
  }

  /**
   * 格式化 JSON 请求/响应体，便于展示
   */
  const formatBodyPreview = (body?: string): string => {
    if (!body) return ''
    try {
      const str = JSON.stringify(JSON.parse(body))
      return str.length > 60 ? str.slice(0, 60) + '...' : str
    } catch {
      return body.length > 60 ? body.slice(0, 60) + '...' : body
    }
  }

  const formatBodyTooltip = (body?: string): string => {
    if (!body) return ''
    try {
      return JSON.stringify(JSON.parse(body), null, 2)
    } catch {
      return body
    }
  }

  const renderBodyCell = (body: string | undefined) => {
    if (!body) return '-'
    const preview = formatBodyPreview(body)
    const formatted = formatBodyTooltip(body)
    return (
      <Tooltip title={<pre style={{ maxHeight: '300px', overflow: 'auto' }}>{formatted}</pre>} placement="topLeft">
        <Typography.Text style={{ fontFamily: 'monospace', fontSize: '12px', color: '#888', cursor: 'help' }} ellipsis>
          {preview}
        </Typography.Text>
      </Tooltip>
    )
  }

  /**
   * 当 marketTitle 为空时，尝试从 rawPayload 解析 title
   */
  const resolveMarketTitle = (record: BridgeTradeRecord): string => {
    if (record.marketTitle) return record.marketTitle
    if (record.rawPayload) {
      try {
        const payload = JSON.parse(record.rawPayload)
        const title = payload?.title || payload?.marketTitle || payload?.market_title
        if (title) return title
      } catch {
        // ignore parse error
      }
    }
    return '-'
  }

  const renderPositionMismatch = (record: BridgeTradeRecord) => {
    if (!record.positionMismatch) return null
    const snapshotTime = record.snapshotSyncedAt
      ? new Date(record.snapshotSyncedAt).toLocaleString(i18n.language || 'zh-CN')
      : '-'
    const tooltip = (
      <Space direction="vertical" size={0}>
        <span>{t('bridgeTradeRecord.positionMismatchReason') || '成功记录与真实持仓不一致'}</span>
        <span>
          {t('bridgeTradeRecord.ledgerNetQuantity') || '账面净持仓'}: {record.ledgerNetQuantity ?? '-'}
        </span>
        <span>
          {t('bridgeTradeRecord.snapshotQuantity') || '真实快照'}: {record.snapshotQuantity ?? '-'}
        </span>
        <span>
          {t('bridgeTradeRecord.snapshotSyncedAt') || '快照同步'}: {snapshotTime}
        </span>
      </Space>
    )
    return (
      <Tooltip title={tooltip} placement="topLeft">
        <Tag color="orange" style={{ cursor: 'help' }}>
          {t('bridgeTradeRecord.positionMismatch') || '持仓漂移'}
        </Tag>
      </Tooltip>
    )
  }

  const recordColumns = [
    {
      title: t('bridgeTradeRecord.id') || 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 70
    },
    {
      title: t('bridgeTradeRecord.market') || '市场',
      dataIndex: 'marketTitle',
      key: 'marketTitle',
      render: (_title: string | undefined, record: BridgeTradeRecord) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{resolveMarketTitle(record)}</Typography.Text>
          <Typography.Text style={{ fontFamily: 'monospace', fontSize: '12px', color: '#888' }}>
            {record.marketId.slice(0, 16)}...
          </Typography.Text>
          {record.externalTradeId && (
            <Typography.Text style={{ fontSize: '11px', color: '#aaa' }}>
              {record.externalTradeId.slice(0, 20)}...
            </Typography.Text>
          )}
        </Space>
      )
    },
    {
      title: t('bridgeTradeRecord.side') || '方向',
      dataIndex: 'side',
      key: 'side',
      width: 90,
      render: (side: string) => <Tag color={getSideColor(side)}>{side}</Tag>
    },
    {
      title: t('bridgeTradeRecord.outcome') || '结果',
      dataIndex: 'outcome',
      key: 'outcome',
      width: 110,
      render: (outcome: string | undefined, record: BridgeTradeRecord) =>
        outcome ? `${outcome} #${record.outcomeIndex ?? '-'}` : '-'
    },
    {
      title: t('bridgeTradeRecord.quantity') || '数量',
      dataIndex: 'quantity',
      key: 'quantity',
      width: 110,
      align: 'right' as const,
      render: (quantity: string) => formatUSDC(quantity)
    },
    {
      title: t('bridgeTradeRecord.price') || '价格',
      dataIndex: 'price',
      key: 'price',
      width: 110,
      align: 'right' as const,
      render: (price: string) => `$${formatUSDC(price)}`
    },
    {
      title: t('bridgeTradeRecord.amount') || '金额',
      dataIndex: 'amount',
      key: 'amount',
      width: 110,
      align: 'right' as const,
      render: (amount: string) => `$${formatUSDC(amount)}`
    },
    {
      title: t('bridgeTradeRecord.status') || '状态',
      dataIndex: 'status',
      key: 'status',
      width: 140,
      render: (status: string, record: BridgeTradeRecord) => {
        const error = classifyError(record.errorMessage)
        return (
          <Space direction="vertical" size={4}>
            <Tag color={getStatusColor(status)}>{status}</Tag>
            {status === 'FAILED' && (
              <Tooltip title={record.errorMessage || '-'} placement="topLeft">
                <Tag color="red" style={{ cursor: 'help', maxWidth: '120px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {error.label}
                </Tag>
              </Tooltip>
            )}
            {renderPositionMismatch(record)}
          </Space>
        )
      }
    },
    {
      title: t('bridgeTradeRecord.createdAt') || '创建时间',
      dataIndex: 'createdAt',
      key: 'createdAt',
      width: 170,
      render: (timestamp: number | undefined) =>
        timestamp ? new Date(timestamp).toLocaleString(i18n.language || 'zh-CN') : '-'
    }
  ]

  const webhookLogColumns = [
    {
      title: t('bridgeWebhookLog.id') || 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 70
    },
    {
      title: t('bridgeWebhookLog.leader') || 'Leader',
      dataIndex: 'leaderName',
      key: 'leader',
      render: (_name: string | undefined, record: BridgeWebhookLog) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{record.leaderName || '-'}</Typography.Text>
          {record.leaderAddress && (
            <Typography.Text style={{ fontFamily: 'monospace', fontSize: '12px', color: '#888' }}>
              {record.leaderAddress.slice(0, 16)}...
            </Typography.Text>
          )}
        </Space>
      )
    },
    {
      title: t('bridgeWebhookLog.market') || '市场',
      dataIndex: 'marketSlug',
      key: 'marketSlug',
      render: (_slug: string | undefined, record: BridgeWebhookLog) => (
        <Space direction="vertical" size={0}>
          <Typography.Text>{record.marketSlug || '-'}</Typography.Text>
          {record.conditionId && (
            <Typography.Text style={{ fontFamily: 'monospace', fontSize: '12px', color: '#888' }}>
              {record.conditionId.slice(0, 16)}...
            </Typography.Text>
          )}
        </Space>
      )
    },
    {
      title: t('bridgeWebhookLog.side') || '方向',
      dataIndex: 'side',
      key: 'side',
      width: 90,
      render: (side: string) => side ? <Tag color={getSideColor(side)}>{side}</Tag> : '-'
    },
    {
      title: t('bridgeWebhookLog.outcome') || '结果',
      dataIndex: 'outcome',
      key: 'outcome',
      width: 120,
      render: (outcome: string | undefined) => outcome || '-'
    },
    {
      title: t('bridgeWebhookLog.statusCode') || 'HTTP 状态',
      dataIndex: 'statusCode',
      key: 'statusCode',
      width: 110,
      render: (code: number | undefined, record: BridgeWebhookLog) => (
        <Tag color={getStatusColor(record.status)}>
          {code ?? '-'}
        </Tag>
      )
    },
    {
      title: t('bridgeWebhookLog.status') || '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string, record: BridgeWebhookLog) => (
        <Space direction="vertical" size={4}>
          <Tag color={getStatusColor(status)}>{status}</Tag>
          {record.errorMessage && (
            <Tooltip title={record.errorMessage} placement="topLeft">
              <Typography.Text style={{ fontSize: '11px', color: '#ff4d4f', cursor: 'help', maxWidth: '120px' }} ellipsis>
                {record.errorMessage}
              </Typography.Text>
            </Tooltip>
          )}
        </Space>
      )
    },
    {
      title: t('bridgeWebhookLog.request') || '请求体',
      dataIndex: 'requestBody',
      key: 'requestBody',
      render: renderBodyCell
    },
    {
      title: t('bridgeWebhookLog.response') || '响应体',
      dataIndex: 'responseBody',
      key: 'responseBody',
      render: renderBodyCell
    },
    {
      title: t('bridgeWebhookLog.createdAt') || '发送时间',
      dataIndex: 'createdAt',
      key: 'createdAt',
      width: 170,
      render: (timestamp: number | undefined) =>
        timestamp ? new Date(timestamp).toLocaleString(i18n.language || 'zh-CN') : '-'
    }
  ]

  const renderRecordsTab = () => (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Space wrap style={{ justifyContent: 'space-between', width: '100%' }}>
        <Radio.Group
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value)
            setRecordsPagination((prev) => ({ ...prev, current: 1 }))
          }}
          optionType="button"
          buttonStyle="solid"
        >
          <Radio.Button value="">{t('bridgeTradeRecord.statusFilter.all') || '全部'}</Radio.Button>
          <Radio.Button value="SUCCESS">{t('bridgeTradeRecord.statusFilter.success') || '成功'}</Radio.Button>
          <Radio.Button value="PENDING">{t('bridgeTradeRecord.statusFilter.pending') || '进行中'}</Radio.Button>
          <Radio.Button value="FAILED">{t('bridgeTradeRecord.statusFilter.failed') || '失败'}</Radio.Button>
        </Radio.Group>
        <Button icon={<ReloadOutlined />} onClick={fetchRecords} loading={recordsLoading}>
          {t('bridgeTradeRecord.refresh') || '刷新'}
        </Button>
      </Space>

      <Table
        dataSource={records}
        columns={recordColumns}
        rowKey="id"
        loading={recordsLoading}
        scroll={isMobile ? { x: 1100 } : undefined}
        pagination={{
          current: recordsPagination.current,
          pageSize: recordsPagination.pageSize,
          total: recordsPagination.total,
          showSizeChanger: !isMobile,
          onChange: (page, pageSize) => setRecordsPagination((prev) => ({ ...prev, current: page, pageSize }))
        }}
      />
    </Space>
  )

  const renderWebhookLogsTab = () => (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Space wrap style={{ justifyContent: 'space-between', width: '100%' }}>
        <Radio.Group
          value={webhookStatusFilter}
          onChange={(e) => {
            setWebhookStatusFilter(e.target.value)
            setWebhookLogsPagination((prev) => ({ ...prev, current: 1 }))
          }}
          optionType="button"
          buttonStyle="solid"
        >
          <Radio.Button value="">{t('bridgeWebhookLog.statusFilter.all') || '全部'}</Radio.Button>
          <Radio.Button value="SUCCESS">{t('bridgeWebhookLog.statusFilter.success') || '成功'}</Radio.Button>
          <Radio.Button value="PENDING">{t('bridgeWebhookLog.statusFilter.pending') || '进行中'}</Radio.Button>
          <Radio.Button value="FAILED">{t('bridgeWebhookLog.statusFilter.failed') || '失败'}</Radio.Button>
        </Radio.Group>
        <Button icon={<ReloadOutlined />} onClick={fetchWebhookLogs} loading={webhookLogsLoading}>
          {t('bridgeWebhookLog.refresh') || '刷新'}
        </Button>
      </Space>

      <Table
        dataSource={webhookLogs}
        columns={webhookLogColumns}
        rowKey="id"
        loading={webhookLogsLoading}
        scroll={isMobile ? { x: 1400 } : undefined}
        pagination={{
          current: webhookLogsPagination.current,
          pageSize: webhookLogsPagination.pageSize,
          total: webhookLogsPagination.total,
          showSizeChanger: !isMobile,
          onChange: (page, pageSize) => setWebhookLogsPagination((prev) => ({ ...prev, current: page, pageSize }))
        }}
      />
    </Space>
  )

  const items = [
    {
      key: 'records',
      label: t('bridgeTradeRecord.recordsTab') || '交易记录',
      children: renderRecordsTab()
    },
    {
      key: 'webhookLogs',
      label: t('bridgeTradeRecord.webhookLogsTab') || 'Webhook 日志',
      children: renderWebhookLogsTab()
    }
  ]

  return (
    <div>
      <div style={{ marginBottom: '16px' }}>
        <h2>{t('bridgeTradeRecord.title') || '桥接交易记录'}</h2>
      </div>
      <Card>
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={items} />
      </Card>
    </div>
  )
}

export default BridgeTradeRecordList
