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
  LeaderResearchPaperProcessCandidate,
  LeaderResearchPaperPromotionResponse,
  LeaderResearchPoliticsRecommendationExecutionSnapshot,
  LeaderResearchPoliticsRecommendationExecuteResponse,
  LeaderResearchPoliticsSourceDiagnose,
  LeaderResearchPolymarketAnalyticsCopyTradeImportResponse,
  LeaderResearchPolyburgTelegramImportResponse,
  LeaderResearchTrialReadiness,
  LeaderResearchSourceState,
  LeaderResearchState,
  LeaderResearchSummary
} from '../types'

const { Paragraph, Text, Title } = Typography

const STATE_COLORS: Record<LeaderResearchState, string> = {
  DISCOVERED: 'default',
  CANDIDATE: 'blue',
  PAPER: 'geekblue',
  TRIAL_READY: 'green',
  COOLDOWN: 'orange',
  RETIRED: 'red'
}

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
  const [running, setRunning] = useState(false)
  const [fastWatchAction, setFastWatchAction] = useState<'score' | 'process' | null>(null)
  const [politicsAction, setPoliticsAction] = useState<'process' | 'importPreview' | 'importConfirm' | 'scoreRefresh' | 'executePreview' | null>(null)
  const [politicsImportResult, setPoliticsImportResult] = useState<LeaderResearchActivitySourceImportResponse | null>(null)
  const [politicsPromotionResult, setPoliticsPromotionResult] = useState<LeaderResearchPaperPromotionResponse | null>(null)
  const [politicsExecutionResult, setPoliticsExecutionResult] = useState<LeaderResearchPoliticsRecommendationExecuteResponse | null>(null)
  const [latestPoliticsExecution, setLatestPoliticsExecution] = useState<LeaderResearchPoliticsRecommendationExecutionSnapshot | null>(null)
  const [lastPaperProcessSummaries, setLastPaperProcessSummaries] = useState<LeaderResearchPaperProcessCandidate[]>([])
  const [detailLoading, setDetailLoading] = useState(false)
  const [marketPeerLoading, setMarketPeerLoading] = useState(false)
  const [externalImportOpen, setExternalImportOpen] = useState(false)
  const [externalImportLoading, setExternalImportLoading] = useState(false)
  const [detail, setDetail] = useState<LeaderResearchCandidateDetail | null>(null)
  const [approvalCandidate, setApprovalCandidate] = useState<LeaderResearchCandidate | null>(null)
  const [approvalLoading, setApprovalLoading] = useState(false)
  const [approvalForm] = Form.useForm()
  const [externalImportForm] = Form.useForm()

  const loadAll = async (showLoading = true) => {
    if (showLoading) setLoading(true)
    try {
      const [candidateResp, summaryResp, funnelResp, fastWatchResp, sourceResp, politicsExecutionResp, accountResp] = await Promise.allSettled([
        apiService.leaderResearch.listCandidates({ page: 0, size: 50, state: stateFilter, query: query || undefined }),
        apiService.leaderResearch.summary(),
        apiService.leaderResearch.funnel(),
        apiService.leaderResearch.fastWatch({ categories: ['politics', 'finance'], limit: 12, includeTrialReady: true }),
        apiService.leaderResearch.sourceHealth(),
        apiService.leaderResearch.latestPoliticsRecommendationExecution(),
        apiService.accounts.list()
      ])

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

      const candidateData = readData(candidateResp, 'candidates')
      if (candidateData) {
        setCandidates(candidateData)
      } else {
        message.warning(t('leaderResearch.fetchFailed'))
      }
      const summaryData = readData(summaryResp, 'summary')
      if (summaryData) {
        setSummary(summaryData)
      }
      const funnelData = readData(funnelResp, 'funnel')
      if (funnelData) {
        setFunnel(funnelData)
      }
      const fastWatchData = readData(fastWatchResp, 'fastWatch')
      if (fastWatchData) {
        setFastWatch(fastWatchData)
      }
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

      void Promise.allSettled([
        apiService.leaderResearch.diagnosePoliticsSource({ limit: 500 }),
        apiService.leaderResearch.diagnosePoliticsSource({ category: 'finance', limit: 500 })
      ]).then(([politicsDiagnoseResp, financeDiagnoseResp]) => {
        if (politicsDiagnoseResp.status === 'fulfilled' && politicsDiagnoseResp.value.data.code === 0 && politicsDiagnoseResp.value.data.data) {
          setPoliticsDiagnose(politicsDiagnoseResp.value.data.data)
        }
        if (financeDiagnoseResp.status === 'fulfilled' && financeDiagnoseResp.value.data.code === 0 && financeDiagnoseResp.value.data.data) {
          setFinanceDiagnose(financeDiagnoseResp.value.data.data)
        }
      })
    } catch (error: any) {
      message.error(error.message || t('leaderResearch.fetchFailed'))
    } finally {
      if (showLoading) setLoading(false)
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
        timePeriods: ['MONTH'],
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

  const openApproval = (candidate: LeaderResearchCandidate) => {
    setApprovalCandidate(candidate)
    approvalForm.setFieldsValue({ accountId: accounts[0]?.id })
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
      openApproval(candidate)
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
          <Tag color={STATE_COLORS[state]}>{t(`leaderResearch.states.${state}`, { defaultValue: state })}</Tag>
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
      width: 160
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
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Space align="start" style={{ justifyContent: 'space-between', width: '100%' }}>
            <div>
              <Title level={3} style={{ marginBottom: 4 }}>{t('leaderResearch.title')}</Title>
              <Paragraph type="secondary" style={{ marginBottom: 0 }}>{t('leaderResearch.subtitle')}</Paragraph>
            </div>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={() => loadAll()}>{t('common.refresh')}</Button>
              <Button onClick={() => setExternalImportOpen(true)}>{t('leaderResearch.importExternalList')}</Button>
              <Button type="primary" icon={<PlayCircleOutlined />} loading={running || lastRun?.status === 'RUNNING'} onClick={runAgent}>
                {t('leaderResearch.runNow')}
              </Button>
            </Space>
          </Space>
          <Alert
            type="info"
            showIcon
            icon={<ExperimentOutlined />}
            message={t('leaderResearch.safetyTitle')}
            description={t('leaderResearch.safetyDesc')}
          />
          {activeSummary.sourceLimitations?.length > 0 && (
            <Alert
              type="warning"
              showIcon
              message={t('leaderResearch.sourceLimitations')}
              description={activeSummary.sourceLimitations.join(' | ')}
            />
          )}
        </Space>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={4}><Card><Statistic title={t('leaderResearch.states.DISCOVERED')} value={activeSummary.discoveredCount} /></Card></Col>
        <Col xs={24} sm={12} lg={4}><Card><Statistic title={t('leaderResearch.states.CANDIDATE')} value={activeSummary.candidateCount} /></Card></Col>
        <Col xs={24} sm={12} lg={4}><Card><Statistic title={t('leaderResearch.states.PAPER')} value={activeSummary.paperCount} /></Card></Col>
        <Col xs={24} sm={12} lg={4}><Card><Statistic title={t('leaderResearch.states.TRIAL_READY')} value={activeSummary.trialReadyCount} /></Card></Col>
        <Col xs={24} sm={12} lg={4}><Card><Statistic title={t('leaderResearch.states.COOLDOWN')} value={activeSummary.cooldownCount} /></Card></Col>
        <Col xs={24} sm={12} lg={4}><Card><Statistic title={t('leaderResearch.states.RETIRED')} value={activeSummary.retiredCount} /></Card></Col>
      </Row>

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
                    politics/finance {funnel.allocationHealth.primaryCleanHighCount} · sports/crypto {funnel.allocationHealth.secondaryCleanHighCount}
                  </Text>
                  <Text type="secondary">{funnel.allocationHealth.message}</Text>
                </Space>
              </Space>
            </Card>
          </Col>
          <Col xs={24} lg={8}>
            <Card title={t('leaderResearch.categoryConversion')}>
              <Space direction="vertical" style={{ width: '100%' }}>
                {funnel.categories.map(category => (
                  <Space key={category.category} style={{ justifyContent: 'space-between', width: '100%' }}>
                    <Text strong>{category.category}</Text>
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
          title={t('leaderResearch.fastWatchCandidatesTitle')}
          extra={
            <Space>
              <Tag color="blue">FAST_WATCH {fastWatch.fastWatchCount}</Tag>
              <Tag color="green">TRIAL_READY {fastWatch.trialReadyCount}</Tag>
              <Button
                size="small"
                loading={fastWatchAction === 'score'}
                disabled={fastWatch.items.length === 0 || fastWatchAction !== null}
                onClick={scoreFastWatch}
              >
                {t('leaderResearch.scoreIncrement')}
              </Button>
              <Button
                size="small"
                type="primary"
                loading={fastWatchAction === 'process'}
                disabled={fastWatch.items.length === 0 || fastWatchAction !== null}
                onClick={processFastWatch}
              >
                {t('leaderResearch.advancePaper')}
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
            <Text type="secondary">{fastWatch.criteria}</Text>
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
                          <Tag color={candidate.category === 'politics' ? 'purple' : 'cyan'}>{candidate.category}</Tag>
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
                          {candidate.trialReadiness.blockers[0] || candidate.trialReadiness.fastWatchBlockers[0] || t('leaderResearch.waitForManualReview')}
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
                    <Tag color="green">IMPORT_NOW {recommendationCount(financeDiagnose, 'IMPORT_NOW')}</Tag>
                    <Tag color="gold">SCORE_REFRESH {recommendationCount(financeDiagnose, 'SCORE_REFRESH')}</Tag>
                    <Tag color="blue">PAPER_PROCESS {recommendationCount(financeDiagnose, 'PAPER_PROCESS')}</Tag>
                    <Tag color="purple">FAST_WATCH_REVIEW {recommendationCount(financeDiagnose, 'FAST_WATCH_REVIEW')}</Tag>
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
                  <Tag color="green">IMPORT_NOW {politicsImportWallets().length}</Tag>
                  <Tag color="gold">SCORE_REFRESH {politicsScoreRefreshCandidateIds().length}</Tag>
                  <Tag color="blue">PAPER_PROCESS {politicsPaperProcessCandidateIds().length}</Tag>
                  <Tag color="purple">FAST_WATCH_REVIEW {politicsFastWatchReviewRecommendations().length}</Tag>
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
                              {item.recommendation}
                            </Tag>
                          </Space>
                          <Text copyable={{ text: item.wallet }}>{item.wallet.slice(0, 10)}...{item.wallet.slice(-6)}</Text>
                          <Text type="secondary">{item.reason}</Text>
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
                        {sample.totalEvents} events · {sample.distinctMarkets} markets · buy/sell {sample.buyEvents}/{sample.sellEvents}
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
          <Card title={t('leaderResearch.runStatus')}>
            {lastRun ? (
              <Descriptions size="small" column={1}>
                <Descriptions.Item label={t('common.status')}>
                  <Tag color={lastRun.partialFailure ? 'orange' : lastRun.status === 'SUCCESS' ? 'green' : 'default'}>{lastRun.status}</Tag>
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

      <Card>
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Space wrap>
            <Select
              allowClear
              style={{ width: 220 }}
              placeholder={t('leaderResearch.filterState')}
              value={stateFilter}
              onChange={setStateFilter}
              options={Object.keys(STATE_COLORS).map(state => ({
                value: state,
                label: t(`leaderResearch.states.${state}`, { defaultValue: state })
              }))}
            />
            <Input.Search
              allowClear
              style={{ width: 320 }}
              placeholder={t('leaderResearch.searchPlaceholder')}
              value={query}
              onChange={event => setQuery(event.target.value)}
              onSearch={() => loadAll()}
            />
          </Space>
          <Table
            rowKey="id"
            loading={loading}
            columns={columns}
            dataSource={candidates.list}
            scroll={{ x: 1300 }}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('leaderResearch.empty')} /> }}
          />
        </Space>
      </Card>

      <Card title={t('leaderResearch.sourceHealth')}>
        <Row gutter={[12, 12]}>
          {sourceHealth.map(source => (
            <Col xs={24} md={12} lg={6} key={source.sourceType}>
              <Card size="small">
                <Space direction="vertical" size={4}>
                  <Badge status={source.status === 'SUCCESS' ? 'success' : source.status === 'DISABLED' ? 'default' : 'warning'} text={source.sourceType} />
                  <Tag>{source.status}</Tag>
                  <Text type="secondary">{t('leaderResearch.candidates')}: {source.lastCandidateCount}</Text>
                  <Text type="secondary">{formatDate(source.lastRunAt)}</Text>
                  {(source.disabledReason || source.errorMessage) && <Text type="secondary">{source.disabledReason || source.errorMessage}</Text>}
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
                      <Descriptions.Item label={t('common.status')}>{detail.candidate.researchState}</Descriptions.Item>
                      <Descriptions.Item label={t('leaderResearch.score')}>{detail.candidate.score || '-'}</Descriptions.Item>
                      <Descriptions.Item label={t('leaderResearch.reason')}>{detail.candidate.reason || '-'}</Descriptions.Item>
                      <Descriptions.Item label={t('leaderResearch.riskFlags')}>{detail.candidate.riskFlags.join(', ') || '-'}</Descriptions.Item>
                      <Descriptions.Item label={t('leaderResearch.sourceEvidence')}>{detail.candidate.sourceEvidence || '-'}</Descriptions.Item>
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
                      { title: t('leaderResearch.eventType'), dataIndex: 'eventType' },
                      { title: t('leaderResearch.reason'), dataIndex: 'reason' }
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
        onCancel={() => setApprovalCandidate(null)}
        onOk={submitApproval}
        confirmLoading={approvalLoading}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Alert
            type="warning"
            showIcon
            message={t('leaderResearch.approvalSafetyTitle')}
            description={t('leaderResearch.approvalSafetyDesc')}
          />
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
                options={accounts.map(account => ({
                  value: account.id,
                  label: `${account.accountName || account.walletAddress} (${account.proxyAddress?.slice(0, 8)}...)`
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
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.fastWatch')} value={officialLeaderboardDiagnose.fastWatchTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.readyForPaper')} value={officialLeaderboardDiagnose.readyForPaperTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title={t('leaderResearch.noActivitySample')} value={officialLeaderboardDiagnose.buckets.find(item => item.bucket === 'NO_ACTIVITY_SAMPLE')?.count || 0} /></Col>
                </Row>
                <Space wrap>
                  {officialLeaderboardDiagnose.buckets.slice(0, 8).map(item => (
                    <Tag key={item.bucket} color={item.bucket === 'CLEAN_HIGH' || item.bucket === 'READY_FOR_PAPER' ? 'green' : item.bucket.includes('RISK') || item.bucket === 'HIGH_FILTERED_RATIO' ? 'red' : 'default'}>
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
                      <Tag>{item.researchState}</Tag>
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
  cooldownCount: 0,
  retiredCount: 0,
  activePaperSessions: 0,
  pendingRiskCount: 0,
  sourceLimitations: []
}

export default LeaderResearch
