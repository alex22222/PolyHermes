import { useEffect, useState } from 'react'
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  Modal,
  Progress,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
  message
} from 'antd'
import {
  ExperimentOutlined,
  ArrowRightOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
  FilterOutlined,
  InfoCircleOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { useTranslation } from 'react-i18next'
import { apiService } from '../services/api'
import type {
  Account,
  LeaderPaperPosition,
  LeaderPaperTrade,
  LeaderResearchActivitySourceImportResponse,
  LeaderResearchApprovalPreviewResponse,
  LeaderResearchCandidate,
  LeaderResearchCandidateDetail,
  LeaderResearchCandidateListResponse,
  LeaderResearchExternalAnalyticsImportItem,
  LeaderResearchExternalAnalyticsImportResponse,
  LeaderResearchFalconLeaderboardImportResponse,
  LeaderResearchFastWatchResponse,
  LeaderResearchFunnel,
  LeaderResearchMarketPeerSourceImportResponse,
  LeaderResearchOfficialLeaderboardDiagnoseResponse,
  LeaderResearchOfficialLeaderboardImportResponse,
  LeaderResearchOfficialLeaderboardSample,
  LeaderResearchPaperProcessCandidate,
  LeaderResearchPaperPromotionResponse,
  LeaderResearchPoliticsRecommendationExecutionSnapshot,
  LeaderResearchPoliticsRecommendationExecuteResponse,
  LeaderResearchPoliticsSourceDiagnose,
  LeaderResearchPolymarketAnalyticsCopyTradeImportResponse,
  LeaderResearchPolyburgTelegramImportResponse,
  LeaderResearchTrialReadyRecheckResponse,
  LeaderResearchTrialReadiness,
  LeaderResearchSourceState,
  LeaderResearchState,
  LeaderResearchSummary
} from '../types'
import './LeaderResearch.css'

const { Paragraph, Text, Title } = Typography

const STATE_COLORS: Record<LeaderResearchState, string> = {
  DISCOVERED: 'default',
  CANDIDATE: 'blue',
  PAPER: 'geekblue',
  TRIAL_READY: 'green',
  COOLDOWN: 'orange',
  RETIRED: 'red'
}

const STATE_LABELS: Record<LeaderResearchState, string> = {
  DISCOVERED: '已发现',
  CANDIDATE: '候选',
  PAPER: '纸跟验证',
  TRIAL_READY: '建议试跟',
  COOLDOWN: '冷却复核',
  RETIRED: '已淘汰'
}

const CATEGORY_LABELS: Record<string, string> = {
  politics: '政治',
  finance: '金融',
  sports: '体育',
  crypto: '加密市场'
}

const STRATEGY_TYPE_LABELS: Record<string, string> = {
  human_directional: '人工方向交易',
  whale: '大额鲸鱼型',
  bot_hft: '高频机器人',
  market_maker_lp: '做市 / 流动性',
  arbitrage: '套利型',
  low_price_tail_risk: '低价尾部风险',
  rebalance_churn: '高频再平衡',
  unknown: '待识别'
}

const SOURCE_LABELS: Record<string, string> = {
  ACTIVITY_DERIVED: '链上活动发现',
  EXISTING_LEADER: '现有 Leader',
  WATCHLIST: '观察名单',
  OFFICIAL_LEADERBOARD: '官方排行榜',
  FALCON_LEADERBOARD: 'Falcon 排行榜',
  EXTERNAL_ANALYTICS: '外部分析',
  POLYBURG_TELEGRAM: 'Polyburg / Telegram',
  MARKET_PEER: '热门市场对手方'
}

const SOURCE_STATUS_LABELS: Record<string, string> = {
  SUCCESS: '正常',
  RUNNING: '运行中',
  DISABLED: '已停用',
  FAILED: '失败',
  PARTIAL: '部分成功',
  NEVER_RUN: '尚未运行'
}

const RECOMMENDATION_LABELS: Record<string, string> = {
  IMPORT_NOW: '导入候选',
  SCORE_REFRESH: '刷新评分',
  PAPER_PROCESS: '推进纸跟',
  FAST_WATCH_REVIEW: '快速观察复核'
}

const RUN_STATUS_LABELS: Record<string, string> = {
  SUCCESS: '成功',
  RUNNING: '运行中',
  FAILED: '失败',
  SKIPPED: '已跳过',
  PARTIAL_SUCCESS: '部分成功'
}

const RISK_FLAG_LABELS: Record<string, string> = {
  mixed_category_evidence: '跨分类证据混杂',
  high_filtered_ratio: '过滤比例过高',
  tail_price_spray: '低价尾部下注过多',
  stale_source: '来源数据过期',
  non_copyable_strategy: '策略不适合复制',
  negative_pnl: '纸跟收益为负',
  insufficient_samples: '有效样本不足',
  unknown_strategy: '策略类型未识别',
  missing_profit_window_all: '缺少全周期收益证据'
}

const REASON_LABELS: Record<string, string> = {
  state_criteria_satisfied: '已满足状态推进条件',
  source_stale: '来源已过期，需要刷新',
  insufficient_paper_age: '纸跟观察时间不足',
  insufficient_trade_count: '有效纸跟成交不足',
  insufficient_stable_scores: '最近评分稳定性不足',
  copyable_pnl_not_positive: '可复制收益尚未为正',
  risk_flags_present: '仍有风险标记未消除',
  unknown_strategy_all_filtered_after_enrichment: '策略未识别且样本全部被过滤',
  unknown_strategy_negative_pnl_after_enrichment: '策略未识别且纸跟收益为负'
}

const STATE_FLOW: Array<{
  state: LeaderResearchState
  stage: string
  description: string
  gate: string
  next: string
}> = [
  {
    state: 'DISCOVERED',
    stage: '来源入库',
    description: '从榜单、链上活动和外部名单发现钱包。',
    gate: '来源在 48 小时内有效，并完成初步评分。',
    next: '评分达到 60 或具备受管观察条件后进入候选。'
  },
  {
    state: 'CANDIDATE',
    stage: '通过初筛',
    description: '已具备研究价值，等待建立纸跟观察。',
    gate: '来源新鲜、分类明确，且具备可复制性线索。',
    next: '建立纸跟会话，开始累计可执行样本。'
  },
  {
    state: 'PAPER',
    stage: '纸跟验证',
    description: '只做模拟跟单，检验成交、收益与风险。',
    gate: '评分 ≥80、观察 ≥168 小时、最近 3 次稳定高分、风险为空且纸跟收益为正。',
    next: '全部通过后进入建议试跟；恶化则转入冷却。'
  },
  {
    state: 'TRIAL_READY',
    stage: '人工决策',
    description: '研究门槛已通过，等待你进行人工预检。',
    gate: '这里只代表“可考虑小额试跟”，不代表已启用。',
    next: '最多创建默认禁用的试跟配置，仍需手动启用。'
  },
  {
    state: 'COOLDOWN',
    stage: '冷却复核',
    description: '数据过期、收益转差或风险信号触发暂停。',
    gate: '冷却 3 天后重新检查来源与质量。',
    next: '恢复则回到候选；累计 3 次或 30 天无来源则淘汰。'
  },
  {
    state: 'RETIRED',
    stage: '停止推进',
    description: '不再进入自动研究推进流程。',
    gate: '保留历史记录用于审计与复盘。',
    next: '不会进入跟单执行链路。'
  }
]

const VALUATION_COLORS: Record<string, string> = {
  AVAILABLE: 'green',
  CONFIRMED_ZERO: 'purple',
  UNKNOWN: 'orange',
  UNAVAILABLE: 'red',
  NO_MATCH: 'volcano'
}

const allocationStatusColor = (status: string) => {
  if (status === 'HEALTHY') return 'green'
  if (status === 'WATCH') return 'gold'
  if (status === 'DEFICIT') return 'red'
  return 'default'
}

const readinessColor = (level: string) => {
  if (level === 'TRIAL_READY') return 'green'
  if (level === 'FAST_WATCH') return 'blue'
  return 'gold'
}

const STRATEGY_TYPE_COLORS: Record<string, string> = {
  human_directional: 'green',
  whale: 'volcano',
  bot_hft: 'red',
  market_maker_lp: 'orange',
  arbitrage: 'orange',
  low_price_tail_risk: 'red',
  rebalance_churn: 'gold',
  unknown: 'default'
}

const strategyTypeTag = (strategyType?: string) => {
  const value = strategyType || 'unknown'
  return <Tag color={STRATEGY_TYPE_COLORS[value] || 'default'}>{STRATEGY_TYPE_LABELS[value] || value}</Tag>
}

const categoryLabel = (category?: string) => category ? CATEGORY_LABELS[category] || category : '-'

const sourceLabel = (source?: string) => {
  if (!source) return '-'
  return source
    .split(',')
    .map(item => SOURCE_LABELS[item.trim()] || item.trim().replace(/_/g, ' '))
    .join('、')
}

const readableCode = (value?: string) => {
  if (!value) return ''
  const normalized = value.trim()
  if (normalized.startsWith('PUBLIC_LEADERBOARD:')) {
    return '公开排行榜：V1 暂未启用；当前发现范围为观察名单、现有 Leader 与已持久化活动数据'
  }
  return RISK_FLAG_LABELS[normalized] ||
    REASON_LABELS[normalized] ||
    normalized
      .replace(/TRIAL_READY/g, '建议试跟')
      .replace(/PAPER/g, '纸跟')
      .replace(/CANDIDATE/g, '候选')
      .replace(/DISCOVERED/g, '已发现')
      .replace(/COOLDOWN/g, '冷却')
      .replace(/RETIRED/g, '淘汰')
      .replace(/_/g, ' ')
}

const officialDiagnoseBucketColor = (bucket: string) => {
  if (bucket === 'CLEAN_HIGH' || bucket === 'READY_FOR_PAPER' || bucket === 'FAST_WATCH') return 'green'
  if (bucket === 'STALE_HIGH_QUALITY') return 'gold'
  if (bucket.includes('RISK') || bucket === 'HIGH_FILTERED_RATIO') return 'red'
  if (bucket === 'CATEGORY_CONFLICT') return 'volcano'
  if (bucket === 'STALE_ACTIVITY') return 'orange'
  return 'default'
}

const isOfficialDisabledTrialCandidate = (item: LeaderResearchOfficialLeaderboardSample) => (
  item.bucket === 'CLEAN_HIGH' &&
  item.researchState === 'TRIAL_READY' &&
  item.strategyType === 'human_directional' &&
  item.riskFlags.length === 0 &&
  (item.category === 'politics' || item.category === 'finance')
)

const formatDate = (timestamp?: number) => {
  if (!timestamp) return '-'
  return dayjs(timestamp).format('YYYY-MM-DD HH:mm')
}

const formatTrialEta = (readiness: LeaderResearchTrialReadiness): string => {
  if (readiness.level === 'TRIAL_READY') return ''
  if (!readiness.hoursUntilTrialReady || readiness.hoursUntilTrialReady <= 0) return ''
  const eta = readiness.trialReadyAt ? formatDate(readiness.trialReadyAt) : '-'
  return `还差 ${readiness.hoursUntilTrialReady}h / ${eta}`
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

const valuationTag = (status?: string) => {
  if (!status) return <Tag>-</Tag>
  return <Tag color={VALUATION_COLORS[status] || 'default'}>{status}</Tag>
}

const LeaderResearch: React.FC = () => {
  const { t } = useTranslation()
  const [summary, setSummary] = useState<LeaderResearchSummary | null>(null)
  const [funnel, setFunnel] = useState<LeaderResearchFunnel | null>(null)
  const [fastWatch, setFastWatch] = useState<LeaderResearchFastWatchResponse | null>(null)
  const [politicsDiagnose, setPoliticsDiagnose] = useState<LeaderResearchPoliticsSourceDiagnose | null>(null)
  const [financeDiagnose, setFinanceDiagnose] = useState<LeaderResearchPoliticsSourceDiagnose | null>(null)
  const [marketPeerStrict] = useState<LeaderResearchMarketPeerSourceImportResponse | null>(null)
  const [marketPeerRelaxed, setMarketPeerRelaxed] = useState<LeaderResearchMarketPeerSourceImportResponse | null>(null)
  const [externalImportResult, setExternalImportResult] = useState<LeaderResearchExternalAnalyticsImportResponse | null>(null)
  const [officialLeaderboardResult, setOfficialLeaderboardResult] = useState<LeaderResearchOfficialLeaderboardImportResponse | null>(null)
  const [falconLeaderboardResult, setFalconLeaderboardResult] = useState<LeaderResearchFalconLeaderboardImportResponse | null>(null)
  const [polymarketAnalyticsCopyTradeResult, setPolymarketAnalyticsCopyTradeResult] = useState<LeaderResearchPolymarketAnalyticsCopyTradeImportResponse | null>(null)
  const [polyburgTelegramResult, setPolyburgTelegramResult] = useState<LeaderResearchPolyburgTelegramImportResponse | null>(null)
  const [officialLeaderboardDiagnose, setOfficialLeaderboardDiagnose] = useState<LeaderResearchOfficialLeaderboardDiagnoseResponse | null>(null)
  const [candidates, setCandidates] = useState<LeaderResearchCandidateListResponse>({ list: [], total: 0, summary: summaryFallback })
  const [sourceHealth, setSourceHealth] = useState<LeaderResearchSourceState[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [stateFilter, setStateFilter] = useState<LeaderResearchState | undefined>()
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [advancedLoading, setAdvancedLoading] = useState(false)
  const [diagnosticsLoading, setDiagnosticsLoading] = useState(false)
  const [running, setRunning] = useState(false)
  const [fastWatchAction, setFastWatchAction] = useState<'score' | 'process' | null>(null)
  const [trialReadyRefreshAction, setTrialReadyRefreshAction] = useState<'dryRun' | 'live' | null>(null)
  const [politicsAction, setPoliticsAction] = useState<'process' | 'importPreview' | 'importConfirm' | 'scoreRefresh' | 'executePreview' | null>(null)
  const [politicsImportResult, setPoliticsImportResult] = useState<LeaderResearchActivitySourceImportResponse | null>(null)
  const [politicsPromotionResult, setPoliticsPromotionResult] = useState<LeaderResearchPaperPromotionResponse | null>(null)
  const [politicsExecutionResult, setPoliticsExecutionResult] = useState<LeaderResearchPoliticsRecommendationExecuteResponse | null>(null)
  const [trialReadyRefreshResult, setTrialReadyRefreshResult] = useState<LeaderResearchTrialReadyRecheckResponse | null>(null)
  const [latestPoliticsExecution, setLatestPoliticsExecution] = useState<LeaderResearchPoliticsRecommendationExecutionSnapshot | null>(null)
  const [lastPaperProcessSummaries, setLastPaperProcessSummaries] = useState<LeaderResearchPaperProcessCandidate[]>([])
  const [detailLoading, setDetailLoading] = useState(false)
  const [marketPeerLoading, setMarketPeerLoading] = useState(false)
  const [externalImportOpen, setExternalImportOpen] = useState(false)
  const [externalImportLoading, setExternalImportLoading] = useState(false)
  const [detail, setDetail] = useState<LeaderResearchCandidateDetail | null>(null)
  const [approvalCandidate, setApprovalCandidate] = useState<LeaderResearchCandidate | null>(null)
  const [approvalPreviewResult, setApprovalPreviewResult] = useState<LeaderResearchApprovalPreviewResponse | null>(null)
  const [approvalLoading, setApprovalLoading] = useState(false)
  const [approvalForm] = Form.useForm()
  const [externalImportForm] = Form.useForm()

  const loadAll = async (showLoading = true) => {
    if (showLoading) setLoading(true)
    try {
      const readData = <T,>(result: PromiseSettledResult<{ data: { code: number; data?: T | null; msg?: string } }>, label: string): T | null => {
        if (result.status === 'rejected') {
          console.warn(`[leader-research] ${label} load failed`, result.reason)
          return null
        }
        if (result.value.data.code !== 0) {
          console.warn(`[leader-research] ${label} api failed`, result.value.data.msg)
          return null
        }
        return result.value.data.data ?? null
      }

      const [candidateResp] = await Promise.allSettled([
        apiService.leaderResearch.listCandidates({ page: 0, size: 50, state: stateFilter, query: query || undefined })
      ])

      const candidateData = readData(candidateResp, 'candidates')
      if (candidateData) {
        setCandidates(candidateData)
        setSummary(candidateData.summary)
      } else {
        message.warning(t('leaderResearch.fetchFailed'))
      }
      void Promise.allSettled([
        apiService.leaderResearch.sourceHealth(),
        apiService.leaderResearch.latestPoliticsRecommendationExecution(),
        apiService.accounts.list()
      ]).then(([sourceResp, politicsExecutionResp, accountResp]) => {
        const sourceData = readData(sourceResp, 'sourceHealth')
        if (sourceData) {
          setSourceHealth(sourceData)
        }
        const politicsExecutionData = readData(politicsExecutionResp, 'latestPoliticsExecution')
        setLatestPoliticsExecution(politicsExecutionData || null)
        const accountData = readData(accountResp, 'accounts')
        if (accountData) {
          setAccounts(accountData.list || [])
        }
      })

    } catch (error: any) {
      message.error(error.message || t('leaderResearch.fetchFailed'))
    } finally {
      if (showLoading) setLoading(false)
    }
  }

  const loadAdvancedResearch = async () => {
    setAdvancedLoading(true)
    try {
      const funnelResp = await apiService.leaderResearch.funnel()
      if (funnelResp.data.code === 0 && funnelResp.data.data) {
        setFunnel(funnelResp.data.data)
      }
      const fastWatchResp = await apiService.leaderResearch.fastWatch({
        categories: ['politics', 'finance'],
        limit: 12,
        includeTrialReady: true
      })
      if (fastWatchResp.data.code === 0 && fastWatchResp.data.data) {
        setFastWatch(fastWatchResp.data.data)
      }
    } catch (error: any) {
      message.error(error.message || '加载漏斗与快速观察失败')
    } finally {
      setAdvancedLoading(false)
    }
  }

  const loadSourceDiagnostics = async () => {
    setDiagnosticsLoading(true)
    try {
      const [politicsResp, financeResp] = await Promise.allSettled([
        apiService.leaderResearch.diagnosePoliticsSource({ limit: 500 }),
        apiService.leaderResearch.diagnosePoliticsSource({ category: 'finance', limit: 500 })
      ])
      const politicsData = politicsResp.status === 'fulfilled' && politicsResp.value.data.code === 0
        ? politicsResp.value.data.data
        : null
      const financeData = financeResp.status === 'fulfilled' && financeResp.value.data.code === 0
        ? financeResp.value.data.data
        : null
      if (politicsData) setPoliticsDiagnose(politicsData)
      if (financeData) setFinanceDiagnose(financeData)
      if (!politicsData && !financeData) {
        message.warning('来源诊断暂时不可用，请稍后重试')
      }
    } catch (error: any) {
      message.error(error.message || '加载来源诊断失败')
    } finally {
      setDiagnosticsLoading(false)
    }
  }

  useEffect(() => {
    loadAll()
  }, [stateFilter])

  useEffect(() => {
    const lastRunStatus = summary?.lastRun?.status || candidates.summary?.lastRun?.status
    if (lastRunStatus !== 'RUNNING') return

    const timer = window.setInterval(() => {
      loadAll(false)
    }, 5000)
    return () => window.clearInterval(timer)
  }, [summary?.lastRun?.status, candidates.summary?.lastRun?.status])

  const runAgent = async () => {
    setRunning(true)
    try {
      const response = await apiService.leaderResearch.run({ dryRun: false, triggerType: 'MANUAL' })
      if (response.data.code === 0) {
        message.success(t('leaderResearch.runStarted'))
        await loadAll()
      } else {
        message.error(response.data.msg || t('leaderResearch.runFailed'))
      }
    } catch (error: any) {
      message.error(error.message || t('leaderResearch.runFailed'))
    } finally {
      setRunning(false)
    }
  }

  const fastWatchCandidateIds = () => fastWatch?.items.map(item => item.candidateId).filter(Boolean) || []

  const uniqueCandidateIds = (candidateIds: number[]) =>
    candidateIds.filter((id, index, ids) => ids.indexOf(id) === index)

  const politicsPaperProcessCandidateIds = () => politicsDiagnose?.recommendations
    .filter(item => item.recommendation === 'PAPER_PROCESS' && item.candidateId)
    .map(item => item.candidateId!)
    .filter((id, index, ids) => ids.indexOf(id) === index) || []

  const politicsImportWallets = () => politicsDiagnose?.recommendations
    .filter(item => item.recommendation === 'IMPORT_NOW')
    .map(item => item.wallet)
    .filter((wallet, index, wallets) => wallets.indexOf(wallet) === index) || []

  const politicsFastWatchReviewRecommendations = () => politicsDiagnose?.recommendations
    .filter(item => item.recommendation === 'FAST_WATCH_REVIEW' && item.candidateId)
    || []

  const politicsScoreRefreshCandidateIds = () => politicsDiagnose?.recommendations
    .filter(item => item.recommendation === 'SCORE_REFRESH' && item.candidateId)
    .map(item => item.candidateId!)
    .filter((id, index, ids) => ids.indexOf(id) === index) || []

  const recommendationCount = (
    diagnose: LeaderResearchPoliticsSourceDiagnose | null,
    recommendation: string
  ) => diagnose?.recommendations.filter(item => item.recommendation === recommendation).length || 0

  const scoreFastWatch = async () => {
    const candidateIds = fastWatchCandidateIds()
    if (candidateIds.length === 0) {
      message.info(t('leaderResearch.noFastWatchCandidatesScore'))
      return
    }
    setFastWatchAction('score')
    try {
      const response = await apiService.leaderResearch.scorePaper({
        candidateIds,
        maxCandidates: 100
      })
      if (response.data.code === 0 && response.data.data) {
        const data = response.data.data
        message.success(t('leaderResearch.scoreFastWatchSuccess', {
          count: data.scoredCount,
          missing: data.missingCandidateIds.length ? t('leaderResearch.missingCandidates', { count: data.missingCandidateIds.length }) : ''
        }))
        await loadAll(false)
      } else {
        message.error(response.data.msg || t('leaderResearch.fetchFailed'))
      }
    } catch (error: any) {
      message.error(error.message || t('leaderResearch.fetchFailed'))
    } finally {
      setFastWatchAction(null)
    }
  }

  const processFastWatch = async () => {
    const candidateIds = fastWatchCandidateIds()
    if (candidateIds.length === 0) {
      message.info(t('leaderResearch.noFastWatchCandidatesProcess'))
      return
    }
    setFastWatchAction('process')
    try {
      const processResponse = await apiService.leaderResearch.processPaper({
        batchSize: 20,
        candidateIds
      })
      if (processResponse.data.code !== 0 || !processResponse.data.data) {
        message.error(processResponse.data.msg || t('leaderResearch.fetchFailed'))
        return
      }
      const processData = processResponse.data.data
      setLastPaperProcessSummaries(processData.candidateSummaries || [])
      const scoreResponse = await apiService.leaderResearch.scorePaper({
        candidateIds,
        maxCandidates: 100
      })
      const scoredCount = scoreResponse.data.code === 0 ? scoreResponse.data.data?.scoredCount ?? 0 : 0
      const summaryCount = processData.candidateSummaries?.length ?? 0
      message.success(t('leaderResearch.processFastWatchSuccess', {
          processed: processData.processed,
          filtered: processData.filtered,
          failed: processData.failed,
          summaryCount,
          scoredCount
        }))
      await loadAll(false)
    } catch (error: any) {
      message.error(error.message || t('leaderResearch.fetchFailed'))
    } finally {
      setFastWatchAction(null)
    }
  }

  const refreshHighQualityTrialReady = async () => {
    const candidateIds = uniqueCandidateIds(fastWatchCandidateIds())
    if (candidateIds.length === 0) {
      message.info(t('leaderResearch.noFastWatchCandidatesRefresh'))
      return
    }
    setTrialReadyRefreshAction('dryRun')
    try {
      const processResponse = await apiService.leaderResearch.processPaper({
        batchSize: 20,
        candidateIds
      })
      if (processResponse.data.code !== 0 || !processResponse.data.data) {
        message.error(processResponse.data.msg || t('leaderResearch.fetchFailed'))
        return
      }
      setLastPaperProcessSummaries(processResponse.data.data.candidateSummaries || [])

      const scoreResponse = await apiService.leaderResearch.scorePaper({
        candidateIds,
        maxCandidates: 100
      })
      if (scoreResponse.data.code !== 0 || !scoreResponse.data.data) {
        message.error(scoreResponse.data.msg || t('leaderResearch.fetchFailed'))
        return
      }

      const recheckResponse = await apiService.leaderResearch.recheckTrialReady({
        dryRun: true,
        candidateIds,
        maxCandidates: candidateIds.length
      })
      if (recheckResponse.data.code !== 0 || !recheckResponse.data.data) {
        message.error(recheckResponse.data.msg || t('leaderResearch.fetchFailed'))
        return
      }

      const dryRunResult = recheckResponse.data.data
      setTrialReadyRefreshResult(dryRunResult)
      message.success(t('leaderResearch.trialReadyRefreshDryRunSuccess', {
        processed: processResponse.data.data.processed,
        scored: scoreResponse.data.data.scoredCount,
        ready: dryRunResult.trialReadyCandidateIds.length
      }))
      await loadAll(false)

      if (dryRunResult.trialReadyCandidateIds.length === 0) return

      Modal.confirm({
        title: t('leaderResearch.confirmTrialReadyRecheckTitle'),
        content: t('leaderResearch.confirmTrialReadyRecheckContent', { count: dryRunResult.trialReadyCandidateIds.length }),
        okText: t('leaderResearch.confirmTrialReadyRecheck'),
        cancelText: t('common.cancel'),
        onOk: async () => {
          setTrialReadyRefreshAction('live')
          try {
            const liveResponse = await apiService.leaderResearch.recheckTrialReady({
              dryRun: false,
              candidateIds: dryRunResult.trialReadyCandidateIds,
              maxCandidates: dryRunResult.trialReadyCandidateIds.length
            })
            if (liveResponse.data.code !== 0 || !liveResponse.data.data) {
              message.error(liveResponse.data.msg || t('leaderResearch.fetchFailed'))
              return
            }
            setTrialReadyRefreshResult(liveResponse.data.data)
            message.success(t('leaderResearch.trialReadyRefreshLiveSuccess', {
              promoted: liveResponse.data.data.trialReadyCandidateIds.length
            }))
            await loadAll(false)
          } finally {
            setTrialReadyRefreshAction(null)
          }
        }
      })
    } catch (error: any) {
      message.error(error.message || t('leaderResearch.fetchFailed'))
    } finally {
      if (trialReadyRefreshAction !== 'live') {
        setTrialReadyRefreshAction(null)
      }
    }
  }

  const processPoliticsRecommendations = async () => {
    const candidateIds = politicsPaperProcessCandidateIds()
    if (candidateIds.length === 0) {
      message.info(t('leaderResearch.noPoliticsPaperProcessRecommendations'))
      return
    }
    setPoliticsAction('process')
    try {
      const processResponse = await apiService.leaderResearch.processPaper({
        batchSize: Math.min(20, candidateIds.length * 3),
        candidateIds
      })
      if (processResponse.data.code !== 0 || !processResponse.data.data) {
        message.error(processResponse.data.msg || t('leaderResearch.fetchFailed'))
        return
      }
      const processData = processResponse.data.data
      setLastPaperProcessSummaries(processData.candidateSummaries || [])
      const scoreResponse = await apiService.leaderResearch.scorePaper({
        candidateIds,
        maxCandidates: 100
      })
      const scoredCount = scoreResponse.data.code === 0 ? scoreResponse.data.data?.scoredCount ?? 0 : 0
      message.success(t('leaderResearch.politicsProcessSuccess', {
          candidateCount: candidateIds.length,
          processed: processData.processed,
          filtered: processData.filtered,
          failed: processData.failed,
          scoredCount
        }))
      await loadAll(false)
    } catch (error: any) {
      message.error(error.message || t('leaderResearch.fetchFailed'))
    } finally {
      setPoliticsAction(null)
    }
  }

  const importPoliticsRecommendations = async (dryRun: boolean) => {
    const wallets = politicsImportWallets()
    if (wallets.length === 0) {
      message.info(t('leaderResearch.noPoliticsImportRecommendations'))
      return
    }
    const runImport = async () => {
      setPoliticsAction(dryRun ? 'importPreview' : 'importConfirm')
      try {
        const response = await apiService.leaderResearch.importActivitySource({
          dryRun,
          categories: ['politics'],
          wallets,
          limitPerCategory: Math.min(100, wallets.length),
          lookbackDays: 60,
          minEvents: 8,
          minDistinctMarkets: 2,
          minBuyEvents: 2,
          minSellEvents: 1,
          minSafePriceRatio: '0.20',
          maxTailPriceRatio: '0.50'
        })
        if (response.data.code !== 0 || !response.data.data) {
          message.error(response.data.msg || t('leaderResearch.fetchFailed'))
          return
        }
        const data = response.data.data
        setPoliticsImportResult(data)
        message.success(dryRun
            ? t('leaderResearch.politicsImportPreviewSuccess', {
                selected: data.selectedTotal,
                created: data.createdTotal,
                updated: data.updatedTotal
              })
            : t('leaderResearch.politicsImportSuccess', {
                selected: data.selectedTotal,
                created: data.createdTotal,
                updated: data.updatedTotal
              }))
        await loadAll(false)
      } catch (error: any) {
        message.error(error.message || t('leaderResearch.fetchFailed'))
      } finally {
        setPoliticsAction(null)
      }
    }

    if (dryRun) {
      await runImport()
      return
    }

    Modal.confirm({
      title: t('leaderResearch.confirmPoliticsImportTitle'),
      content: t('leaderResearch.confirmPoliticsImportContent', { count: wallets.length }),
      okText: t('leaderResearch.confirmImport'),
      cancelText: t('common.cancel'),
      onOk: runImport
    })
  }

  const scoreRefreshPoliticsRecommendations = async () => {
    const candidateIds = politicsScoreRefreshCandidateIds()
    if (candidateIds.length === 0) {
      message.info(t('leaderResearch.noPoliticsScoreRefreshRecommendations'))
      return
    }
    setPoliticsAction('scoreRefresh')
    try {
      const scoreResponse = await apiService.leaderResearch.runActivityScore({
        states: ['DISCOVERED', 'CANDIDATE'],
        force: true,
        candidateIds
      })
      if (scoreResponse.data.code !== 0 || !scoreResponse.data.data) {
        message.error(scoreResponse.data.msg || t('leaderResearch.fetchFailed'))
        return
      }
      const promoteResponse = await apiService.leaderResearch.promoteActivityScoreToPaper({
        minScore: '70',
        politicsLimit: Math.min(20, candidateIds.length),
        financeLimit: 0,
        sportsLimit: 0,
        cryptoLimit: 0,
        dryRun: false,
        candidateIds
      })
      if (promoteResponse.data.code !== 0 || !promoteResponse.data.data) {
        message.error(promoteResponse.data.msg || t('leaderResearch.fetchFailed'))
        return
      }
      setPoliticsPromotionResult(promoteResponse.data.data)
      message.success(t('leaderResearch.politicsScoreRefreshSuccess', {
          scored: scoreResponse.data.data.scoredCount,
          paper: 'PAPER',
          promoted: promoteResponse.data.data.promotedTotal
        }))
      await loadAll(false)
    } catch (error: any) {
      message.error(error.message || t('leaderResearch.fetchFailed'))
    } finally {
      setPoliticsAction(null)
    }
  }

  const previewPoliticsRecommendationLoop = async () => {
    setPoliticsAction('executePreview')
    try {
      const response = await apiService.leaderResearch.executePoliticsRecommendations({
        dryRun: true,
        actions: ['IMPORT_NOW', 'SCORE_REFRESH', 'PAPER_PROCESS', 'FAST_WATCH_REVIEW'],
        diagnose: {
          limit: 500,
          lookbackDays: 60,
          minEvents: 8,
          minDistinctMarkets: 2,
          minBuyEvents: 2,
          minSellEvents: 1,
          minSafePriceRatio: '0.20',
          maxTailPriceRatio: '0.50'
        },
        maxImport: 20,
        maxScoreRefresh: 20,
        maxPaperProcess: 20,
        paperProcessBatchSize: 20,
        promotionMinScore: '70'
      })
      if (response.data.code !== 0 || !response.data.data) {
        message.error(response.data.msg || t('leaderResearch.fetchFailed'))
        return
      }
      const data = response.data.data
      setPoliticsExecutionResult(data)
      message.success(t('leaderResearch.politicsLoopPreviewSuccess', {
          recommendations: data.recommendations.length,
          plannedActions: data.plannedActions.reduce((sum, item) => sum + item.selectedCount, 0)
        }))
      await loadAll(false)
    } catch (error: any) {
      message.error(error.message || t('leaderResearch.fetchFailed'))
    } finally {
      setPoliticsAction(null)
    }
  }

  const openDetail = async (candidate: LeaderResearchCandidate) => {
    setDetailLoading(true)
    try {
      const response = await apiService.leaderResearch.detail({ candidateId: candidate.id })
      if (response.data.code === 0 && response.data.data) {
        setDetail(response.data.data)
      } else {
        message.error(response.data.msg || t('leaderResearch.fetchFailed'))
      }
    } finally {
      setDetailLoading(false)
    }
  }

  const runMarketPeerRelaxed = async () => {
    setMarketPeerLoading(true)
    try {
      const response = await apiService.leaderResearch.importMarketPeerSource({
        dryRun: true,
        categories: ['finance'],
        limitPerCategory: 20,
        lookbackDays: 60,
        hotMarketLimit: 80,
        minMarketEvents: 10,
        minMarketWallets: 5,
        minEvents: 5,
        minDistinctMarkets: 2,
        minBuyEvents: 1,
        minSellEvents: 1,
        minSafePriceRatio: '0.20',
        maxTailPriceRatio: '0.50'
      })
      if (response.data.code === 0 && response.data.data) {
        setMarketPeerRelaxed(response.data.data)
        message.success(t('leaderResearch.marketPeerRelaxedRefreshed'))
      } else {
        message.error(response.data.msg || t('leaderResearch.fetchFailed'))
      }
    } catch (error: any) {
      message.error(error.message || t('leaderResearch.fetchFailed'))
    } finally {
      setMarketPeerLoading(false)
    }
  }

  const parseExternalWalletLines = (
    raw: string,
    defaultCategory: string,
    defaultSourceName: string
  ): LeaderResearchExternalAnalyticsImportItem[] => {
    const walletRegex = /0x[a-fA-F0-9]{40}/
    const categoryRegex = /\b(politics|finance|sports|crypto)\b/i
    const scoreRegex = /^\d+(\.\d+)?%?$/

    return raw
      .split(/\r?\n/)
      .map((line, index) => {
        const trimmed = line.trim()
        if (!trimmed) return null
        const wallet = trimmed.match(walletRegex)?.[0]
        if (!wallet) return null

        const parts = trimmed.split(/[,\t ]+/).map(part => part.trim()).filter(Boolean)
        const category = trimmed.match(categoryRegex)?.[1] || defaultCategory
        const score = parts
          .map(part => part.replace(/[%$,]/g, ''))
          .find(part => scoreRegex.test(part) && part !== wallet)

        return {
          wallet,
          category,
          sourceName: defaultSourceName,
          externalRank: index + 1,
          externalScore: score,
          note: trimmed
        }
      })
      .filter(Boolean) as LeaderResearchExternalAnalyticsImportItem[]
  }

  const submitExternalImport = async (dryRun: boolean) => {
    const values = await externalImportForm.validateFields()
    const items = parseExternalWalletLines(
      values.walletLines || '',
      values.defaultCategory || 'finance',
      values.defaultSourceName || 'external_analytics'
    )
    if (items.length === 0) {
      message.warning(t('leaderResearch.pleaseEnterWallet'))
      return
    }
    setExternalImportLoading(true)
    try {
      const response = await apiService.leaderResearch.importExternalAnalytics({
        dryRun,
        items,
        defaultCategory: values.defaultCategory || 'finance',
        defaultSourceName: values.defaultSourceName || 'external_analytics',
        maxItems: 500
      })
      if (response.data.code === 0 && response.data.data) {
        setExternalImportResult(response.data.data)
        message.success(dryRun ? t('leaderResearch.externalListDryRunSuccess') : t('leaderResearch.externalListImported'))
        if (!dryRun) await loadAll(false)
      } else {
        message.error(response.data.msg || t('leaderResearch.fetchFailed'))
      }
    } catch (error: any) {
      message.error(error.message || t('leaderResearch.fetchFailed'))
    } finally {
      setExternalImportLoading(false)
    }
  }

  const submitOfficialLeaderboardImport = async (dryRun: boolean) => {
    setExternalImportLoading(true)
    try {
      const response = await apiService.leaderResearch.importOfficialLeaderboard({
        dryRun,
        categories: ['politics', 'finance'],
        timePeriods: ['MONTH', 'ALL'],
        orderBys: ['PNL'],
        limitPerPage: 50,
        maxPagesPerQuery: 2,
        maxItems: 500
      })
      if (response.data.code === 0 && response.data.data) {
        setOfficialLeaderboardResult(response.data.data)
        setExternalImportResult(response.data.data.importResult)
        const failedFetches = response.data.data.fetches.filter(item => item.error).length
        if (failedFetches > 0) {
          message.warning(t('leaderResearch.officialLeaderboardFetchErrors', { count: failedFetches }))
        } else {
          message.success(dryRun ? t('leaderResearch.officialLeaderboardDryRunSuccess') : t('leaderResearch.officialLeaderboardImported'))
        }
        if (!dryRun) await loadAll(false)
      } else {
        message.error(response.data.msg || t('leaderResearch.fetchFailed'))
      }
    } catch (error: any) {
      message.error(error.message || t('leaderResearch.fetchFailed'))
    } finally {
      setExternalImportLoading(false)
    }
  }

  const submitFalconLeaderboardImport = async (dryRun: boolean) => {
    setExternalImportLoading(true)
    try {
      const response = await apiService.leaderResearch.importFalconLeaderboard({
        dryRun,
        sortBys: ['h_score', 'sharpe', 'pnl'],
        minWinRate15d: '0.45',
        maxWinRate15d: '0.95',
        minRoi15d: '0',
        minTotalTrades15d: '50',
        maxTotalTrades15d: '100000',
        minPnl15d: '0',
        limitPerPage: 50,
        maxPagesPerSort: 1,
        maxItems: 500,
        defaultCategory: 'finance'
      })
      if (response.data.code === 0 && response.data.data) {
        setFalconLeaderboardResult(response.data.data)
        setExternalImportResult(response.data.data.importResult)
        const failedFetches = response.data.data.fetches.filter(item => item.error).length
        if (failedFetches > 0) {
          message.warning(t('leaderResearch.falconFetchErrors', { count: failedFetches }))
        } else {
          message.success(dryRun ? t('leaderResearch.falconDryRunSuccess') : t('leaderResearch.falconImported'))
        }
        if (!dryRun) await loadAll(false)
      } else {
        message.error(response.data.msg || t('leaderResearch.fetchFailed'))
      }
    } catch (error: any) {
      message.error(error.message || t('leaderResearch.fetchFailed'))
    } finally {
      setExternalImportLoading(false)
    }
  }

  const submitPolyburgTelegramImport = async (dryRun: boolean) => {
    const values = await externalImportForm.validateFields(['walletLines', 'defaultCategory'])
    setExternalImportLoading(true)
    try {
      const response = await apiService.leaderResearch.importPolyburgTelegram({
        dryRun,
        rawText: values.walletLines || '',
        defaultCategory: values.defaultCategory || 'finance',
        sourceUrl: 'https://web.telegram.org/a/#7698624735',
        maxItems: 500
      })
      if (response.data.code === 0 && response.data.data) {
        setPolyburgTelegramResult(response.data.data)
        setExternalImportResult(response.data.data.importResult)
        message.success(dryRun ? t('leaderResearch.polyburgDryRunSuccess') : t('leaderResearch.polyburgImported'))
        if (!dryRun) await loadAll(false)
      } else {
        message.error(response.data.msg || t('leaderResearch.fetchFailed'))
      }
    } catch (error: any) {
      message.error(error.message || t('leaderResearch.fetchFailed'))
    } finally {
      setExternalImportLoading(false)
    }
  }

  const submitPolymarketAnalyticsCopyTradeImport = async (dryRun: boolean) => {
    const values = await externalImportForm.validateFields(['walletLines', 'defaultCategory'])
    setExternalImportLoading(true)
    try {
      const response = await apiService.leaderResearch.importPolymarketAnalyticsCopyTrade({
        dryRun,
        rawText: values.walletLines || '',
        defaultCategory: values.defaultCategory || 'finance',
        sourceUrl: 'https://polymarketanalytics.com/copy-trade',
        maxItems: 500
      })
      if (response.data.code === 0 && response.data.data) {
        setPolymarketAnalyticsCopyTradeResult(response.data.data)
        setExternalImportResult(response.data.data.importResult)
        message.success(dryRun ? t('leaderResearch.polymarketAnalyticsDryRunSuccess') : t('leaderResearch.polymarketAnalyticsImported'))
        if (!dryRun) await loadAll(false)
      } else {
        message.error(response.data.msg || t('leaderResearch.fetchFailed'))
      }
    } catch (error: any) {
      message.error(error.message || t('leaderResearch.fetchFailed'))
    } finally {
      setExternalImportLoading(false)
    }
  }

  const runOfficialLeaderboardDiagnose = async () => {
    setExternalImportLoading(true)
    try {
      const response = await apiService.leaderResearch.diagnoseOfficialLeaderboard({
        sampleLimit: 15,
        staleHours: 48
      })
      if (response.data.code === 0 && response.data.data) {
        setOfficialLeaderboardDiagnose(response.data.data)
        message.success(t('leaderResearch.officialLeaderboardDiagnoseComplete'))
      } else {
        message.error(response.data.msg || t('leaderResearch.fetchFailed'))
      }
    } catch (error: any) {
      message.error(error.message || t('leaderResearch.fetchFailed'))
    } finally {
      setExternalImportLoading(false)
    }
  }

  const refreshOfficialLeaderboardCandidate = async (candidateId: number) => {
    setExternalImportLoading(true)
    try {
      const response = await apiService.leaderResearch.refreshOfficialLeaderboardCandidates({
        dryRun: false,
        candidateIds: [candidateId],
        categories: ['finance', 'politics'],
        timePeriods: ['MONTH', 'WEEK'],
        orderBys: ['PNL', 'VOL'],
        limitPerPage: 50,
        maxPagesPerQuery: 5,
        maxItems: 50
      })
      if (response.data.code !== 0 || !response.data.data) {
        message.error(response.data.msg || t('leaderResearch.fetchFailed'))
        return
      }
      if (response.data.data.matchedTotal > 0) {
        message.success(t('leaderResearch.officialSourceRefreshed'))
      } else {
        message.warning(t('leaderResearch.officialSourceRefreshNoMatch'))
      }
      await runOfficialLeaderboardDiagnose()
    } catch (error: any) {
      message.error(error.message || t('leaderResearch.fetchFailed'))
    } finally {
      setExternalImportLoading(false)
    }
  }

  const openApproval = async (candidate: LeaderResearchCandidate) => {
    setApprovalLoading(true)
    setApprovalPreviewResult(null)
    setApprovalCandidate(candidate)
    try {
      const response = await apiService.leaderResearch.previewDisabledTrialConfig({ candidateId: candidate.id })
      if (response.data.code !== 0 || !response.data.data) {
        message.error(response.data.msg || t('leaderResearch.approvalPreviewFailed'))
        approvalForm.setFieldsValue({ accountId: accounts[0]?.id })
        return
      }
      const preview = response.data.data
      setApprovalPreviewResult(preview)
      const availableAccount = preview.accounts.find(account => !account.duplicateConfigId)
      approvalForm.setFieldsValue({ accountId: availableAccount?.accountId })
    } catch (error: any) {
      message.error(error.message || t('leaderResearch.approvalPreviewFailed'))
      approvalForm.setFieldsValue({ accountId: accounts[0]?.id })
    } finally {
      setApprovalLoading(false)
    }
  }

  const openApprovalByCandidateId = async (candidateId: number) => {
    setApprovalLoading(true)
    try {
      const response = await apiService.leaderResearch.detail({ candidateId })
      if (response.data.code !== 0 || !response.data.data) {
        message.error(response.data.msg || t('leaderResearch.fetchFailed'))
        return
      }
      const candidate = response.data.data.candidate
      if (candidate.researchState !== 'TRIAL_READY') {
        message.warning(t('leaderResearch.candidateNotTrialReadyWarning'))
        return
      }
      await openApproval(candidate)
    } catch (error: any) {
      message.error(error.message || t('leaderResearch.fetchFailed'))
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
        message.success(t('leaderResearch.approvalCreated'))
        setApprovalCandidate(null)
        setApprovalPreviewResult(null)
        await loadAll()
      } else {
        message.error(response.data.msg || t('leaderResearch.approvalFailed'))
      }
    } catch (error: any) {
      message.error(error.message || t('leaderResearch.approvalFailed'))
    } finally {
      setApprovalLoading(false)
    }
  }

  const activeSummary = summary || candidates.summary || summaryFallback
  const pendingDecisions = candidates.list.filter(candidate => candidate.researchState === 'TRIAL_READY')
  const lastRun = activeSummary.lastRun
  const activeApprovalPreview = approvalPreview(approvalCandidate)
  const stateCounts: Record<LeaderResearchState, number> = {
    DISCOVERED: activeSummary.discoveredCount,
    CANDIDATE: activeSummary.candidateCount,
    PAPER: activeSummary.paperCount,
    TRIAL_READY: activeSummary.trialReadyCount,
    COOLDOWN: activeSummary.cooldownCount,
    RETIRED: activeSummary.retiredCount
  }

  const selectState = (state?: LeaderResearchState) => {
    setStateFilter(state)
    window.setTimeout(() => {
      document.getElementById('leader-candidate-workbench')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }, 0)
  }

  const candidateNextStep = (candidate: LeaderResearchCandidate) => {
    const firstRisk = candidate.riskFlags[0]
    if (firstRisk) {
      return {
        title: '先消除风险标记',
        detail: readableCode(firstRisk),
        tone: 'warning'
      }
    }
    if (candidate.locked) {
      return {
        title: '已锁定，等待人工处理',
        detail: '自动状态机不会推进已锁定候选。',
        tone: 'warning'
      }
    }
    if (candidate.researchState === 'DISCOVERED') {
      return {
        title: '等待初评与来源确认',
        detail: readableCode(candidate.reason) || '需要新鲜来源，并达到初筛分数。',
        tone: 'neutral'
      }
    }
    if (candidate.researchState === 'CANDIDATE') {
      return {
        title: '建立纸跟观察',
        detail: readableCode(candidate.reason) || '下一轮状态推进会创建纸跟会话。',
        tone: 'active'
      }
    }
    if (candidate.researchState === 'PAPER') {
      const session = candidate.latestPaperSession
      return {
        title: '继续累计可执行样本',
        detail: session
          ? `已成交 ${session.tradeCount} 笔，可复制收益 ${session.copyablePnl} USDC。`
          : '尚未建立有效纸跟样本。',
        tone: 'active'
      }
    }
    if (candidate.researchState === 'TRIAL_READY') {
      return {
        title: '等待人工预检',
        detail: '可创建默认禁用的小额试跟配置。',
        tone: 'success'
      }
    }
    if (candidate.researchState === 'COOLDOWN') {
      return {
        title: '等待冷却后复核',
        detail: candidate.cooldownUntil ? `预计 ${formatDate(candidate.cooldownUntil)} 后重新检查。` : readableCode(candidate.reason),
        tone: 'warning'
      }
    }
    return {
      title: '已停止自动推进',
      detail: readableCode(candidate.reason) || '保留记录，仅用于审计与复盘。',
      tone: 'neutral'
    }
  }

  const primaryGuidance = lastRun?.status === 'RUNNING'
    ? {
        title: '研究任务正在运行',
        description: '系统正在更新来源、评分和状态；完成前无需重复触发。',
        state: undefined as LeaderResearchState | undefined,
        action: '查看运行状态',
        icon: <ClockCircleOutlined />
      }
    : activeSummary.trialReadyCount > 0
      ? {
          title: `有 ${activeSummary.trialReadyCount} 个候选进入建议试跟`,
          description: '先查看硬门槛与风险，再决定是否创建默认禁用的试跟配置。',
          state: 'TRIAL_READY' as LeaderResearchState,
          action: '处理人工决策',
          icon: <CheckCircleOutlined />
        }
      : (fastWatch?.fastWatchCount || 0) > 0
        ? {
            title: `有 ${fastWatch?.fastWatchCount || 0} 个快速观察候选`,
            description: '优先补充纸跟样本、增量评分，并等待 7 天观察门槛。',
            state: 'PAPER' as LeaderResearchState,
            action: '查看纸跟候选',
            icon: <InfoCircleOutlined />
          }
        : {
            title: '当前重点是积累有效纸跟样本',
            description: `${activeSummary.paperCount} 个候选正在纸跟验证；不要仅凭排行榜或单次高分进入试跟。`,
            state: 'PAPER' as LeaderResearchState,
            action: '查看纸跟进度',
            icon: <DatabaseOutlined />
          }

  const columns = [
    {
      title: t('leaderResearch.wallet'),
      key: 'wallet',
      width: 260,
      render: (_: unknown, item: LeaderResearchCandidate) => (
        <Space direction="vertical" size={0}>
          <Text strong>{item.leaderName || item.normalizedWallet.slice(0, 10)}</Text>
          <Text copyable type="secondary" style={{ fontSize: 12, fontFamily: 'monospace' }}>
            {item.normalizedWallet}
          </Text>
        </Space>
      )
    },
    {
      title: t('common.status'),
      dataIndex: 'researchState',
      width: 130,
      render: (state: LeaderResearchState) => (
        <Space direction="vertical" size={0}>
          <Tag color={STATE_COLORS[state]}>{STATE_LABELS[state]}</Tag>
          {state === 'TRIAL_READY' && (
            <Text type="secondary" style={{ fontSize: 12 }}>{t('leaderResearch.trialReadyHint')}</Text>
          )}
        </Space>
      )
    },
    {
      title: t('leaderResearch.score'),
      dataIndex: 'score',
      width: 100,
      render: (score?: string) => <Text strong>{score || '-'}</Text>
    },
    {
      title: t('leaderResearch.strategyType'),
      dataIndex: 'strategyType',
      width: 150,
      render: (strategyType?: string) => strategyTypeTag(strategyType)
    },
    {
      title: t('leaderResearch.paper'),
      key: 'paper',
      width: 220,
      render: (_: unknown, item: LeaderResearchCandidate) => {
        const session = item.latestPaperSession
        if (!session) return <Text type="secondary">-</Text>
        return (
          <Space direction="vertical" size={0}>
            <Text>{t('leaderResearch.copyablePnl')}: {session.copyablePnl}</Text>
            <Text type="secondary">{t('leaderResearch.trades')}: {session.tradeCount} / {t('leaderResearch.filtered')}: {session.filteredCount}</Text>
          </Space>
        )
      }
    },
    {
      title: t('leaderResearch.source'),
      dataIndex: 'source',
      width: 180,
      render: (source?: string) => sourceLabel(source)
    },
    {
      title: '当前卡点 / 下一步',
      key: 'nextStep',
      width: 260,
      render: (_: unknown, item: LeaderResearchCandidate) => {
        const nextStep = candidateNextStep(item)
        return (
          <Space direction="vertical" size={2} className={`leader-next-step is-${nextStep.tone}`}>
            <Text strong>{nextStep.title}</Text>
            <Text type="secondary">{nextStep.detail}</Text>
          </Space>
        )
      }
    },
    {
      title: t('leaderResearch.lastSeen'),
      dataIndex: 'lastSourceSeenAt',
      width: 160,
      render: (value?: number) => formatDate(value)
    },
    {
      title: t('common.actions'),
      key: 'actions',
      fixed: 'right' as const,
      width: 230,
      render: (_: unknown, item: LeaderResearchCandidate) => (
        <Space wrap>
          <Button size="small" onClick={() => openDetail(item)}>
            {t('common.detail')}
          </Button>
          <Button
            size="small"
            type="primary"
            icon={<SafetyCertificateOutlined />}
            disabled={item.researchState !== 'TRIAL_READY'}
            onClick={() => openApproval(item)}
          >
            {t('leaderResearch.createDisabledTrial')}
          </Button>
        </Space>
      )
    }
  ]

  return (
    <Space className="leader-research-page" direction="vertical" size="large" style={{ width: '100%' }}>
      <Card className="leader-research-hero" bordered={false}>
        <div className="leader-research-hero-main">
          <div>
            <Text className="leader-research-eyebrow">研究状态机 · RESEARCH WORKFLOW</Text>
            <Title level={2}>Leader 研究工作台</Title>
            <Paragraph>
              按“发现 → 候选 → 纸跟验证 → 人工试跟决策”推进。每个阶段都展示进入门槛、当前卡点和下一步操作。
            </Paragraph>
          </div>
          <Space className="leader-research-hero-actions" wrap>
            <Button icon={<ReloadOutlined />} loading={loading} onClick={() => loadAll()}>刷新数据</Button>
            <Button icon={<DatabaseOutlined />} onClick={() => setExternalImportOpen(true)}>导入研究候选</Button>
            <Button type="primary" icon={<PlayCircleOutlined />} loading={running || lastRun?.status === 'RUNNING'} onClick={runAgent}>
              运行一次研究
            </Button>
          </Space>
        </div>
        <nav className="leader-research-nav" aria-label="Leader 研究页面导航">
          <a href="#leader-state-machine">状态流程</a>
          <a href="#leader-candidate-workbench">候选工作台</a>
          <a href="#leader-fast-watch">快速观察</a>
          <a href="#leader-advanced-research">高级诊断</a>
          <a href="#leader-source-health">来源健康</a>
        </nav>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            icon={<ExperimentOutlined />}
            message="研究与真实跟单严格隔离"
            description="本页只维护研究状态、纸跟账本和试跟建议。即使人工批准，也只会创建默认禁用的配置，不会自动启用真钱跟单。"
          />
          {activeSummary.sourceLimitations?.length > 0 && (
            <Alert
              type="warning"
              showIcon
              message="当前数据来源存在限制"
              description={activeSummary.sourceLimitations.map(readableCode).join('；')}
            />
          )}
        </Space>
      </Card>

      <section id="leader-state-machine" className="leader-state-section" aria-labelledby="leader-state-title">
        <div className="leader-section-heading">
          <div>
            <Text className="leader-section-kicker">主流程</Text>
            <Title id="leader-state-title" level={3}>候选现在走到哪一步</Title>
            <Paragraph>点击任一阶段即可筛选对应候选。绿色路径代表研究通过，不代表实盘已经启用。</Paragraph>
          </div>
          {stateFilter && (
            <Button icon={<FilterOutlined />} onClick={() => selectState(undefined)}>清除状态筛选</Button>
          )}
        </div>
        <div className="leader-state-grid">
          {STATE_FLOW.map((item, index) => (
            <button
              type="button"
              className={`leader-state-card state-${item.state.toLowerCase()} ${stateFilter === item.state ? 'is-selected' : ''}`}
              key={item.state}
              aria-pressed={stateFilter === item.state}
              onClick={() => selectState(item.state)}
            >
              <span className="leader-state-card-top">
                <span className="leader-state-index">{String(index + 1).padStart(2, '0')}</span>
                <span className="leader-state-count">{stateCounts[item.state].toLocaleString()}</span>
              </span>
              <strong>{STATE_LABELS[item.state]}</strong>
              <span className="leader-state-stage">{item.stage}</span>
              <span className="leader-state-description">{item.description}</span>
              <span className="leader-state-gate">
                <SafetyCertificateOutlined />
                {item.gate}
              </span>
              <span className="leader-state-next">
                {item.next}
                {index < STATE_FLOW.length - 1 && <ArrowRightOutlined />}
              </span>
              {item.state === 'TRIAL_READY' && (
                <span className="leader-state-strict">其中严格可试跟 {activeSummary.strictReadyCount}</span>
              )}
            </button>
          ))}
        </div>
      </section>

      <Card className="leader-guidance-card" bordered={false}>
        <div className="leader-guidance-icon">{primaryGuidance.icon}</div>
        <div className="leader-guidance-copy">
          <Text className="leader-section-kicker">系统建议的下一步</Text>
          <Title level={4}>{primaryGuidance.title}</Title>
          <Paragraph>{primaryGuidance.description}</Paragraph>
        </div>
        <Button
          type="primary"
          onClick={() => {
            if (primaryGuidance.state) {
              selectState(primaryGuidance.state)
            } else {
              document.getElementById('leader-run-status')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
            }
          }}
        >
          {primaryGuidance.action}
        </Button>
      </Card>

      <Card
        id="leader-candidate-workbench"
        className="leader-candidate-workbench"
        title={
          <Space direction="vertical" size={0}>
            <Text strong>候选工作台</Text>
            <Text type="secondary">查看每个候选的当前卡点，并只执行该状态允许的操作。</Text>
          </Space>
        }
        extra={<Tag color={stateFilter ? STATE_COLORS[stateFilter] : 'blue'}>{stateFilter ? STATE_LABELS[stateFilter] : '全部状态'} · {candidates.total}</Tag>}
      >
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Space wrap>
            <Select
              allowClear
              style={{ width: 220 }}
              placeholder="按研究状态筛选"
              value={stateFilter}
              onChange={setStateFilter}
              options={Object.keys(STATE_COLORS).map(state => ({
                value: state,
                label: STATE_LABELS[state as LeaderResearchState]
              }))}
            />
            <Input.Search
              allowClear
              style={{ width: 320 }}
              placeholder="搜索钱包、Leader 名称或原因"
              value={query}
              onChange={event => setQuery(event.target.value)}
              onSearch={() => loadAll()}
              enterButton="搜索"
            />
          </Space>
          <Table
            rowKey="id"
            loading={loading}
            columns={columns}
            dataSource={candidates.list}
            scroll={{ x: 1560 }}
            pagination={{ pageSize: 20, showSizeChanger: false }}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前筛选下没有研究候选" /> }}
          />
        </Space>
      </Card>

      <div id="leader-advanced-research" className="leader-section-heading leader-section-heading-standalone">
        <div>
          <Text className="leader-section-kicker">高级研究区</Text>
          <Title level={3}>漏斗、快速观察与来源诊断</Title>
          <Paragraph>这些工具会扫描大量研究历史，已改为需要时手动加载，避免影响主状态和实时数据。</Paragraph>
        </div>
        <Space wrap>
          <Button icon={<FilterOutlined />} loading={advancedLoading} onClick={loadAdvancedResearch}>
            {funnel || fastWatch ? '重新加载漏斗与快速观察' : '加载漏斗与快速观察'}
          </Button>
          <Button icon={<DatabaseOutlined />} loading={diagnosticsLoading} onClick={loadSourceDiagnostics}>
            {politicsDiagnose || financeDiagnose ? '重新加载来源诊断' : '加载来源诊断'}
          </Button>
        </Space>
      </div>

      {funnel && (
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={8}>
            <Card title={t('leaderResearch.researchFunnelTitle')}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Statistic title={t('leaderResearch.funnelTargetProgress')} value={`${funnel.totalCandidates}/${funnel.targetTotal}`} />
                <Progress percent={Math.min(100, Number(funnel.progressPercent))} />
                <Statistic title={t('leaderResearch.managedLeaders')} value={funnel.managedLeaderTotal} />
                <Statistic title={t('leaderResearch.leaderPool')} value={funnel.leaderPoolTotal} />
                <Statistic title={t('leaderResearch.cleanHighQualityWatchable')} value={funnel.cleanHighScoreTotal} />
                <Text type="secondary">{funnel.criteria}</Text>
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                    <Text strong>{t('leaderResearch.primaryAllocationRatio')}</Text>
                    <Tag color={allocationStatusColor(funnel.allocationHealth.status)}>
                      {funnel.allocationHealth.primaryActualPercent}%
                    </Tag>
                  </Space>
                  <Progress
                    percent={Math.min(100, Number(funnel.allocationHealth.primaryActualPercent))}
                    status={funnel.allocationHealth.status === 'DEFICIT' ? 'exception' : 'normal'}
                  />
                  <Text type="secondary">
                    政治 / 金融 {funnel.allocationHealth.primaryCleanHighCount} · 体育 / 加密市场 {funnel.allocationHealth.secondaryCleanHighCount}
                  </Text>
                  <Text type="secondary">{readableCode(funnel.allocationHealth.message)}</Text>
                </Space>
              </Space>
            </Card>
          </Col>
          <Col xs={24} lg={8}>
            <Card title={t('leaderResearch.categoryConversion')}>
              <Space direction="vertical" style={{ width: '100%' }}>
                {funnel.categories.map(category => (
                  <Space key={category.category} style={{ justifyContent: 'space-between', width: '100%' }}>
                    <Text strong>{categoryLabel(category.category)}</Text>
                    <Text>{t('leaderResearch.categoryConversionItem', {
                      total: category.totalCandidates,
                      paperState: t('leaderResearch.states.PAPER'),
                      paperCount: category.paperCandidates,
                      highScore: t('leaderResearch.categoryHighScore'),
                      cleanHighCount: category.cleanHighScoreCandidates
                    })}</Text>
                    <Tag color={category.cleanHighScoreCandidates > 0 ? 'green' : 'default'}>
                      {category.topScore || '-'}
                    </Tag>
                  </Space>
                ))}
              </Space>
            </Card>
          </Col>
          <Col xs={24} lg={8}>
            <Card title={t('leaderResearch.priorityCandidatesTitle')}>
              {funnel.priorityCandidates.length > 0 ? (
                <Space direction="vertical" style={{ width: '100%' }}>
                  {funnel.priorityCandidates.slice(0, 5).map(candidate => (
                    <Space key={candidate.candidateId} style={{ justifyContent: 'space-between', width: '100%' }}>
                      <Space direction="vertical" size={0}>
                        <Text strong>#{candidate.candidateId} {candidate.wallet.slice(0, 10)}...</Text>
                        <Text type="secondary">{t('leaderResearch.priorityCandidateMeta', {
                          category: candidate.category,
                          tradeCount: candidate.tradeCount,
                          trades: t('leaderResearch.trades'),
                          pnl: candidate.copyablePnl
                        })}</Text>
                        <Text type="secondary">
                          {candidate.trialReadiness.level === 'FAST_WATCH'
                            ? t('leaderResearch.fastWatchNotReleased')
                            : candidate.trialReadiness.eligible
                              ? candidate.trialReadiness.label
                              : `${candidate.trialReadiness.label} · ${candidate.trialReadiness.blockers[0] || candidate.trialReadiness.fastWatchBlockers[0] || t('leaderResearch.waitForMoreSamples')}`}
                        </Text>
                        {formatTrialEta(candidate.trialReadiness) && (
                          <Text type="secondary">{formatTrialEta(candidate.trialReadiness)}</Text>
                        )}
                      </Space>
                      <Space direction="vertical" size={0} align="end">
                        <Tag color="green">{candidate.score}</Tag>
                        <Tag color={readinessColor(candidate.trialReadiness.level)}>
                          {candidate.trialReadiness.label}
                        </Tag>
                        <Tag color={candidate.trialReadiness.eligible ? 'green' : 'gold'}>
                          {candidate.trialReadiness.stableHighScoreCount}/{candidate.trialReadiness.requiredStableHighScoreCount}
                        </Tag>
                      </Space>
                    </Space>
                  ))}
                </Space>
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('leaderResearch.noHighQualityCandidates')} />
              )}
            </Card>
          </Col>
        </Row>
      )}

      {fastWatch && (
        <Card
          id="leader-fast-watch"
          className="leader-fast-watch-card"
          title={t('leaderResearch.fastWatchCandidatesTitle')}
          extra={
            <Space wrap>
              <Tag color="blue">快速观察 {fastWatch.fastWatchCount}</Tag>
              <Tag color="green">建议试跟 {fastWatch.trialReadyCount}</Tag>
              <Button
                size="small"
                loading={fastWatchAction === 'score'}
                disabled={fastWatch.items.length === 0 || fastWatchAction !== null || trialReadyRefreshAction !== null}
                onClick={scoreFastWatch}
              >
                {t('leaderResearch.scoreIncrement')}
              </Button>
              <Button
                size="small"
                type="primary"
                loading={fastWatchAction === 'process'}
                disabled={fastWatch.items.length === 0 || fastWatchAction !== null || trialReadyRefreshAction !== null}
                onClick={processFastWatch}
              >
                {t('leaderResearch.advancePaper')}
              </Button>
              <Button
                size="small"
                type="primary"
                loading={trialReadyRefreshAction !== null}
                disabled={fastWatch.items.length === 0 || fastWatchAction !== null || trialReadyRefreshAction !== null}
                onClick={refreshHighQualityTrialReady}
              >
                {t('leaderResearch.refreshHighQualityStatus')}
              </Button>
              <Button size="small" icon={<ReloadOutlined />} onClick={() => loadAll(false)}>
                {t('common.refresh')}
              </Button>
            </Space>
          }
        >
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Row gutter={[12, 12]}>
              <Col xs={12} md={6}><Statistic title={t('common.total')} value={fastWatch.total} /></Col>
              <Col xs={12} md={6}><Statistic title={t('leaderResearch.fastWatch')} value={fastWatch.fastWatchCount} /></Col>
              <Col xs={12} md={6}><Statistic title={t('leaderResearch.states.TRIAL_READY')} value={fastWatch.trialReadyCount} /></Col>
              <Col xs={12} md={6}><Statistic title={t('leaderResearch.coveredCategories')} value={fastWatch.categories.join(' / ')} /></Col>
            </Row>
            <Text type="secondary">{readableCode(fastWatch.criteria)}</Text>
            {trialReadyRefreshResult && (
              <Alert
                showIcon
                type={trialReadyRefreshResult.trialReadyCandidateIds.length > 0 ? 'success' : 'info'}
                message={trialReadyRefreshResult.dryRun
                  ? t('leaderResearch.trialReadyRefreshDryRunMessage', {
                      scanned: trialReadyRefreshResult.scannedCount,
                      selected: trialReadyRefreshResult.selectedCount,
                      ready: trialReadyRefreshResult.trialReadyCandidateIds.length
                    })
                  : t('leaderResearch.trialReadyRefreshLiveMessage', {
                      scanned: trialReadyRefreshResult.scannedCount,
                      promoted: trialReadyRefreshResult.trialReadyCandidateIds.length
                    })}
                description={trialReadyRefreshResult.items.slice(0, 5).map(item => `#${item.candidateId} ${readableCode(item.action)}：${readableCode(item.reason)}`).join('；')}
              />
            )}
            {fastWatch.items.length > 0 ? (
              <Row gutter={[12, 12]}>
                {fastWatch.items.slice(0, 8).map(candidate => (
                  <Col xs={24} md={12} xl={6} key={candidate.candidateId}>
                    <Card size="small">
                      <Space direction="vertical" style={{ width: '100%' }} size={4}>
                        <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                          <Text strong>#{candidate.candidateId}</Text>
                          <Tag color={readinessColor(candidate.trialReadiness.level)}>
                            {candidate.trialReadiness.label}
                          </Tag>
                        </Space>
                        <Text copyable={{ text: candidate.wallet }}>{candidate.wallet.slice(0, 10)}...{candidate.wallet.slice(-6)}</Text>
                        <Space wrap size={4}>
                          <Tag color={candidate.category === 'politics' ? 'purple' : 'cyan'}>{categoryLabel(candidate.category)}</Tag>
                          {strategyTypeTag(candidate.strategyType)}
                          <Tag color="green">{candidate.score}</Tag>
                          <Tag>{t('leaderResearch.tradeCountLabel', { count: candidate.tradeCount, trades: t('leaderResearch.trades') })}</Tag>
                        </Space>
                        <Text type="secondary">{t('leaderResearch.fastWatchPnlFiltered', {
                          pnl: candidate.copyablePnl,
                          ratio: candidate.filteredRatio,
                          filterLabel: t('leaderResearch.filtered')
                        })}</Text>
                        <Text type="secondary">{t('leaderResearch.fastWatchAgeStable', {
                          ageLabel: t('leaderResearch.ageLabel'),
                          ageHours: candidate.trialReadiness.ageHours,
                          stableLabel: t('leaderResearch.stableLabel'),
                          stable: candidate.trialReadiness.stableHighScoreCount,
                          required: candidate.trialReadiness.requiredStableHighScoreCount
                        })}</Text>
                        {formatTrialEta(candidate.trialReadiness) && (
                          <Text type="secondary">{formatTrialEta(candidate.trialReadiness)}</Text>
                        )}
                        <Text type="secondary">
                          {readableCode(candidate.trialReadiness.blockers[0] || candidate.trialReadiness.fastWatchBlockers[0]) || t('leaderResearch.waitForManualReview')}
                        </Text>
                      </Space>
                    </Card>
                  </Col>
                ))}
              </Row>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('leaderResearch.noFastWatchCandidates')} />
            )}
            {lastPaperProcessSummaries.length > 0 && (
              <Card size="small" title={t('leaderResearch.recentAdvanceResults')}>
                <Row gutter={[12, 12]}>
                  {lastPaperProcessSummaries.slice(0, 8).map(item => (
                    <Col xs={24} md={12} xl={6} key={item.candidateId}>
                      <Space direction="vertical" size={4} style={{ width: '100%' }}>
                        <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                          <Text strong>#{item.candidateId}</Text>
                          <Tag color={item.tradeCountDelta > 0 ? 'green' : item.filteredCountDelta > 0 ? 'orange' : 'default'}>
                            {t('leaderResearch.tradeDelta', { count: item.tradeCountDelta, trades: t('leaderResearch.trades') })}
                          </Tag>
                        </Space>
                        <Text copyable={{ text: item.wallet }}>{item.wallet.slice(0, 10)}...{item.wallet.slice(-6)}</Text>
                        <Text type="secondary">
                          {t('leaderResearch.advanceResultTradeFilter', {
                            beforeTradeCount: item.beforeTradeCount,
                            afterTradeCount: item.afterTradeCount,
                            beforeFilteredCount: item.beforeFilteredCount,
                            afterFilteredCount: item.afterFilteredCount
                          })}
                        </Text>
                        <Text type="secondary">
                          {t('leaderResearch.advanceResultPnl', {
                            beforePnl: item.beforeCopyablePnl,
                            afterPnl: item.afterCopyablePnl,
                            delta: item.copyablePnlDelta
                          })}
                        </Text>
                        <Space wrap size={4}>
                          <Tag>{t('leaderResearch.processedCount', { count: item.processed })}</Tag>
                          <Tag color={item.filtered > 0 ? 'orange' : 'default'}>{t('leaderResearch.filteredCount', { count: item.filtered })}</Tag>
                          <Tag color={item.failed > 0 ? 'red' : 'default'}>{t('leaderResearch.failedCount', { count: item.failed })}</Tag>
                        </Space>
                      </Space>
                    </Col>
                  ))}
                </Row>
              </Card>
            )}
          </Space>
        </Card>
      )}

      {politicsDiagnose && (
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={12}>
            <Card title={t('leaderResearch.politicsSourceDiagnosis')}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Row gutter={[12, 12]}>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.politicsScannedWallets')} value={politicsDiagnose.scannedWallets} /></Col>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.politicsPassedThreshold')} value={politicsDiagnose.passImportCriteria} /></Col>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.politicsEligibleForPaperNow')} value={politicsDiagnose.eligibleForPaperNow} /></Col>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.politicsUnknownWallets')} value={politicsDiagnose.unknownWallets} /></Col>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.politicsExistingWallets')} value={politicsDiagnose.existingWallets} /></Col>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.politicsPaperWallets')} value={politicsDiagnose.paperWallets} /></Col>
                </Row>
                <Progress
                  percent={politicsDiagnose.scannedWallets > 0 ? Number(((politicsDiagnose.passImportCriteria / politicsDiagnose.scannedWallets) * 100).toFixed(2)) : 0}
                  status={politicsDiagnose.eligibleForPaperNow > 0 ? 'active' : 'normal'}
                />
                <Text type="secondary">
                  {t('leaderResearch.politicsLookbackCleanHigh', {
                    lookback: t('leaderResearch.lookbackLabel'),
                    days: politicsDiagnose.lookbackDays,
                    cleanHigh: t('leaderResearch.cleanHighLabel'),
                    count: politicsDiagnose.cleanHighWallets
                  })}
                </Text>
                <Alert
                  type={politicsDiagnose.eligibleForPaperNow > 0 ? 'success' : 'info'}
                  showIcon
                  message={politicsDiagnose.eligibleForPaperNow > 0
                    ? t('leaderResearch.politicsNewPaperCandidatesFound', { count: politicsDiagnose.eligibleForPaperNow })
                    : t('leaderResearch.politicsNoNewPaperCandidates')}
                />
              </Space>
            </Card>
          </Col>
          <Col xs={24} lg={12}>
            <Card title={t('leaderResearch.politicsSourceBlockers')}>
              <Space direction="vertical" style={{ width: '100%' }}>
                {politicsDiagnose.buckets.slice(0, 6).map(bucket => (
                  <Space key={bucket.bucket} style={{ justifyContent: 'space-between', width: '100%' }}>
                    <Space direction="vertical" size={0}>
                      <Text strong>{bucket.bucket}</Text>
                      <Text type="secondary">{bucket.description}</Text>
                    </Space>
                    <Tag color={bucket.bucket === 'pass_import_criteria' ? 'green' : 'orange'}>{bucket.count}</Tag>
                  </Space>
                ))}
              </Space>
            </Card>
          </Col>
          {financeDiagnose && (
            <Col xs={24}>
              <Card
                title={t('leaderResearch.financeSourceDiagnosis')}
                extra={
                  <Space wrap>
                    <Tag color="green">导入候选 {recommendationCount(financeDiagnose, 'IMPORT_NOW')}</Tag>
                    <Tag color="gold">刷新评分 {recommendationCount(financeDiagnose, 'SCORE_REFRESH')}</Tag>
                    <Tag color="blue">推进纸跟 {recommendationCount(financeDiagnose, 'PAPER_PROCESS')}</Tag>
                    <Tag color="purple">快速观察复核 {recommendationCount(financeDiagnose, 'FAST_WATCH_REVIEW')}</Tag>
                  </Space>
                }
              >
                <Row gutter={[16, 16]}>
                  <Col xs={12} md={6}><Statistic title={t('leaderResearch.financeScannedWallets')} value={financeDiagnose.scannedWallets} /></Col>
                  <Col xs={12} md={6}><Statistic title={t('leaderResearch.importable')} value={financeDiagnose.eligibleForPaperNow} /></Col>
                  <Col xs={12} md={6}><Statistic title={t('leaderResearch.states.PAPER')} value={financeDiagnose.paperWallets} /></Col>
                  <Col xs={12} md={6}><Statistic title={t('leaderResearch.cleanHighScore')} value={financeDiagnose.cleanHighWallets} /></Col>
                </Row>
                <Space size={[8, 8]} wrap style={{ marginTop: 12 }}>
                  {financeDiagnose.buckets.slice(0, 6).map(bucket => (
                    <Tag key={bucket.bucket} color={bucket.bucket === 'pass_import_criteria' ? 'green' : 'orange'}>
                      {bucket.bucket}: {bucket.count}
                    </Tag>
                  ))}
                </Space>
              </Card>
            </Col>
          )}
          <Col xs={24}>
            <Card
              title={t('leaderResearch.politicsRecommendationActions')}
              extra={
                <Space wrap>
                  <Tag color="green">导入候选 {politicsImportWallets().length}</Tag>
                  <Tag color="gold">刷新评分 {politicsScoreRefreshCandidateIds().length}</Tag>
                  <Tag color="blue">推进纸跟 {politicsPaperProcessCandidateIds().length}</Tag>
                  <Tag color="purple">快速观察复核 {politicsFastWatchReviewRecommendations().length}</Tag>
                  <Button
                    size="small"
                    loading={politicsAction === 'executePreview'}
                    disabled={politicsAction !== null || fastWatchAction !== null}
                    onClick={previewPoliticsRecommendationLoop}
                  >
                    {t('leaderResearch.backendLoopPreview')}
                  </Button>
                  <Button
                    size="small"
                    loading={politicsAction === 'importPreview'}
                    disabled={politicsImportWallets().length === 0 || politicsAction !== null || fastWatchAction !== null}
                    onClick={() => importPoliticsRecommendations(true)}
                  >
                    {t('leaderResearch.previewImport')}
                  </Button>
                  <Button
                    size="small"
                    danger
                    loading={politicsAction === 'importConfirm'}
                    disabled={politicsImportWallets().length === 0 || politicsAction !== null || fastWatchAction !== null}
                    onClick={() => importPoliticsRecommendations(false)}
                  >
                    {t('leaderResearch.confirmImport')}
                  </Button>
                  <Button
                    size="small"
                    loading={politicsAction === 'scoreRefresh'}
                    disabled={politicsScoreRefreshCandidateIds().length === 0 || politicsAction !== null || fastWatchAction !== null}
                    onClick={scoreRefreshPoliticsRecommendations}
                  >
                    {t('leaderResearch.refreshScorePromotion')}
                  </Button>
                  <Button
                    size="small"
                    type="primary"
                    loading={politicsAction === 'process'}
                    disabled={politicsPaperProcessCandidateIds().length === 0 || politicsAction !== null || fastWatchAction !== null}
                    onClick={processPoliticsRecommendations}
                  >
                    {t('leaderResearch.executePaperRecommendations')}
                  </Button>
                </Space>
              }
            >
              {politicsDiagnose.recommendations.length > 0 ? (
                <Space direction="vertical" style={{ width: '100%' }} size="middle">
                  {politicsImportResult && (
                    <Alert
                      showIcon
                      type={politicsImportResult.dryRun ? 'info' : 'success'}
                      message={politicsImportResult.dryRun
                        ? t('leaderResearch.importPreviewResultMessage', {
                            selected: politicsImportResult.selectedTotal,
                            created: politicsImportResult.createdTotal,
                            updated: politicsImportResult.updatedTotal,
                            skipped: politicsImportResult.skippedExistingTotal + politicsImportResult.skippedLockedTotal
                          })
                        : t('leaderResearch.importResultMessage', {
                            selected: politicsImportResult.selectedTotal,
                            created: politicsImportResult.createdTotal,
                            updated: politicsImportResult.updatedTotal,
                            skipped: politicsImportResult.skippedExistingTotal + politicsImportResult.skippedLockedTotal
                          })}
                      description={politicsImportResult.previewItems.slice(0, 5).map(item => `${item.action} ${item.wallet.slice(0, 10)}...${item.wallet.slice(-6)}`).join(' · ') || t('leaderResearch.noPreviewItems')}
                    />
                  )}
                  {politicsPromotionResult && (
                    <Alert
                      showIcon
                      type={politicsPromotionResult.promotedTotal > 0 ? 'success' : 'info'}
                      message={t('leaderResearch.scorePromotionResultMessage', {
                            selected: politicsPromotionResult.selectedTotal,
                            paper: 'PAPER',
                            promoted: politicsPromotionResult.promotedTotal,
                            skippedRisk: politicsPromotionResult.skippedRiskTotal
                          })}
                      description={politicsPromotionResult.items.slice(0, 5).map(item => `#${item.candidateId} ${item.previousState}->${item.nextState}`).join(' · ') || t('leaderResearch.noPromotionItems')}
                    />
                  )}
                  {politicsExecutionResult && (
                    <Alert
                      showIcon
                      type="info"
                      message={politicsExecutionResult.dryRun
                          ? t('leaderResearch.backendLoopPreviewMessage', {
                              importCount: politicsExecutionResult.recommendationCounts.IMPORT_NOW || 0,
                              scoreCount: politicsExecutionResult.recommendationCounts.SCORE_REFRESH || 0,
                              paperCount: politicsExecutionResult.recommendationCounts.PAPER_PROCESS || 0,
                              reviewCount: politicsExecutionResult.recommendationCounts.FAST_WATCH_REVIEW || 0
                            })
                          : t('leaderResearch.backendLoopExecutionMessage', {
                              importCount: politicsExecutionResult.recommendationCounts.IMPORT_NOW || 0,
                              scoreCount: politicsExecutionResult.recommendationCounts.SCORE_REFRESH || 0,
                              paperCount: politicsExecutionResult.recommendationCounts.PAPER_PROCESS || 0,
                              reviewCount: politicsExecutionResult.recommendationCounts.FAST_WATCH_REVIEW || 0
                            })}
                      description={politicsExecutionResult.plannedActions.map(item => `${item.action}: ${item.selectedCount}${item.skippedReason ? ` (${item.skippedReason})` : ''}`).join(' · ')}
                    />
                  )}
                  {latestPoliticsExecution && (
                    <Alert
                      showIcon
                      type={latestPoliticsExecution.status === 'SUCCESS' ? 'success' : 'warning'}
                      message={t('leaderResearch.latestBackendLoopMessage', {
                            id: latestPoliticsExecution.id,
                            status: latestPoliticsExecution.status,
                            mode: latestPoliticsExecution.dryRun ? t('leaderResearch.dryRun') : t('leaderResearch.liveMode'),
                            date: formatDate(latestPoliticsExecution.startedAt)
                          })}
                      description={latestPoliticsExecution.plannedActions.map(item => `${item.action}: ${item.selectedCount}`).join(' · ') || latestPoliticsExecution.errorMessage || t('leaderResearch.noActionDetails')}
                    />
                  )}
                  <Row gutter={[12, 12]}>
                    {politicsDiagnose.recommendations.slice(0, 8).map(item => (
                      <Col xs={24} md={12} xl={6} key={`${item.recommendation}-${item.wallet}`}>
                        <Space direction="vertical" size={4} style={{ width: '100%' }}>
                          <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                            <Text strong>{item.candidateId ? `#${item.candidateId}` : item.wallet.slice(0, 10)}</Text>
                            <Tag color={
                              item.recommendation === 'IMPORT_NOW' ? 'green'
                                : item.recommendation === 'PAPER_PROCESS' ? 'blue'
                                  : item.recommendation === 'FAST_WATCH_REVIEW' ? 'purple'
                                    : 'gold'
                            }>
                              {RECOMMENDATION_LABELS[item.recommendation] || readableCode(item.recommendation)}
                            </Tag>
                          </Space>
                          <Text copyable={{ text: item.wallet }}>{item.wallet.slice(0, 10)}...{item.wallet.slice(-6)}</Text>
                          <Text type="secondary">{readableCode(item.reason)}</Text>
                          <Text type="secondary">
                            {t('leaderResearch.sourceSampleMeta', {
                              events: item.totalEvents,
                              eventLabel: t('leaderResearch.eventCountLabel'),
                              markets: item.distinctMarkets,
                              marketLabel: t('leaderResearch.marketCountLabel'),
                              buySellLabel: t('leaderResearch.buySellLabel'),
                              buy: item.buyEvents,
                              sell: item.sellEvents
                            })}
                          </Text>
                          <Space wrap size={4}>
                            <Tag color={item.currentScore ? 'geekblue' : 'default'}>{t('leaderResearch.scoreLabel')} {item.currentScore || '-'}</Tag>
                            <Tag>{t('leaderResearch.paperTradeCount', { value: item.paperTradeCount ?? '-' })}</Tag>
                            <Tag color={(Number(item.copyablePnl || 0) > 0) ? 'green' : 'default'}>PnL {item.copyablePnl || '-'}</Tag>
                            <Tag>{t('leaderResearch.priorityLabel')} {item.priority}</Tag>
                            {item.recommendation === 'FAST_WATCH_REVIEW' && item.candidateId && (
                              <Button
                                size="small"
                                type="primary"
                                disabled={item.currentState !== 'TRIAL_READY'}
                                loading={approvalLoading && approvalCandidate?.id !== item.candidateId}
                                onClick={() => openApprovalByCandidateId(item.candidateId!)}
                              >
                                {item.currentState === 'TRIAL_READY' ? t('leaderResearch.createDisabledTrial') : t('leaderResearch.waitingForTrialReady')}
                              </Button>
                            )}
                          </Space>
                        </Space>
                      </Col>
                    ))}
                  </Row>
                </Space>
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('leaderResearch.noPoliticsRecommendations')} />
              )}
            </Card>
          </Col>
          <Col xs={24}>
            <Card title={t('leaderResearch.politicsSourceSamples')}>
              <Space direction="vertical" style={{ width: '100%' }}>
                {politicsDiagnose.samples.slice(0, 5).map(sample => (
                  <Space key={sample.wallet} style={{ justifyContent: 'space-between', width: '100%' }}>
                    <Space direction="vertical" size={0}>
                      <Text strong>{sample.wallet.slice(0, 12)}...</Text>
                      <Text type="secondary">
                        {sample.totalEvents} 条活动 · {sample.distinctMarkets} 个市场 · 买入 / 卖出 {sample.buyEvents}/{sample.sellEvents}
                      </Text>
                      <Text type="secondary">
                        {t('leaderResearch.sourceSampleThreshold', {
                          safeLabel: t('leaderResearch.safeLabel'),
                          safeRatio: sample.safePriceRatio,
                          tailLabel: t('leaderResearch.tailLabel'),
                          tailRatio: sample.tailPriceRatio,
                          result: sample.blockers[0] || t('leaderResearch.passedCurrentThreshold')
                        })}
                      </Text>
                    </Space>
                    <Space direction="vertical" size={0} align="end">
                      <Tag color={sample.action === 'UNKNOWN_ELIGIBLE' ? 'green' : sample.currentState === 'PAPER' ? 'blue' : 'default'}>
                        {sample.action}
                      </Tag>
                      <Tag color={sample.currentScore ? 'geekblue' : 'default'}>{sample.currentScore || '-'}</Tag>
                      <Tag>{t('leaderResearch.paperTradeCount', { value: sample.paperTradeCount ?? '-' })}</Tag>
                    </Space>
                  </Space>
                ))}
              </Space>
            </Card>
          </Col>
        </Row>
      )}

      {(marketPeerStrict || marketPeerRelaxed) && (
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={12}>
            <Card
              title={t('leaderResearch.hotMarketPeerSource')}
              extra={
                <Space>
                  <Button size="small" icon={<ReloadOutlined />} onClick={() => loadAll(false)}>
                    strict
                  </Button>
                  <Button size="small" loading={marketPeerLoading} onClick={runMarketPeerRelaxed}>
                    relaxed finance
                  </Button>
                </Space>
              }
            >
              {marketPeerStrict ? (
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Row gutter={[12, 12]}>
                    <Col xs={12} sm={8}><Statistic title={t('leaderResearch.selectedWallets')} value={marketPeerStrict.selectedTotal} /></Col>
                    <Col xs={12} sm={8}><Statistic title={t('leaderResearch.creatable')} value={marketPeerStrict.createdTotal} /></Col>
                    <Col xs={12} sm={8}><Statistic title={t('leaderResearch.updatable')} value={marketPeerStrict.updatedTotal} /></Col>
                  </Row>
                  <Space wrap>
                    {marketPeerStrict.categories.map(category => (
                      <Tag key={category.category} color={category.createdCount > 0 ? 'green' : category.selectedCount > 0 ? 'blue' : 'default'}>
                        {category.category}: {category.selectedCount} / {t('leaderResearch.newCount', { count: category.createdCount })}
                      </Tag>
                    ))}
                  </Space>
                  <Alert
                    type={marketPeerStrict.createdTotal > 0 ? 'success' : 'info'}
                    showIcon
                    message={marketPeerStrict.createdTotal > 0
                      ? t('leaderResearch.strictSourceNewCandidatesFound', { count: marketPeerStrict.createdTotal })
                      : t('leaderResearch.strictSourceNoNewCandidates')}
                  />
                </Space>
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('leaderResearch.noStrictSourceResults')} />
              )}
            </Card>
          </Col>
          <Col xs={24} lg={12}>
            <Card title={t('leaderResearch.secondSourceSamples')}>
              <Space direction="vertical" style={{ width: '100%' }}>
                {(marketPeerRelaxed || marketPeerStrict)?.previewItems.slice(0, 5).map(sample => (
                  <Space key={`${sample.category}-${sample.wallet}-${sample.action}`} style={{ justifyContent: 'space-between', width: '100%' }}>
                    <Space direction="vertical" size={0}>
                      <Text strong>{sample.wallet.slice(0, 12)}...</Text>
                      <Text type="secondary">
                        {sample.category} · {t('leaderResearch.sourceSampleMeta', {
                          events: sample.totalEvents,
                          eventLabel: t('leaderResearch.eventCountLabel'),
                          markets: sample.distinctMarkets,
                          marketLabel: t('leaderResearch.marketCountLabel'),
                          buySellLabel: t('leaderResearch.buySellLabel'),
                          buy: sample.buyEvents,
                          sell: sample.sellEvents
                        })}
                      </Text>
                      <Text type="secondary">
                        {sample.topMarkets.slice(0, 2).join(' · ') || t('leaderResearch.noMarketSample')}
                      </Text>
                    </Space>
                    <Space direction="vertical" size={0} align="end">
                      <Tag color={sample.action === 'CREATE' ? 'green' : sample.action === 'UPDATE' ? 'blue' : 'default'}>
                        {sample.action}
                      </Tag>
                      <Text type="secondary">{sample.totalAmount} USDC</Text>
                    </Space>
                  </Space>
                )) || (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('leaderResearch.noSecondSourceSamples')} />
                )}
                {marketPeerRelaxed && (
                  <Alert
                    type={marketPeerRelaxed.createdTotal > 0 ? 'success' : 'warning'}
                    showIcon
                    message={t('leaderResearch.relaxedSourceResultMessage', {
                      category: 'relaxed finance',
                      selected: marketPeerRelaxed.selectedTotal,
                      created: marketPeerRelaxed.createdTotal,
                      updated: marketPeerRelaxed.updatedTotal
                    })}
                  />
                )}
              </Space>
            </Card>
          </Col>
        </Row>
      )}

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card id="leader-run-status" title="最近一次研究运行">
            {lastRun ? (
              <Descriptions size="small" column={1}>
                <Descriptions.Item label={t('common.status')}>
                  <Tag color={lastRun.partialFailure ? 'orange' : lastRun.status === 'SUCCESS' ? 'green' : 'default'}>
                    {lastRun.partialFailure ? '部分成功' : RUN_STATUS_LABELS[lastRun.status] || lastRun.status}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label={t('leaderResearch.lastRun')}>{formatDate(lastRun.startedAt)}</Descriptions.Item>
                <Descriptions.Item label={t('leaderResearch.duration')}>{lastRun.durationMs ?? '-'} ms</Descriptions.Item>
                <Descriptions.Item label={t('leaderResearch.sourceCounts')}>{lastRun.sourceCountsJson || '-'}</Descriptions.Item>
                <Descriptions.Item label={t('leaderResearch.candidateCounts')}>{lastRun.candidateCountsJson || '-'}</Descriptions.Item>
                {(lastRun.errorMessage || lastRun.skippedReason) && (
                  <Descriptions.Item label={t('leaderResearch.reason')}>{lastRun.errorMessage || lastRun.skippedReason}</Descriptions.Item>
                )}
              </Descriptions>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('leaderResearch.noRuns')} />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title={t('leaderResearch.pendingDecisions')}>
            {pendingDecisions.length > 0 ? (
              <Space direction="vertical" style={{ width: '100%' }}>
                {pendingDecisions.slice(0, 5).map(candidate => (
                  <Card key={candidate.id} size="small">
                    <Space style={{ justifyContent: 'space-between', width: '100%' }} wrap>
                      <Space direction="vertical" size={0}>
                        <Text strong>{candidate.leaderName || candidate.normalizedWallet.slice(0, 10)}</Text>
                        <Text type="secondary">{t('leaderResearch.trialReadyHint')}</Text>
                      </Space>
                      <Button size="small" type="primary" loading={approvalLoading && approvalCandidate?.id === candidate.id} onClick={() => openApproval(candidate)}>
                        {t('leaderResearch.createDisabledTrial')}
                      </Button>
                    </Space>
                  </Card>
                ))}
              </Space>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('leaderResearch.noPendingDecisions')} />
            )}
          </Card>
        </Col>
      </Row>

      <Card id="leader-source-health" title="数据来源健康">
        <Row gutter={[12, 12]}>
          {sourceHealth.map(source => (
            <Col xs={24} md={12} lg={6} key={source.sourceType}>
              <Card size="small">
                <Space direction="vertical" size={4}>
                  <Badge status={source.status === 'SUCCESS' ? 'success' : source.status === 'DISABLED' ? 'default' : 'warning'} text={sourceLabel(source.sourceType)} />
                  <Tag>{SOURCE_STATUS_LABELS[source.status] || source.status}</Tag>
                  <Text type="secondary">{t('leaderResearch.candidates')}: {source.lastCandidateCount}</Text>
                  <Text type="secondary">{formatDate(source.lastRunAt)}</Text>
                  {(source.disabledReason || source.errorMessage) && <Text type="secondary">{readableCode(source.disabledReason || source.errorMessage)}</Text>}
                </Space>
              </Card>
            </Col>
          ))}
        </Row>
      </Card>

      <Drawer
        width={880}
        open={!!detail}
        title={t('leaderResearch.detailTitle')}
        onClose={() => setDetail(null)}
        loading={detailLoading}
      >
        {detail && (
          <Tabs
            items={[
              {
                key: 'overview',
                label: t('common.overview'),
                children: (
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Descriptions bordered column={1} size="small">
                      <Descriptions.Item label={t('leaderResearch.wallet')}>{detail.candidate.normalizedWallet}</Descriptions.Item>
                      <Descriptions.Item label={t('common.status')}>{STATE_LABELS[detail.candidate.researchState]}</Descriptions.Item>
                      <Descriptions.Item label={t('leaderResearch.score')}>{detail.candidate.score || '-'}</Descriptions.Item>
                      <Descriptions.Item label={t('leaderResearch.strategyType')}>{strategyTypeTag(detail.candidate.strategyType)}</Descriptions.Item>
                      <Descriptions.Item label={t('leaderResearch.reason')}>{readableCode(detail.candidate.reason) || '-'}</Descriptions.Item>
                      <Descriptions.Item label={t('leaderResearch.riskFlags')}>
                        {detail.candidate.riskFlags.length > 0
                          ? detail.candidate.riskFlags.map(flag => <Tag color="orange" key={flag}>{readableCode(flag)}</Tag>)
                          : '无'}
                      </Descriptions.Item>
                      <Descriptions.Item label={t('leaderResearch.sourceEvidence')}>{readableCode(detail.candidate.sourceEvidence) || '-'}</Descriptions.Item>
                    </Descriptions>
                    {detail.latestScore && (
                      <Descriptions bordered size="small" column={2} title={t('leaderResearch.scoreBreakdown')}>
                        <Descriptions.Item label={t('leaderResearch.scoreProfit')}>{detail.latestScore.profitSignal}</Descriptions.Item>
                        <Descriptions.Item label={t('leaderResearch.scoreRepeatability')}>{detail.latestScore.repeatability}</Descriptions.Item>
                        <Descriptions.Item label={t('leaderResearch.scoreLiquidityFit')}>{detail.latestScore.liquidityFit}</Descriptions.Item>
                        <Descriptions.Item label={t('leaderResearch.scoreEntry')}>{detail.latestScore.entryPriceFit}</Descriptions.Item>
                        <Descriptions.Item label={t('leaderResearch.scoreSlippage')}>{detail.latestScore.slippageRisk}</Descriptions.Item>
                        <Descriptions.Item label={t('leaderResearch.scoreDrawdown')}>{detail.latestScore.drawdownRisk}</Descriptions.Item>
                      </Descriptions>
                    )}
                  </Space>
                )
              },
              {
                key: 'trades',
                label: t('leaderResearch.paperTrades'),
                children: <PaperTradeTable trades={detail.paperTrades} />
              },
              {
                key: 'positions',
                label: t('leaderResearch.paperPositions'),
                children: <PaperPositionTable positions={detail.paperPositions} />
              },
              {
                key: 'events',
                label: t('leaderResearch.events'),
                children: (
                  <Table
                    rowKey="id"
                    size="small"
                    dataSource={detail.events}
                    columns={[
                      { title: t('common.time'), dataIndex: 'createdAt', render: formatDate },
                      { title: t('leaderResearch.eventType'), dataIndex: 'eventType', render: readableCode },
                      { title: t('leaderResearch.reason'), dataIndex: 'reason', render: readableCode }
                    ]}
                  />
                )
              }
            ]}
          />
        )}
      </Drawer>

      <Modal
        open={!!approvalCandidate}
        title={t('leaderResearch.createDisabledTrial')}
        onCancel={() => {
          setApprovalCandidate(null)
          setApprovalPreviewResult(null)
        }}
        onOk={submitApproval}
        confirmLoading={approvalLoading}
        okButtonProps={{ disabled: !approvalPreviewResult?.canCreate }}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Alert
            type="warning"
            showIcon
            message={t('leaderResearch.approvalSafetyTitle')}
            description={t('leaderResearch.approvalSafetyDesc')}
          />
          {approvalPreviewResult && (
            <Alert
              type={approvalPreviewResult.canCreate ? 'success' : 'error'}
              showIcon
              message={approvalPreviewResult.canCreate ? t('leaderResearch.approvalPreviewCanCreate') : t('leaderResearch.approvalPreviewBlocked')}
              description={
                approvalPreviewResult.blockerCodes.length > 0
                  ? approvalPreviewResult.blockerCodes.join(', ')
                  : `${approvalPreviewResult.category} · ${approvalPreviewResult.strategyType || 'unknown'}`
              }
            />
          )}
            <Form form={approvalForm} layout="vertical">
            <Descriptions bordered size="small" column={1} title={t('leaderResearch.approvalPreview')}>
              <Descriptions.Item label={t('leaderResearch.fixedAmount')}>{activeApprovalPreview.fixedAmount}</Descriptions.Item>
              <Descriptions.Item label={t('leaderResearch.maxDailyLoss')}>{activeApprovalPreview.maxDailyLoss}</Descriptions.Item>
              <Descriptions.Item label={t('leaderResearch.maxDailyOrders')}>{activeApprovalPreview.maxDailyOrders}</Descriptions.Item>
              <Descriptions.Item label={t('leaderResearch.priceRange')}>{activeApprovalPreview.priceRange}</Descriptions.Item>
              <Descriptions.Item label={t('leaderResearch.maxPositionValue')}>{activeApprovalPreview.maxPositionValue}</Descriptions.Item>
            </Descriptions>
            <Form.Item name="accountId" label={t('leaderPool.account')} rules={[{ required: true, message: t('leaderPool.selectAccount') }]}>
              <Select
                options={(approvalPreviewResult?.accounts || accounts.map(account => ({
                  accountId: account.id,
                  accountName: account.accountName,
                  walletAddress: account.walletAddress,
                  proxyAddress: account.proxyAddress,
                  duplicateConfigId: undefined
                }))).map(account => ({
                  value: account.accountId,
                  disabled: !!account.duplicateConfigId,
                  label: `${account.accountName || account.walletAddress} (${account.proxyAddress?.slice(0, 8)}...)${account.duplicateConfigId ? ` · ${t('leaderResearch.duplicateTrialConfig')}` : ''}`
                }))}
              />
            </Form.Item>
          </Form>
        </Space>
      </Modal>

      <Modal
        width={860}
        open={externalImportOpen}
        title={t('leaderResearch.importExternalAnalyticsWallets')}
        onCancel={() => setExternalImportOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setExternalImportOpen(false)}>{t('common.close')}</Button>,
          <Button key="officialDiagnose" loading={externalImportLoading} onClick={runOfficialLeaderboardDiagnose}>{t('leaderResearch.officialLeaderboardDiagnose')}</Button>,
          <Button key="officialDryRun" loading={externalImportLoading} onClick={() => submitOfficialLeaderboardImport(true)}>{t('leaderResearch.officialLeaderboardDryRun')}</Button>,
          <Button key="officialImport" loading={externalImportLoading} onClick={() => submitOfficialLeaderboardImport(false)}>{t('leaderResearch.officialLeaderboardImport')}</Button>,
          <Button key="falconDryRun" loading={externalImportLoading} onClick={() => submitFalconLeaderboardImport(true)}>{t('leaderResearch.falconDryRun')}</Button>,
          <Button key="falconImport" loading={externalImportLoading} onClick={() => submitFalconLeaderboardImport(false)}>{t('leaderResearch.falconImport')}</Button>,
          <Button key="polymarketAnalyticsDryRun" loading={externalImportLoading} onClick={() => submitPolymarketAnalyticsCopyTradeImport(true)}>{t('leaderResearch.polymarketAnalyticsDryRun')}</Button>,
          <Button key="polymarketAnalyticsImport" loading={externalImportLoading} onClick={() => submitPolymarketAnalyticsCopyTradeImport(false)}>{t('leaderResearch.polymarketAnalyticsImport')}</Button>,
          <Button key="polyburgDryRun" loading={externalImportLoading} onClick={() => submitPolyburgTelegramImport(true)}>{t('leaderResearch.polyburgDryRun')}</Button>,
          <Button key="polyburgImport" loading={externalImportLoading} onClick={() => submitPolyburgTelegramImport(false)}>{t('leaderResearch.polyburgImport')}</Button>,
          <Button key="dryRun" loading={externalImportLoading} onClick={() => submitExternalImport(true)}>{t('leaderResearch.dryRun')}</Button>,
          <Button key="import" type="primary" loading={externalImportLoading} onClick={() => submitExternalImport(false)}>{t('leaderResearch.formalImport')}</Button>
        ]}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            message={t('leaderResearch.externalImportSupport')}
            description={t('leaderResearch.externalImportDescription')}
          />
          <Form
            form={externalImportForm}
            layout="vertical"
            initialValues={{
              defaultCategory: 'finance',
              defaultSourceName: 'polymarket_analytics_page_copy'
            }}
          >
            <Row gutter={12}>
              <Col xs={24} md={12}>
                <Form.Item label={t('leaderResearch.defaultCategory')} name="defaultCategory">
                  <Select
                    options={[
                      { value: 'finance', label: 'finance' },
                      { value: 'politics', label: 'politics' },
                      { value: 'sports', label: 'sports' },
                      { value: 'crypto', label: 'crypto' }
                    ]}
                  />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                <Form.Item label={t('leaderResearch.sourceName')} name="defaultSourceName">
                  <Input placeholder={t('leaderResearch.sourceNamePlaceholder')} />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item
              label={t('leaderResearch.walletList')}
              name="walletLines"
              rules={[{ required: true, message: t('leaderResearch.walletListRequired') }]}
            >
              <Input.TextArea
                rows={8}
                placeholder={t('leaderResearch.walletListPlaceholder')}
              />
            </Form.Item>
          </Form>
          {polymarketAnalyticsCopyTradeResult && (
            <Card size="small" title={t('leaderResearch.polymarketAnalyticsParseResult')}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Row gutter={[12, 12]}>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.parsed')} value={polymarketAnalyticsCopyTradeResult.parsedTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.deduped')} value={polymarketAnalyticsCopyTradeResult.dedupedTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.source')} value={polymarketAnalyticsCopyTradeResult.sourceName} /></Col>
                </Row>
                <Text type="secondary">{t('leaderResearch.polymarketAnalyticsPasteNote')}</Text>
              </Space>
            </Card>
          )}
          {polyburgTelegramResult && (
            <Card size="small" title={t('leaderResearch.polyburgParseResult')}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Row gutter={[12, 12]}>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.parsed')} value={polyburgTelegramResult.parsedTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.deduped')} value={polyburgTelegramResult.dedupedTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.source')} value={polyburgTelegramResult.sourceName} /></Col>
                </Row>
                <Text type="secondary">{t('leaderResearch.polyburgImportNote')}</Text>
              </Space>
            </Card>
          )}
          {officialLeaderboardResult && (
            <Card size="small" title={t('leaderResearch.officialLeaderboardFetchResult')}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Row gutter={[12, 12]}>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.fetched')} value={officialLeaderboardResult.fetchedTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.deduped')} value={officialLeaderboardResult.dedupedTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.errors')} value={officialLeaderboardResult.fetches.filter(item => item.error).length} /></Col>
                </Row>
                {officialLeaderboardResult.fetches.map(item => (
                  <Text key={`${item.category}-${item.timePeriod}-${item.orderBy}`} type={item.error ? 'danger' : 'secondary'}>
                    {item.category} · {item.timePeriod} · {item.orderBy}: {item.fetchedItems} {item.error ? `· ${item.error}` : ''}
                  </Text>
                ))}
              </Space>
            </Card>
          )}
          {falconLeaderboardResult && (
            <Card size="small" title={t('leaderResearch.falconFetchResult')}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Row gutter={[12, 12]}>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.fetched')} value={falconLeaderboardResult.fetchedTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.deduped')} value={falconLeaderboardResult.dedupedTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.errors')} value={falconLeaderboardResult.fetches.filter(item => item.error).length} /></Col>
                </Row>
                {falconLeaderboardResult.fetches.map(item => (
                  <Text key={item.sortBy} type={item.error ? 'danger' : 'secondary'}>
                    {item.sortBy}: {item.fetchedItems} {item.error ? `· ${item.error}` : ''}
                  </Text>
                ))}
              </Space>
            </Card>
          )}
          {officialLeaderboardDiagnose && (
            <Card size="small" title={t('leaderResearch.officialLeaderboardQualityDiagnosis')}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Row gutter={[12, 12]}>
                  <Col xs={12} sm={8}><Statistic title={t('common.total')} value={officialLeaderboardDiagnose.total} /></Col>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.states.PAPER')} value={officialLeaderboardDiagnose.paperTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.cleanHighScore')} value={officialLeaderboardDiagnose.cleanHighTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.officialDisabledTrialCandidates')} value={officialLeaderboardDiagnose.disabledTrialCandidateTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.fastWatch')} value={officialLeaderboardDiagnose.fastWatchTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.readyForPaper')} value={officialLeaderboardDiagnose.readyForPaperTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.staleHighQuality')} value={officialLeaderboardDiagnose.buckets.find(item => item.bucket === 'STALE_HIGH_QUALITY')?.count || 0} /></Col>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.noActivitySample')} value={officialLeaderboardDiagnose.buckets.find(item => item.bucket === 'NO_ACTIVITY_SAMPLE')?.count || 0} /></Col>
                </Row>
                <Space wrap>
                  {officialLeaderboardDiagnose.buckets.slice(0, 8).map(item => (
                    <Tag key={item.bucket} color={officialDiagnoseBucketColor(item.bucket)}>
                      {item.bucket}: {item.count}
                    </Tag>
                  ))}
                </Space>
                <Row gutter={[12, 12]}>
                  {officialLeaderboardDiagnose.categories.filter(item => item.total > 0).map(item => (
                    <Col xs={24} md={12} key={item.category}>
                      <Card size="small" title={item.category}>
                        <Space direction="vertical" size={0}>
                          <Text>{t('leaderResearch.officialDiagnoseCategorySummary', {
                              total: item.total,
                              paperState: t('leaderResearch.states.PAPER'),
                              paper: item.paper,
                              cleanHigh: item.cleanHigh
                            })}</Text>
                          <Text type="secondary">{t('leaderResearch.officialDiagnoseCategoryDetail', {
                              paperState: t('leaderResearch.states.PAPER'),
                              readyForPaper: item.readyForPaper,
                              noActivitySample: item.noActivitySample,
                              staleActivity: item.staleActivity
                            })}</Text>
                        </Space>
                      </Card>
                    </Col>
                  ))}
                </Row>
                <Space direction="vertical" style={{ width: '100%' }}>
                  {officialLeaderboardDiagnose.samples.slice(0, 5).map(item => (
                    <Space key={item.candidateId} style={{ justifyContent: 'space-between', width: '100%' }}>
                      <Space direction="vertical" size={0}>
                        <Text strong>{item.wallet.slice(0, 12)}... · {item.category}</Text>
                        <Text type="secondary">{t('leaderResearch.officialDiagnoseSampleMeta', {
                              bucket: item.bucket,
                              score: item.score || '-',
                              age: item.lastSourceAgeHours ?? '-'
                            })}</Text>
                      </Space>
                      <Space>
                        <Tag color={officialDiagnoseBucketColor(item.bucket)}>{item.bucket}</Tag>
                        <Tag>{item.researchState}</Tag>
                        {strategyTypeTag(item.strategyType)}
                        {item.bucket === 'STALE_HIGH_QUALITY' && (
                          <Button
                            size="small"
                            loading={externalImportLoading}
                            onClick={() => refreshOfficialLeaderboardCandidate(item.candidateId)}
                          >
                            {t('leaderResearch.refreshOfficialSource')}
                          </Button>
                        )}
                        {isOfficialDisabledTrialCandidate(item) && (
                          <Button
                            size="small"
                            type="primary"
                            loading={approvalLoading && approvalCandidate?.id !== item.candidateId}
                            onClick={() => openApprovalByCandidateId(item.candidateId)}
                          >
                            {t('leaderResearch.createDisabledTrial')}
                          </Button>
                        )}
                      </Space>
                    </Space>
                  ))}
                </Space>
              </Space>
            </Card>
          )}
          {externalImportResult && (
            <Card size="small" title={t('leaderResearch.latestImportResult')}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Row gutter={[12, 12]}>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.requested')} value={externalImportResult.requestedTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.selected')} value={externalImportResult.selectedTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.created')} value={externalImportResult.createdTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.updated')} value={externalImportResult.updatedTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.invalid')} value={externalImportResult.skippedInvalidTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.duplicateOrLocked')} value={externalImportResult.skippedExistingTotal + externalImportResult.skippedLockedTotal} /></Col>
                </Row>
                <Space direction="vertical" style={{ width: '100%' }}>
                  {externalImportResult.previewItems.slice(0, 6).map(item => (
                    <Space key={`${item.wallet}-${item.action}`} style={{ justifyContent: 'space-between', width: '100%' }}>
                      <Space direction="vertical" size={0}>
                        <Text strong>{item.wallet.slice(0, 12)}...</Text>
                        <Text type="secondary">{t('leaderResearch.externalImportItemMeta', {
                              category: item.category,
                              sourceName: item.sourceName,
                              externalScore: item.externalScore || '-'
                            })}</Text>
                      </Space>
                      <Tag color={item.action === 'CREATE' ? 'green' : item.action === 'UPDATE' ? 'blue' : item.action === 'SKIP_INVALID' ? 'red' : 'default'}>
                        {item.action}
                      </Tag>
                    </Space>
                  ))}
                </Space>
              </Space>
            </Card>
          )}
        </Space>
      </Modal>
    </Space>
  )
}

