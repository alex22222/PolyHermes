import { useCallback, useEffect, useRef, useState } from 'react'
import { Alert, Button, Card, Descriptions, Drawer, Empty, Select, Space, Spin, Switch, Table, Tag, Typography, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { ReloadOutlined } from '@ant-design/icons'
import { useMediaQuery } from 'react-responsive'
import { apiService } from '../services/api'
import { preflightIsFresh, preflightReasonText, signalIsFresh } from '../utils/futureBtc5mPreflight'
import type { FutureBtc5mBridgeStatus, FutureBtc5mOrder, FutureBtc5mOrderStatus, FutureBtc5mPreparationState } from '../types'

const preparationStateText: Record<FutureBtc5mPreparationState, string> = {
  DISABLED: '已关闭',
  WAITING_SIGNAL: '等待有效信号',
  WAITING_BROWSER: '等待 Chrome 报告',
  PENDING: '等待 Chrome 准备',
  CLAIMED: 'Chrome 正在准备',
  READY: '票据已准备，未自动买入',
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
  const statusInFlight = useRef<number | null>(null)
  const ordersInFlight = useRef<number | null>(null)
  const detailInFlight = useRef<number | null>(null)

  useEffect(() => {
    mounted.current = true
    const timer = window.setInterval(() => setClock(Date.now()), 1000)
    return () => {
      window.clearInterval(timer)
      mounted.current = false
      statusRequestSeq.current += 1
      ordersRequestSeq.current += 1
      detailRequestSeq.current += 1
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
      message.success(enabled ? '自动准备票据已开启，最终买入由你完成' : '自动准备票据已关闭')
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

  const statusStale = Boolean(runtime && (clock < statusReceivedAt || clock - statusReceivedAt > 15000 ||
    !Number.isFinite(runtime.serverTime) || Math.abs(runtime.serverTime - statusReceivedAt / 1000) > 3))
  const ledgerError = runtime?.blockReasons.some((reason) => reason.startsWith('ORDER_LEDGER_')) ?? false
  const orderCounts = runtime && !ledgerError ? runtime.orderCounts : null
  const signalFresh = signalIsFresh(runtime, statusReceivedAt, clock)
  const preflight = runtime?.preflight
  const browserFresh = preflightIsFresh(runtime, statusReceivedAt, clock)
  const preflightReady = Boolean(browserFresh && signalFresh && preflight?.result === 'READ_ONLY_READY' &&
    preflight.pagePeriodStart === runtime?.periodStart && preflight.navigation === 'CURRENT' &&
    preflight.ticketStatus === 'PASS' && preflight.amountUsd === 1 && preflight.sideMatches &&
    preflight.selectedSide === runtime?.signal?.side && preflight.buyButtonEnabled)
  const preparation = runtime?.preparation
  const serverNow = runtime ? Math.max(runtime.serverTime + (clock - statusReceivedAt) / 1000, clock / 1000) : 0
  const activeRecord = preparation?.intent || (preparation?.enabled && preparation.state === 'READY' ? preparation.lastAttempt : null)
  const intentExpired = Boolean(activeRecord && serverNow >= activeRecord.expiresAt)
  const intentFresh = Boolean(runtime && !statusStale && preparation?.enabled && preparation.intent &&
    serverNow >= preparation.intent.priceObservedAt && serverNow - preparation.intent.priceObservedAt <= 5 && !intentExpired)
  const readyFresh = Boolean(activeRecord && serverNow >= activeRecord.priceObservedAt &&
    serverNow - activeRecord.priceObservedAt <= 5 && signalFresh && runtime?.signal?.side === activeRecord.side)
  const preparationState = runtime && !statusStale && preparation
    ? intentExpired ? 'EXPIRED'
      : preparation.intent && !intentFresh || preparation.state === 'READY' && !readyFresh ? 'WAITING_SIGNAL'
        : preparation.state === 'READY' && !browserFresh ? 'WAITING_BROWSER' : preparation.state
    : null
  const intent = intentFresh ? preparation?.intent : null
  const lastAttempt = preparation?.lastAttempt
  const actualState = runtime && !statusStale
    ? preparation?.enabled ? '自动准备已开启，买入由你完成' : '自动准备已关闭'
    : '状态未知'

  return <Space direction="vertical" size="middle" style={{ width: '100%' }}>
    <div>
      <Typography.Title level={3} style={{ marginBottom: 4 }}>Future BTC 5 分钟 Bridge</Typography.Title>
      <Typography.Text type="secondary">自动准备 BTC 5 分钟 $1 票据，最终买入由你完成。每 5 秒更新准备状态与真实订单记录。</Typography.Text>
    </div>

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
          description="开启后会在有效信号出现时前往当前市场、选择方向并填写 $1，核对结果后由你检查并点击 Future 买入。准备流程不会点击买入或提交订单。" />}
        <Descriptions size="small" column={isMobile ? 1 : 3}>
          <Descriptions.Item label="Bridge 连接">{runtime ? runtime.online ? '在线' : '离线' : '未知'}</Descriptions.Item>
          <Descriptions.Item label="执行器">{runtime ? '未接入' : '未知'}</Descriptions.Item>
          <Descriptions.Item label="实际下单">{runtime && !statusStale ? '未运行' : '未知'}</Descriptions.Item>
          <Descriptions.Item label="最终买入">由你在 Future 页面完成</Descriptions.Item>
          <Descriptions.Item label="行情状态">{runtime?.feedStatus || '—'}</Descriptions.Item>
          <Descriptions.Item label="当前轮次">{formatTime(runtime?.periodStart)}</Descriptions.Item>
          <Descriptions.Item label="服务器更新时间">{formatTime(runtime?.serverTime)}</Descriptions.Item>
          <Descriptions.Item label="下单阻断原因" span={isMobile ? 1 : 3}>{runtime?.blockReasons.join('；') || '—'}</Descriptions.Item>
        </Descriptions>
        {runtime?.signal && <Descriptions title="信号采样记录" size="small" column={isMobile ? 1 : 3}>
          <Descriptions.Item label="市场" span={isMobile ? 1 : 3}>{marketLink(runtime.signal.slug)}</Descriptions.Item>
          <Descriptions.Item label="观察方向">{signalFresh ? runtime.signal.side || '—' : '采样已过期'}</Descriptions.Item>
          <Descriptions.Item label="开盘参考价">{formatValue(runtime.signal.open_price, '$')}</Descriptions.Item>
          <Descriptions.Item label="采样价格">{formatValue(runtime.signal.current_price, '$')}</Descriptions.Item>
          <Descriptions.Item label="价格采样时间">{formatTime(runtime.signal.price_observed_at)}</Descriptions.Item>
        </Descriptions>}
      </Space>
    </Card>

    <Card title="票据准备状态">
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Alert type="info" showIcon message="准备结果不代表买入或成交"
          description="准备报告只记录页面金额、方向及检查结果。历史报告不能用于当前轮次入场，最终买入前请核对实时市场与票据。" />
        <Descriptions size="small" column={isMobile ? 1 : 3}>
          <Descriptions.Item label="准备阶段">{preparationState ? preparationStateText[preparationState] : '状态未知'}</Descriptions.Item>
          <Descriptions.Item label="准备模式">{preparation ? '仅准备票据，未提交订单' : '未知'}</Descriptions.Item>
          <Descriptions.Item label="待准备方向 / 金额">{intent ? `${intent.side} / $1` : '—'}</Descriptions.Item>
          <Descriptions.Item label="待准备市场" span={isMobile ? 1 : 3}>{intent ? marketLink(intent.slug) : '—'}</Descriptions.Item>
          <Descriptions.Item label="准备截止时间">{formatTime(intent?.expiresAt)}</Descriptions.Item>
          <Descriptions.Item label="准备原因" span={isMobile ? 1 : 2}>{preparation?.reasons.join('；') || '—'}</Descriptions.Item>
        </Descriptions>
        {lastAttempt && <Descriptions title="最近操作报告（历史事实）" size="small" column={isMobile ? 1 : 3}>
          <Descriptions.Item label="最近准备结果">{preparationStateText[lastAttempt.state]}</Descriptions.Item>
          <Descriptions.Item label="准备报告方向 / 本金">{lastAttempt.side} / $1</Descriptions.Item>
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
          description="此预检核对已登录 Chrome 当前市场、票据现有金额和选中方向。自动准备票据另由上方开关控制，最终买入由你完成。" />
        <Descriptions size="small" column={isMobile ? 1 : 3}>
          <Descriptions.Item label="项目接口">{runtime && !statusStale && runtime.online ? '已连接' : '未知'}</Descriptions.Item>
          <Descriptions.Item label="Chrome 预检报告">{browserFresh ? '新鲜' : '未连接或已过期'}</Descriptions.Item>
          <Descriptions.Item label="当前 BTC 5 分钟市场">{browserFresh && preflight?.navigation === 'CURRENT' && preflight.pagePeriodStart === runtime?.periodStart ? '已匹配' : '待匹配'}</Descriptions.Item>
          <Descriptions.Item label="Chainlink / TWAP 60 秒">{signalFresh ? '已核对，采样新鲜' : '等待有效入场采样'}</Descriptions.Item>
          <Descriptions.Item label="美元市价买入栏">{browserFresh && preflight?.ticketStatus === 'PASS' ? '只读检查通过' : '待检查'}</Descriptions.Item>
          <Descriptions.Item label="页面现有金额">{browserFresh ? formatValue(preflight?.amountUsd, '$') : '—'}</Descriptions.Item>
          <Descriptions.Item label="当前选中方向">{browserFresh ? preflight?.selectedSide || '—' : '—'}</Descriptions.Item>
          <Descriptions.Item label="新鲜信号方向">{signalFresh ? runtime?.signal?.side || '—' : '—'}</Descriptions.Item>
          <Descriptions.Item label="方向匹配">{browserFresh && signalFresh ? preflight?.sideMatches ? '匹配' : '待匹配' : '待核对'}</Descriptions.Item>
          <Descriptions.Item label="页面买入按钮">{browserFresh ? preflight?.buyButtonEnabled ? '可用，未点击' : '不可用' : '未知'}</Descriptions.Item>
          <Descriptions.Item label="浏览器检查时间">{formatTime(preflight?.checkedAt)}</Descriptions.Item>
          <Descriptions.Item label="服务接收时间">{formatTime(preflight?.receivedAt)}</Descriptions.Item>
          <Descriptions.Item label="浏览器市场" span={isMobile ? 1 : 3}>{preflight?.marketUrl ? <Typography.Link href={preflight.marketUrl} target="_blank" rel="noopener noreferrer">{preflight.marketUrl}</Typography.Link> : '—'}</Descriptions.Item>
          <Descriptions.Item label="预检原因" span={isMobile ? 1 : 3}>{preflightReasonText(preflightReady, browserFresh, signalFresh, preflight?.reasons || [])}</Descriptions.Item>
        </Descriptions>
        {preflight?.lastPassed && <Descriptions title="最后通过的只读预检（历史记录）" size="small" column={isMobile ? 1 : 3}>
          <Descriptions.Item label="轮次">{formatTime(preflight.lastPassed.periodStart)}</Descriptions.Item>
          <Descriptions.Item label="检查时间">{formatTime(preflight.lastPassed.checkedAt)}</Descriptions.Item>
          <Descriptions.Item label="方向 / 现有金额">{preflight.lastPassed.signalSide} / $1</Descriptions.Item>
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
