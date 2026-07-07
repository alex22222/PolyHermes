import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Col, Descriptions, Form, Modal, Row, Select, Space, Statistic, Table, Tag, Typography, message } from 'antd'
import { CheckCircleOutlined, ClockCircleOutlined, PauseCircleOutlined, PlayCircleOutlined, ReloadOutlined, SettingOutlined, WarningOutlined } from '@ant-design/icons'
import { apiService } from '../services/api'
import type {
  Account,
  BridgeAuditBucket,
  BridgeAuditReconciliationSuggestion,
  BridgeAuditResponse,
  BridgeRuntimeStatus,
  LeaderResearchCandidate,
  LeaderResearchFunnelCandidate,
  LeaderResearchPoliticsRecommendationExecutionSnapshot,
  LeaderResearchTrialReadiness,
  LoopGoal,
  LoopGoalAction,
  LoopGoalControlStatus,
  LoopGoalStatus
} from '../types'

const { Title, Text } = Typography

type OptimizationItem = {
  key: string
  area: string
  item: string
  impact: string
  status: string
}

const optimizationItems: OptimizationItem[] = [
  {
    key: 'monitor-status',
    area: 'Bridge audit',
    item: '固化 monitor_status',
    impact: '自动区分 clear/actionable/no_recent_records，减少人工解释 metrics 的时间。',
    status: '已完成'
  },
  {
    key: 'post-fix-window',
    area: 'Bridge audit',
    item: '支持 since_ms 修复后窗口',
    impact: '日报和 loop 可以只观察修复后新增 PENDING/FAILED，避免历史噪音反复进入队列。',
    status: '已完成'
  },
  {
    key: 'backend-proxy',
    area: 'PolyHermes 后端',
    item: '新增正式 audit 代理接口',
    impact: '前端不再直接依赖 8080 Bridge 端口，统一通过后端读取执行链路状态。',
    status: '已完成'
  },
  {
    key: 'statistics-card',
    area: '统计信息页',
    item: '展示执行链路监控卡片',
    impact: '人工打开 /statistics 即可看到可行动失败桶、Pending 超时和最近记录水位。',
    status: '已完成'
  },
  {
    key: 'daily-page',
    area: '优化日报',
    item: '新增优化点日报页面',
    impact: '把当前 Bridge 状态、24 小时窗口和最近优化点集中展示，便于持续 loop。',
    status: '本轮新增'
  },
  {
    key: 'runtime-status',
    area: 'Bridge status',
    item: '展示实际跟单账号',
    impact: '页面直接显示 Bridge 当前 account id 与配置数量，降低跟错账号或空配置继续执行的风险。',
    status: '本轮新增'
  },
  {
    key: 'reconciliation-suggestions',
    area: 'Bridge audit',
    item: '展示历史错配复盘建议',
    impact: '把 stale success mismatch 转成可人工确认的建议，减少历史账本噪音对 SELL 监控的干扰。',
    status: '本轮新增'
  }
]

const getStatusView = (status?: string) => {
  switch (status) {
    case 'clear':
      return { color: 'green', label: '正常', icon: <CheckCircleOutlined /> }
    case 'actionable':
      return { color: 'red', label: '需处理', icon: <WarningOutlined /> }
    case 'runtime_blocked':
      return { color: 'red', label: '执行受阻', icon: <WarningOutlined /> }
    case 'no_recent_records':
      return { color: 'orange', label: '暂无新记录', icon: <ClockCircleOutlined /> }
    default:
      return { color: 'default', label: status || '未知', icon: <ClockCircleOutlined /> }
  }
}

const formatTimestamp = (value?: number | null): string => {
  if (!value) return '-'
  return new Date(value).toLocaleString()
}

const formatTrialEta = (readiness: LeaderResearchTrialReadiness): string => {
  if (readiness.level === 'TRIAL_READY') return ''
  if (!readiness.hoursUntilTrialReady || readiness.hoursUntilTrialReady <= 0) return ''
  const eta = readiness.trialReadyAt ? formatTimestamp(readiness.trialReadyAt) : '-'
  return `还差 ${readiness.hoursUntilTrialReady}h / ${eta}`
}

const formatGoalStatus = (status?: LoopGoalStatus): { color: string; label: string } => {
  switch (status) {
    case 'ACTIVE':
      return { color: 'green', label: '运行中' }
    case 'PAUSED':
      return { color: 'orange', label: '已暂停' }
    case 'COMPLETED_PENDING_RESTART':
      return { color: 'blue', label: '已完成，保留待重启' }
    default:
      return { color: 'default', label: status || '-' }
  }
}

const formatBucketLabel = (bucket: BridgeAuditBucket): string => {
  const count = bucket.uncoveredCount ?? bucket.count ?? 0
  return `${bucket.bucket || 'unknown'}: ${count}`
}

const formatSuggestionStatus = (status?: string): string => {
  const labels: Record<string, string> = {
    accepted_stale: '建议标记历史错配',
    manual_closed: '人工平仓',
    externally_closed: '外部平仓',
    wrong_market_known: '已知市场错配'
  }
  return status ? labels[status] || status : '-'
}

const formatConfidence = (confidence?: string): { color: string; label: string } => {
  switch (confidence) {
    case 'high':
      return { color: 'green', label: '高' }
    case 'medium':
      return { color: 'orange', label: '中' }
    case 'low':
      return { color: 'default', label: '低' }
    default:
      return { color: 'default', label: confidence || '-' }
  }
}

const runtimeBlockReasonLabels: Record<string, string> = {
  executor_not_ready: '执行器未就绪',
  not_logged_in: 'Bridge 未登录',
  copy_trading_account_missing: '跟单账号缺失',
  copy_trading_config_empty: '有效配置为 0',
  last_error_present: '存在最近错误'
}

const formatRuntimeBlockReason = (reason: string): string =>
  runtimeBlockReasonLabels[reason] || reason