const PaperTradeTable: React.FC<{ trades: LeaderPaperTrade[] }> = ({ trades }) => {
  const { t } = useTranslation()
  return (
    <Table
      rowKey="id"
      size="small"
      dataSource={trades}
      columns={[
        { title: t('leaderResearch.paperTradeTime'), dataIndex: 'eventTime', render: formatDate },
        { title: t('leaderResearch.paperTradeSide'), dataIndex: 'side' },
        { title: t('leaderResearch.paperTradeMarket'), dataIndex: 'marketTitle', render: (value?: string, item?: LeaderPaperTrade) => value || item?.marketId },
        { title: t('leaderResearch.paperTradeLeaderPrice'), dataIndex: 'leaderPrice' },
        { title: t('leaderResearch.paperTradeSimAmount'), dataIndex: 'simulatedAmount' },
        { title: t('leaderResearch.paperTradeFilter'), dataIndex: 'filterResult' },
        { title: t('leaderResearch.paperTradeQuote'), dataIndex: 'quoteConfidence' },
        { title: t('leaderResearch.paperTradeValuation'), dataIndex: 'valuationStatus', render: valuationTag }
      ]}
    />
  )
}

const PaperPositionTable: React.FC<{ positions: LeaderPaperPosition[] }> = ({ positions }) => {
  const { t } = useTranslation()
  return (
    <Table
      rowKey="id"
      size="small"
      dataSource={positions}
      columns={[
        { title: t('leaderResearch.paperPositionMarket'), dataIndex: 'marketId' },
        { title: t('leaderResearch.paperPositionOutcome'), dataIndex: 'outcome' },
        { title: t('leaderResearch.paperPositionQty'), dataIndex: 'quantity' },
        { title: t('leaderResearch.paperPositionCost'), dataIndex: 'cost' },
        { title: t('leaderResearch.paperPositionValue'), dataIndex: 'currentValue' },
        { title: t('leaderResearch.paperPositionPnl'), dataIndex: 'unrealizedPnl' },
        { title: t('leaderResearch.paperPositionQuote'), dataIndex: 'quoteConfidence' },
        { title: t('leaderResearch.paperPositionValuation'), dataIndex: 'valuationStatus', render: valuationTag }
      ]}
    />
  )
}

const summaryFallback: LeaderResearchSummary = {
  discoveredCount: 0,
  candidateCount: 0,
  paperCount: 0,
  trialReadyCount: 0,
  strictReadyCount: 0,
  cooldownCount: 0,
  retiredCount: 0,
  activePaperSessions: 0,
  pendingRiskCount: 0,
  strategyTypeCounts: [],
  nonCopyableStrategyBlockers: [],
  sourceLimitations: []
}

export default LeaderResearch
