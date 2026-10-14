import { useCallback, useEffect, useRef, useState } from 'react'
import { Alert, Button, Card, Descriptions, Drawer, Empty, Progress, Select, Space, Spin, Switch, Table, Tag, Typography, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { ReloadOutlined } from '@ant-design/icons'
import { useMediaQuery } from 'react-responsive'
import { apiService } from '../services/api'
import { higherButtonSide, preflightIsFresh, preflightReasonText, referenceIsFresh } from '../utils/futureBtc5mPreflight'
import type { FutureBtc5mAssets, FutureBtc5mAssetBuy, FutureBtc5mAssetPosition, FutureBtc5mBridgeStatus, FutureBtc5mOrder, FutureBtc5mOrderStatus, FutureBtc5mPreparationState } from '../types'

const preparationStateText: Record<FutureBtc5mPreparationState, string> = {
  DISABLED: '已关闭',
  WAITING_SIGNAL: '等待有效信号',
  WAITING_BROWSER: '等待 Chrome 报告',
  PENDING: '等待 Chrome 准备',
  CLAIMED: 'Chrome 正在准备',
  READY: '票据已准备，交由扩展自动买入',
  FAILED: '准备失败',
  EXPIRED: '已过期',
  REVOKED: '已撤销',
  RECEIPT_UNKNOWN: '准备结果未知',
  BLOCKED: '准备受阻'
}

const orderStatusText: Record<FutureBtc5mOrderStatus, string> = {
  PENDING: '待处理',
  SKIPPED: '已跳过',
  FAILED: '执行失败',
  SUBMITTED_UNVERIFIED: '已提交，成交未核实',
  FILLED: '已成交'
}

const orderStatusColor: Record<FutureBtc5mOrderStatus, string> = {
  PENDING: 'processing',
  SKIPPED: 'default',
  FAILED: 'error',
  SUBMITTED_UNVERIFIED: 'warning',
  FILLED: 'success'
}

const formatTime = (value?: number | null): string => {
  if (value == null || !Number.isFinite(value)) return '—'
  return new Date(value * 1000).toLocaleString('zh-CN', { hour12: false })
}

const formatValue = (value?: number | null, prefix = ''): string =>
  value == null || !Number.isFinite(value) ? '—' : `${prefix}${value.toLocaleString('zh-CN', { maximumFractionDigits: 6 })}`

const formatMoney = (value?: number | null): string => value == null || !Number.isFinite(value)
  ? '—' : `$${value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

const formatCents = (value?: number | null): string => value == null || !Number.isFinite(value)
  ? '—' : `${(value * 100).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}¢`

const errorText = (error: unknown, fallback: string): string =>
  error instanceof Error ? error.message : fallback

const marketLink = (slug: string) => /^btc-updown-5m-\d+$/.test(slug)
  ? <Typography.Link href={`https://future.news/zh/event/${slug}`} target="_blank" rel="noopener noreferrer">{slug}</Typography.Link>
  : <Typography.Text>{slug}</Typography.Text>

const statusTag = (status: FutureBtc5mOrderStatus) =>
  <Tag color={orderStatusColor[status]}>{orderStatusText[status] || status}</Tag>

const FutureBtc5mBridge: React.FC = () => {
  const isMobile = useMediaQuery({ maxWidth: 768 })
  const [runtime, setRuntime] = useState<FutureBtc5mBridgeStatus | null>(null)
  const [statusReceivedAt, setStatusReceivedAt] = useState(0)
  const [clock, setClock] = useState(Date.now)
  const [statusError, setStatusError] = useState<string | null>(null)
  const [statusLoading, setStatusLoading] = useState(false)
  const [controlLoading, setControlLoading] = useState(false)
  const [assets, setAssets] = useState<FutureBtc5mAssets | null>(null)
  const [assetsError, setAssetsError] = useState<string | null>(null)
  const [assetsLoading, setAssetsLoading] = useState(false)
  const [buyPagination, setBuyPagination] = useState({ current: 1, pageSize: 20 })
  const [orders, setOrders] = useState<FutureBtc5mOrder[]>([])
  const [ordersLoading, setOrdersLoading] = useState(false)
  const [ordersError, setOrdersError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<FutureBtc5mOrderStatus | ''>('')
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 })
  const [detailId, setDetailId] = useState<string | null>(null)
  const [detail, setDetail] = useState<FutureBtc5mOrder | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)
  const mounted = useRef(true)
  const controlPending = useRef(false)
  const statusRequestSeq = useRef(0)
  const ordersRequestSeq = useRef(0)
  const detailRequestSeq = useRef(0)
  const assetsRequestSeq = useRef(0)
  const statusInFlight = useRef<number | null>(null)
  const ordersInFlight = useRef<number | null>(null)
  const detailInFlight = useRef<number | null>(null)
  const assetsInFlight = useRef<number | null>(null)
  const buyHistorySnapshot = useRef<{ walletAddress: string | null, count: number }>({ walletAddress: null, count: 0 })

  useEffect(() => {
    mounted.current = true
    const timer = window.setInterval(() => setClock(Date.now()), 1000)
    return () => {
      window.clearInterval(timer)
      mounted.current = false
      statusRequestSeq.current += 1
      ordersRequestSeq.current += 1
      detailRequestSeq.current += 1
      assetsRequestSeq.current += 1
    }
  }, [])

  const fetchAssets = useCallback(async () => {
    if (assetsInFlight.current === assetsRequestSeq.current) return
    const requestSeq = ++assetsRequestSeq.current
    assetsInFlight.current = requestSeq
    setAssetsLoading(true)
    try {
      const response = await apiService.futureBtc5mBridge.assets()
      if (!mounted.current || requestSeq !== assetsRequestSeq.current) return
      if (response.data.code !== 0 || !response.data.data) {
        throw new Error(response.data.msg || '获取钱包资产失败')
      }
      const nextAssets = response.data.data
      const walletAddress = nextAssets.wallet?.walletAddress.toLowerCase() ?? null
      const count = nextAssets.recentBuys?.length ?? 0
      if (walletAddress !== buyHistorySnapshot.current.walletAddress || count < buyHistorySnapshot.current.count) {
        setBuyPagination((prev) => ({ ...prev, current: 1 }))
      }
      buyHistorySnapshot.current = { walletAddress, count }
      setAssets(nextAssets)
      setAssetsError(null)
      setClock(Date.now())
    } catch (error: unknown) {
      if (!mounted.current || requestSeq !== assetsRequestSeq.current) return
      setAssets(null)
      setAssetsError(errorText(error, '获取钱包资产失败'))
    } finally {
      if (assetsInFlight.current === requestSeq) assetsInFlight.current = null
      if (mounted.current && requestSeq === assetsRequestSeq.current) setAssetsLoading(false)
    }
  }, [])

  const fetchStatus = useCallback(async () => {
    if (controlPending.current || statusInFlight.current === statusRequestSeq.current) return
    const requestSeq = ++statusRequestSeq.current
    statusInFlight.current = requestSeq
    setStatusLoading(true)
    try {
      const response = await apiService.futureBtc5mBridge.status()
      if (!mounted.current || requestSeq !== statusRequestSeq.current) return
      if (response.data.code !== 0 || !response.data.data) {
        throw new Error(response.data.msg || '获取 Future Bridge 状态失败')
      }
      const receivedAt = Date.now()
      setRuntime(response.data.data)
      setStatusReceivedAt(receivedAt)
      setClock(receivedAt)
      setStatusError(null)
    } catch (error: unknown) {
      if (!mounted.current || requestSeq !== statusRequestSeq.current) return
      setRuntime(null)
      setStatusError(errorText(error, '获取 Future Bridge 状态失败'))
    } finally {
      if (statusInFlight.current === requestSeq) statusInFlight.current = null
      if (mounted.current && requestSeq === statusRequestSeq.current) setStatusLoading(false)
    }
  }, [])

  const fetchOrders = useCallback(async () => {
    if (ordersInFlight.current === ordersRequestSeq.current) return
    const requestSeq = ++ordersRequestSeq.current
    ordersInFlight.current = requestSeq
    setOrdersLoading(true)
    try {
      const response = await apiService.futureBtc5mBridge.list({
        page: pagination.current,
        size: pagination.pageSize,
        status: statusFilter || undefined
      })
      if (!mounted.current || requestSeq !== ordersRequestSeq.current) return
      if (response.data.code !== 0 || !response.data.data) {
        throw new Error(response.data.msg || '获取订单记录失败')
      }
      setOrders(response.data.data.list)
      setPagination((prev) => ({ ...prev, total: response.data.data!.total }))
      setOrdersError(null)
    } catch (error: unknown) {
      if (!mounted.current || requestSeq !== ordersRequestSeq.current) return
      setOrders([])
      setOrdersError(errorText(error, '获取订单记录失败'))
    } finally {
      if (ordersInFlight.current === requestSeq) ordersInFlight.current = null
      if (mounted.current && requestSeq === ordersRequestSeq.current) setOrdersLoading(false)
    }
  }, [pagination.current, pagination.pageSize, statusFilter])

  const fetchDetail = useCallback(async () => {
    if (!detailId || detailInFlight.current === detailRequestSeq.current) return
    const requestSeq = ++detailRequestSeq.current
    detailInFlight.current = requestSeq
    setDetailLoading(true)
    try {
      const response = await apiService.futureBtc5mBridge.detail({ id: detailId })
      if (!mounted.current || requestSeq !== detailRequestSeq.current) return
      if (response.data.code !== 0 || !response.data.data) {
        throw new Error(response.data.msg || '获取订单详情失败')
      }
      setDetail(response.data.data)
      setDetailError(null)
    } catch (error: unknown) {
      if (!mounted.current || requestSeq !== detailRequestSeq.current) return
      setDetail(null)
      setDetailError(errorText(error, '获取订单详情失败'))
    } finally {
      if (detailInFlight.current === requestSeq) detailInFlight.current = null
      if (mounted.current && requestSeq === detailRequestSeq.current) setDetailLoading(false)
    }
  }, [detailId])

  useEffect(() => {
    fetchStatus()
    const interval = window.setInterval(fetchStatus, 5000)
    return () => window.clearInterval(interval)
  }, [fetchStatus])

  useEffect(() => {
    fetchAssets()
    const interval = window.setInterval(fetchAssets, 5000)
    return () => window.clearInterval(interval)
  }, [fetchAssets])

  useEffect(() => {
    fetchOrders()
    const interval = window.setInterval(fetchOrders, 5000)
    return () => {
      window.clearInterval(interval)
      ordersRequestSeq.current += 1
    }
  }, [fetchOrders])

  useEffect(() => {
    setDetail(null)
    setDetailError(null)
    if (!detailId) return
    fetchDetail()
    const interval = window.setInterval(fetchDetail, 5000)
    return () => {
      window.clearInterval(interval)
      detailRequestSeq.current += 1
    }
  }, [detailId, fetchDetail])

  useEffect(() => {
    const refreshConnection = () => {
      if (document.visibilityState === 'hidden') return
      setClock(Date.now())
      fetchStatus()
      fetchOrders()
      fetchDetail()
      fetchAssets()
    }
    window.addEventListener('focus', refreshConnection)
    window.addEventListener('online', refreshConnection)
    document.addEventListener('visibilitychange', refreshConnection)
    return () => {
      window.removeEventListener('focus', refreshConnection)
      window.removeEventListener('online', refreshConnection)
      document.removeEventListener('visibilitychange', refreshConnection)
    }
  }, [fetchStatus, fetchOrders, fetchDetail, fetchAssets])

  const handleControl = async (enabled: boolean) => {
    if (controlPending.current) return
    controlPending.current = true
    statusRequestSeq.current += 1
    setStatusLoading(false)
    setControlLoading(true)
    try {
      const response = await apiService.futureBtc5mBridge.control({ enabled })
      if (!mounted.current) return
      if (response.data.code !== 0 || !response.data.data) {
        throw new Error(response.data.msg || '更新自动准备票据开关失败')
      }
      const receivedAt = Date.now()
      setRuntime(response.data.data)
      setStatusReceivedAt(receivedAt)
      setClock(receivedAt)
      setStatusError(null)
      message.success(enabled ? '自动准备票据已开启，票据准备好后扩展将自动点击买入' : '自动准备票据已关闭，扩展不再自动买入')
      fetchOrders()
    } catch (error: unknown) {
      if (!mounted.current) return
      setRuntime(null)
      setStatusError(`开关状态未知：${errorText(error, '更新失败')}。请刷新核对，或再次点击关闭自动准备票据。`)
      message.error('更新失败，自动准备票据开关状态未知')
    } finally {
      controlPending.current = false
      if (mounted.current) setControlLoading(false)
    }
  }

  const columns: ColumnsType<FutureBtc5mOrder> = [
    {
      title: 'BTC 5 分钟轮次', key: 'market', width: 275,
      render: (_, record) => <Space direction="vertical" size={0}>
        {marketLink(record.slug)}
        <Typography.Text type="secondary">{formatTime(record.periodStart)} — {formatTime(record.periodEnd)}</Typography.Text>
      </Space>
    },
    { title: '方向', dataIndex: 'side', width: 75, render: (side: string) => <Tag color={side === 'Up' ? 'green' : 'red'}>{side}</Tag> },
    { title: '本金', dataIndex: 'amountUsd', width: 80, render: (amount: number) => formatValue(amount, '$') },
    {
      title: '执行状态', dataIndex: 'status', width: 190,
      render: (status: FutureBtc5mOrderStatus, record) => <Space direction="vertical" size={0}>
        {statusTag(status)}
        {record.reason && <Typography.Text type="secondary">{record.reason}</Typography.Text>}
      </Space>
    },
    { title: '平台订单号', dataIndex: 'platformOrderId', width: 160, render: (value: string | null) => value || '—' },
    { title: '实际成交量', dataIndex: 'filledQuantity', width: 110, render: (value: number | null) => formatValue(value) },
    { title: '成交均价', dataIndex: 'avgFilledPrice', width: 110, render: (value: number | null) => formatValue(value, '$') },
    { title: '费用', dataIndex: 'feeUsd', width: 90, render: (value: number | null) => formatValue(value, '$') },
    { title: '记录时间', dataIndex: 'createdAt', width: 175, render: (value: number) => formatTime(value) },
    { title: '操作', key: 'actions', fixed: 'right', width: 80, render: (_, record) => <Button type="link" onClick={() => {
      detailRequestSeq.current += 1
      setDetail(null)
      setDetailId(record.id)
    }}>详情</Button> }
  ]

  const positionColumns: ColumnsType<FutureBtc5mAssetPosition> = [
    { title: '市场', key: 'market', width: 285, render: (_, record) => <Space direction="vertical" size={0}>
      <Typography.Text>{record.title}</Typography.Text>{marketLink(record.slug)}
    </Space> },
    { title: '方向', dataIndex: 'side', width: 75, render: (side: string) => <Tag color={side === 'Up' ? 'green' : 'red'}>{side === 'Up' ? '涨' : '跌'}</Tag> },
    { title: '持有份额', dataIndex: 'quantity', width: 110, render: (value: number) => formatValue(value) },
    { title: '买入均价', dataIndex: 'avgPrice', width: 100, render: formatCents },
    { title: '当前价格', dataIndex: 'currentPrice', width: 100, render: formatCents },
    { title: '当前市值', dataIndex: 'currentValueUsd', width: 110, render: formatMoney },
    { title: '持仓盈亏', dataIndex: 'cashPnlUsd', width: 110, render: (value: number | null) =>
      <Typography.Text type={value == null ? 'secondary' : value < 0 ? 'danger' : 'success'}>{formatMoney(value)}</Typography.Text> },
    { title: '状态', dataIndex: 'redeemable', width: 95, render: (value: boolean) => value ? <Tag>待领取</Tag> : <Tag color="processing">持有中</Tag> }
  ]

  const buyColumns: ColumnsType<FutureBtc5mAssetBuy> = [
    { title: '买入时间', dataIndex: 'boughtAt', width: 175, render: (value: number) => formatTime(value) },
    { title: '市场', key: 'market', width: 285, render: (_, record) => <Space direction="vertical" size={0}>
      <Typography.Text>{record.title}</Typography.Text>{marketLink(record.slug)}
    </Space> },
    { title: '方向', dataIndex: 'side', width: 75, render: (side: string) => <Tag color={side === 'Up' ? 'green' : 'red'}>{side === 'Up' ? '涨' : '跌'}</Tag> },
    { title: '买入份额', dataIndex: 'quantity', width: 110, render: (value: number) => formatValue(value) },
    { title: '买入价格', dataIndex: 'price', width: 100, render: formatCents },
    { title: '买入金额', dataIndex: 'amountUsd', width: 110, render: formatMoney },
    { title: '结算结果', dataIndex: 'result', width: 145, render: (result: FutureBtc5mAssetBuy['result'], record) =>
      <Space direction="vertical" size={0}>
        <Tag color={result === 'WIN' ? 'green' : result === 'LOSS' ? 'red' : result === 'PENDING' ? 'processing' : 'default'}>
          {result === 'WIN' ? '赢' : result === 'LOSS' ? '亏' : result === 'PENDING' ? '待结算' : '待确认'}
        </Tag>
        {record.winningSide && <Typography.Text type="secondary">结算方向：{record.winningSide === 'Up' ? '涨' : '跌'}</Typography.Text>}
      </Space> }
  ]

  const wallet = assets?.wallet
  const walletFresh = Boolean(wallet?.fresh && [wallet.observedAt, wallet.receivedAt].every(value =>
    Number.isFinite(value) && clock / 1000 - value >= 0 && clock / 1000 - value <= 15))
  const marketDataFresh = Boolean(walletFresh && assets?.marketDataObservedAt != null &&
    clock / 1000 - assets.marketDataObservedAt >= 0 && clock / 1000 - assets.marketDataObservedAt <= 15)
  const buyResultCounts = { win: 0, loss: 0, pending: 0, unknown: 0 }
  for (const buy of assets?.recentBuys ?? []) {
    if (buy.result === 'WIN') buyResultCounts.win += 1
    else if (buy.result === 'LOSS') buyResultCounts.loss += 1
    else if (buy.result === 'PENDING') buyResultCounts.pending += 1
    else buyResultCounts.unknown += 1
  }
  const settledBuyCount = buyResultCounts.win + buyResultCounts.loss
  const buyWinPercent = settledBuyCount > 0 ? buyResultCounts.win / settledBuyCount * 100 : null
  const buyWinPercentText = buyWinPercent == null ? '—' : `${buyWinPercent.toFixed(1)}%`
  const buyLossPercentText = settledBuyCount > 0 ? `${(buyResultCounts.loss / settledBuyCount * 100).toFixed(1)}%` : '—'

  const statusStale = Boolean(runtime && (clock < statusReceivedAt || clock - statusReceivedAt > 15000 ||
    !Number.isFinite(runtime.serverTime) || Math.abs(runtime.serverTime - statusReceivedAt / 1000) > 3))
  const ledgerError = runtime?.blockReasons.some((reason) => reason.startsWith('ORDER_LEDGER_')) ?? false
  const orderCounts = runtime && !ledgerError ? runtime.orderCounts : null
  const referenceFresh = referenceIsFresh(runtime, statusReceivedAt, clock)
  const preflight = runtime?.preflight
  const browserFresh = preflightIsFresh(runtime, statusReceivedAt, clock)
  const buttonSide = browserFresh && preflight?.selectionSource === 'HIGHER_BUTTON_PRICE'
    ? higherButtonSide(preflight.upQuoteCents, preflight.downQuoteCents) : null
  const quotesFresh = Boolean(buttonSide && buttonSide === preflight?.preferredSide)
  const preflightReady = Boolean(browserFresh && referenceFresh && quotesFresh && preflight?.result === 'READ_ONLY_READY' &&
    preflight.pagePeriodStart === runtime?.periodStart && preflight.navigation === 'CURRENT' &&
    preflight.ticketStatus === 'PASS' && preflight.amountUsd === 1 && preflight.sideMatches &&
    preflight.selectedSide === buttonSide && preflight.buyButtonEnabled)
  const preparation = runtime?.preparation
  const serverNow = runtime ? Math.max(runtime.serverTime + (clock - statusReceivedAt) / 1000, clock / 1000) : 0
  const activeRecord = preparation?.intent || (preparation?.enabled && preparation.state === 'READY' ? preparation.lastAttempt : null)
  const intentExpired = Boolean(activeRecord && serverNow >= activeRecord.expiresAt)
  const originalSamplesFresh = Boolean(activeRecord?.schemaVersion === 2 &&
    activeRecord.selectionSource === 'HIGHER_BUTTON_PRICE' &&
    higherButtonSide(activeRecord.upQuoteCents, activeRecord.downQuoteCents) === activeRecord.side &&
    serverNow >= activeRecord.priceObservedAt && serverNow - activeRecord.priceObservedAt <= 5 &&
    serverNow >= activeRecord.quoteObservedAt && serverNow - activeRecord.quoteObservedAt <= 5)
  const currentPreparationFresh = originalSamplesFresh && referenceFresh && quotesFresh && buttonSide === activeRecord?.side &&
    preflight?.pagePeriodStart === activeRecord?.periodStart && preflight?.navigation === 'CURRENT' && preflight?.ticketStatus === 'PASS'
  const intentFresh = Boolean(runtime && !statusStale && preparation?.enabled && preparation.intent && currentPreparationFresh && !intentExpired)
  const readyRecord = preparation?.lastAttempt
  const readyFresh = Boolean(currentPreparationFresh && preflight?.result === 'READ_ONLY_READY' &&
    preflight.amountUsd === 1 && preflight.selectedSide === readyRecord?.side && preflight.buyButtonEnabled &&
    readyRecord?.claimedAt != null && preflight.receivedAt != null && preflight.receivedAt >= readyRecord.claimedAt)
  const preparationState = runtime && !statusStale && preparation
    ? intentExpired ? 'EXPIRED'
      : preparation.intent && !intentFresh || preparation.state === 'READY' && !readyFresh ? 'WAITING_SIGNAL'
        : preparation.state === 'READY' && !browserFresh ? 'WAITING_BROWSER' : preparation.state
    : null
  const intent = intentFresh ? preparation?.intent : null
  const lastAttempt = preparation?.lastAttempt
  const actualState = runtime && !statusStale
    ? preparation?.enabled ? '自动准备与自动买入已开启' : '自动准备与自动买入已关闭'
    : '状态未知'

  return <Space direction="vertical" size="middle" style={{ width: '100%' }}>
    <div>
      <Typography.Title level={3} style={{ marginBottom: 4 }}>Future BTC 5 分钟 Bridge</Typography.Title>
      <Typography.Text type="secondary">按 Future 按钮报价较高的一侧自动准备 BTC 5 分钟 $1 票据，准备好后由浏览器扩展自动点击一次买入。每 5 秒更新准备状态与真实订单记录。</Typography.Text>
    </div>

    <Card title="我的资产 · BTC 5 分钟" extra={<Button icon={<ReloadOutlined />} loading={assetsLoading} onClick={fetchAssets}>刷新资产</Button>}>
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Descriptions size="small" column={isMobile ? 1 : 3}>
          <Descriptions.Item label="钱包现金"><Typography.Text strong style={{ fontSize: 24 }}>{formatMoney(walletFresh ? wallet?.cashUsd : null)}</Typography.Text></Descriptions.Item>
          <Descriptions.Item label="BTC 5 分钟持仓市值"><Typography.Text strong style={{ fontSize: 24 }}>{formatMoney(marketDataFresh ? assets?.positionsValueUsd : null)}</Typography.Text></Descriptions.Item>
          <Descriptions.Item label="数据状态"><Tag color={marketDataFresh && assets?.dataStatus === 'READY' ? 'success' : 'warning'}>
            {!assets ? assetsLoading ? '读取中' : '未连接' : !wallet ? '等待钱包' : !walletFresh ? '钱包数据已过期' :
              assets.dataStatus === 'PARTIAL' ? '部分数据不可用' : !marketDataFresh ? '持仓等待更新' : '已更新'}</Tag></Descriptions.Item>
          <Descriptions.Item label="当前钱包" span={isMobile ? 1 : 3}>{wallet
            ? <Typography.Link href={`https://future.news/zh/address/${wallet.walletAddress}`} target="_blank" rel="noopener noreferrer" style={{ wordBreak: 'break-all' }}>{wallet.walletAddress}</Typography.Link>
            : '等待同步'}</Descriptions.Item>
          <Descriptions.Item label="现金采样时间">{formatTime(wallet?.observedAt)}</Descriptions.Item>
          <Descriptions.Item label="持仓与买入更新时间">{formatTime(assets?.marketDataObservedAt)}</Descriptions.Item>
        </Descriptions>
        <Typography.Text type="secondary">每 5 秒自动刷新。现金取自当前 Future 登录钱包的页面显示；持仓与买入历史按同一地址查询 Polymarket，可能有索引延迟。市值包含待领取持仓，不计入现金。</Typography.Text>
        {assetsError && <Alert type="error" showIcon message="钱包资产暂不可用" description={assetsError} />}
        {assets && (assets.reasons.length > 0 || !walletFresh || !marketDataFresh) && <Alert type="warning" showIcon message="资产数据等待同步"
          description={assets.reasons.join('；') || (!walletFresh ? 'Future 钱包采样已过期，请保持当前市场页面打开。' : '持仓数据已过期，正在重新读取。')} />}
        <Typography.Title level={5} style={{ margin: 0 }}>当前买入资产</Typography.Title>
        {marketDataFresh && assets?.positions != null
          ? <Table rowKey="asset" size="small" dataSource={assets.positions} columns={positionColumns} pagination={false} scroll={{ x: 1085 }}
            locale={{ emptyText: '当前暂无 BTC 5 分钟持仓' }} />
          : <Typography.Text type="secondary">{assetsLoading ? '正在读取持仓…' : '持仓暂未核实'}</Typography.Text>}
        <Typography.Title level={5} style={{ margin: 0 }}>全部买入记录</Typography.Title>
        <Typography.Text type="secondary">赢 / 亏按市场最终结算方向标注，表示买入方向是否命中；不代表已领取，也不表示包含提前卖出和手续费的实际净盈亏。</Typography.Text>
        {marketDataFresh && assets?.recentBuys != null
          ? <>
            <Typography.Text type="secondary">已加载 {assets.recentBuys.length} 笔 · {assets.buyHistoryComplete === true ? '历史记录已完整加载' : '历史记录未完整加载'}</Typography.Text>
            {assets.buyHistoryComplete !== true && <Alert type="warning" showIcon message="买入历史尚未完整核实"
              description="当前仅展示已加载记录，不能视为全部买入；请等待历史数据完整同步后核对。" />}
            <div style={{ width: '100%', boxSizing: 'border-box', padding: isMobile ? 16 : 20, background: '#fafafa', borderRadius: 8 }}>
              <Typography.Title level={5} style={{ marginTop: 0 }}>赢亏比例</Typography.Title>
              <div style={{ display: 'flex', flexDirection: isMobile ? 'column' : 'row', alignItems: 'center', gap: isMobile ? 20 : 32 }}>
                <div role="img" aria-label={`赢亏比例：赢 ${buyResultCounts.win} 笔，亏 ${buyResultCounts.loss} 笔，${buyWinPercent == null ? '暂无已结算记录，胜率未知' : `已结算胜率 ${buyWinPercentText}`}`}>
                  <Progress type="circle" size={160} percent={buyWinPercent ?? 0} status="normal" strokeWidth={10}
                    strokeColor="#52c41a" trailColor={settledBuyCount > 0 ? '#ff4d4f' : '#f0f0f0'} strokeLinecap="butt"
                    format={() => <>
                      <Typography.Text strong style={{ display: 'block', fontSize: 28 }}>{buyWinPercentText}</Typography.Text>
                      <Typography.Text style={{ fontSize: 12, color: '#595959' }}>{settledBuyCount > 0 ? '已结算胜率' : '暂无已结算记录'}</Typography.Text>
                    </>} />
                </div>
                <Space direction="vertical" size={12} style={{ width: isMobile ? '100%' : undefined }}>
                  <Typography.Text strong style={{ color: '#237804' }}>赢 {buyResultCounts.win} 笔 · {buyWinPercentText}</Typography.Text>
                  <Typography.Text strong style={{ color: '#cf1322' }}>亏 {buyResultCounts.loss} 笔 · {buyLossPercentText}</Typography.Text>
                  <Typography.Text style={{ color: '#595959' }}>待结算 {buyResultCounts.pending} 笔</Typography.Text>
                  <Typography.Text style={{ color: '#595959' }}>待确认 {buyResultCounts.unknown} 笔</Typography.Text>
                </Space>
              </div>
              <Typography.Paragraph style={{ marginTop: 16, marginBottom: 0, color: '#595959' }}>
                已结算 {settledBuyCount} 笔。按已加载的全部买入笔数统计，同一轮多笔分别计数；待结算和待确认不计入胜率。
              </Typography.Paragraph>
              {assets.buyHistoryComplete !== true && <Typography.Text style={{ color: '#874d00' }}>仅统计已加载记录，完整历史同步后比例可能变化。</Typography.Text>}
            </div>
            <Table rowKey={(record, index) => `${record.id}:${index}`} size="small" dataSource={assets.recentBuys} columns={buyColumns} scroll={{ x: 1000 }}
              pagination={{ ...buyPagination, total: assets.recentBuys.length, showSizeChanger: true,
                pageSizeOptions: ['10', '20', '50', '100'], showTotal: (total) => `已加载 ${total} 笔`,
                onChange: (current, pageSize) => setBuyPagination({ current, pageSize }) }}
              locale={{ emptyText: assets.buyHistoryComplete === true ? '暂无 BTC 5 分钟买入记录' : '当前尚未加载 BTC 5 分钟买入记录' }} />
          </>
          : <Typography.Text type="secondary">{assetsLoading ? '正在读取买入记录…' : '买入历史暂未核实'}</Typography.Text>}
      </Space>
    </Card>

    <Card title="自动准备票据控制" extra={<Button icon={<ReloadOutlined />} loading={statusLoading} onClick={() => { fetchStatus(); fetchOrders() }}>刷新</Button>}>
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Space wrap>
          <Typography.Text strong>自动准备票据开关</Typography.Text>
          <Switch checked={runtime?.requestedEnabled ?? false} loading={controlLoading} disabled={!runtime || statusStale}
            checkedChildren="开启" unCheckedChildren="关闭" onChange={handleControl} />
          <Button danger loading={controlLoading} onClick={() => handleControl(false)}>关闭自动准备票据</Button>
          <Tag color={!runtime || statusStale ? 'default' : preparation?.enabled ? 'processing' : 'default'}>{actualState}</Tag>
          <Typography.Text type="secondary">保存开关：{runtime ? runtime.requestedEnabled ? '开启' : '关闭' : '未知'}</Typography.Text>
        </Space>
        {statusError && <Alert type="error" showIcon message="Bridge 状态未知" description={statusError} />}
        {statusStale && <Alert type="error" showIcon message="运行状态已过期，请刷新核对" description="当前状态时间已失效，开关与准备情况未知；仍可点击关闭自动准备票据。" />}
        {runtime && !runtime.executorReady && <Alert type="info" showIcon message="当前尚未接入 Future 交易执行器"
          description="开启后会前往当前市场，按 Up / Down 按钮数字较高的一侧选择方向并填写 $1；报价缺失或相同则等待。Chainlink 价格仅作参考。票据准备好后，浏览器扩展会自动点击一次 Future 买入（每轮最多一次）；实际成交以 Future 订单为准。" />}
        <Descriptions size="small" column={isMobile ? 1 : 3}>
          <Descriptions.Item label="Bridge 连接">{runtime ? runtime.online ? '在线' : '离线' : '未知'}</Descriptions.Item>
          <Descriptions.Item label="执行器">{runtime ? '未接入' : '未知'}</Descriptions.Item>
          <Descriptions.Item label="实际下单">{runtime && !statusStale ? '未运行' : '未知'}</Descriptions.Item>
          <Descriptions.Item label="最终买入">浏览器扩展在票据准备好后自动点击（每轮最多一次）</Descriptions.Item>
          <Descriptions.Item label="行情状态">{runtime?.feedStatus || '—'}</Descriptions.Item>
          <Descriptions.Item label="当前轮次">{formatTime(runtime?.periodStart)}</Descriptions.Item>
          <Descriptions.Item label="服务器更新时间">{formatTime(runtime?.serverTime)}</Descriptions.Item>
          <Descriptions.Item label="下单阻断原因" span={isMobile ? 1 : 3}>{runtime?.blockReasons.join('；') || '—'}</Descriptions.Item>
        </Descriptions>
        {runtime?.signal && <Descriptions title="Chainlink 参考采样（不用于选择准备方向）" size="small" column={isMobile ? 1 : 3}>
          <Descriptions.Item label="市场" span={isMobile ? 1 : 3}>{marketLink(runtime.signal.slug)}</Descriptions.Item>
          <Descriptions.Item label="观察方向">{referenceFresh ? runtime.signal.side || '平价' : '采样已过期'}</Descriptions.Item>
          <Descriptions.Item label="开盘参考价">{formatValue(runtime.signal.open_price, '$')}</Descriptions.Item>
          <Descriptions.Item label="采样价格">{formatValue(runtime.signal.current_price, '$')}</Descriptions.Item>
          <Descriptions.Item label="价格采样时间">{formatTime(runtime.signal.price_observed_at)}</Descriptions.Item>
        </Descriptions>}
      </Space>
    </Card>

    <Card title="票据准备状态">
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Alert type="info" showIcon message="准备结果不代表买入或成交"
          description="准备报告只记录页面金额、方向及检查结果。历史报告不能用于当前轮次入场；自动买入的实际订单与成交以 Future 订单记录为准。" />
        <Descriptions size="small" column={isMobile ? 1 : 3}>
          <Descriptions.Item label="准备阶段">{preparationState ? preparationStateText[preparationState] : '状态未知'}</Descriptions.Item>
          <Descriptions.Item label="准备方向规则">Future Up / Down 按钮报价较高的一侧</Descriptions.Item>
          <Descriptions.Item label="准备模式">{preparation ? '仅准备票据，未提交订单' : '未知'}</Descriptions.Item>
          <Descriptions.Item label="待准备方向 / 金额">{intent ? `${intent.side} / $1` : '—'}</Descriptions.Item>
          <Descriptions.Item label="待准备市场" span={isMobile ? 1 : 3}>{intent ? marketLink(intent.slug) : '—'}</Descriptions.Item>
          <Descriptions.Item label="原按钮快照接收时间">{formatTime(intent?.quoteObservedAt)}</Descriptions.Item>
          <Descriptions.Item label="准备截止时间">{formatTime(intent?.expiresAt)}</Descriptions.Item>
          <Descriptions.Item label="准备原因" span={isMobile ? 1 : 2}>{preparation?.reasons.join('；') || '—'}</Descriptions.Item>
        </Descriptions>
        {lastAttempt && <Descriptions title="最近操作报告（历史事实）" size="small" column={isMobile ? 1 : 3}>
          <Descriptions.Item label="最近准备结果">{preparationStateText[lastAttempt.state]}</Descriptions.Item>
          <Descriptions.Item label="准备报告方向 / 本金">{lastAttempt.side} / $1</Descriptions.Item>
          <Descriptions.Item label="报告选边规则">{lastAttempt.schemaVersion === 2 ? 'Future 按钮报价较高的一侧' : '历史规则：Chainlink 动量'}</Descriptions.Item>
          <Descriptions.Item label="报告 Up / Down 报价">{lastAttempt.schemaVersion === 2 ? `${formatValue(lastAttempt.upQuoteCents)}¢ / ${formatValue(lastAttempt.downQuoteCents)}¢` : '历史记录未保存按钮报价'}</Descriptions.Item>
          <Descriptions.Item label="报告按钮快照接收时间">{formatTime(lastAttempt.quoteObservedAt)}</Descriptions.Item>
          <Descriptions.Item label="操作报告更新时间">{formatTime(lastAttempt.updatedAt)}</Descriptions.Item>
          <Descriptions.Item label="准备报告市场" span={isMobile ? 1 : 3}>{marketLink(lastAttempt.slug)}</Descriptions.Item>
          <Descriptions.Item label="准备报告金额 / 方向">{lastAttempt.receipt ? `${formatValue(lastAttempt.receipt.amountUsd, '$')} / ${lastAttempt.receipt.selectedSide || '—'}` : '—'}</Descriptions.Item>
          <Descriptions.Item label="操作检查时间">{formatTime(lastAttempt.receipt?.checkedAt)}</Descriptions.Item>
          <Descriptions.Item label="操作报告原因">{lastAttempt.reason || '—'}</Descriptions.Item>
          <Descriptions.Item label="准备提交状态" span={isMobile ? 1 : 3}>未提交订单；买入与成交均未由此报告确认。</Descriptions.Item>
        </Descriptions>}
      </Space>
    </Card>

    <Card title="下单前只读预检" extra={<Tag color={preflightReady ? 'success' : browserFresh ? 'warning' : 'default'}>
      {preflightReady ? '只读预检通过' : browserFresh ? '待满足预检条件' : '等待浏览器报告'}
    </Tag>}>
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Alert type="info" showIcon message="只读预检，不提交订单"
          description="此预检核对已登录 Chrome 当前市场、票据现有金额和选中方向。自动准备票据与自动买入由上方开关控制。" />
        <Descriptions size="small" column={isMobile ? 1 : 3}>
          <Descriptions.Item label="项目接口">{runtime && !statusStale && runtime.online ? '已连接' : '未知'}</Descriptions.Item>
          <Descriptions.Item label="Chrome 预检报告">{browserFresh ? '新鲜' : '未连接或已过期'}</Descriptions.Item>
          <Descriptions.Item label="当前 BTC 5 分钟市场">{browserFresh && preflight?.navigation === 'CURRENT' && preflight.pagePeriodStart === runtime?.periodStart ? '已匹配' : '待匹配'}</Descriptions.Item>
          <Descriptions.Item label="Chainlink / TWAP 60 秒">{referenceFresh ? '参考已核对，采样新鲜' : '等待有效入场采样'}</Descriptions.Item>
          <Descriptions.Item label="美元市价买入栏">{browserFresh && preflight?.ticketStatus === 'PASS' ? '只读检查通过' : '待检查'}</Descriptions.Item>
          <Descriptions.Item label="页面现有金额">{browserFresh ? formatValue(preflight?.amountUsd, '$') : '—'}</Descriptions.Item>
          <Descriptions.Item label="当前选中方向">{browserFresh ? preflight?.selectedSide || '—' : '—'}</Descriptions.Item>
          <Descriptions.Item label="Up / Down 按钮报价">{browserFresh && preflight?.selectionSource === 'HIGHER_BUTTON_PRICE' ? `${formatValue(preflight.upQuoteCents)}¢ / ${formatValue(preflight.downQuoteCents)}¢` : '—'}</Descriptions.Item>
          <Descriptions.Item label="按钮报价方向">{quotesFresh ? buttonSide : '等待不同且有效的按钮报价'}</Descriptions.Item>
          <Descriptions.Item label="方向匹配">{browserFresh && quotesFresh ? preflight?.sideMatches ? '匹配' : '待匹配' : '待核对'}</Descriptions.Item>
          <Descriptions.Item label="页面买入按钮">{browserFresh ? preflight?.buyButtonEnabled ? '可用，未点击' : '不可用' : '未知'}</Descriptions.Item>
          <Descriptions.Item label="浏览器检查时间">{formatTime(preflight?.checkedAt)}</Descriptions.Item>
          <Descriptions.Item label="服务接收时间">{formatTime(preflight?.receivedAt)}</Descriptions.Item>
          <Descriptions.Item label="浏览器市场" span={isMobile ? 1 : 3}>{preflight?.marketUrl ? <Typography.Link href={preflight.marketUrl} target="_blank" rel="noopener noreferrer">{preflight.marketUrl}</Typography.Link> : '—'}</Descriptions.Item>
          <Descriptions.Item label="预检原因" span={isMobile ? 1 : 3}>{preflightReasonText(preflightReady, browserFresh, referenceFresh, preflight?.reasons || [])}</Descriptions.Item>
        </Descriptions>
        {preflight?.lastPassed && <Descriptions title="最后通过的只读预检（历史记录）" size="small" column={isMobile ? 1 : 3}>
          <Descriptions.Item label="轮次">{formatTime(preflight.lastPassed.periodStart)}</Descriptions.Item>
          <Descriptions.Item label="检查时间">{formatTime(preflight.lastPassed.checkedAt)}</Descriptions.Item>
          <Descriptions.Item label="方向 / 现有金额">{preflight.lastPassed.schemaVersion === 2 ? preflight.lastPassed.preferredSide : preflight.lastPassed.signalSide} / $1</Descriptions.Item>
          <Descriptions.Item label="提交状态" span={isMobile ? 1 : 3}>未提交订单；历史通过记录不能用于当前轮次入场。</Descriptions.Item>
        </Descriptions>}
      </Space>
    </Card>

    <Card title="真实订单与历史跳过记录">
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        {ledgerError && <Alert type="error" showIcon message="订单账本不可用，记录数量未知" description="记录损坏或写入未获确认，暂停显示统计。请检查服务记录后再核对历史。" />}
        <Space wrap style={{ justifyContent: 'space-between', width: '100%' }}>
          <Space wrap>
            <Typography.Text>状态</Typography.Text>
            <Select value={statusFilter} style={{ width: 210 }} onChange={(value: FutureBtc5mOrderStatus | '') => {
              ordersRequestSeq.current += 1
              setOrders([])
              setStatusFilter(value)
              setPagination((prev) => ({ ...prev, current: 1 }))
            }} options={[{ value: '', label: '全部' }, ...Object.entries(orderStatusText).map(([value, label]) => ({ value, label }))]} />
          </Space>
          <Button icon={<ReloadOutlined />} loading={ordersLoading} onClick={fetchOrders}>刷新记录</Button>
        </Space>
        <Space wrap>
          <Tag>总记录 {orderCounts?.total ?? '—'}</Tag>
          <Tag color="processing">待处理 {orderCounts?.pending ?? '—'}</Tag>
          <Tag color="warning">已提交 {orderCounts?.submitted ?? '—'}</Tag>
          <Tag color="success">已成交 {orderCounts?.filled ?? '—'}</Tag>
          <Tag color="error">失败 {orderCounts?.failed ?? '—'}</Tag>
          <Tag>跳过 {orderCounts?.skipped ?? '—'}</Tag>
        </Space>
        <Typography.Text type="secondary">跳过记录表示未提交订单；提交状态与实际成交分别显示，成交量、均价及费用以平台回执为准。</Typography.Text>
        {ordersError && <Alert type="error" showIcon message="订单记录暂不可用" description={ordersError} />}
        <Table rowKey="id" dataSource={orders} columns={columns} loading={ordersLoading} scroll={{ x: 1445 }}
          locale={{ emptyText: ordersError ? '订单记录状态未知' : '暂无订单记录' }}
          pagination={{ current: pagination.current, pageSize: pagination.pageSize, total: pagination.total,
            showSizeChanger: !isMobile,
            onChange: (current, pageSize) => {
              ordersRequestSeq.current += 1
              setOrders([])
              setPagination((prev) => ({ ...prev, current, pageSize }))
            } }} />
      </Space>
    </Card>

    <Drawer title="订单详情" open={Boolean(detailId)} onClose={() => {
      detailRequestSeq.current += 1
      setDetail(null)
      setDetailId(null)
    }} width={isMobile ? '100%' : 650}
      extra={<Button icon={<ReloadOutlined />} loading={detailLoading} onClick={fetchDetail}>刷新</Button>}>
      {detailError && <Alert type="error" showIcon message={detailError} />}
      {detailLoading && !detail && <Spin />}
      {!detail && !detailLoading && !detailError && <Empty description="暂无详情" />}
      {detail && <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Descriptions column={1} size="small" bordered>
          <Descriptions.Item label="记录 ID">{detail.id}</Descriptions.Item>
          <Descriptions.Item label="Bridge">{detail.bridgeId}</Descriptions.Item>
          <Descriptions.Item label="市场">{marketLink(detail.slug)}</Descriptions.Item>
          <Descriptions.Item label="轮次">{formatTime(detail.periodStart)} — {formatTime(detail.periodEnd)}</Descriptions.Item>
          <Descriptions.Item label="方向 / 本金">{detail.side} / {formatValue(detail.amountUsd, '$')}</Descriptions.Item>
          <Descriptions.Item label="执行状态">{statusTag(detail.status)}</Descriptions.Item>
          <Descriptions.Item label="原因">{detail.reason || '—'}</Descriptions.Item>
          <Descriptions.Item label="平台订单号">{detail.platformOrderId || '—'}</Descriptions.Item>
          <Descriptions.Item label="实际成交量">{formatValue(detail.filledQuantity)}</Descriptions.Item>
          <Descriptions.Item label="成交均价">{formatValue(detail.avgFilledPrice, '$')}</Descriptions.Item>
          <Descriptions.Item label="费用">{formatValue(detail.feeUsd, '$')}</Descriptions.Item>
          <Descriptions.Item label="记录时间">{formatTime(detail.createdAt)}</Descriptions.Item>
          <Descriptions.Item label="提交时间">{formatTime(detail.submittedAt)}</Descriptions.Item>
          <Descriptions.Item label="成交时间">{formatTime(detail.filledAt)}</Descriptions.Item>
          <Descriptions.Item label="更新时间">{formatTime(detail.updatedAt)}</Descriptions.Item>
        </Descriptions>
        <Typography.Title level={5} style={{ margin: 0 }}>执行步骤</Typography.Title>
        <Table rowKey={(_, index) => String(index)} dataSource={detail.events} size="small" pagination={false}
          columns={[
            { title: '步骤', dataIndex: 'stage' },
            { title: '时间', dataIndex: 'at', render: (at: number) => formatTime(at) },
            { title: '说明', dataIndex: 'reason', render: (reason: string | null) => reason || '—' }
          ]} />
      </Space>}
    </Drawer>
  </Space>
}

export default FutureBtc5mBridge