const recommendationActionColor = (action: string): string => {
  if (action === 'IMPORT_NOW') return 'green'
  if (action === 'SCORE_REFRESH') return 'gold'
  if (action === 'PAPER_PROCESS') return 'blue'
  if (action === 'FAST_WATCH_REVIEW') return 'purple'
  return 'default'
}

const aggregateRecommendationCounts = (snapshots: LeaderResearchPoliticsRecommendationExecutionSnapshot[]): Record<string, number> =>
  snapshots.reduce<Record<string, number>>((acc, snapshot) => {
    Object.entries(snapshot.recommendationCounts || {}).forEach(([key, value]) => {
      acc[key] = (acc[key] || 0) + (value || 0)
    })
    return acc
  }, {})

const primaryRecommendationHealth = (snapshots: LeaderResearchPoliticsRecommendationExecutionSnapshot[]): { color: string; label: string; message: string } => {
  if (snapshots.length === 0) {
    return { color: 'orange', label: '暂无快照', message: '等待 politics / finance 推荐闭环 dry-run 产出快照。' }
  }
  const failed = snapshots.find((snapshot) => snapshot.status !== 'SUCCESS')
  if (failed) {
    return { color: 'red', label: '执行失败', message: `${failed.category} 最近一次推荐闭环失败：${failed.errorMessage || '未返回错误详情'}` }
  }
  const counts = aggregateRecommendationCounts(snapshots)
  const paperProcess = counts.PAPER_PROCESS || 0
  const fastWatchReview = counts.FAST_WATCH_REVIEW || 0
  if (paperProcess === 0 && fastWatchReview === 0) {
    return { color: 'orange', label: '样本偏薄', message: '最近一轮 politics / finance 都没有可推进 PAPER 或可复核 FAST_WATCH，主策略高质量样本仍不足。' }
  }
  if (fastWatchReview > 0) {
    return { color: 'green', label: '可复核', message: `主策略发现 ${fastWatchReview} 个 FAST_WATCH_REVIEW 候选，可进入人工复核。` }
  }
  return { color: 'blue', label: '可推进', message: `主策略发现 ${paperProcess} 个 PAPER_PROCESS 候选，可继续加厚纸跟样本。` }
}

const isThinRecommendationSnapshot = (snapshot: LeaderResearchPoliticsRecommendationExecutionSnapshot): boolean =>
  snapshot.status === 'SUCCESS' &&
  (snapshot.recommendationCounts.PAPER_PROCESS || 0) === 0 &&
  (snapshot.recommendationCounts.FAST_WATCH_REVIEW || 0) === 0

const consecutiveThinRounds = (snapshots: LeaderResearchPoliticsRecommendationExecutionSnapshot[]): number => {
  let count = 0
  for (const snapshot of snapshots) {
    if (!isThinRecommendationSnapshot(snapshot)) break
    count += 1
  }
  return count
}

const consecutiveThinRoundsForCategory = (
  snapshots: LeaderResearchPoliticsRecommendationExecutionSnapshot[],
  category: string
): number => consecutiveThinRounds(snapshots.filter((snapshot) => snapshot.category === category))

const primaryCategories = ['politics', 'finance']

const primaryCategoryLabel = (category: string): string => {
  if (category === 'politics') return '政治'
  if (category === 'finance') return '金融'
  return category
}

const categorySnapshotStatus = (snapshot?: LeaderResearchPoliticsRecommendationExecutionSnapshot): { color: string; label: string; message: string } => {
  if (!snapshot) {
    return { color: 'orange', label: '暂无快照', message: '等待 dry-run 证据。' }
  }
  if (snapshot.status !== 'SUCCESS') {
    return { color: 'red', label: '失败', message: snapshot.errorMessage || '最近 dry-run 失败。' }
  }
  const paperProcess = snapshot.recommendationCounts.PAPER_PROCESS || 0
  const fastWatchReview = snapshot.recommendationCounts.FAST_WATCH_REVIEW || 0
  const importNow = snapshot.recommendationCounts.IMPORT_NOW || 0
  const scoreRefresh = snapshot.recommendationCounts.SCORE_REFRESH || 0
  if (fastWatchReview > 0) {
    return { color: 'green', label: '可复核', message: `${fastWatchReview} 个 FAST_WATCH_REVIEW。` }
  }
  if (paperProcess > 0) {
    return { color: 'blue', label: '可加厚', message: `${paperProcess} 个 PAPER_PROCESS。` }
  }
  if (importNow > 0 || scoreRefresh > 0) {
    return { color: 'gold', label: '待推进', message: `${importNow} 个待导入，${scoreRefresh} 个待刷新。` }
  }
  return { color: 'orange', label: '样本偏薄', message: '暂无可推进或可复核候选。' }
}

const shortWallet = (wallet: string): string => {
  if (!wallet || wallet.length <= 12) return wallet
  return `${wallet.slice(0, 6)}...${wallet.slice(-4)}`
}

const usdc = (value?: string) => value ? `${value} USDC` : '-'

const approvalPreview = (candidate?: LeaderResearchCandidate | null) => ({
  fixedAmount: usdc(candidate?.suggestedFixedAmount),
  maxDailyLoss: usdc(candidate?.suggestedMaxDailyLoss),
  maxDailyOrders: candidate?.suggestedMaxDailyOrders ?? '-',
  priceRange: candidate?.suggestedMinPrice || candidate?.suggestedMaxPrice
    ? `${candidate?.suggestedMinPrice ?? '-'} - ${candidate?.suggestedMaxPrice ?? '-'}`
    : '-',
  maxPositionValue: usdc(candidate?.suggestedMaxPositionValue)
})

