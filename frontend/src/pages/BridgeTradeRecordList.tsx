import { useEffect, useRef, useState } from 'react'
import { Card, Table, Tag, Tabs, message, Space, Button, Tooltip, Radio, Typography } from 'antd'
import { useTranslation } from 'react-i18next'
import { useMediaQuery } from 'react-responsive'
import { ReloadOutlined } from '@ant-design/icons'
import { apiService } from '../services/api'
import type { BridgeTradeRecord } from '../types'
import { formatUSDC } from '../utils'

const LOG_POLL_INTERVAL = 2000
const LOG_MAX_LINES = 300

type RecordStatus = '' | 'SUCCESS' | 'PENDING' | 'FAILED'

const BridgeTradeRecordList: React.FC = () => {
  const { t, i18n } = useTranslation()
  const isMobile = useMediaQuery({ maxWidth: 768 })

  const [records, setRecords] = useState<BridgeTradeRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState<RecordStatus>('')
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 20,
    total: 0
  })

  const [activeTab, setActiveTab] = useState('records')
  const [logs, setLogs] = useState<Record<string, string>>({})
  const [logInfos, setLogInfos] = useState<{ name: string; displayName: string }[]>([])
  const logPreRefs = useRef<Record<string, HTMLPreElement | null>>({})

  useEffect(() => {
    fetchRecords()
  }, [pagination.current, pagination.pageSize, statusFilter])

  // Fetch log list once when entering logs tab
  useEffect(() => {
    if (activeTab !== 'logs') return

    let intervalId: number

    const fetchLogList = async () => {
      try {
        const response = await apiService.bridgeLogs.list()
        if (response.data.code === 0 && response.data.data) {
          setLogInfos(response.data.data)
        }
      } catch (error: any) {
        console.error('Failed to fetch log list:', error)
      }
    }

    const fetchLogs = async () => {
      const names = logInfos.length > 0 ? logInfos.map((l) => l.name) : ['bridge', 'poller']
      for (const name of names) {
        try {
          const response = await apiService.bridgeLogs.content({
            name,
            lines: LOG_MAX_LINES
          })
          if (response.data.code === 0 && response.data.data) {
            setLogs((prev) => ({ ...prev, [name]: response.data.data!.content }))
          }
        } catch (error: any) {
          console.error(`Failed to fetch log ${name}:`, error)
        }
      }
    }

    fetchLogList()
    fetchLogs()
    intervalId = window.setInterval(fetchLogs, LOG_POLL_INTERVAL)

    return () => {
      if (intervalId) window.clearInterval(intervalId)
    }
  }, [activeTab, logInfos.length])

  // Auto-scroll log panels to bottom when content changes
  useEffect(() => {
    Object.values(logPreRefs.current).forEach((el) => {
      if (el) {
        el.scrollTop = el.scrollHeight
      }
    })
  }, [logs])

  const fetchRecords = async () => {
    setLoading(true)
    try {
      const response = await apiService.bridgeTradeRecords.list({
        page: pagination.current,
        size: pagination.pageSize,
        status: statusFilter || undefined
      })
      if (response.data.code === 0 && response.data.data) {
        setRecords(response.data.data.list || [])
        setPagination((prev) => ({
          ...prev,
          total: response.data.data?.total || 0
        }))
      } else {
        message.error(response.data.msg || t('bridgeTradeRecord.fetchFailed') || '获取桥接交易记录失败')
      }
    } catch (error: any) {
      message.error(error.message || t('bridgeTradeRecord.fetchFailed') || '获取桥接交易记录失败')
    } finally {
      setLoading(false)
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
    if (lower.includes('could not open sell dialog')) {
      return { key: 'open_sell', label: t('bridgeTradeRecord.errorType.openSell') || '无法打开卖出' }
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
    if (lower.includes('network/deposit modal') || lower.includes('insufficient usdc balance') || lower.includes('needs a deposit')) {
      return { key: 'insufficient_balance', label: t('bridgeTradeRecord.errorType.insufficientBalance') || '余额不足' }
    }
    return { key: 'other', label: t('bridgeTradeRecord.errorType.other') || '其他' }
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

  const columns = [
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

  const logPanelStyle: React.CSSProperties = {
    height: '400px',
    overflow: 'auto',
    backgroundColor: '#1e1e1e',
    color: '#d4d4d4',
    fontFamily: 'monospace',
    fontSize: '12px',
    padding: '12px',
    borderRadius: '4px',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-all'
  }

  const renderRecordsTab = () => (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Space wrap style={{ justifyContent: 'space-between', width: '100%' }}>
        <Radio.Group
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value)
            setPagination((prev) => ({ ...prev, current: 1 }))
          }}
          optionType="button"
          buttonStyle="solid"
        >
          <Radio.Button value="">{t('bridgeTradeRecord.statusFilter.all') || '全部'}</Radio.Button>
          <Radio.Button value="SUCCESS">{t('bridgeTradeRecord.statusFilter.success') || '成功'}</Radio.Button>
          <Radio.Button value="PENDING">{t('bridgeTradeRecord.statusFilter.pending') || '进行中'}</Radio.Button>
          <Radio.Button value="FAILED">{t('bridgeTradeRecord.statusFilter.failed') || '失败'}</Radio.Button>
        </Radio.Group>
        <Button icon={<ReloadOutlined />} onClick={fetchRecords} loading={loading}>
          {t('bridgeTradeRecord.refresh') || '刷新'}
        </Button>
      </Space>

      <Table
        dataSource={records}
        columns={columns}
        rowKey="id"
        loading={loading}
        scroll={isMobile ? { x: 1100 } : undefined}
        pagination={{
          current: pagination.current,
          pageSize: pagination.pageSize,
          total: pagination.total,
          showSizeChanger: !isMobile,
          onChange: (page, pageSize) => setPagination((prev) => ({ ...prev, current: page, pageSize }))
        }}
      />
    </Space>
  )

  const renderLogsTab = () => {
    const infos = logInfos.length > 0 ? logInfos : [
      { name: 'bridge', displayName: t('bridgeTradeRecord.logs.bridge') || 'Bridge 运行日志' },
      { name: 'poller', displayName: t('bridgeTradeRecord.logs.poller') || 'Leader Event Poller 日志' }
    ]

    return (
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        {infos.map((info) => (
          <Card
            key={info.name}
            title={info.displayName}
            size="small"
            bodyStyle={{ padding: 0 }}
          >
            <pre
              style={logPanelStyle}
              ref={(el) => (logPreRefs.current[info.name] = el)}
            >
              {logs[info.name] || t('bridgeTradeRecord.logs.loading') || '加载中...'}
            </pre>
          </Card>
        ))}
      </Space>
    )
  }

  const items = [
    {
      key: 'records',
      label: t('bridgeTradeRecord.recordsTab') || '交易记录',
      children: renderRecordsTab()
    },
    {
      key: 'logs',
      label: t('bridgeTradeRecord.logsTab') || '运行日志',
      children: renderLogsTab()
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
