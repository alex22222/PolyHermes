import { useEffect, useState, useMemo, useRef } from 'react'
import { Card, Table, Tag, message, Space, Input, Radio, Select, Button, Row, Col, Empty, Modal, Form, Descriptions } from 'antd'
import { SearchOutlined, AppstoreOutlined, UnorderedListOutlined, UpOutlined, DownOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { apiService } from '../services/api'
import type { AccountPosition, Account, PositionPushMessage, PositionSellRequest, MarketPriceResponse, RedeemablePositionsSummary, PositionRedeemRequest, BridgePositionSellRequest, DailyAssetPoint, PortfolioExposureResponse, PortfolioExposureBucket, PortfolioRelationResponse, PortfolioPositionRelation, PortfolioRelationType, PortfolioBuyControl, PortfolioReductionPreview, PortfolioRiskHistoricalReplay } from '../types'
import * as echarts from 'echarts'
import { getPositionKey } from '../types'
import { useMediaQuery } from 'react-responsive'
import { useWebSocketSubscription } from '../hooks/useWebSocket'
import { wsManager } from '../services/websocket'
import { formatUSDC, formatNumber as formatNumberUtil } from '../utils'

type PositionFilter = 'current' | 'historical'
type ViewMode = 'card' | 'list'

const PositionList: React.FC = () => {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const isMobile = useMediaQuery({ maxWidth: 768 })
  const [currentPositions, setCurrentPositions] = useState<AccountPosition[]>([])
  const [historyPositions, setHistoryPositions] = useState<AccountPosition[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [loading, setLoading] = useState(false)
  const [accountsLoading, setAccountsLoading] = useState(false)
  const [searchKeyword, setSearchKeyword] = useState('')
  const [positionFilter, setPositionFilter] = useState<PositionFilter>('current')
  const [selectedAccountId, setSelectedAccountId] = useState<number | undefined>(undefined)
  const [viewMode, setViewMode] = useState<ViewMode>(isMobile ? 'card' : 'list')
  const [expandedCards, setExpandedCards] = useState<Set<string>>(new Set())
  const [sellModalVisible, setSellModalVisible] = useState(false)
  const [selectedPosition, setSelectedPosition] = useState<AccountPosition | null>(null)
  const [marketPrice, setMarketPrice] = useState<MarketPriceResponse | null>(null)
  const [orderType, setOrderType] = useState<'MARKET' | 'LIMIT'>('LIMIT')
  const [sellMethod, setSellMethod] = useState<'direct' | 'bridge'>('direct')
  const [sellQuantity, setSellQuantity] = useState<string>('')
  const [limitPrice, setLimitPrice] = useState<string>('')
  const [selectedPercent, setSelectedPercent] = useState<string | null>(null)  // 记录选择的百分比（字符串格式）
  const [form] = Form.useForm()
  const [submitting, setSubmitting] = useState(false)
  const [wsConnected, setWsConnected] = useState(false)
  const [redeemModalVisible, setRedeemModalVisible] = useState(false)
  const [redeemableSummary, setRedeemableSummary] = useState<RedeemablePositionsSummary | null>(null)
  const [loadingRedeemableSummary, setLoadingRedeemableSummary] = useState(false)
  const [redeeming, setRedeeming] = useState(false)
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [dailyAssets, setDailyAssets] = useState<DailyAssetPoint[]>([])
  const [portfolioExposure, setPortfolioExposure] = useState<PortfolioExposureResponse | null>(null)
  const [portfolioRelations, setPortfolioRelations] = useState<PortfolioRelationResponse | null>(null)
  const [portfolioBuyControl, setPortfolioBuyControl] = useState<PortfolioBuyControl | null>(null)
  const [buyControlModalVisible, setBuyControlModalVisible] = useState(false)
  const [buyControlReason, setBuyControlReason] = useState('')
  const [buyControlSubmitting, setBuyControlSubmitting] = useState(false)
  const [exposurePositionKeys, setExposurePositionKeys] = useState<string[]>([])
  const [reductionModalVisible, setReductionModalVisible] = useState(false)
  const [reductionRelation, setReductionRelation] = useState<PortfolioPositionRelation | null>(null)
  const [reductionPositionKey, setReductionPositionKey] = useState('')
  const [reductionQuantity, setReductionQuantity] = useState('')
  const [reductionPreview, setReductionPreview] = useState<PortfolioReductionPreview | null>(null)
  const [reductionLoading, setReductionLoading] = useState(false)
  const [reductionConfirming, setReductionConfirming] = useState(false)
  const [reductionExecuting, setReductionExecuting] = useState(false)
  const [reductionDrafts, setReductionDrafts] = useState<PortfolioReductionPreview[]>([])
  const [historicalReplay, setHistoricalReplay] = useState<PortfolioRiskHistoricalReplay | null>(null)
  const assetChartRef = useRef<HTMLDivElement>(null)
  const assetAccountId = selectedAccountId ?? currentPositions[0]?.accountId

  useEffect(() => {
    setExposurePositionKeys([])
    if (!assetAccountId) {
      setDailyAssets([])
      setPortfolioExposure(null)
      setPortfolioRelations(null)
      setPortfolioBuyControl(null)
      setReductionDrafts([])
      setHistoricalReplay(null)
      return
    }
    apiService.accounts.dailyAssets(assetAccountId).then(response => {
      if (response.data.code === 0) setDailyAssets(response.data.data || [])
    }).catch(error => console.error('获取每日总资产失败:', error))
    apiService.accounts.portfolioExposures(assetAccountId).then(response => {
      if (response.data.code === 0) setPortfolioExposure(response.data.data || null)
    }).catch(error => console.error('获取组合暴露失败:', error))
    apiService.accounts.portfolioRelations(assetAccountId).then(response => {
      if (response.data.code === 0) setPortfolioRelations(response.data.data || null)
    }).catch(error => console.error('获取仓位关系失败:', error))
    apiService.accounts.portfolioBuyControl(assetAccountId).then(response => {
      if (response.data.code === 0) setPortfolioBuyControl(response.data.data || null)
    }).catch(error => console.error('获取 BUY 控制状态失败:', error))
    apiService.accounts.portfolioReductionDrafts(assetAccountId).then(response => {
      if (response.data.code === 0) setReductionDrafts(response.data.data || [])
    }).catch(error => console.error('获取减仓草案失败:', error))
    apiService.accounts.portfolioHistoricalReplay(assetAccountId).then(response => {
      if (response.data.code === 0) setHistoricalReplay(response.data.data || null)
    }).catch(error => console.error('获取历史回放报告失败:', error))
  }, [assetAccountId])

  const updateBuyControl = async (paused: boolean, reason?: string) => {
    if (!assetAccountId || buyControlSubmitting) return
    setBuyControlSubmitting(true)
    try {
      const response = await apiService.accounts.updatePortfolioBuyControl({ accountId: assetAccountId, paused, reason })
      if (response.data.code === 0 && response.data.data) {
        setPortfolioBuyControl(response.data.data)
        setBuyControlModalVisible(false)
        setBuyControlReason('')
        message.success(paused ? '已暂停该账户新增 BUY，SELL 不受影响' : '已恢复该账户新增 BUY')
      } else {
        message.error(response.data.msg || '更新 BUY 控制失败')
      }
    } catch (error: any) {
      message.error(error.message || '更新 BUY 控制失败')
    } finally {
      setBuyControlSubmitting(false)
    }
  }

  const confirmResumeBuy = () => {
    Modal.confirm({
      title: '恢复该账户新增 BUY？',
      content: '恢复后所有通过现有组合风控的 BUY 入口将重新允许执行；SELL 始终不受此开关影响。',
      okText: '确认恢复',
      cancelText: '取消',
      onOk: () => updateBuyControl(false, '人工确认恢复 BUY')
    })
  }

  const relationMeta: Record<PortfolioRelationType, { label: string; color: string }> = {
    DUPLICATE: { label: '重复', color: 'red' },
    TRUE_HEDGE: { label: '真对冲', color: 'green' },
    PSEUDO_HEDGE: { label: '伪对冲', color: 'volcano' },
    RELATED: { label: '相关', color: 'blue' },
    LONG_OCCUPIED: { label: '长期占资', color: 'gold' },
    UNKNOWN: { label: '未知', color: 'orange' }
  }

  const openReductionPreview = (relation: PortfolioPositionRelation) => {
    const firstKey = relation.positionKeys[0] || ''
    setReductionRelation(relation)
    setReductionPositionKey(firstKey)
    setReductionQuantity('')
    setReductionPreview(null)
    setReductionModalVisible(true)
  }

  const openReductionDraft = (draft: PortfolioReductionPreview) => {
    setReductionRelation(portfolioRelations?.relations.find(item => item.positionKeys.includes(draft.positionKey)) || null)
    setReductionPositionKey(draft.positionKey)
    setReductionQuantity(draft.requestedQuantity)
    setReductionPreview(draft)
    setReductionModalVisible(true)
  }

  const createReductionPreview = async () => {
    if (!assetAccountId || !reductionPositionKey || !reductionQuantity) return
    setReductionLoading(true)
    try {
      const response = await apiService.accounts.previewPortfolioReduction({
        accountId: assetAccountId,
        positionKey: reductionPositionKey,
        quantity: reductionQuantity
      })
      if (response.data.code === 0 && response.data.data) {
        setReductionPreview(response.data.data)
        setReductionDrafts(items => [response.data.data!, ...items.filter(item => item.draftId !== response.data.data!.draftId)])
        message.success('减仓预览草案已保存；尚未执行 SELL')
      } else {
        message.error(response.data.msg || '生成减仓预览失败')
      }
    } catch (error: any) {
      message.error(error.message || '生成减仓预览失败')
    } finally {
      setReductionLoading(false)
    }
  }

  const confirmReductionDraft = () => {
    if (!reductionPreview || reductionConfirming) return
    Modal.confirm({
      title: '确认这份减仓草案？',
      content: '系统会重新校验真实持仓和可用数量，并记录你的逐笔确认。本步仍不执行 SELL。',
      okText: '确认草案',
      cancelText: '取消',
      onOk: async () => {
        setReductionConfirming(true)
        try {
          const response = await apiService.accounts.confirmPortfolioReduction(reductionPreview.draftId)
          if (response.data.code === 0 && response.data.data) {
            setReductionPreview(response.data.data)
            setReductionDrafts(items => items.map(item => item.draftId === response.data.data!.draftId ? response.data.data! : item))
            message.success('草案已逐笔确认；仍未执行 SELL')
          } else {
            message.error(response.data.msg || '确认减仓草案失败')
          }
        } catch (error: any) {
          message.error(error.message || '确认减仓草案失败')
        } finally {
          setReductionConfirming(false)
        }
      }
    })
  }

  const executeReductionDraft = () => {
    if (!reductionPreview || !reductionPreview.executionEnabled || reductionExecuting) return
    Modal.confirm({
      title: '最终确认：立即执行真实 SELL？',
      content: `将通过 Bridge 市价卖出 ${reductionPreview.requestedQuantity} 份 ${reductionPreview.outcome}。这是真实资金操作，提交后不能撤销。`,
      okText: '确认真实卖出',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        setReductionExecuting(true)
        try {
          const response = await apiService.accounts.executePortfolioReduction(reductionPreview.draftId)
          if (response.data.code === 0 && response.data.data) {
            setReductionPreview(response.data.data)
            setReductionDrafts(items => items.map(item => item.draftId === response.data.data!.draftId ? response.data.data! : item))
            if (response.data.data.status === 'SUBMITTED') {
              message.success('SELL 已幂等提交到 Bridge，请在桥接记录中跟踪终态')
            } else {
              message.error(response.data.data.executionError || `执行状态：${response.data.data.status}`)
            }
          } else {
            message.error(response.data.msg || '提交减仓 SELL 失败')
          }
        } catch (error: any) {
          message.error(error.message || '提交减仓 SELL 失败')
        } finally {
          setReductionExecuting(false)
        }
      }
    })
  }

  const refreshReductionDraft = async () => {
    if (!reductionPreview || reductionLoading) return
    setReductionLoading(true)
    try {
      const response = await apiService.accounts.refreshPortfolioReduction(reductionPreview.draftId)
      if (response.data.code === 0 && response.data.data) {
        setReductionPreview(response.data.data)
        setReductionDrafts(items => items.map(item => item.draftId === response.data.data!.draftId ? response.data.data! : item))
        message.success(`已刷新 Bridge 终态：${response.data.data.status}`)
      } else {
        message.error(response.data.msg || '刷新 Bridge 终态失败')
      }
    } catch (error: any) {
      message.error(error.message || '刷新 Bridge 终态失败')
    } finally {
      setReductionLoading(false)
    }
  }

  const relationColumns = useMemo(() => [
    {
      title: '关系', dataIndex: 'type', key: 'type', width: 100,
      render: (value: PortfolioRelationType) => <Tag color={relationMeta[value].color}>{relationMeta[value].label}</Tag>
    },
    {
      title: '领域 / 实体', key: 'entity', width: 150,
      render: (_: unknown, row: PortfolioPositionRelation) => `${row.category || '未知'} / ${row.entityKey || '未识别'}`
    },
    {
      title: '仓位', key: 'positions',
      render: (_: unknown, row: PortfolioPositionRelation) => (
        <Button type="link" size="small" style={{ padding: 0 }} onClick={() => {
          setExposurePositionKeys(row.positionKeys)
          setPositionFilter('current')
          setCurrentPage(1)
        }}>
          查看 {row.positionKeys.length} 个仓位
        </Button>
      )
    },
    {
      title: '关联 / 未对冲价值', key: 'value', align: 'right' as const, width: 180,
      render: (_: unknown, row: PortfolioPositionRelation) => (
        <span>${formatUSDC(row.relatedValue || '0')} / {row.unmatchedValue == null ? '—' : `$${formatUSDC(row.unmatchedValue)}`}</span>
      )
    },
    {
      title: '证据', key: 'evidence',
      render: (_: unknown, row: PortfolioPositionRelation) => (
        <Space size={4} wrap><Tag>{row.confidence}</Tag><span>{row.rationale}</span></Space>
      )
    },
    {
      title: '处置', key: 'action', width: 150,
      render: (_: unknown, row: PortfolioPositionRelation) => <Button size="small" onClick={() => openReductionPreview(row)}>减仓预览</Button>
    }
  ], [assetAccountId, portfolioRelations])

  const exposureColumns = useMemo(() => [
    {
      title: '归属',
      dataIndex: 'label',
      key: 'label',
      render: (value: string, row: PortfolioExposureBucket) => (
        <Button type="link" size="small" style={{ padding: 0 }} onClick={() => {
          setExposurePositionKeys(row.positionKeys)
          setPositionFilter('current')
          setCurrentPage(1)
        }}>
          {row.key.startsWith('UNKNOWN') ? <Tag color="orange">{value}</Tag> : value}
        </Button>
      )
    },
    {
      title: '归因证据',
      dataIndex: 'attributionSource',
      key: 'attributionSource',
      render: (value: string, row: PortfolioExposureBucket) => (
        <Space size={4}>
          <Tag color={row.attributionQuality === 'EXACT' ? 'green' : row.attributionQuality === 'INFERRED' ? 'blue' : 'orange'}>
            {value} / {row.attributionQuality}
          </Tag>
          {row.leaderId != null && <Button size="small" onClick={() => navigate(`/copy-trading?leaderId=${row.leaderId}`)}>跟单配置</Button>}
        </Space>
      )
    },
    {
      title: '成本 / 未实现盈亏',
      key: 'costAndPnl',
      align: 'right' as const,
      render: (_: unknown, row: PortfolioExposureBucket) => row.costBasis == null || row.unrealizedPnl == null
        ? '未知'
        : <span>${formatUSDC(row.costBasis)} / <span style={{ color: Number(row.unrealizedPnl) >= 0 ? '#3f8600' : '#cf1322' }}>{Number(row.unrealizedPnl) >= 0 ? '+' : ''}${formatUSDC(row.unrealizedPnl)}</span></span>
    },
    {
      title: '已观察占资',
      dataIndex: 'firstObservedAt',
      key: 'firstObservedAt',
      render: (value: number | null) => {
        if (value == null) return '未知'
        const hours = Math.max(0, Math.floor((Date.now() - value) / 3600000))
        return hours >= 24 ? `${Math.floor(hours / 24)}天 ${hours % 24}小时` : `${hours}小时`
      }
    },
    {
      title: '暴露价值',
      dataIndex: 'value',
      key: 'value',
      align: 'right' as const,
      render: (value: string) => `$${formatUSDC(value)}`
    },
    {
      title: '总资产占比',
      dataIndex: 'percentOfTotalAssets',
      key: 'percentOfTotalAssets',
      align: 'right' as const,
      render: (value: string | null) => value == null ? '未知' : `${Number(value).toFixed(2)}%`
    },
    { title: '仓位', dataIndex: 'positionCount', key: 'positionCount', align: 'right' as const }
  ], [navigate])

  useEffect(() => {
    if (!assetChartRef.current) return
    const chart = echarts.init(assetChartRef.current)
    chart.setOption({
      tooltip: {
        trigger: 'axis',
        formatter: (params: any) => {
          const point = dailyAssets[params?.[0]?.dataIndex]
          if (!point) return ''
          const total = point.totalAssets == null ? '估值不完整' : `$${formatUSDC(point.totalAssets)}`
          const quality = point.valuationStatus === 'INCOMPLETE'
            ? `<br/>未知估值持仓：${point.unknownPositionCount}`
            : point.valuationStatus === 'REDEEM_VALUE_UNKNOWN'
              ? '<br/>待赎回价值：数据源不可用'
              : ''
          const redeemValue = point.pendingRedeemValue == null
            ? '未知'
            : `$${formatUSDC(point.pendingRedeemValue)}（${point.redeemablePositionCount ?? 0} 个）`
          const captureLabel = point.snapshotType === 'MIDNIGHT'
            ? `零点采样（偏移 ${Math.round(point.captureOffsetMs / 1000)} 秒）`
            : `当日首次采样（${new Date(point.capturedAt).toLocaleTimeString('zh-CN')}）`
          return `${params[0].axisValue}<br/>${captureLabel}<br/>总资产：${total}<br/>余额：$${formatUSDC(point.availableBalance)}<br/>开放持仓价值：$${formatUSDC(point.positionsValue)}<br/>待赎回价值：${redeemValue}${quality}`
        }
      },
      grid: { left: 56, right: 24, top: 24, bottom: 40 },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: dailyAssets.map(point => new Date(point.dayStartAt).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }))
      },
      yAxis: { type: 'value', axisLabel: { formatter: (value: number) => `$${value}` }, scale: true },
      series: [{
        name: '总资产',
        type: 'line',
        smooth: true,
        symbolSize: 7,
        data: dailyAssets.map(point => point.totalAssets == null ? null : Number(point.totalAssets)),
        lineStyle: { width: 3, color: '#1677ff' },
        itemStyle: { color: '#1677ff' },
        areaStyle: { color: 'rgba(22, 119, 255, 0.12)' }
      }]
    })
    const resize = () => chart.resize()
    window.addEventListener('resize', resize)
    return () => {
      window.removeEventListener('resize', resize)
      chart.dispose()
    }
  }, [dailyAssets])

  useEffect(() => {
    fetchAccounts()
    // 优先通过 API 加载初始仓位数据，避免 WebSocket 连接/推送异常时页面一直 loading
    // WebSocket 仍会推送后续实时更新
    setLoading(true)
    fetchPositions()

    // 监听连接状态（WebSocket 连接在 App.tsx 中全局初始化，全局共享）
    const removeListener = wsManager.onConnectionChange((connected) => {
      setWsConnected(connected)
    })

    // 获取当前连接状态
    setWsConnected(wsManager.isConnected())

    return () => {
      removeListener()
    }
  }, [])

  // 当仓位数据变化时，静默更新可赎回统计（不显示loading状态）
  useEffect(() => {
    if (currentPositions.length > 0) {
      fetchRedeemableSummarySilently()
    }
  }, [currentPositions, selectedAccountId])

  // 当筛选条件或搜索关键词变化时，重置分页到第一页
  useEffect(() => {
    setCurrentPage(1)
  }, [positionFilter, selectedAccountId, searchKeyword])

  // Bridge 执行方式只支持市价单，切换时强制改为市价
  useEffect(() => {
    if (sellMethod === 'bridge') {
      setOrderType('MARKET')
    }
  }, [sellMethod])

  // 静默获取可赎回仓位统计（不显示loading状态）
  const fetchRedeemableSummarySilently = async () => {
    try {
      const response = await apiService.accounts.getRedeemableSummary({ accountId: selectedAccountId })
      if (response.data.code === 0 && response.data.data) {
        setRedeemableSummary(response.data.data)
      }
    } catch (error: any) {
      console.error('获取可赎回统计失败:', error)
    }
  }

  // 获取可赎回仓位统计（带loading状态，用于用户主动操作）
  const fetchRedeemableSummary = async () => {
    setLoadingRedeemableSummary(true)
    try {
      const response = await apiService.accounts.getRedeemableSummary({ accountId: selectedAccountId })
      if (response.data.code === 0 && response.data.data) {
        setRedeemableSummary(response.data.data)
      }
    } catch (error: any) {
      console.error('获取可赎回统计失败:', error)
    } finally {
      setLoadingRedeemableSummary(false)
    }
  }

  // 处理赎回按钮点击
  const handleRedeemClick = async () => {
    setRedeemModalVisible(true)
    // 打开模态框时重新获取最新数据
    fetchRedeemableSummary()
  }

  // 提交赎回
  const handleRedeemSubmit = async () => {
    if (!redeemableSummary || redeemableSummary.positions.length === 0) {
      message.warning('没有可赎回的仓位')
      return
    }

    setRedeeming(true)
    try {
      const request: PositionRedeemRequest = {
        positions: redeemableSummary.positions.map(pos => ({
          accountId: pos.accountId,
          marketId: pos.marketId,
          outcomeIndex: pos.outcomeIndex,
          side: pos.side
        }))
      }

      const response = await apiService.accounts.redeemPositions(request)
      if (response.data.code === 0 && response.data.data) {
        const transactions = response.data.data.transactions || []
        const txHashes = transactions.map((tx: any) => tx.transactionHash.substring(0, 10) + '...').join(', ')
        message.success(`赎回成功！共 ${transactions.length} 个账户，交易哈希: ${txHashes}`)
        setRedeemModalVisible(false)
        // 刷新可赎回统计
        await fetchRedeemableSummary()
      } else {
        // 检查是否是 Builder API Key 未配置的错误
        if (response.data.code === 2014 || response.data.msg?.includes('Builder API Key 未配置')) {
          message.error({
            content: response.data.msg || 'Builder API Key 未配置',
            duration: 5,
          })
          // 延迟跳转，让用户看到错误消息
          setTimeout(() => {
            navigate('/system-settings/builder-api-key')
          }, 1500)
        } else {
          message.error(response.data.msg || '赎回失败')
        }
      }
    } catch (error: any) {
      // 检查是否是 Builder API Key 未配置的错误
      if (error.response?.data?.code === 2014 || error.message?.includes('Builder API Key 未配置')) {
        message.error({
          content: error.response?.data?.msg || error.message || 'Builder API Key 未配置，请前往系统设置页面配置',
          duration: 5,
        })
        // 延迟跳转，让用户看到错误消息
        setTimeout(() => {
          navigate('/system-settings/builder-api-key')
        }, 1500)
      } else {
        message.error('赎回失败: ' + (error.message || '未知错误'))
      }
    } finally {
      setRedeeming(false)
    }
  }

  // 订阅仓位推送
  const { connected: positionConnected } = useWebSocketSubscription<PositionPushMessage>(
    'position',
    (message) => {
      handlePositionPushMessage(message)
    }
  )

  // 更新连接状态（使用订阅的连接状态）
  useEffect(() => {
    setWsConnected(positionConnected)
  }, [positionConnected])

  /**
   * 处理仓位推送消息
   */
  const handlePositionPushMessage = (message: PositionPushMessage) => {
    if (message.type === 'FULL') {
      // 全量推送：直接替换（这是首次连接时的数据，完全以推送数据为准）
      setCurrentPositions(dedupePositions(message.currentPositions || []))
      setHistoryPositions(dedupePositions(message.historyPositions || []))
      setLoading(false)
      console.log('收到仓位全量推送:', {
        current: message.currentPositions?.length || 0,
        history: message.historyPositions?.length || 0
      })
    } else if (message.type === 'INCREMENTAL') {
      // 增量推送：合并数据（始终以推送数据为准）
      setCurrentPositions(prev => mergePositions(prev, message.currentPositions || [], message.removedPositionKeys || []))
      setHistoryPositions(prev => mergePositions(prev, message.historyPositions || [], message.removedPositionKeys || []))
      console.log('收到仓位增量推送:', {
        current: message.currentPositions?.length || 0,
        history: message.historyPositions?.length || 0,
        removed: message.removedPositionKeys?.length || 0
      })
    }
  }

  /**
   * 合并仓位数据
   * 新增的仓位插入到列表顶部，更新的仓位更新现有数据并保持位置，删除的仓位从列表中移除
   */
  const mergePositions = (
    prev: AccountPosition[],
    updates: AccountPosition[],
    removedKeys: string[]
  ): AccountPosition[] => {
    // 创建现有仓位的键集合，用于快速判断是新增还是更新
    const existingKeys = new Set(prev.map(pos => getPositionKey(pos)))

    // 区分新增和更新的仓位
    const newPositions: AccountPosition[] = []
    const updateMap = new Map<string, AccountPosition>()

    updates.forEach(update => {
      const key = getPositionKey(update)
      if (existingKeys.has(key)) {
        // 已存在的仓位，记录更新
        updateMap.set(key, update)
      } else {
        // 新增的仓位，插入到顶部
        newPositions.push(update)
      }
    })

    // 构建结果数组
    const result: AccountPosition[] = []

    // 1. 先添加新增的仓位（在顶部）
    result.push(...newPositions)

    // 2. 遍历原有仓位，应用更新或保持不变
    prev.forEach(pos => {
      const key = getPositionKey(pos)

      // 如果被删除，跳过
      if (removedKeys.includes(key)) {
        return
      }

      // 如果有更新，使用新数据；否则保持原数据
      if (updateMap.has(key)) {
        result.push(updateMap.get(key)!)
      } else {
        result.push(pos)
      }
    })

    return dedupePositions(result)
  }

  const dedupePositions = (positions: AccountPosition[]): AccountPosition[] => {
    const byKey = new Map<string, AccountPosition>()
    positions.forEach(position => {
      const key = getPositionKey(position)
      const existing = byKey.get(key)
      if (!existing) {
        byKey.set(key, position)
        return
      }
      const existingValue = parseFloat(existing.currentValue || '0')
      const nextValue = parseFloat(position.currentValue || '0')
      byKey.set(key, nextValue >= existingValue ? position : existing)
    })
    return Array.from(byKey.values())
  }

  const fetchAccounts = async () => {
    setAccountsLoading(true)
    try {
      const response = await apiService.accounts.list()
      if (response.data.code === 0 && response.data.data) {
        setAccounts(response.data.data.list || [])
      } else {
        message.error(response.data.msg || '获取账户列表失败')
      }
    } catch (error: any) {
      message.error(error.message || '获取账户列表失败')
    } finally {
      setAccountsLoading(false)
    }
  }

  // 通过 API 获取仓位列表（作为 WebSocket 首推的 fallback）
  const fetchPositions = async () => {
    try {
      const response = await apiService.accounts.positionsList()
      if (response.data.code === 0 && response.data.data) {
        const data = response.data.data
        setCurrentPositions(dedupePositions(data.currentPositions || []))
        setHistoryPositions(dedupePositions(data.historyPositions || []))
      } else {
        message.error(response.data.msg || '获取仓位数据失败')
      }
    } catch (error: any) {
      console.error('获取仓位数据失败:', error)
      message.error(error.message || '获取仓位数据失败')
    } finally {
      setLoading(false)
    }
  }

  // 根据筛选器选择对应的仓位列表
  const basePositions = useMemo(() => {
    return positionFilter === 'current' ? currentPositions : historyPositions
  }, [positionFilter, currentPositions, historyPositions])

  // 本地搜索和筛选过滤
  const filteredPositions = useMemo(() => {
    let filtered = basePositions

    // 1. 先按账户筛选
    if (selectedAccountId !== undefined) {
      filtered = filtered.filter(p => p.accountId === selectedAccountId)
    }

    if (exposurePositionKeys.length > 0) {
      const keys = new Set(exposurePositionKeys)
      filtered = filtered.filter(position => keys.has(`${position.marketId || position.marketTitle}|${position.side.toUpperCase()}`))
    }

    // 2. 最后按关键词搜索
    if (searchKeyword.trim()) {
      const keyword = searchKeyword.trim().toLowerCase()
      filtered = filtered.filter(position => {
        // 搜索账户名
        if (position.accountName?.toLowerCase().includes(keyword)) {
          return true
        }
        // 搜索钱包地址
        if (position.walletAddress.toLowerCase().includes(keyword)) {
          return true
        }
        // 搜索市场标题
        if (position.marketTitle?.toLowerCase().includes(keyword)) {
          return true
        }
        // 搜索市场slug
        if (position.marketSlug?.toLowerCase().includes(keyword)) {
          return true
        }
        // 搜索市场ID
        if (position.marketId.toLowerCase().includes(keyword)) {
          return true
        }
        // 搜索方向（YES/NO）
        if (position.side.toLowerCase().includes(keyword)) {
          return true
        }
        return false
      })
    }

    return filtered
  }, [basePositions, searchKeyword, selectedAccountId, exposurePositionKeys])

  // 分页后的数据
  const paginatedPositions = useMemo(() => {
    const startIndex = (currentPage - 1) * pageSize
    const endIndex = startIndex + pageSize
    return filteredPositions.slice(startIndex, endIndex)
  }, [filteredPositions, currentPage, pageSize])

  const getSideColor = (side: string) => {
    return side === 'YES' ? 'green' : 'red'
  }

  const formatNumber = (value: string | undefined, decimals: number = 2) => {
    if (!value) return '-'
    const num = parseFloat(value)
    if (isNaN(num)) return value
    return formatNumberUtil(value, decimals)
  }

  const formatPercent = (value: string | undefined) => {
    if (!value) return '-'
    const num = parseFloat(value)
    if (isNaN(num)) return value
    return `${num >= 0 ? '+' : ''}${num.toFixed(2)}%`
  }

  // 统计当前筛选后的仓位合计：开仓价值、当前价值、盈亏、已实现盈亏
  const positionTotals = useMemo(() => {
    if (filteredPositions.length === 0) {
      return {
        totalInitialValue: 0,
        totalCurrentValue: 0,
        totalPnl: 0,
        totalRealizedPnl: 0
      }
    }

    let totalInitialValue = 0
    let totalCurrentValue = 0
    let totalPnl = 0
    let totalRealizedPnl = 0

    filteredPositions.forEach((pos) => {
      const initialValue = parseFloat(pos.initialValue || '0')
      const currentValue = parseFloat(pos.currentValue || '0')
      const pnl = parseFloat(pos.pnl || '0')
      const realizedPnl = parseFloat(pos.realizedPnl || '0')

      if (!isNaN(initialValue)) {
        totalInitialValue += initialValue
      }

      // 当前仓位：统计持仓价值
      // 历史仓位：currentValue 应该为 0（已平仓）
      if (!isNaN(currentValue)) {
        totalCurrentValue += currentValue
      }

      // 对于当前仓位：
      //   - pnl：未实现盈亏（浮动盈亏）
      //   - realizedPnl：已实现盈亏（部分平仓时产生）
      // 对于历史仓位：
      //   - pnl：总已实现盈亏（包含部分平仓 + 完全平仓）
      //   - realizedPnl：部分平仓的已实现盈亏（可能与 pnl 重复）
      if (pos.isCurrent) {
        // 当前仓位：未实现盈亏 + 已实现盈亏
        if (!isNaN(pnl)) {
          totalPnl += pnl
        }
        if (!isNaN(realizedPnl)) {
          totalRealizedPnl += realizedPnl
        }
      } else {
        // 历史仓位：pnl 是总已实现盈亏，realizedPnl 可能重复，所以只统计 pnl
        if (!isNaN(pnl)) {
          totalRealizedPnl += pnl
        }
      }
    })

    return {
      totalInitialValue,
      totalCurrentValue,
      totalPnl,
      totalRealizedPnl
    }
  }, [filteredPositions])

  // 切换卡片展开/折叠状态
  const toggleCard = (cardKey: string) => {
    setExpandedCards(prev => {
      const newSet = new Set(prev)
      if (newSet.has(cardKey)) {
        newSet.delete(cardKey)
      } else {
        newSet.add(cardKey)
      }
      return newSet
    })
  }

  // 判断账户是否支持后端直接卖出（需要完整 CLOB API 凭证）
  const canSellDirect = (account?: Account): boolean => {
    return !!account && account.apiKeyConfigured && account.apiSecretConfigured && account.apiPassphraseConfigured
  }

  // 判断账户是否支持 Bridge 执行（只读账户 或 Magic 钱包）
  const canSellBridge = (account?: Account): boolean => {
    return !!account && (account.readOnly === true || account.walletType === 'magic')
  }

  // 处理卖出按钮点击
  const handleSellClick = async (position: AccountPosition) => {
    const account = accounts.find(a => a.id === position.accountId)
    setSelectedPosition(position)
    setSellModalVisible(true)
    setOrderType('LIMIT')
    setSellQuantity('')
    setLimitPrice('')
    setSelectedPercent(null)  // 重置百分比选择
    form.resetFields()

    // 默认执行方式：只读账户强制 Bridge；Magic 钱包优先直接卖出，没有 API 凭证时回退 Bridge
    if (account?.readOnly) {
      setSellMethod('bridge')
    } else if (account?.walletType === 'magic') {
      setSellMethod(canSellDirect(account) ? 'direct' : 'bridge')
    } else {
      setSellMethod('direct')
    }

    // 加载市场价格
    try {
      const response = await apiService.markets.getMarketPrice({
        marketId: position.marketId,
        outcomeIndex: position.outcomeIndex  // 传递结果索引，用于确定需要查询哪个 outcome 的价格
      })
      if (response.data.code === 0 && response.data.data) {
        setMarketPrice(response.data.data)
        // 默认使用当前价格作为限价
        if (response.data.data.currentPrice) {
          setLimitPrice(response.data.data.currentPrice)
          form.setFieldsValue({ limitPrice: response.data.data.currentPrice })
        }
      }
    } catch (error: any) {
      message.error('获取市场价格失败: ' + (error.message || '未知错误'))
    }
  }

  // 处理数量快捷按钮
  const handleQuantityQuickSelect = (percent: number) => {
    if (!selectedPosition) return
    // 记录选择的百分比（转为字符串，避免精度问题）
    setSelectedPercent(percent.toString())
    // 计算显示用的数量（用于预览，使用显示数量即可）
    const quantity = parseFloat(selectedPosition.quantity)
    const sellQty = (quantity * percent / 100).toFixed(4)
    setSellQuantity(sellQty)
    form.setFieldsValue({ quantity: sellQty })
    // 使用当前卖出价格计算收益
    const price = getCurrentSellPrice()
    if (price && price !== '0') {
      calculatePnl(sellQty, price)
    }
  }

  // 计算平仓收益
  const calculatePnl = (quantity: string, price: string) => {
    if (!selectedPosition || !quantity || !price) return { pnl: 0, percentPnl: 0 }

    const avgPrice = parseFloat(selectedPosition.avgPrice || '0')
    const sellPrice = parseFloat(price || '0')
    const qty = parseFloat(quantity || '0')

    // 验证数据有效性
    if (isNaN(avgPrice) || isNaN(sellPrice) || isNaN(qty) || avgPrice <= 0 || sellPrice <= 0 || qty <= 0) {
      return { pnl: 0, percentPnl: 0 }
    }

    // 计算收益：收益金额 = (卖出价格 - 平均买入价格) × 卖出数量
    const pnl = (sellPrice - avgPrice) * qty
    // 计算收益率：收益率 = (卖出价格 - 平均买入价格) / 平均买入价格 × 100%
    const percentPnl = ((sellPrice - avgPrice) / avgPrice) * 100

    return { pnl, percentPnl }
  }

  // 获取当前卖出价格（市价或限价）
  const getCurrentSellPrice = (): string => {
    if (orderType === 'MARKET') {
      // 市价订单（卖出）：使用当前价格
      return marketPrice?.currentPrice || selectedPosition?.currentPrice || '0'
    }
    return limitPrice || '0'
  }

  // 提交卖出订单
  const handleSellSubmit = async () => {
    if (!selectedPosition || submitting) return

    try {
      await form.validateFields()

      setSubmitting(true)

      const account = accounts.find(a => a.id === selectedPosition.accountId)
      const isBridgeReadOnly = account?.readOnly === true
      const useBridge = isBridgeReadOnly || sellMethod === 'bridge'

      // Bridge 执行（只读账户 或 用户选择 Bridge 方式的 Magic 钱包），当前只支持市价单
      if (useBridge) {
        if (orderType !== 'MARKET') {
          message.warning('Bridge 执行当前只支持市价卖出')
          setSubmitting(false)
          return
        }

        const request: BridgePositionSellRequest = {
          accountId: selectedPosition.accountId,
          marketId: selectedPosition.marketId,
          side: selectedPosition.side,
          outcomeIndex: selectedPosition.outcomeIndex,
          orderType: 'MARKET',
          ...(selectedPercent != null
            ? { percent: selectedPercent }
            : { quantity: sellQuantity }
          )
        }

        const response = await apiService.accounts.sellBridgePosition(request)

        if (response.data.code === 0) {
          message.success('已通知 Bridge 执行卖出，请稍后查看交易记录')
          setSellModalVisible(false)
          setSellQuantity('')
          setLimitPrice('')
          setSelectedPercent(null)
          form.resetFields()
        } else {
          message.error(response.data.msg || '通知 Bridge 卖出失败')
        }
        setSubmitting(false)
        return
      }

      const request: PositionSellRequest = {
        accountId: selectedPosition.accountId,
        marketId: selectedPosition.marketId,
        side: selectedPosition.side,
        outcomeIndex: selectedPosition.outcomeIndex,  // 传递 outcomeIndex
        orderType: orderType,
        // 如果选择了百分比，只传递百分比，不传 quantity
        // 如果手动输入，只传递 quantity，不传 percent
        ...(selectedPercent != null
          ? { percent: selectedPercent }
          : { quantity: sellQuantity }
        ),
        price: orderType === 'LIMIT' ? limitPrice : undefined
      }

      const response = await apiService.accounts.sellPosition(request)

      if (response.data.code === 0) {
        message.success('卖出订单创建成功')
        setSellModalVisible(false)
        // 重置表单
        setSellQuantity('')
        setLimitPrice('')
        setSelectedPercent(null)  // 重置百分比选择
        form.resetFields()
        // 仓位列表会通过WebSocket自动更新
      } else {
        message.error(response.data.msg || '创建卖出订单失败')
      }
    } catch (error: any) {
      if (error.errorFields) {
        // 表单验证错误
        return
      }
      message.error('创建卖出订单失败: ' + (error.message || '未知错误'))
    } finally {
      setSubmitting(false)
    }
  }

  // 实时计算收益（用于显示）
  const currentPnl = useMemo(() => {
    if (!selectedPosition || !sellQuantity) return { pnl: 0, percentPnl: 0 }
    const price = getCurrentSellPrice()
    if (!price || price === '0') return { pnl: 0, percentPnl: 0 }
    return calculatePnl(sellQuantity, price)
  }, [selectedPosition, sellQuantity, orderType, limitPrice, marketPrice])

  // 渲染卡片视图
  const renderCardView = () => {
    if (paginatedPositions.length === 0) {
      return (
        <Empty
          description="暂无仓位数据"
          style={{ padding: '60px 0' }}
        />
      )
    }

    return (
      <Row gutter={[16, 16]}>
        {paginatedPositions.map((position) => {
          const pnlNum = parseFloat(position.pnl || '0')
          const isProfit = pnlNum >= 0
          // 只有当前仓位才根据盈亏显示边框颜色
          const borderColor = positionFilter === 'current'
            ? (isProfit ? 'rgba(82, 196, 26, 0.2)' : 'rgba(245, 34, 45, 0.2)')
            : 'rgba(0,0,0,0.06)'

          const cardKey = getPositionKey(position)
          const isExpanded = expandedCards.has(cardKey)
          // 移动端需要折叠功能，桌面端始终展开
          const shouldCollapse = isMobile && !isExpanded

          return (
            <Col
              key={cardKey}
              xs={24}
              sm={12}
              lg={8}
              xl={6}
            >
              <Card
                hoverable={!isMobile}
                onClick={() => isMobile && toggleCard(cardKey)}
                style={{
                  height: '100%',
                  borderRadius: '12px',
                  boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
                  transition: 'all 0.3s ease',
                  border: `1px solid ${borderColor}`,
                  cursor: isMobile ? 'pointer' : 'default'
                }}
                bodyStyle={{ padding: '16px' }}
              >
                {/* 头部：市场图标和标题 */}
                <div style={{ marginBottom: '12px' }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
                    {position.marketIcon && (
                      <img
                        src={position.marketIcon}
                        alt={position.marketTitle || 'Market'}
                        style={{
                          width: '48px',
                          height: '48px',
                          borderRadius: '8px',
                          objectFit: 'cover',
                          flexShrink: 0
                        }}
                        onError={(e) => {
                          e.currentTarget.style.display = 'none'
                        }}
                      />
                    )}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      {position.marketTitle ? (
                        (position.marketSlug || position.eventSlug) ? (
                          <a
                            href={position.marketSlug
                              ? `https://polymarket.com/market/${position.marketSlug}`
                              : `https://polymarket.com/event/${position.eventSlug}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            style={{
                              fontWeight: 'bold',
                              color: '#1890ff',
                              textDecoration: 'none',
                              fontSize: '15px',
                              lineHeight: '1.4',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              display: '-webkit-box',
                              WebkitLineClamp: 2,
                              WebkitBoxOrient: 'vertical'
                            }}
                          >
                            {position.marketTitle}
                          </a>
                        ) : (
                          <div style={{ fontWeight: 'bold', fontSize: '15px', lineHeight: '1.4' }}>
                            {position.marketTitle}
                          </div>
                        )
                      ) : (
                        <div style={{ fontFamily: 'monospace', fontSize: '12px', color: '#999' }}>
                          {position.marketId.slice(0, 16)}...
                        </div>
                      )}
                      {position.marketSlug && (
                        <div style={{ fontSize: '12px', color: '#999', marginTop: '4px' }}>
                          {position.marketSlug}
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* 账户信息 */}
                <div style={{ marginBottom: '12px', paddingBottom: '12px', borderBottom: '1px solid #f0f0f0' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <div style={{ fontWeight: '500', fontSize: '14px', color: '#333' }}>
                        {position.accountName || `账户 ${position.accountId}`}
                      </div>
                      <div style={{ fontSize: '12px', color: '#999', fontFamily: 'monospace', marginTop: '2px' }}>
                        {position.walletAddress.slice(0, 6)}...{position.walletAddress.slice(-4)}
                      </div>
                    </div>
                    <Tag color={getSideColor(position.side)} style={{ margin: 0 }}>
                      {position.side}
                    </Tag>
                  </div>
                </div>

                {/* 关键数据 */}
                <div style={{ marginBottom: '12px' }}>
                  {/* 移动端折叠时，显示盈亏（使用简单样式） */}
                  {shouldCollapse && positionFilter === 'current' && (
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                      <span style={{ fontSize: '13px', color: '#666' }}>盈亏</span>
                      <span style={{
                        fontSize: '13px',
                        fontWeight: '500',
                        color: isProfit ? '#52c41a' : '#f5222d'
                      }}>
                        {pnlNum >= 0 ? '+' : ''}${formatUSDC(position.pnl)}
                      </span>
                    </div>
                  )}

                  {/* 展开时显示所有数据 */}
                  {!shouldCollapse && (
                    <>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                        <span style={{ fontSize: '13px', color: '#666' }}>数量</span>
                        <span style={{ fontSize: '13px', fontWeight: '500' }}>
                          {formatNumber(position.quantity, 4)}
                        </span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                        <span style={{ fontSize: '13px', color: '#666' }}>平均价格</span>
                        <span style={{ fontSize: '13px', fontWeight: '500' }}>
                          {formatNumber(position.avgPrice, 4)}
                        </span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                        <span style={{ fontSize: '13px', color: '#666' }}>开仓价值</span>
                        <span style={{ fontSize: '13px', fontWeight: '500' }}>
                          ${formatUSDC(position.initialValue)}
                        </span>
                      </div>
                      {positionFilter === 'current' && position.currentPrice && (
                        <>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                            <span style={{ fontSize: '13px', color: '#666' }}>当前价格</span>
                            <span style={{ fontSize: '13px', fontWeight: '500' }}>
                              {formatNumber(position.currentPrice, 4)}
                            </span>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                            <span style={{ fontSize: '13px', color: '#666' }}>当前价值</span>
                            <span style={{ fontSize: '13px', fontWeight: '600' }}>
                              ${formatUSDC(position.currentValue)}
                            </span>
                          </div>
                        </>
                      )}
                    </>
                  )}

                  {/* 移动端展开/折叠指示器 */}
                  {isMobile && (
                    <div style={{
                      display: 'flex',
                      justifyContent: 'center',
                      alignItems: 'center',
                      marginTop: '8px',
                      paddingTop: '8px',
                      borderTop: '1px solid #f0f0f0'
                    }}>
                      {isExpanded ? (
                        <UpOutlined style={{ color: '#999', fontSize: '14px' }} />
                      ) : (
                        <DownOutlined style={{ color: '#999', fontSize: '14px' }} />
                      )}
                    </div>
                  )}
                </div>

                {/* 盈亏信息 - 突出显示（仅当前仓位显示，仅展开时显示） */}
                {positionFilter === 'current' && !shouldCollapse && (
                  <div style={{
                    marginBottom: '12px',
                    padding: '12px',
                    borderRadius: '8px',
                    background: isProfit ? 'rgba(82, 196, 26, 0.08)' : 'rgba(245, 34, 45, 0.08)',
                    border: `1px solid ${isProfit ? 'rgba(82, 196, 26, 0.2)' : 'rgba(245, 34, 45, 0.2)'}`
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                      <span style={{ fontSize: '13px', color: '#666' }}>盈亏</span>
                      <span style={{
                        fontSize: '16px',
                        fontWeight: 'bold',
                        color: isProfit ? '#52c41a' : '#f5222d'
                      }}>
                        {pnlNum >= 0 ? '+' : ''}${formatUSDC(position.pnl)}
                      </span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                      <span style={{
                        fontSize: '14px',
                        color: isProfit ? '#52c41a' : '#f5222d',
                        fontWeight: '500'
                      }}>
                        {formatPercent(position.percentPnl)}
                      </span>
                    </div>
                    {position.realizedPnl && (
                      <div style={{
                        marginTop: '8px',
                        paddingTop: '8px',
                        borderTop: '1px solid rgba(0,0,0,0.06)',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center'
                      }}>
                        <span style={{ fontSize: '12px', color: '#999' }}>已实现盈亏</span>
                        <span style={{
                          fontSize: '13px',
                          color: parseFloat(position.realizedPnl) >= 0 ? '#52c41a' : '#f5222d',
                          fontWeight: '500'
                        }}>
                          {parseFloat(position.realizedPnl) >= 0 ? '+' : ''}${formatUSDC(position.realizedPnl)}
                        </span>
                      </div>
                    )}
                  </div>
                )}

                {/* 操作按钮（移动端折叠时隐藏） */}
                {positionFilter === 'current' && !shouldCollapse && (
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '8px' }}>
                    {!position.redeemable && (
                      <Button
                        type="primary"
                        danger
                        size="small"
                        block={isMobile}
                        onClick={() => handleSellClick(position)}
                      >
                        卖出
                      </Button>
                    )}
                  </div>
                )}
              </Card>
            </Col>
          )
        })}
      </Row>
    )
  }

  // 根据仓位类型动态生成列（优化后的紧凑布局）
  const columns = useMemo(() => {
    const baseColumns: any[] = [
      {
        title: '',
        key: 'icon',
        width: 50,
        render: (_: any, record: AccountPosition) => {
          if (!record.marketIcon) return null
          return (
            <img
              src={record.marketIcon}
              alt={record.marketTitle || 'Market'}
              style={{
                width: '32px',
                height: '32px',
                borderRadius: '4px',
                objectFit: 'cover'
              }}
              onError={(e) => {
                e.currentTarget.style.display = 'none'
              }}
            />
          )
        },
        fixed: isMobile ? ('left' as const) : undefined
      },
      {
        title: '账户',
        dataIndex: 'accountName',
        key: 'accountName',
        render: (text: string | undefined, record: AccountPosition) => (
          <div>
            <div style={{ fontWeight: 'bold' }}>
              {text || `账户 ${record.accountId}`}
            </div>
            <div style={{ fontSize: '12px', color: '#999', fontFamily: 'monospace' }}>
              {record.walletAddress.slice(0, 6)}...{record.walletAddress.slice(-6)}
            </div>
          </div>
        ),
        fixed: isMobile ? ('left' as const) : undefined,
        width: isMobile ? 120 : 160
      },
      {
        title: '市场',
        dataIndex: 'marketTitle',
        key: 'marketTitle',
        render: (text: string | undefined, record: AccountPosition) => {
          const url = record.marketSlug
            ? `https://polymarket.com/market/${record.marketSlug}`
            : record.eventSlug
              ? `https://polymarket.com/event/${record.eventSlug}`
              : null

          const handleTitleClick = (e: React.MouseEvent) => {
            e.preventDefault()
            e.stopPropagation()
            if (url) {
              window.open(url, '_blank', 'noopener,noreferrer')
            }
          }

          return (
            <div>
              {text ? (
                <div>
                  {url ? (
                    <a
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={handleTitleClick}
                      style={{ fontWeight: 'bold', color: '#1890ff', textDecoration: 'none', cursor: 'pointer' }}
                    >
                      {text}
                    </a>
                  ) : (
                    <div style={{ fontWeight: 'bold' }}>{text}</div>
                  )}
                </div>
              ) : (
                <div style={{ fontFamily: 'monospace', fontSize: '12px' }}>
                  {record.marketId.slice(0, 10)}...
                </div>
              )}
              {record.marketSlug && (
                <div style={{ fontSize: '12px', color: '#999' }}>{record.marketSlug}</div>
              )}
            </div>
          )
        },
        width: isMobile ? 180 : 220
      },
      {
        title: '方向',
        dataIndex: 'side',
        key: 'side',
        render: (side: string) => (
          <Tag color={getSideColor(side)}>{side}</Tag>
        ),
        width: 70
      },
      {
        title: '持仓',
        key: 'position',
        render: (_: any, record: AccountPosition) => (
          <div>
            <div style={{ fontWeight: '500' }}>{formatNumber(record.quantity, 4)}</div>
            <div style={{ fontSize: '12px', color: '#999' }}>@{formatNumber(record.avgPrice, 4)}</div>
          </div>
        ),
        align: 'right' as const,
        width: 100
      },
      {
        title: '开仓价值',
        dataIndex: 'initialValue',
        key: 'initialValue',
        render: (value: string) => (
          <span>${formatUSDC(value)}</span>
        ),
        align: 'right' as const,
        width: 110
      },
    ]

    // 只有当前仓位才显示当前价值/盈亏合并列
    if (positionFilter === 'current') {
      baseColumns.push({
        title: '当前价值 / 盈亏',
        key: 'valueAndPnl',
        render: (_: any, record: AccountPosition) => {
          const pnlNum = parseFloat(record.pnl || '0')
          const realizedPnl = record.realizedPnl ? parseFloat(record.realizedPnl) : null
          const percentRealizedPnl = record.percentRealizedPnl ? parseFloat(record.percentRealizedPnl) : null

          return (
            <div>
              <div style={{ fontWeight: '600', marginBottom: '2px' }}>
                ${formatUSDC(record.currentValue)}
              </div>
              <div style={{
                fontSize: '13px',
                color: pnlNum >= 0 ? '#3f8600' : '#cf1322',
                fontWeight: '500'
              }}>
                {pnlNum >= 0 ? '+' : ''}{formatUSDC(record.pnl)} ({formatPercent(record.percentPnl)})
              </div>
              {realizedPnl !== null && (
                <div style={{
                  fontSize: '11px',
                  color: '#999',
                  marginTop: '2px'
                }}>
                  已实现: {realizedPnl >= 0 ? '+' : ''}{formatUSDC(record.realizedPnl)}
                  {percentRealizedPnl !== null && ` (${formatPercent(record.percentRealizedPnl)})`}
                </div>
              )}
            </div>
          )
        },
        align: 'right' as const,
        width: 160,
        sorter: (a: AccountPosition, b: AccountPosition) => {
          const valA = parseFloat(a.currentValue || '0')
          const valB = parseFloat(b.currentValue || '0')
          return valA - valB
        },
        defaultSortOrder: 'descend' as const
      })
    }

    // 只有当前仓位才显示操作列
    if (positionFilter === 'current') {
      baseColumns.push({
        title: '操作',
        key: 'action',
        render: (_: any, record: AccountPosition) => (
          <Space size="small">
            {!record.redeemable && (
              <Button
                type="primary"
                danger
                size="small"
                onClick={() => handleSellClick(record)}
              >
                卖出
              </Button>
            )}
          </Space>
        ),
        width: 80,
        fixed: isMobile ? ('right' as const) : undefined
      })
    }

    return baseColumns
  }, [positionFilter, isMobile])

  // 统计当前和历史仓位数量（根据账户筛选）
  const filteredCurrentPositions = useMemo(() => {
    if (selectedAccountId === undefined) return currentPositions
    return currentPositions.filter(p => p.accountId === selectedAccountId)
  }, [currentPositions, selectedAccountId])

  const filteredHistoryPositions = useMemo(() => {
    if (selectedAccountId === undefined) return historyPositions
    return historyPositions.filter(p => p.accountId === selectedAccountId)
  }, [historyPositions, selectedAccountId])

  const currentCount = filteredCurrentPositions.length
  const historicalCount = filteredHistoryPositions.length

  return (
    <div>
      <div style={{ marginBottom: '16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px', marginBottom: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <h2 style={{ margin: 0 }}>仓位管理</h2>
            {/* WebSocket 连接状态指示器 */}
            <Tag
              color={wsConnected ? 'green' : 'orange'}
              style={{ margin: 0 }}
            >
              <span style={{
                display: 'inline-block',
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                backgroundColor: wsConnected ? '#52c41a' : '#fa8c16',
                marginRight: '6px',
                animation: wsConnected ? 'pulse 2s infinite' : 'pulse 1s infinite'
              }}></span>
              {wsConnected ? '实时更新' : '连接中...'}
            </Tag>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: isMobile ? '1 1 100%' : '0 0 auto', flexWrap: 'wrap' }}>
            <Input
              placeholder="搜索账户、市场、方向..."
              prefix={<SearchOutlined />}
              value={searchKeyword}
              onChange={(e) => setSearchKeyword(e.target.value)}
              allowClear
              style={{ width: isMobile ? '100%' : 300 }}
            />
            {!isMobile && (
              <Button.Group>
                <Button
                  type={viewMode === 'list' ? 'primary' : 'default'}
                  icon={<UnorderedListOutlined />}
                  onClick={() => setViewMode('list')}
                  title="列表视图"
                />
                <Button
                  type={viewMode === 'card' ? 'primary' : 'default'}
                  icon={<AppstoreOutlined />}
                  onClick={() => setViewMode('card')}
                  title="卡片视图"
                />
              </Button.Group>
            )}
            <span style={{ color: '#999', fontSize: '14px', whiteSpace: 'nowrap' }}>
              {searchKeyword || selectedAccountId !== undefined
                ? `找到 ${filteredPositions.length} / ${basePositions.length} 个仓位`
                : `共 ${basePositions.length} 个仓位`}
            </span>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
          <Select
            placeholder="选择账户"
            value={selectedAccountId ?? null}
            onChange={(value) => setSelectedAccountId(value ?? undefined)}
            style={{ width: isMobile ? '100%' : 200 }}
            loading={accountsLoading}
            options={[
              { value: null, label: '全部账户' },
              ...accounts
                .sort((a, b) => {
                  const nameA = (a.accountName || `账户 ${a.id}`).toLowerCase()
                  const nameB = (b.accountName || `账户 ${b.id}`).toLowerCase()
                  return nameA.localeCompare(nameB, 'zh-CN')
                })
                .map(account => ({
                  value: account.id,
                  label: account.accountName || `账户 ${account.id}`
                }))
            ]}
          />
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
            <div style={{
              background: '#f5f5f5',
              padding: '4px',
              borderRadius: '8px',
              display: 'inline-flex',
              gap: '4px'
            }}>
              <Radio.Group
                value={positionFilter}
                onChange={(e) => setPositionFilter(e.target.value)}
                size={isMobile ? 'small' : 'middle'}
                style={{ display: 'flex', gap: '4px' }}
              >
                <Radio.Button
                  value="current"
                  style={{
                    border: 'none',
                    borderRadius: '6px',
                    padding: '8px 16px',
                    height: 'auto',
                    lineHeight: '1.5',
                    transition: 'all 0.3s ease',
                    background: positionFilter === 'current' ? '#1890ff' : 'transparent',
                    color: positionFilter === 'current' ? '#fff' : '#666',
                    fontWeight: positionFilter === 'current' ? '500' : 'normal',
                    boxShadow: positionFilter === 'current' ? '0 2px 4px rgba(24, 144, 255, 0.2)' : 'none'
                  }}
                >
                  <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span>当前仓位</span>
                    <Tag
                      color={positionFilter === 'current' ? 'default' : 'blue'}
                      style={{
                        margin: 0,
                        borderRadius: '10px',
                        fontSize: '12px',
                        lineHeight: '20px',
                        padding: '0 8px',
                        background: positionFilter === 'current' ? 'rgba(255, 255, 255, 0.3)' : undefined,
                        color: positionFilter === 'current' ? '#fff' : undefined,
                        border: positionFilter === 'current' ? 'none' : undefined
                      }}
                    >
                      {currentCount}
                    </Tag>
                  </span>
                </Radio.Button>
                <Radio.Button
                  value="historical"
                  style={{
                    border: 'none',
                    borderRadius: '6px',
                    padding: '8px 16px',
                    height: 'auto',
                    lineHeight: '1.5',
                    transition: 'all 0.3s ease',
                    background: positionFilter === 'historical' ? '#1890ff' : 'transparent',
                    color: positionFilter === 'historical' ? '#fff' : '#666',
                    fontWeight: positionFilter === 'historical' ? '500' : 'normal',
                    boxShadow: positionFilter === 'historical' ? '0 2px 4px rgba(24, 144, 255, 0.2)' : 'none'
                  }}
                >
                  <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span>历史仓位</span>
                    <Tag
                      color={positionFilter === 'historical' ? 'default' : 'default'}
                      style={{
                        margin: 0,
                        borderRadius: '10px',
                        fontSize: '12px',
                        lineHeight: '20px',
                        padding: '0 8px',
                        background: positionFilter === 'historical' ? 'rgba(255, 255, 255, 0.3)' : undefined,
                        color: positionFilter === 'historical' ? '#fff' : undefined,
                        border: positionFilter === 'historical' ? 'none' : undefined
                      }}
                    >
                      {historicalCount}
                    </Tag>
                  </span>
                </Radio.Button>
              </Radio.Group>
            </div>
            {redeemableSummary && redeemableSummary.totalCount > 0 && (
              <Button
                type="primary"
                onClick={handleRedeemClick}
                loading={loadingRedeemableSummary}
                style={{
                  background: '#52c41a',
                  borderColor: '#52c41a'
                }}
              >
                赎回 ({redeemableSummary.totalCount}个, ${formatUSDC(redeemableSummary.totalValue)})
              </Button>
            )}
          </div>
        </div>
        {/* 合计信息：开仓价值、当前价值、盈亏、已实现盈亏（仅当前仓位显示） */}
        {filteredPositions.length > 0 && positionFilter === 'current' && (
          <div
            style={{
              marginTop: '12px',
              padding: '10px 16px',
              borderRadius: '8px',
              background: '#f5f5f5',
              display: 'flex',
              flexWrap: 'wrap',
              gap: '16px',
              fontSize: '13px',
              color: '#555'
            }}
          >
            <span>
              开仓价值合计：{' '}
              <span style={{ fontWeight: 600 }}>
                ${formatUSDC(positionTotals.totalInitialValue.toString())}
              </span>
            </span>
            <span>
              当前价值合计：{' '}
              <span style={{ fontWeight: 600 }}>
                ${formatUSDC(positionTotals.totalCurrentValue.toString())}
              </span>
            </span>
            <span>
              浮动盈亏合计：{' '}
              <span
                style={{
                  fontWeight: 600,
                  color: positionTotals.totalPnl >= 0 ? '#3f8600' : '#cf1322'
                }}
              >
                {positionTotals.totalPnl >= 0 ? '+' : ''}
                ${formatUSDC(positionTotals.totalPnl.toString())}
              </span>
            </span>
            <span>
              已实现盈亏合计：{' '}
              <span
                style={{
                  fontWeight: 600,
                  color: positionTotals.totalRealizedPnl >= 0 ? '#3f8600' : '#cf1322'
                }}
              >
                {positionTotals.totalRealizedPnl >= 0 ? '+' : ''}
                ${formatUSDC(positionTotals.totalRealizedPnl.toString())}
              </span>
            </span>
          </div>
        )}
      </div>
      <Card
        title="每日总资产快照"
        extra={<span style={{ color: '#999', fontSize: 12 }}>完整总资产 = 可用余额 + 开放持仓价值 + 待赎回价值；未知项不按 0 计算</span>}
        style={{ marginBottom: 16 }}
      >
        {dailyAssets.length > 0 ? (
          <div ref={assetChartRef} style={{ width: '100%', height: isMobile ? 260 : 320 }} />
        ) : (
          <Empty description="暂无每日资产快照，首次同步后开始记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Card>

      <Card title="组合风险暴露" style={{ marginBottom: 16 }}>
        {portfolioExposure ? (
          <>
            {exposurePositionKeys.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                <Tag color="blue" closable onClose={() => setExposurePositionKeys([])}>
                  正在下钻查看 {exposurePositionKeys.length} 个仓位
                </Tag>
              </div>
            )}
            <Descriptions bordered size="small" column={isMobile ? 1 : 4} style={{ marginBottom: 16 }}>
              <Descriptions.Item label="账户总资产">
                {portfolioExposure.account.totalAssets == null ? '估值不完整' : `$${formatUSDC(portfolioExposure.account.totalAssets)}`}
              </Descriptions.Item>
              <Descriptions.Item label="开放持仓">${formatUSDC(portfolioExposure.account.openPositionsValue)}</Descriptions.Item>
              <Descriptions.Item label="待赎回">
                {portfolioExposure.account.pendingRedeemValue == null ? '未知' : `$${formatUSDC(portfolioExposure.account.pendingRedeemValue)}`}
              </Descriptions.Item>
              <Descriptions.Item label="数据状态">
                <Tag color={portfolioExposure.account.valuationStatus === 'COMPLETE' ? 'green' : 'orange'}>
                  {portfolioExposure.account.valuationStatus}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="持仓成本">
                {portfolioExposure.account.positionCostBasis == null ? '未知' : `$${formatUSDC(portfolioExposure.account.positionCostBasis)}`}
              </Descriptions.Item>
              <Descriptions.Item label="未实现盈亏">
                {portfolioExposure.account.unrealizedPnl == null ? '未知' : (
                  <span style={{ color: Number(portfolioExposure.account.unrealizedPnl) >= 0 ? '#3f8600' : '#cf1322' }}>
                    {Number(portfolioExposure.account.unrealizedPnl) >= 0 ? '+' : ''}${formatUSDC(portfolioExposure.account.unrealizedPnl)}
                  </span>
                )}
              </Descriptions.Item>
              <Descriptions.Item label="最早观察时间">
                {portfolioExposure.account.firstObservedAt == null ? '未知' : new Date(portfolioExposure.account.firstObservedAt).toLocaleString('zh-CN')}
              </Descriptions.Item>
            </Descriptions>
            <Space wrap style={{ marginBottom: 16 }}>
              <Tag>总仓位 {portfolioExposure.coverage.totalPositions}</Tag>
              <Tag color={portfolioExposure.coverage.unknownLeaderPositions ? 'orange' : 'green'}>Leader 未归属 {portfolioExposure.coverage.unknownLeaderPositions}</Tag>
              <Tag color={portfolioExposure.coverage.unknownCategoryPositions ? 'orange' : 'green'}>领域未分类 {portfolioExposure.coverage.unknownCategoryPositions}</Tag>
              <Tag color={portfolioExposure.coverage.unknownEventPositions ? 'orange' : 'green'}>事件未归属 {portfolioExposure.coverage.unknownEventPositions}</Tag>
              <Tag color={portfolioExposure.coverage.unknownValuePositions ? 'red' : 'green'}>估值未知 {portfolioExposure.coverage.unknownValuePositions}</Tag>
            </Space>
            <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
              {([
                ['Leader', portfolioExposure.coverage.leader],
                ['领域', portfolioExposure.coverage.category],
                ['事件', portfolioExposure.coverage.event]
              ] as const).map(([label, coverage]) => (
                <Col xs={24} md={8} key={label}>
                  <Card size="small" title={`${label}归因质量`}>
                    <Space direction="vertical" size={4}>
                      <span>已知价值覆盖率：{coverage.knownValueCoveragePercent == null ? '未知' : `${Number(coverage.knownValueCoveragePercent).toFixed(2)}%`}</span>
                      <span>已知 ${formatUSDC(coverage.knownValue)} / 未知 ${formatUSDC(coverage.unknownValue)}</span>
                      <Tag color={coverage.shadowEligible ? 'green' : 'orange'}>
                        {coverage.status}（Shadow 门槛 {coverage.minimumShadowCoveragePercent}%）
                      </Tag>
                    </Space>
                  </Card>
                </Col>
              ))}
            </Row>
            <Row gutter={[16, 16]}>
              <Col xs={24} xl={8}>
                <Card size="small" title="按 Leader">
                  <Table rowKey="key" size="small" pagination={false} dataSource={portfolioExposure.leaders} columns={exposureColumns} scroll={{ x: 640 }} />
                </Card>
              </Col>
              <Col xs={24} xl={8}>
                <Card size="small" title="按领域">
                  <Table rowKey="key" size="small" pagination={false} dataSource={portfolioExposure.categories} columns={exposureColumns} scroll={{ x: 640 }} />
                </Card>
              </Col>
              <Col xs={24} xl={8}>
                <Card size="small" title="按事件">
                  <Table rowKey="key" size="small" pagination={false} dataSource={portfolioExposure.events} columns={exposureColumns} scroll={{ x: 640 }} />
                </Card>
              </Col>
            </Row>
          </>
        ) : (
          <Empty description="暂无组合暴露数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Card>

      <Card
        title="G3 历史回放与 Shadow 数据质量"
        extra={<span style={{ color: '#999', fontSize: 12 }}>只读报告；不改变 BUY/SELL 规则</span>}
        style={{ marginBottom: 16 }}
      >
        {historicalReplay ? (
          <>
            <Space wrap style={{ marginBottom: 16 }}>
              <Tag color="green">BUY 成功 {historicalReplay.buySuccess}</Tag>
              <Tag color="red">BUY 失败 {historicalReplay.buyFailed}</Tag>
              <Tag color="green">SELL 成功 {historicalReplay.sellSuccess}</Tag>
              <Tag color="red">SELL 失败 {historicalReplay.sellFailed}</Tag>
              <Tag>账户归属记录 {historicalReplay.scopedBridgeRecords}</Tag>
              {historicalReplay.unscopedBridgeRecords > 0 && <Tag color="orange">未归属 Bridge 记录 {historicalReplay.unscopedBridgeRecords}</Tag>}
            </Space>
            <Table
              size="small"
              pagination={false}
              rowKey="code"
              dataSource={historicalReplay.metrics}
              columns={[
                { title: '指标', dataIndex: 'code', width: 220 },
                { title: '数值', dataIndex: 'value', width: 150, render: value => value ?? '—' },
                { title: '数据状态', dataIndex: 'status', width: 160, render: value => <Tag color={value === 'AVAILABLE' ? 'green' : 'orange'}>{value}</Tag> },
                { title: '口径/说明', dataIndex: 'rationale' }
              ]}
            />
            {historicalReplay.blockers.length > 0 && (
              <div style={{ marginTop: 16, padding: 12, background: '#fffbe6', border: '1px solid #ffe58f', borderRadius: 8 }}>
                <div style={{ marginBottom: 4, fontWeight: 500 }}>当前不可用于 Enforced 评审的数据缺口</div>
                {historicalReplay.blockers.map(item => <div key={item} style={{ fontSize: 12, color: '#8c6d1f' }}>{item}</div>)}
              </div>
            )}
          </>
        ) : (
          <Empty description="暂无历史回放数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Card>

      <Card
        title="重复、对冲与相关仓位"
        extra={<span style={{ color: '#999', fontSize: 12 }}>只读识别；相反 outcome 不会自动按全额抵消，任何处置都需人工预览和逐笔确认</span>}
        style={{ marginBottom: 16 }}
      >
        {portfolioRelations ? (
          <>
            <div style={{ marginBottom: 16, padding: 12, borderRadius: 8, background: portfolioBuyControl?.paused ? '#fff2f0' : '#f6ffed', border: `1px solid ${portfolioBuyControl?.paused ? '#ffccc7' : '#b7eb8f'}` }}>
              <Space wrap style={{ width: '100%', justifyContent: 'space-between' }}>
                <Space wrap>
                  <Tag color={portfolioBuyControl?.paused ? 'red' : 'green'}>
                    {portfolioBuyControl?.paused ? '新增 BUY 已暂停' : '新增 BUY 正常'}
                  </Tag>
                  <span>该人工开关覆盖 Bridge、自动策略和手工 BUY；SELL 始终优先且不受影响。</span>
                  {portfolioBuyControl?.paused && <span style={{ color: '#cf1322' }}>原因：{portfolioBuyControl.reason}</span>}
                  {portfolioBuyControl?.updatedAt && (
                    <span style={{ color: '#999', fontSize: 12 }}>
                      {portfolioBuyControl.updatedBy} · {new Date(portfolioBuyControl.updatedAt).toLocaleString('zh-CN')}
                    </span>
                  )}
                </Space>
                {portfolioBuyControl?.paused ? (
                  <Button onClick={confirmResumeBuy} loading={buyControlSubmitting}>恢复 BUY</Button>
                ) : (
                  <Button danger onClick={() => setBuyControlModalVisible(true)}>暂停新增 BUY</Button>
                )}
              </Space>
            </div>
            <Space wrap style={{ marginBottom: 16 }}>
              {(Object.keys(relationMeta) as PortfolioRelationType[]).map(type => {
                const count = portfolioRelations.countsByType[type] || 0
                if (count === 0) return null
                return (
                  <Tag color={relationMeta[type].color} key={type}>
                    {relationMeta[type].label} {count} 组 · ${formatUSDC(portfolioRelations.relatedValueByType[type] || '0')}
                  </Tag>
                )
              })}
              <span style={{ color: '#999', fontSize: 12 }}>
                识别时间：{new Date(portfolioRelations.generatedAt).toLocaleString('zh-CN')}
              </span>
            </Space>
            {portfolioRelations.relations.length > 0 ? (
              <Table
                rowKey={(row) => `${row.type}:${row.positionKeys.join('|')}`}
                size="small"
                pagination={{ pageSize: 10, hideOnSinglePage: true }}
                dataSource={portfolioRelations.relations}
                columns={relationColumns}
                scroll={{ x: 900 }}
              />
            ) : (
              <Empty description="当前没有识别到重复、对冲、相关或长期占资关系" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
            {reductionDrafts.some(item => item.status !== 'EXPIRED') && (
              <Card size="small" title="人工减仓队列" style={{ marginTop: 16 }}>
                <Table
                  size="small"
                  rowKey="draftId"
                  pagination={{ pageSize: 5, hideOnSinglePage: true }}
                  dataSource={reductionDrafts.filter(item => item.status !== 'EXPIRED')}
                  columns={[
                    { title: '市场', dataIndex: 'marketTitle', ellipsis: true },
                    { title: '方向', dataIndex: 'outcome', width: 90, render: value => <Tag>{value}</Tag> },
                    { title: '数量', dataIndex: 'requestedQuantity', width: 110 },
                    { title: '状态', dataIndex: 'status', width: 120, render: value => <Tag color={value === 'FAILED' ? 'red' : value === 'EXECUTED' ? 'green' : 'blue'}>{value}</Tag> },
                    { title: '尝试', dataIndex: 'executionAttempt', width: 80, render: value => value || '—' },
                    { title: '操作', width: 100, render: (_, row) => <Button size="small" onClick={() => openReductionDraft(row)}>查看</Button> }
                  ]}
                />
              </Card>
            )}
          </>
        ) : (
          <Empty description="请选择账户查看仓位关系" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Card>

      <Modal
        title="暂停该账户新增 BUY"
        open={buyControlModalVisible}
        okText="确认暂停"
        cancelText="取消"
        okButtonProps={{ danger: true, disabled: buyControlReason.trim().length === 0 }}
        confirmLoading={buyControlSubmitting}
        onCancel={() => !buyControlSubmitting && setBuyControlModalVisible(false)}
        onOk={() => updateBuyControl(true, buyControlReason.trim())}
      >
        <p>暂停立即覆盖 Bridge、后端 Gateway、自动策略和手工 BUY，不影响 SELL、赎回和安全退出。</p>
        <Input.TextArea
          value={buyControlReason}
          onChange={event => setBuyControlReason(event.target.value)}
          placeholder="必须填写暂停原因，写入审计记录"
          rows={4}
          maxLength={500}
          showCount
        />
      </Modal>

      {(isMobile || viewMode === 'card') ? (
        <Card loading={loading}>
          {renderCardView()}
          {/* 移动端分页 */}
          {filteredPositions.length > 0 && (
            <>
              <div style={{
                marginTop: '16px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: '8px'
              }}>
                <div style={{ fontSize: '14px', color: '#666' }}>
                  共 {filteredPositions.length} 个仓位{searchKeyword ? `（已过滤）` : ''}
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <Button
                    size="small"
                    disabled={currentPage === 1}
                    onClick={() => setCurrentPage(currentPage - 1)}
                  >
                    上一页
                  </Button>
                  <span style={{ lineHeight: '32px', fontSize: '14px' }}>
                    {currentPage} / {Math.ceil(filteredPositions.length / pageSize)}
                  </span>
                  <Button
                    size="small"
                    disabled={currentPage >= Math.ceil(filteredPositions.length / pageSize)}
                    onClick={() => setCurrentPage(currentPage + 1)}
                  >
                    下一页
                  </Button>
                </div>
              </div>
              {/* 每页条数选择器 */}
              <div style={{
                marginTop: '8px',
                textAlign: 'right',
                fontSize: '14px'
              }}>
                <Select
                  value={pageSize}
                  onChange={(value) => {
                    setPageSize(value)
                    setCurrentPage(1)
                  }}
                  size="small"
                  style={{ width: '100px' }}
                >
                  <Select.Option value={10}>10 条/页</Select.Option>
                  <Select.Option value={20}>20 条/页</Select.Option>
                  <Select.Option value={50}>50 条/页</Select.Option>
                </Select>
              </div>
            </>
          )}
        </Card>
      ) : (
        <Card>
          <Table
            dataSource={filteredPositions}
            columns={columns}
            rowKey={(record) => getPositionKey(record)}
            loading={loading}
            pagination={{
              current: currentPage,
              pageSize: pageSize,
              total: filteredPositions.length,
              showSizeChanger: true,
              pageSizeOptions: ['10', '20', '50'],
              showTotal: (total) => `共 ${total} 个仓位${searchKeyword ? `（已过滤）` : ''}`,
              onChange: (page, size) => {
                setCurrentPage(page)
                if (size !== pageSize) {
                  setPageSize(size)
                }
              }
            }}
            scroll={isMobile ? { x: 1500 } : undefined}
          />
        </Card>
      )}

      {/* 出售模态框 */}
      <Modal
        title={`出售仓位 - ${selectedPosition?.marketTitle || selectedPosition?.marketId || ''}`}
        open={sellModalVisible}
        onCancel={() => {
          if (!submitting) {
            setSellModalVisible(false)
          }
        }}
        onOk={handleSellSubmit}
        okText="确认卖出"
        cancelText="取消"
        width={isMobile ? '90%' : 600}
        destroyOnClose
        confirmLoading={submitting}
        maskClosable={!submitting}
      >
        {selectedPosition && (
          <Form form={form} layout="vertical">
            <div style={{ marginBottom: '16px', padding: '12px', background: '#f5f5f5', borderRadius: '8px' }}>
              <div style={{ marginBottom: '8px' }}>
                <span style={{ color: '#666' }}>账户: </span>
                <span style={{ fontWeight: '500' }}>{selectedPosition.accountName || `账户 ${selectedPosition.accountId}`}</span>
              </div>
              <div style={{ marginBottom: '8px' }}>
                <span style={{ color: '#666' }}>方向: </span>
                <Tag color={getSideColor(selectedPosition.side)}>{selectedPosition.side}</Tag>
              </div>
              <div style={{ marginBottom: '8px' }}>
                <span style={{ color: '#666' }}>当前持仓: </span>
                <span style={{ fontWeight: '500' }}>{formatNumber(selectedPosition.quantity, 4)}</span>
              </div>
              <div style={{ marginBottom: '8px' }}>
                <span style={{ color: '#666' }}>平均价格: </span>
                <span style={{ fontWeight: '500' }}>{formatNumber(selectedPosition.avgPrice, 4)}</span>
              </div>
              {selectedPosition.currentPrice && (
                <div>
                  <span style={{ color: '#666' }}>当前价格: </span>
                  <span style={{ fontWeight: '500' }}>{formatNumber(selectedPosition.currentPrice, 4)}</span>
                </div>
              )}
            </div>

            {/* 执行方式选择：Magic 钱包显示，只读账户强制 Bridge */}
            {(() => {
              const account = accounts.find(a => a.id === selectedPosition.accountId)
              if (!account) return null
              if (account.readOnly) {
                return (
                  <div style={{ marginBottom: '16px', padding: '12px', background: '#fff7e6', borderRadius: '8px' }}>
                    <span style={{ color: '#fa8c16', fontWeight: 500 }}>
                      {t('positionList.sellBridgeReadOnlyTip') || '该账户为 Bridge 只读账户，将通过 Bridge 浏览器执行市价卖出'}
                    </span>
                  </div>
                )
              }
              if (account.walletType === 'magic') {
                return (
                  <Form.Item label={t('positionList.sellMethod') || '执行方式'} required>
                    <Radio.Group
                      value={sellMethod}
                      onChange={(e) => setSellMethod(e.target.value)}
                    >
                      <Radio value="direct" disabled={!canSellDirect(account)}>
                        {t('positionList.sellMethodDirect') || '后端直接卖出 (CLOB)'}
                      </Radio>
                      <Radio value="bridge" disabled={!canSellBridge(account)}>
                        {t('positionList.sellMethodBridge') || 'Bridge 浏览器执行'}
                      </Radio>
                    </Radio.Group>
                    {sellMethod === 'bridge' && (
                      <div style={{ marginTop: '4px', fontSize: '12px', color: '#999' }}>
                        {t('positionList.sellBridgeTip') || 'Bridge 执行当前只支持市价单，由 Bridge 在浏览器会话中完成卖出'}
                      </div>
                    )}
                  </Form.Item>
                )
              }
              return null
            })()}

            <Form.Item label="订单类型" required>
              <Radio.Group
                value={orderType}
                onChange={(e) => {
                  setOrderType(e.target.value)
                  // 切换订单类型时重新计算收益
                  if (sellQuantity) {
                    const price = e.target.value === 'MARKET'
                      ? (marketPrice?.currentPrice || selectedPosition?.currentPrice || '0')
                      : limitPrice || '0'
                    calculatePnl(sellQuantity, price)
                  }
                }}
                disabled={sellMethod === 'bridge'}
              >
                <Radio value="MARKET" disabled={sellMethod === 'bridge'}>市价出售</Radio>
                <Radio value="LIMIT" disabled={sellMethod === 'bridge'}>限价出售</Radio>
              </Radio.Group>
            </Form.Item>

            <Form.Item
              label="卖出数量"
              name="quantity"
              rules={[
                { required: true, message: '请输入卖出数量' },
                {
                  validator: (_, value) => {
                    if (!value || parseFloat(value) <= 0) {
                      return Promise.reject('卖出数量必须大于0')
                    }
                    if (parseFloat(value) > parseFloat(selectedPosition.quantity)) {
                      return Promise.reject('卖出数量不能超过持仓数量')
                    }
                    return Promise.resolve()
                  }
                }
              ]}
            >
              <Input
                value={sellQuantity}
                onChange={(e) => {
                  const newQuantity = e.target.value
                  setSellQuantity(newQuantity)
                  // 用户手动输入时，清除百分比选择
                  setSelectedPercent(null)
                  if (newQuantity) {
                    const price = getCurrentSellPrice()
                    calculatePnl(newQuantity, price)
                  }
                }}
                placeholder="请输入卖出数量"
                suffix={
                  <Space size="small">
                    <Button size="small" onClick={() => handleQuantityQuickSelect(20)}>20%</Button>
                    <Button size="small" onClick={() => handleQuantityQuickSelect(50)}>50%</Button>
                    <Button size="small" onClick={() => handleQuantityQuickSelect(80)}>80%</Button>
                    <Button size="small" onClick={() => handleQuantityQuickSelect(100)}>100%</Button>
                  </Space>
                }
              />
            </Form.Item>

            {orderType === 'LIMIT' && (
              <Form.Item
                label="限价价格"
                name="limitPrice"
                rules={[
                  { required: true, message: '请输入限价价格' },
                  {
                    validator: (_, value) => {
                      if (!value || parseFloat(value) <= 0) {
                        return Promise.reject('价格必须大于0')
                      }
                      return Promise.resolve()
                    }
                  }
                ]}
              >
                <Input
                  value={limitPrice}
                  onChange={(e) => {
                    const newPrice = e.target.value
                    setLimitPrice(newPrice)
                    if (sellQuantity && newPrice) {
                      calculatePnl(sellQuantity, newPrice)
                    }
                  }}
                  placeholder="请输入限价价格"
                />
                {marketPrice?.currentPrice && (
                  <div style={{ marginTop: '4px', fontSize: '12px', color: '#999' }}>
                    参考价格（卖出参考）: {formatNumber(marketPrice.currentPrice, 4)}
                  </div>
                )}
              </Form.Item>
            )}

            {orderType === 'MARKET' && (
              <div style={{ marginBottom: '16px', padding: '12px', background: '#f0f7ff', borderRadius: '8px' }}>
                <div style={{ fontSize: '12px', color: '#666', marginBottom: '4px' }}>市价参考（卖出）</div>
                <div style={{ fontSize: '14px' }}>
                  {marketPrice?.currentPrice ? (
                    <>当前价格: <span style={{ fontWeight: '500' }}>{formatNumber(marketPrice.currentPrice, 4)}</span></>
                  ) : selectedPosition?.currentPrice ? (
                    <>当前价格: <span style={{ fontWeight: '500' }}>{formatNumber(selectedPosition.currentPrice, 4)}</span></>
                  ) : (
                    <span style={{ color: '#999' }}>暂无价格数据</span>
                  )}
                </div>
              </div>
            )}

            {/* 预计平仓收益 */}
            {sellQuantity && (
              <div style={{
                marginTop: '16px',
                padding: '16px',
                background: currentPnl.pnl >= 0 ? 'rgba(82, 196, 26, 0.08)' : 'rgba(245, 34, 45, 0.08)',
                border: `1px solid ${currentPnl.pnl >= 0 ? 'rgba(82, 196, 26, 0.2)' : 'rgba(245, 34, 45, 0.2)'}`,
                borderRadius: '8px'
              }}>
                <div style={{ fontSize: '13px', color: '#666', marginBottom: '8px' }}>预计平仓收益</div>
                <div style={{
                  fontSize: '20px',
                  fontWeight: 'bold',
                  color: currentPnl.pnl >= 0 ? '#52c41a' : '#f5222d',
                  marginBottom: '4px'
                }}>
                  {currentPnl.pnl >= 0 ? '+' : ''}${formatUSDC(currentPnl.pnl)}
                </div>
                <div style={{
                  fontSize: '14px',
                  color: currentPnl.percentPnl >= 0 ? '#52c41a' : '#f5222d',
                  fontWeight: '500'
                }}>
                  {currentPnl.percentPnl >= 0 ? '+' : ''}{currentPnl.percentPnl.toFixed(2)}%
                </div>
              </div>
            )}
          </Form>
        )}
      </Modal>

      <Modal
        title="人工减仓预览（不执行 SELL）"
        open={reductionModalVisible}
        onCancel={() => setReductionModalVisible(false)}
        width={isMobile ? '95%' : 900}
        destroyOnClose
        footer={[
          <Button key="close" onClick={() => setReductionModalVisible(false)}>关闭</Button>,
          <Button key="preview" type="primary" loading={reductionLoading} disabled={!reductionPositionKey || !reductionQuantity} onClick={createReductionPreview}>
            生成新预览草案
          </Button>
        ]}
      >
        <div style={{ marginBottom: 16, padding: 12, background: '#fffbe6', border: '1px solid #ffe58f', borderRadius: 8 }}>
          本页只计算并保存可过期草案，不会下单。草案有效期 10 分钟，后续执行必须逐笔人工确认。
        </div>
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Select
            style={{ width: '100%' }}
            value={reductionPositionKey || undefined}
            placeholder="选择需要减仓的真实持仓"
            onChange={(value) => {
              setReductionPositionKey(value)
              setReductionQuantity('')
              setReductionPreview(null)
            }}
            options={(reductionRelation?.positionKeys || []).map(key => {
              const position = portfolioRelations?.positions.find(item => item.positionKey === key)
              return { value: key, label: position ? `${position.marketTitle} · ${position.outcome} · 可用 ${position.quantity}` : key }
            })}
          />
          <Input
            value={reductionQuantity}
            onChange={event => {
              setReductionQuantity(event.target.value)
              setReductionPreview(null)
            }}
            placeholder="输入减仓数量"
          />
        </Space>
        {reductionPreview && (
          <>
            <Descriptions bordered size="small" column={isMobile ? 1 : 2} style={{ marginTop: 20 }}>
              <Descriptions.Item label="草案 ID">{reductionPreview.draftId}</Descriptions.Item>
              <Descriptions.Item label="状态"><Tag color="blue">{reductionPreview.status}</Tag></Descriptions.Item>
              <Descriptions.Item label="减仓数量">{reductionPreview.requestedQuantity} / {reductionPreview.availableQuantity}</Descriptions.Item>
              <Descriptions.Item label="预计回收现金">${formatUSDC(reductionPreview.estimatedProceeds)}</Descriptions.Item>
              <Descriptions.Item label="可用余额">${formatUSDC(reductionPreview.beforeAvailableBalance)} → ${formatUSDC(reductionPreview.afterAvailableBalance)}</Descriptions.Item>
              <Descriptions.Item label="开放持仓价值">${formatUSDC(reductionPreview.beforeOpenPositionsValue)} → ${formatUSDC(reductionPreview.afterOpenPositionsValue)}</Descriptions.Item>
              <Descriptions.Item label="总资产">${formatUSDC(reductionPreview.beforeTotalAssets)} → ${formatUSDC(reductionPreview.afterTotalAssets)}</Descriptions.Item>
              <Descriptions.Item label="过期时间">{new Date(reductionPreview.expiresAt).toLocaleString('zh-CN')}</Descriptions.Item>
              {reductionPreview.confirmedAt && <Descriptions.Item label="确认记录">{reductionPreview.confirmedBy} · {new Date(reductionPreview.confirmedAt).toLocaleString('zh-CN')}</Descriptions.Item>}
              {reductionPreview.executionExternalTradeId && <Descriptions.Item label="执行幂等键">{reductionPreview.executionExternalTradeId}</Descriptions.Item>}
              {reductionPreview.executionRecordId && <Descriptions.Item label="Bridge 记录">#{reductionPreview.executionRecordId}</Descriptions.Item>}
              {reductionPreview.executionAttempt > 0 && <Descriptions.Item label="执行尝试">#{reductionPreview.executionAttempt}</Descriptions.Item>}
              {reductionPreview.executionError && <Descriptions.Item label="执行错误"><span style={{ color: '#cf1322' }}>{reductionPreview.executionError}</span></Descriptions.Item>}
            </Descriptions>
            <Table
              style={{ marginTop: 16 }}
              size="small"
              pagination={false}
              rowKey={row => `${row.dimension}:${row.key}`}
              dataSource={reductionPreview.impacts}
              columns={[
                { title: '维度', dataIndex: 'dimension' },
                { title: '归属', dataIndex: 'label' },
                { title: '价值前 → 后', render: (_, row) => `$${formatUSDC(row.beforeValue)} → $${formatUSDC(row.afterValue)}` },
                { title: '占比前 → 后', render: (_, row) => `${row.beforePercent ?? '—'}% → ${row.afterPercent ?? '—'}%` },
                { title: '计算质量', render: (_, row) => <Tag color={row.calculationQuality === 'EXACT' ? 'green' : 'orange'}>{row.calculationQuality}</Tag> }
              ]}
            />
            {reductionPreview.status === 'DRAFT' ? (
              <Button block type="primary" loading={reductionConfirming} style={{ marginTop: 16 }} onClick={confirmReductionDraft}>
                逐笔确认草案（不执行 SELL）
              </Button>
            ) : reductionPreview.status === 'SUBMITTED' || reductionPreview.status === 'EXECUTING' ? (
              <Button block loading={reductionLoading} style={{ marginTop: 16 }} onClick={refreshReductionDraft}>
                刷新 Bridge 执行终态
              </Button>
            ) : reductionPreview.executionEnabled ? (
              <Button block danger type="primary" loading={reductionExecuting} style={{ marginTop: 16 }} onClick={executeReductionDraft}>
                {reductionPreview.status === 'FAILED' ? '幂等重试真实 SELL' : '最终确认并执行真实 SELL'}
              </Button>
            ) : (
              <Button block disabled style={{ marginTop: 16 }}>
                草案状态：{reductionPreview.status}
              </Button>
            )}
          </>
        )}
      </Modal>

      {/* 赎回模态框 */}
      <Modal
        title="赎回仓位详情"
        open={redeemModalVisible}
        onCancel={() => {
          if (!redeeming) {
            setRedeemModalVisible(false)
          }
        }}
        onOk={handleRedeemSubmit}
        okText="确认赎回"
        cancelText="取消"
        width={isMobile ? '90%' : 800}
        destroyOnClose
        confirmLoading={redeeming}
        maskClosable={!redeeming}
      >
        {redeemableSummary && redeemableSummary.positions.length > 0 ? (
          <div>
            <Descriptions bordered column={1} size="small" style={{ marginBottom: '16px' }}>
              <Descriptions.Item label="可赎回仓位数量">
                <Tag color="green">{redeemableSummary.totalCount} 个</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="可赎回总价值">
                <span style={{ fontSize: '18px', fontWeight: 'bold', color: '#52c41a' }}>
                  ${formatUSDC(redeemableSummary.totalValue)}
                </span>
              </Descriptions.Item>
              <Descriptions.Item label="涉及账户">
                <Tag color="blue">
                  {new Set(redeemableSummary.positions.map(p => p.accountId)).size} 个账户
                </Tag>
              </Descriptions.Item>
            </Descriptions>

            <div style={{ marginTop: '16px' }}>
              <div style={{ marginBottom: '8px', fontWeight: '500' }}>赎回仓位列表：</div>
              <Table
                dataSource={redeemableSummary.positions}
                rowKey={(record, index) => `${record.marketId}-${record.outcomeIndex}-${index}`}
                pagination={false}
                size="small"
                scroll={{ y: 300 }}
                columns={[
                  {
                    title: '账户',
                    dataIndex: 'accountName',
                    key: 'account',
                    render: (text, record) => (
                      <span>
                        {text || `账户 ${record.accountId}`}
                      </span>
                    ),
                    width: 150
                  },
                  {
                    title: '市场',
                    dataIndex: 'marketTitle',
                    key: 'marketTitle',
                    render: (text, record) => text || record.marketId.substring(0, 10) + '...',
                    width: 200
                  },
                  {
                    title: '方向',
                    dataIndex: 'side',
                    key: 'side',
                    render: (side) => <Tag color={getSideColor(side)}>{side}</Tag>,
                    width: 80
                  },
                  {
                    title: '数量',
                    dataIndex: 'quantity',
                    key: 'quantity',
                    align: 'right' as const,
                    render: (value) => formatNumber(value, 4),
                    width: 120
                  },
                  {
                    title: '价值 ($)',
                    dataIndex: 'value',
                    key: 'value',
                    align: 'right' as const,
                    render: (value) => (
                      <span style={{ fontWeight: '500', color: '#52c41a' }}>
                        {formatNumber(value, 2)}
                      </span>
                    ),
                    width: 120
                  }
                ]}
              />
            </div>

            <div style={{
              marginTop: '16px',
              padding: '12px',
              background: '#f0f9ff',
              borderRadius: '8px',
              border: '1px solid #bae7ff'
            }}>
              <div style={{ color: '#666', fontSize: '12px', lineHeight: '1.8' }}>
                <div>💡 <strong>提示：</strong></div>
                <div>• 赎回将按 1:1 比例将获胜仓位换回 USDC</div>
                <div>• 同一市场的多个仓位将批量赎回，节省 Gas 费用</div>
                <div>• 赎回操作需要发送链上交易，请确保账户有足够的 POL 支付 Gas</div>
                <div>• 赎回成功后，仓位将从当前仓位列表中移除</div>
              </div>
            </div>
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: '40px' }}>
            <Empty description="没有可赎回的仓位" />
          </div>
        )}
      </Modal>
    </div>
  )
}

export default PositionList