const reviewDecision = (candidate: LeaderResearchFunnelCandidate): { color: string; label: string; message: string } => {
  const blockers = candidate.trialReadiness.blockers || []
  const fastWatchBlockers = candidate.trialReadiness.fastWatchBlockers || []
  const blockerText = [...blockers, ...fastWatchBlockers].join('；')
  const filteredRatio = Number(candidate.filteredRatio) || 0
  if (candidate.trialReadiness.level === 'TRIAL_READY') {
    return { color: 'green', label: '可试跟复核', message: '已满足试跟门槛，可人工创建禁用试跟配置。' }
  }
  if (blockerText.includes('观察不足')) {
    return { color: 'blue', label: '等观察期', message: blockers.find((item) => item.includes('观察不足')) || '继续等待 PAPER 观察期。' }
  }
  if (filteredRatio >= 0.2 || blockerText.includes('过滤率')) {
    return { color: 'orange', label: '复核过滤率', message: fastWatchBlockers.find((item) => item.includes('过滤率')) || '过滤率偏高，先检查 leader 交易是否常被风控跳过。' }
  }
  if (blockerText.includes('评分')) {
    return { color: 'gold', label: '等评分稳定', message: blockers.find((item) => item.includes('评分')) || fastWatchBlockers.find((item) => item.includes('评分')) || '继续观察评分稳定性。' }
  }
  return { color: 'purple', label: '人工复核', message: blockerText || '进入人工复核，检查市场类型、交易质量和可复制性。' }
}

const fetchRuntimeStatus = async (): Promise<BridgeRuntimeStatus | null> => {
  try {
    const response = await apiService.bridgeTradeRecords.status()
    if (response.data.code === 0 && response.data.data) {
      return response.data.data
    }
  } catch (error) {
    // Dev fallback below keeps the page useful before backend restart.
  }

  const response = await fetch('/bridge-runtime/status')
  if (!response.ok) return null
  const runtime = await response.json()
  return {
    ready: runtime.ready,
    loggedIn: runtime.logged_in,
    lastError: runtime.last_error,
    copyTradingAccountId: runtime.copy_trading_account_id,
    copyTradingConfigCount: runtime.copy_trading_config_count
  }
}

const OptimizationDaily: React.FC = () => {
  const [audit, setAudit] = useState<BridgeAuditResponse | null>(null)
  const [dailyAudit, setDailyAudit] = useState<BridgeAuditResponse | null>(null)
  const [runtimeStatus, setRuntimeStatus] = useState<BridgeRuntimeStatus | null>(null)
  const [goalControl, setGoalControl] = useState<LoopGoalControlStatus | null>(null)
  const [recommendationSnapshot, setRecommendationSnapshot] = useState<LeaderResearchPoliticsRecommendationExecutionSnapshot | null>(null)
  const [latestRecommendationSnapshots, setLatestRecommendationSnapshots] = useState<LeaderResearchPoliticsRecommendationExecutionSnapshot[]>([])
  const [recommendationSnapshots, setRecommendationSnapshots] = useState<LeaderResearchPoliticsRecommendationExecutionSnapshot[]>([])
  const [loading, setLoading] = useState(false)
  const [confirmingKey, setConfirmingKey] = useState<string | null>(null)
  const [goalModalOpen, setGoalModalOpen] = useState(false)
  const [updatingGoalKey, setUpdatingGoalKey] = useState<string | null>(null)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [approvalCandidate, setApprovalCandidate] = useState<LeaderResearchCandidate | null>(null)
  const [approvalLoading, setApprovalLoading] = useState(false)
  const [approvalForm] = Form.useForm()

  const fetchData = async () => {
    setLoading(true)
    try {
      const sinceMs = Date.now() - 24 * 60 * 60 * 1000
      const [defaultAudit, recentAudit, latestRecommendation, recentRecommendations, accountResp] = await Promise.allSettled([
        apiService.bridgeTradeRecords.audit({ limit: 500, failureLimit: 100, portfolioTimeout: 90 }),
        apiService.bridgeTradeRecords.audit({ sinceMs, limit: 500, failureLimit: 100, portfolioTimeout: 90 }),
        apiService.leaderResearch.latestPrimaryRecommendationExecutions(),
        apiService.leaderResearch.recentPrimaryRecommendationExecutions(),
        apiService.accounts.list()
      ])

      let nextRuntimeStatus: BridgeRuntimeStatus | null = null
      if (defaultAudit.status === 'fulfilled' && defaultAudit.value.data.code === 0) {
        const data = defaultAudit.value.data.data || null
        setAudit(data)
        nextRuntimeStatus = data?.runtimeStatus || null
      } else {
        setAudit(null)
      }

      if (recentAudit.status === 'fulfilled' && recentAudit.value.data.code === 0) {
        setDailyAudit(recentAudit.value.data.data || null)
      } else {
        setDailyAudit(null)
      }

      if (latestRecommendation.status === 'fulfilled' && latestRecommendation.value.data.code === 0) {
        const latestItems = latestRecommendation.value.data.data || []
        setLatestRecommendationSnapshots(latestItems)
        setRecommendationSnapshot(latestItems[0] || null)
      } else {
        setLatestRecommendationSnapshots([])
        setRecommendationSnapshot(null)
      }

      if (recentRecommendations.status === 'fulfilled' && recentRecommendations.value.data.code === 0) {
        const recentItems = recentRecommendations.value.data.data || []
        setRecommendationSnapshots(recentItems)
        if (latestRecommendation.status !== 'fulfilled' && recentItems.length > 0) {
          setRecommendationSnapshot(recentItems[0])
        }
      } else {
        setRecommendationSnapshots([])
      }

      if (accountResp.status === 'fulfilled' && accountResp.value.data.code === 0 && accountResp.value.data.data) {
        setAccounts(accountResp.value.data.data.list || [])
      }

      setRuntimeStatus(nextRuntimeStatus || await fetchRuntimeStatus())

      const goalResponse = await apiService.loopGoals.status()
      if (goalResponse.data.code === 0 && goalResponse.data.data) {
        setGoalControl(goalResponse.data.data)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [])

  const openApprovalByCandidateId = async (candidateId: number) => {
    setApprovalLoading(true)
    try {
      const response = await apiService.leaderResearch.detail({ candidateId })
      if (response.data.code !== 0 || !response.data.data) {
        message.error(response.data.msg || '获取研究候选详情失败')
        return
      }
      const candidate = response.data.data.candidate
      if (candidate.researchState !== 'TRIAL_READY') {
        message.warning('候选尚未进入 TRIAL_READY，暂不能创建禁用试跟配置')
        return
      }
      setApprovalCandidate(candidate)
      approvalForm.setFieldsValue({ accountId: accounts[0]?.id })
    } catch (error: any) {
      message.error(error.message || '获取研究候选详情失败')
    } finally {
      setApprovalLoading(false)
    }
  }

  const submitApproval = async () => {
    if (!approvalCandidate) return
    const values = await approvalForm.validateFields()
    setApprovalLoading(true)
    try {
      const response = await apiService.leaderResearch.createDisabledTrialConfig({
        candidateId: approvalCandidate.id,
        accountId: values.accountId,
        confirm: true
      })
      if (response.data.code === 0) {
        message.success('已创建禁用试跟配置，需要手动启用后才会真钱跟单')
        setApprovalCandidate(null)
        await fetchData()
      } else {
        message.error(response.data.msg || '创建禁用试跟配置失败')
      }
    } catch (error: any) {
      message.error(error.message || '创建禁用试跟配置失败')
    } finally {
      setApprovalLoading(false)
    }
  }

  const handleConfirmSuggestion = (record: BridgeAuditReconciliationSuggestion) => {
    const payload = record.annotationPayload
    const marketId = payload?.marketId || record.marketId
    const outcome = payload?.outcome || record.outcome
    if (!marketId || !outcome) {
      message.error('建议缺少 marketId 或 outcome，无法确认')
      return
    }

    Modal.confirm({
      title: '确认历史错配建议',
      content: (
        <Space direction="vertical" size={4}>
          <Text>该操作会把这条 stale mismatch 标记为已接受的历史错配。</Text>
          <Text type="secondary">{record.marketTitle || marketId}</Text>
          <Text type="secondary">账本/实仓: {record.expectedQuantity || '0'} / {record.actualQuantity || '0'}</Text>
        </Space>
      ),
      okText: '确认',
      cancelText: '取消',
      onOk: async () => {
        const key = record.key || `${marketId}-${outcome}-${record.latestRecordId}`
        setConfirmingKey(key)
        try {
          const response = await apiService.bridgeTradeRecords.upsertAuditReconciliation({
            status: payload?.status || record.status || 'accepted_stale',
            note: payload?.note || 'Accepted from optimization daily reconciliation suggestion.',
            actor: 'operator',
            marketId,
            marketTitle: payload?.marketTitle || record.marketTitle,
            outcome,
            outcomeIndex: payload?.outcomeIndex ?? record.outcomeIndex
          })
          if (response.data.code === 0) {
            message.success('已确认历史错配')
            await fetchData()
          } else {
            message.error(response.data.msg || '确认失败')
          }
        } finally {
          setConfirmingKey(null)
        }
      }
    })
  }

  const handleGoalAction = async (goal: LoopGoal, action: LoopGoalAction) => {
    setUpdatingGoalKey(`${goal.goalKey}:${action}`)
    try {
      const response = await apiService.loopGoals.update({ goalKey: goal.goalKey, action })
      if (response.data.code === 0 && response.data.data) {
        setGoalControl(response.data.data)
        message.success(action === 'START' ? '目标已启动' : action === 'PAUSE' ? '目标已暂停' : '目标已完成并保留')
      } else {
        message.error(response.data.msg || '目标状态更新失败')
      }
    } finally {
      setUpdatingGoalKey(null)
    }
  }

  const monitor = audit?.monitorStatus
  const dailyMonitor = dailyAudit?.monitorStatus
  const statusView = getStatusView(monitor?.status)
  const dailyStatusView = getStatusView(dailyMonitor?.status)
  const runtimeReady = Boolean(runtimeStatus?.ready && runtimeStatus?.loggedIn)
  const nextBuckets = monitor?.nextActionBuckets || audit?.nextActionCandidates || []
  const dailyBuckets = dailyMonitor?.nextActionBuckets || dailyAudit?.nextActionCandidates || []
  const runtimeBlockReasons = monitor?.runtimeBlockReasons || []
  const reconciliationSuggestions = (
    dailyAudit?.reconciliationSuggestions?.length
      ? dailyAudit.reconciliationSuggestions
      : audit?.reconciliationSuggestions || []
  )
  const sortedGoals = [...(goalControl?.goals || [])].sort((a, b) => a.priority - b.priority)
  const activeGoal = sortedGoals.find((goal) => goal.status === 'ACTIVE')
  const primaryRecommendationSnapshots = latestRecommendationSnapshots.length > 0
    ? latestRecommendationSnapshots
    : (recommendationSnapshot ? [recommendationSnapshot] : [])
  const recommendationStatus = primaryRecommendationHealth(primaryRecommendationSnapshots)
  const recommendationCounts = aggregateRecommendationCounts(primaryRecommendationSnapshots)
  const plannedRecommendationActions = primaryRecommendationSnapshots.flatMap((snapshot) =>
    snapshot.plannedActions.map((action) => ({ ...action, category: snapshot.category }))
  )
  const fastWatchReviewCandidateIds = plannedRecommendationActions
    .filter((action) => action.action === 'FAST_WATCH_REVIEW')
    .flatMap((action) => action.candidateIds || [])
  const importNowWallets = plannedRecommendationActions
    .filter((action) => action.action === 'IMPORT_NOW')
    .flatMap((action) => action.wallets || [])
  const reviewCandidates = primaryRecommendationSnapshots.flatMap((snapshot) => snapshot.reviewCandidates || [])
  const latestRecommendationStartedAt = primaryRecommendationSnapshots.reduce<number | undefined>((latest, snapshot) => {
    if (!latest || snapshot.startedAt > latest) return snapshot.startedAt
    return latest
  }, undefined)
  const latestRecommendationDurationMs = primaryRecommendationSnapshots.reduce((sum, snapshot) => sum + (snapshot.durationMs || 0), 0)
  const recommendationMode = primaryRecommendationSnapshots.length > 0 && primaryRecommendationSnapshots.every((snapshot) => snapshot.dryRun) ? 'dry-run' : (primaryRecommendationSnapshots.length > 0 ? 'mixed/live' : '-')
  const activeApprovalPreview = approvalPreview(approvalCandidate)
  const thinRounds = consecutiveThinRounds(recommendationSnapshots)
  const latestSnapshotsByCategory = primaryRecommendationSnapshots.reduce<Record<string, LeaderResearchPoliticsRecommendationExecutionSnapshot>>((acc, snapshot) => {
    acc[snapshot.category] = snapshot
    return acc
  }, {})
  const thinRoundsByCategory = primaryCategories.reduce<Record<string, number>>((acc, category) => {
    acc[category] = consecutiveThinRoundsForCategory(recommendationSnapshots, category)
    return acc
  }, {})

  const columns = useMemo(() => [
    {
      title: '模块',
      dataIndex: 'area',
      key: 'area',
      width: 160
    },
    {
      title: '优化点',
      dataIndex: 'item',
      key: 'item',
      width: 220
    },
    {
      title: '收益',
      dataIndex: 'impact',
      key: 'impact'
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (value: string) => <Tag color={value === '本轮新增' ? 'blue' : 'green'}>{value}</Tag>
    }
  ], [])

  const suggestionColumns = useMemo(() => [
    {
      title: '置信度',
      dataIndex: 'confidence',
      key: 'confidence',
      width: 90,
      render: (value: string | undefined) => {
        const view = formatConfidence(value)
        return <Tag color={view.color}>{view.label}</Tag>
      }
    },
    {
      title: '市场',
      dataIndex: 'marketTitle',
      key: 'marketTitle',
      ellipsis: true,
      render: (value: string | undefined, record: BridgeAuditReconciliationSuggestion) => (
        <Space direction="vertical" size={0}>
          <Text>{value || record.marketId || '-'}</Text>
          <Text type="secondary">#{record.latestRecordId || '-'} / {record.outcome || '-'}</Text>
        </Space>
      )
    },
    {
      title: '账本/实仓',
      key: 'quantity',
      width: 140,
      render: (_: unknown, record: BridgeAuditReconciliationSuggestion) => (
        <Text>{record.expectedQuantity || '0'} / {record.actualQuantity || '0'}</Text>
      )
    },
    {
      title: '建议',
      key: 'status',
      width: 160,
      render: (_: unknown, record: BridgeAuditReconciliationSuggestion) => (
        <Tag color="blue">{formatSuggestionStatus(record.annotationPayload?.status || record.status)}</Tag>
      )
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_: unknown, record: BridgeAuditReconciliationSuggestion) => {
        const key = record.key || `${record.marketId}-${record.outcome}-${record.latestRecordId}`
        return (
          <Button
            size="small"
            onClick={() => handleConfirmSuggestion(record)}
            loading={confirmingKey === key}
          >
            确认
          </Button>
        )
      }
    }
  ], [confirmingKey])

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <Title level={2} style={{ margin: 0 }}>优化点日报</Title>
        <Space>
          <Button icon={<SettingOutlined />} onClick={() => setGoalModalOpen(true)}>
            目标控制
          </Button>
          <Button type="primary" icon={<ReloadOutlined />} onClick={fetchData} loading={loading}>
            刷新
          </Button>
        </Space>
      </div>

      <Card
        title="Loop 当前目标"
        extra={activeGoal ? <Tag color="green">主目标</Tag> : <Tag color="orange">未启动</Tag>}
        style={{ marginBottom: 16 }}
      >
        <Row gutter={[16, 16]}>
          <Col xs={24} md={14}>
            <Space direction="vertical" size={2}>
              <Text strong>{activeGoal?.title || '暂无运行中目标'}</Text>
              <Text type="secondary">{activeGoal?.summary || '可在目标控制中启动第二目标或恢复第一目标。'}</Text>
            </Space>
          </Col>
          <Col xs={12} md={5}>
            <Statistic title="第二目标" value={formatGoalStatus(sortedGoals.find((goal) => goal.goalKey === 'leader-discovery-goal-2')?.status).label} loading={loading && !goalControl} />
          </Col>
          <Col xs={12} md={5}>
            <Statistic title="第一目标" value={formatGoalStatus(sortedGoals.find((goal) => goal.goalKey === 'bridge-reliability-goal-1')?.status).label} loading={loading && !goalControl} />
          </Col>
        </Row>
      </Card>

      <Card
        title="第二目标推荐闭环"
        extra={<Tag color={recommendationStatus.color}>{recommendationStatus.label}</Tag>}
        style={{ marginBottom: 16 }}
      >
        <Row gutter={[16, 16]}>
          <Col xs={12} md={4}>
            <Statistic title="IMPORT_NOW" value={recommendationCounts.IMPORT_NOW || 0} loading={loading && !recommendationSnapshot} />
          </Col>
          <Col xs={12} md={4}>
            <Statistic title="SCORE_REFRESH" value={recommendationCounts.SCORE_REFRESH || 0} loading={loading && !recommendationSnapshot} />
          </Col>
          <Col xs={12} md={4}>
            <Statistic title="PAPER_PROCESS" value={recommendationCounts.PAPER_PROCESS || 0} loading={loading && !recommendationSnapshot} />
          </Col>
          <Col xs={12} md={4}>
            <Statistic title="FAST_WATCH_REVIEW" value={recommendationCounts.FAST_WATCH_REVIEW || 0} loading={loading && !recommendationSnapshot} />
          </Col>
          <Col xs={12} md={4}>
            <Statistic title="模式" value={recommendationMode} loading={loading && primaryRecommendationSnapshots.length === 0} />
          </Col>
          <Col xs={12} md={4}>
            <Statistic title="耗时合计" value={latestRecommendationDurationMs || '-'} suffix={latestRecommendationDurationMs ? 'ms' : undefined} loading={loading && primaryRecommendationSnapshots.length === 0} />
          </Col>
        </Row>
        <Space direction="vertical" size={8} style={{ width: '100%', marginTop: 12 }}>
          <Text type="secondary">最近运行: {formatTimestamp(latestRecommendationStartedAt)}</Text>
          <Text type={thinRounds >= 3 ? 'warning' : 'secondary'}>连续薄样本轮次: {thinRounds}</Text>
          <Text>{recommendationStatus.message}</Text>
          <Row gutter={[12, 12]}>
            {primaryCategories.map((category) => {
              const snapshot = latestSnapshotsByCategory[category]
              const status = categorySnapshotStatus(snapshot)
              const categoryThinRounds = thinRoundsByCategory[category] || 0
              return (
                <Col key={category} xs={24} md={12}>
                  <div style={{ border: '1px solid #f0f0f0', borderRadius: 6, padding: 12 }}>
                    <Space direction="vertical" size={4} style={{ width: '100%' }}>
                      <Space size={[8, 8]} wrap>
                        <Text strong>{primaryCategoryLabel(category)}</Text>
                        <Tag color={status.color}>{status.label}</Tag>
                        <Tag color={categoryThinRounds >= 3 ? 'orange' : 'blue'}>薄样本 {categoryThinRounds}</Tag>
                      </Space>
                      <Text type="secondary">{status.message}</Text>
                      <Space size={[8, 8]} wrap>
                        <Tag>IMPORT {snapshot?.recommendationCounts.IMPORT_NOW || 0}</Tag>
                        <Tag>SCORE {snapshot?.recommendationCounts.SCORE_REFRESH || 0}</Tag>
                        <Tag>PAPER {snapshot?.recommendationCounts.PAPER_PROCESS || 0}</Tag>
                        <Tag>REVIEW {snapshot?.recommendationCounts.FAST_WATCH_REVIEW || 0}</Tag>
                      </Space>
                      <Text type="secondary">
                        最近快照: {snapshot ? `#${snapshot.id} ${formatTimestamp(snapshot.startedAt)}` : '-'}
                      </Text>
                    </Space>
                  </div>
                </Col>
              )
            })}
          </Row>
          {primaryRecommendationSnapshots.length > 0 && (
            <Space size={[8, 8]} wrap>
              {primaryRecommendationSnapshots.map((snapshot) => (
                <Tag key={`${snapshot.category}-${snapshot.id}`} color={isThinRecommendationSnapshot(snapshot) ? 'orange' : 'green'}>
                  {snapshot.category} #{snapshot.id} · P{snapshot.recommendationCounts.PAPER_PROCESS || 0}/R{snapshot.recommendationCounts.FAST_WATCH_REVIEW || 0}
                </Tag>
              ))}
            </Space>
          )}
          {plannedRecommendationActions.length > 0 && (
            <Space size={[8, 8]} wrap>
              {plannedRecommendationActions.map((action) => (
                <Tag key={`${action.category}-${action.action}`} color={recommendationActionColor(action.action)}>
                  {action.category}.{action.action}: {action.selectedCount}{action.skippedReason ? ` / ${action.skippedReason}` : ''}
                </Tag>
              ))}
            </Space>
          )}
          {(fastWatchReviewCandidateIds.length > 0 || importNowWallets.length > 0) && (
            <Space direction="vertical" size={4}>
              {fastWatchReviewCandidateIds.length > 0 && (
                <Space size={[8, 8]} wrap>
                  <Text type="secondary">复核候选</Text>
                  {fastWatchReviewCandidateIds.slice(0, 8).map((candidateId, index) => (
                    <Tag key={`${candidateId}-${index}`} color="purple">#{candidateId}</Tag>
                  ))}
                </Space>
              )}
              {importNowWallets.length > 0 && (
                <Space size={[8, 8]} wrap>
                  <Text type="secondary">待导入钱包</Text>
                  {importNowWallets.slice(0, 5).map((wallet) => (
                    <Tag key={wallet} color="green">{shortWallet(wallet)}</Tag>
                  ))}
                </Space>
              )}
            </Space>
          )}
          {reviewCandidates.length > 0 && (
            <Space direction="vertical" size={6} style={{ width: '100%' }}>
              <Text type="secondary">复核候选质量</Text>
              {reviewCandidates.slice(0, 5).map((candidate) => {
                const decision = reviewDecision(candidate)
                return (
                  <Space key={candidate.candidateId} direction="vertical" size={2} style={{ width: '100%' }}>
                    <Space size={[8, 8]} wrap>
                      <Tag color={candidate.trialReadiness.level === 'TRIAL_READY' ? 'green' : 'purple'}>
                        #{candidate.candidateId} {candidate.trialReadiness.label}
                      </Tag>
                      <Tag color={decision.color}>{decision.label}</Tag>
                      <Tag>{candidate.category}</Tag>
                      <Tag>分数 {candidate.score}</Tag>
                      <Tag>交易 {candidate.tradeCount}</Tag>
                      <Tag color={(Number(candidate.copyablePnl) || 0) > 0 ? 'green' : 'orange'}>PnL {candidate.copyablePnl}</Tag>
                      <Tag color={(Number(candidate.filteredRatio) || 0) >= 0.2 ? 'orange' : 'blue'}>过滤 {candidate.filteredRatio}</Tag>
                      <Tag>观察 {candidate.trialReadiness.ageHours}h</Tag>
                      {formatTrialEta(candidate.trialReadiness) && (
                        <Tag color="blue">{formatTrialEta(candidate.trialReadiness)}</Tag>
                      )}
                      <Text type="secondary">{shortWallet(candidate.wallet)}</Text>
                      <Button
                        size="small"
                        type={candidate.trialReadiness.level === 'TRIAL_READY' ? 'primary' : 'default'}
                        disabled={candidate.trialReadiness.level !== 'TRIAL_READY'}
                        loading={approvalLoading && approvalCandidate?.id !== candidate.candidateId}
                        onClick={() => openApprovalByCandidateId(candidate.candidateId)}
                      >
                        {candidate.trialReadiness.level === 'TRIAL_READY' ? '创建禁用试跟' : '等待TRIAL_READY'}
                      </Button>
                    </Space>
                    <Text type="secondary">{decision.message}</Text>
                  </Space>
                )
              })}
            </Space>
          )}
          {recommendationSnapshots.length > 0 && (
            <Space size={[8, 8]} wrap>
              {recommendationSnapshots.slice(0, 5).map((snapshot) => (
                <Tag key={snapshot.id} color={isThinRecommendationSnapshot(snapshot) ? 'orange' : 'green'}>
                  {snapshot.category} #{snapshot.id} {formatTimestamp(snapshot.startedAt)} · P{snapshot.recommendationCounts.PAPER_PROCESS || 0}/R{snapshot.recommendationCounts.FAST_WATCH_REVIEW || 0}
                </Tag>
              ))}
            </Space>
          )}
        </Space>
      </Card>

      <Alert
        type={monitor?.status === 'actionable' ? 'error' : 'success'}
        showIcon
        message={`Bridge 执行链路：${statusView.label}`}
        description={monitor?.message || 'Bridge audit 暂无返回'}
        style={{ marginBottom: 16 }}
      />

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24}>
          <Card title="Bridge 运行状态" extra={<Tag color={runtimeReady ? 'green' : 'red'}>{runtimeReady ? '在线' : '异常'}</Tag>}>
            <Row gutter={[16, 16]}>
              <Col xs={12} md={6}>
                <Statistic title="执行器 Ready" value={runtimeStatus?.ready ? '是' : '否'} loading={loading && !runtimeStatus} />
              </Col>
              <Col xs={12} md={6}>
                <Statistic title="登录状态" value={runtimeStatus?.loggedIn ? '已登录' : '未登录'} loading={loading && !runtimeStatus} />
              </Col>
              <Col xs={12} md={6}>
                <Statistic title="跟单账号 ID" value={runtimeStatus?.copyTradingAccountId ?? '-'} loading={loading && !runtimeStatus} />
              </Col>
              <Col xs={12} md={6}>
                <Statistic title="有效配置数" value={runtimeStatus?.copyTradingConfigCount ?? 0} loading={loading && !runtimeStatus} />
              </Col>
            </Row>
            {runtimeStatus?.lastError && (
              <div style={{ marginTop: 12 }}>
                <Text type="danger">最近错误: {runtimeStatus.lastError}</Text>
              </div>
            )}
            {runtimeBlockReasons.length > 0 && (
              <Space size={[8, 8]} wrap style={{ marginTop: 12 }}>
                {runtimeBlockReasons.map((reason) => (
                  <Tag key={reason} color="red">{formatRuntimeBlockReason(reason)}</Tag>
                ))}
              </Space>
            )}
          </Card>
        </Col>

        <Col xs={24} md={12}>
          <Card title="当前审计窗口" extra={<Tag icon={statusView.icon} color={statusView.color}>{statusView.label}</Tag>}>
            <Row gutter={[16, 16]}>
              <Col xs={12}>
                <Statistic title="可处理失败桶" value={monitor?.actionableFailureBucketCount || 0} loading={loading && !audit} />
              </Col>
              <Col xs={12}>
                <Statistic title="Pending 超时" value={monitor?.pendingTimeoutCount || 0} loading={loading && !audit} />
              </Col>
              <Col xs={12}>
                <Statistic title="最近失败数" value={monitor?.recentFailureCount || audit?.metrics?.recentFailureCount || 0} loading={loading && !audit} />
              </Col>
              <Col xs={12}>
                <Statistic title="持仓快照" value={audit?.metrics?.portfolioPositionCount || 0} loading={loading && !audit} />
              </Col>
            </Row>
            <div style={{ marginTop: 12 }}>
              <Text type="secondary">最近记录: {formatTimestamp(monitor?.latestRecordTimeMs || audit?.metrics?.latestRecordTimeMs)}</Text>
            </div>
          </Card>
        </Col>

        <Col xs={24} md={12}>
          <Card title="最近 24 小时" extra={<Tag icon={dailyStatusView.icon} color={dailyStatusView.color}>{dailyStatusView.label}</Tag>}>
            <Row gutter={[16, 16]}>
              <Col xs={12}>
                <Statistic title="窗口记录数" value={dailyAudit?.metrics?.recordsChecked || 0} loading={loading && !dailyAudit} />
              </Col>
              <Col xs={12}>
                <Statistic title="可处理失败桶" value={dailyMonitor?.actionableFailureBucketCount || 0} loading={loading && !dailyAudit} />
              </Col>
              <Col xs={12}>
                <Statistic title="最近失败数" value={dailyMonitor?.recentFailureCount || dailyAudit?.metrics?.recentFailureCount || 0} loading={loading && !dailyAudit} />
              </Col>
              <Col xs={12}>
                <Statistic title="Pending 超时" value={dailyMonitor?.pendingTimeoutCount || 0} loading={loading && !dailyAudit} />
              </Col>
            </Row>
            <div style={{ marginTop: 12 }}>
              <Text type="secondary">最近失败: {formatTimestamp(dailyMonitor?.latestFailureTimeMs || dailyAudit?.metrics?.latestFailureTimeMs)}</Text>
            </div>
          </Card>
        </Col>
      </Row>

      {(nextBuckets.length > 0 || dailyBuckets.length > 0) && (
        <Card title="下一步处理桶" style={{ marginBottom: 16 }}>
          <Space size={[8, 8]} wrap>
            {[...dailyBuckets, ...nextBuckets].slice(0, 8).map((bucket) => (
              <Tag key={`${bucket.bucket}-${bucket.priority}-${bucket.latestCreatedAt}`} color="red">
                {formatBucketLabel(bucket)}
              </Tag>
            ))}
          </Space>
        </Card>
      )}

      <Card
        title="历史错配复盘建议"
        extra={<Tag color={reconciliationSuggestions.length > 0 ? 'orange' : 'green'}>{reconciliationSuggestions.length}</Tag>}
        style={{ marginBottom: 16 }}
      >
        <Row gutter={[16, 16]} style={{ marginBottom: 12 }}>
          <Col xs={12} md={6}>
            <Statistic title="历史错配" value={dailyAudit?.metrics?.staleSuccessPositionMismatchCount ?? audit?.metrics?.staleSuccessPositionMismatchCount ?? 0} loading={loading && !dailyAudit && !audit} />
          </Col>
          <Col xs={12} md={6}>
            <Statistic title="当前错配" value={dailyAudit?.metrics?.activeSuccessPositionMismatchCount ?? audit?.metrics?.activeSuccessPositionMismatchCount ?? 0} loading={loading && !dailyAudit && !audit} />
          </Col>
          <Col xs={12} md={6}>
            <Statistic title="复盘建议" value={dailyAudit?.metrics?.reconciliationSuggestionCount ?? audit?.metrics?.reconciliationSuggestionCount ?? reconciliationSuggestions.length} loading={loading && !dailyAudit && !audit} />
          </Col>
          <Col xs={12} md={6}>
            <Statistic title="可行动问题" value={dailyMonitor?.actionableIssueCount ?? monitor?.actionableIssueCount ?? 0} loading={loading && !dailyAudit && !audit} />
          </Col>
        </Row>
        <Table
          rowKey={(record) => record.key || `${record.marketId}-${record.outcome}-${record.latestRecordId}`}
          columns={suggestionColumns}
          dataSource={reconciliationSuggestions.slice(0, 8)}
          pagination={false}
          size="small"
          locale={{ emptyText: '暂无历史错配建议' }}
        />
      </Card>

      <Card title="今日优化点">
        <Table
          rowKey="key"
          columns={columns}
          dataSource={optimizationItems}
          pagination={false}
          size="middle"
        />
      </Card>

      <Modal
        open={!!approvalCandidate}
        title="创建禁用试跟配置"
        onCancel={() => setApprovalCandidate(null)}
        onOk={submitApproval}
        confirmLoading={approvalLoading}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Alert
            type="warning"
            showIcon
            message="只创建禁用状态配置"
            description="该操作不会自动真钱跟单；创建后仍需要你在跟单配置中手动启用。后端会再次校验候选必须是 TRIAL_READY。"
          />
          <Form form={approvalForm} layout="vertical">
            <Descriptions bordered size="small" column={1} title="试跟风控预览">
              <Descriptions.Item label="固定金额">{activeApprovalPreview.fixedAmount}</Descriptions.Item>
              <Descriptions.Item label="最大日亏损">{activeApprovalPreview.maxDailyLoss}</Descriptions.Item>
              <Descriptions.Item label="最大日订单">{activeApprovalPreview.maxDailyOrders}</Descriptions.Item>
              <Descriptions.Item label="价格范围">{activeApprovalPreview.priceRange}</Descriptions.Item>
              <Descriptions.Item label="最大持仓价值">{activeApprovalPreview.maxPositionValue}</Descriptions.Item>
            </Descriptions>
            <Form.Item name="accountId" label="跟单账户" rules={[{ required: true, message: '请选择跟单账户' }]}>
              <Select
                options={accounts.map(account => ({
                  value: account.id,
                  label: `${account.accountName || account.walletAddress} (${shortWallet(account.proxyAddress || account.walletAddress)})`
                }))}
              />
            </Form.Item>
          </Form>
        </Space>
      </Modal>

      <Modal
        title="Loop 目标控制"
        open={goalModalOpen}
        onCancel={() => setGoalModalOpen(false)}
        footer={null}
        width={760}
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            message="目标状态只控制研究/优化 loop 的优先级与自动执行，不会自动创建或启用真钱跟单。"
          />
          {sortedGoals.map((goal) => {
            const statusView = formatGoalStatus(goal.status)
            return (
              <Card
                key={goal.goalKey}
                size="small"
                title={goal.title}
                extra={<Tag color={statusView.color}>{statusView.label}</Tag>}
              >
                <Space direction="vertical" size={8} style={{ width: '100%' }}>
                  <Text type="secondary">{goal.summary}</Text>
                  <Space size={[8, 8]} wrap>
                    <Tag color={goal.retained ? 'blue' : 'default'}>{goal.retained ? '保留' : '可删除'}</Tag>
                    <Text type="secondary">最近更新: {formatTimestamp(goal.updatedAt)}</Text>
                  </Space>
                  <Space>
                    <Button
                      type={goal.status === 'ACTIVE' ? 'default' : 'primary'}
                      icon={<PlayCircleOutlined />}
                      disabled={!goal.canStart}
                      loading={updatingGoalKey === `${goal.goalKey}:START`}
                      onClick={() => handleGoalAction(goal, 'START')}
                    >
                      启动
                    </Button>
                    <Button
                      icon={<PauseCircleOutlined />}
                      disabled={!goal.canPause}
                      loading={updatingGoalKey === `${goal.goalKey}:PAUSE`}
                      onClick={() => handleGoalAction(goal, 'PAUSE')}
                    >
                      暂停
                    </Button>
                  </Space>
                </Space>
              </Card>
            )
          })}
        </Space>
      </Modal>
    </div>
  )
}

export default OptimizationDaily
