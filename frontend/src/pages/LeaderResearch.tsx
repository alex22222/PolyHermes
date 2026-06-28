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
  LeaderResearchCandidate,
  LeaderResearchCandidateDetail,
  LeaderResearchCandidateListResponse,
  LeaderResearchExternalAnalyticsImportItem,
  LeaderResearchExternalAnalyticsImportResponse,
  LeaderResearchFalconLeaderboardImportResponse,
  LeaderResearchFunnel,
  LeaderResearchMarketPeerSourceImportResponse,
  LeaderResearchOfficialLeaderboardDiagnoseResponse,
  LeaderResearchOfficialLeaderboardImportResponse,
  LeaderResearchPoliticsSourceDiagnose,
  LeaderResearchPolymarketAnalyticsCopyTradeImportResponse,
  LeaderResearchPolyburgTelegramImportResponse,
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
  const [politicsDiagnose, setPoliticsDiagnose] = useState<LeaderResearchPoliticsSourceDiagnose | null>(null)
  const [marketPeerStrict, setMarketPeerStrict] = useState<LeaderResearchMarketPeerSourceImportResponse | null>(null)
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
      const [candidateResp, summaryResp, funnelResp, sourceResp, politicsDiagnoseResp, marketPeerResp, accountResp] = await Promise.all([
        apiService.leaderResearch.listCandidates({ page: 0, size: 50, state: stateFilter, query: query || undefined }),
        apiService.leaderResearch.summary(),
        apiService.leaderResearch.funnel(),
        apiService.leaderResearch.sourceHealth(),
        apiService.leaderResearch.diagnosePoliticsSource({ limit: 500 }),
        apiService.leaderResearch.importMarketPeerSource({
          dryRun: true,
          categories: ['politics', 'finance'],
          limitPerCategory: 20,
          lookbackDays: 60,
          hotMarketLimit: 50,
          minMarketEvents: 25,
          minMarketWallets: 20,
          minEvents: 8,
          minDistinctMarkets: 2,
          minBuyEvents: 2,
          minSellEvents: 1,
          minSafePriceRatio: '0.20',
          maxTailPriceRatio: '0.50'
        }),
        apiService.accounts.list()
      ])
      if (candidateResp.data.code === 0 && candidateResp.data.data) {
        setCandidates(candidateResp.data.data)
      } else {
        message.error(candidateResp.data.msg || t('leaderResearch.fetchFailed'))
      }
      if (summaryResp.data.code === 0 && summaryResp.data.data) {
        setSummary(summaryResp.data.data)
      }
      if (funnelResp.data.code === 0 && funnelResp.data.data) {
        setFunnel(funnelResp.data.data)
      }
      if (sourceResp.data.code === 0 && sourceResp.data.data) {
        setSourceHealth(sourceResp.data.data)
      }
      if (politicsDiagnoseResp.data.code === 0 && politicsDiagnoseResp.data.data) {
        setPoliticsDiagnose(politicsDiagnoseResp.data.data)
      }
      if (marketPeerResp.data.code === 0 && marketPeerResp.data.data) {
        setMarketPeerStrict(marketPeerResp.data.data)
      }
      if (accountResp.data.code === 0 && accountResp.data.data) {
        setAccounts(accountResp.data.data.list || [])
      }
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
        message.success('已刷新放宽金融来源')
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
      message.warning('请输入至少 1 个 wallet')
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
        message.success(dryRun ? '外部名单 dry-run 完成' : '外部名单已导入')
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
          message.warning(`官方榜单返回 ${failedFetches} 个抓取错误，请查看结果`)
        } else {
          message.success(dryRun ? '官方榜单 dry-run 完成' : '官方榜单已导入')
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
          message.warning(`Falcon 返回 ${failedFetches} 个抓取错误，请查看结果`)
        } else {
          message.success(dryRun ? 'Falcon 榜单 dry-run 完成' : 'Falcon 榜单已导入')
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
        message.success(dryRun ? 'Polyburg dry-run 完成' : 'Polyburg leader 已导入')
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
        message.success(dryRun ? 'Polymarket Analytics dry-run 完成' : 'Polymarket Analytics leader 已导入')
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
        message.success('官方榜单诊断完成')
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
              <Button onClick={() => setExternalImportOpen(true)}>导入外部名单</Button>
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
            <Card title="研究候选漏斗">
              <Space direction="vertical" style={{ width: '100%' }}>
                <Statistic title="研究候选目标进度" value={`${funnel.totalCandidates}/${funnel.targetTotal}`} />
                <Progress percent={Math.min(100, Number(funnel.progressPercent))} />
                <Statistic title="正式 Leader 管理" value={funnel.managedLeaderTotal} />
                <Statistic title="Leader 池" value={funnel.leaderPoolTotal} />
                <Statistic title="高质量可观察" value={funnel.cleanHighScoreTotal} />
                <Text type="secondary">{funnel.criteria}</Text>
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                    <Text strong>主类别配比</Text>
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
            <Card title="分类转化">
              <Space direction="vertical" style={{ width: '100%' }}>
                {funnel.categories.map(category => (
                  <Space key={category.category} style={{ justifyContent: 'space-between', width: '100%' }}>
                    <Text strong>{category.category}</Text>
                    <Text>{category.totalCandidates} / PAPER {category.paperCandidates} / 高分 {category.cleanHighScoreCandidates}</Text>
                    <Tag color={category.cleanHighScoreCandidates > 0 ? 'green' : 'default'}>
                      {category.topScore || '-'}
                    </Tag>
                  </Space>
                ))}
              </Space>
            </Card>
          </Col>
          <Col xs={24} lg={8}>
            <Card title="优先观察候选">
              {funnel.priorityCandidates.length > 0 ? (
                <Space direction="vertical" style={{ width: '100%' }}>
                  {funnel.priorityCandidates.slice(0, 5).map(candidate => (
                    <Space key={candidate.candidateId} style={{ justifyContent: 'space-between', width: '100%' }}>
                      <Space direction="vertical" size={0}>
                        <Text strong>#{candidate.candidateId} {candidate.wallet.slice(0, 10)}...</Text>
                        <Text type="secondary">{candidate.category} · {candidate.tradeCount} trades · PnL {candidate.copyablePnl}</Text>
                        <Text type="secondary">
                          {candidate.trialReadiness.level === 'FAST_WATCH'
                            ? '快速观察 · 未放开正式试跟'
                            : candidate.trialReadiness.eligible
                              ? candidate.trialReadiness.label
                              : `${candidate.trialReadiness.label} · ${candidate.trialReadiness.blockers[0] || candidate.trialReadiness.fastWatchBlockers[0] || '等待更多样本'}`}
                        </Text>
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
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无高质量候选" />
              )}
            </Card>
          </Col>
        </Row>
      )}

      {politicsDiagnose && (
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={12}>
            <Card title="政治来源诊断">
              <Space direction="vertical" style={{ width: '100%' }}>
                <Row gutter={[12, 12]}>
                  <Col xs={12} sm={8}><Statistic title="扫描钱包" value={politicsDiagnose.scannedWallets} /></Col>
                  <Col xs={12} sm={8}><Statistic title="通过阈值" value={politicsDiagnose.passImportCriteria} /></Col>
                  <Col xs={12} sm={8}><Statistic title="可新增 PAPER" value={politicsDiagnose.eligibleForPaperNow} /></Col>
                  <Col xs={12} sm={8}><Statistic title="未知钱包" value={politicsDiagnose.unknownWallets} /></Col>
                  <Col xs={12} sm={8}><Statistic title="已在池中" value={politicsDiagnose.existingWallets} /></Col>
                  <Col xs={12} sm={8}><Statistic title="已 PAPER" value={politicsDiagnose.paperWallets} /></Col>
                </Row>
                <Progress
                  percent={politicsDiagnose.scannedWallets > 0 ? Number(((politicsDiagnose.passImportCriteria / politicsDiagnose.scannedWallets) * 100).toFixed(2)) : 0}
                  status={politicsDiagnose.eligibleForPaperNow > 0 ? 'active' : 'normal'}
                />
                <Text type="secondary">
                  lookback {politicsDiagnose.lookbackDays} 天 · clean high {politicsDiagnose.cleanHighWallets}
                </Text>
                <Alert
                  type={politicsDiagnose.eligibleForPaperNow > 0 ? 'success' : 'info'}
                  showIcon
                  message={politicsDiagnose.eligibleForPaperNow > 0
                    ? `发现 ${politicsDiagnose.eligibleForPaperNow} 个可新增政治 PAPER 候选`
                    : '当前 activity-source 暂无可新增政治 PAPER 候选，优先寻找新来源'}
                />
              </Space>
            </Card>
          </Col>
          <Col xs={24} lg={12}>
            <Card title="政治来源阻塞">
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
          <Col xs={24}>
            <Card title="政治来源样本">
              <Space direction="vertical" style={{ width: '100%' }}>
                {politicsDiagnose.samples.slice(0, 5).map(sample => (
                  <Space key={sample.wallet} style={{ justifyContent: 'space-between', width: '100%' }}>
                    <Space direction="vertical" size={0}>
                      <Text strong>{sample.wallet.slice(0, 12)}...</Text>
                      <Text type="secondary">
                        {sample.totalEvents} events · {sample.distinctMarkets} markets · buy/sell {sample.buyEvents}/{sample.sellEvents}
                      </Text>
                      <Text type="secondary">
                        safe {sample.safePriceRatio} · tail {sample.tailPriceRatio} · {sample.blockers[0] || '通过当前阈值'}
                      </Text>
                    </Space>
                    <Space direction="vertical" size={0} align="end">
                      <Tag color={sample.action === 'UNKNOWN_ELIGIBLE' ? 'green' : sample.currentState === 'PAPER' ? 'blue' : 'default'}>
                        {sample.action}
                      </Tag>
                      <Tag color={sample.currentScore ? 'geekblue' : 'default'}>{sample.currentScore || '-'}</Tag>
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
              title="热门市场对手方来源"
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
                    <Col xs={12} sm={8}><Statistic title="选中钱包" value={marketPeerStrict.selectedTotal} /></Col>
                    <Col xs={12} sm={8}><Statistic title="可新建" value={marketPeerStrict.createdTotal} /></Col>
                    <Col xs={12} sm={8}><Statistic title="可更新" value={marketPeerStrict.updatedTotal} /></Col>
                  </Row>
                  <Space wrap>
                    {marketPeerStrict.categories.map(category => (
                      <Tag key={category.category} color={category.createdCount > 0 ? 'green' : category.selectedCount > 0 ? 'blue' : 'default'}>
                        {category.category}: {category.selectedCount} / 新 {category.createdCount}
                      </Tag>
                    ))}
                  </Space>
                  <Alert
                    type={marketPeerStrict.createdTotal > 0 ? 'success' : 'info'}
                    showIcon
                    message={marketPeerStrict.createdTotal > 0
                      ? `strict 来源发现 ${marketPeerStrict.createdTotal} 个可新增候选`
                      : 'strict 来源暂无可新增候选，当前更多是刷新已有 evidence'}
                  />
                </Space>
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无 strict 来源结果" />
              )}
            </Card>
          </Col>
          <Col xs={24} lg={12}>
            <Card title="第二来源样本">
              <Space direction="vertical" style={{ width: '100%' }}>
                {(marketPeerRelaxed || marketPeerStrict)?.previewItems.slice(0, 5).map(sample => (
                  <Space key={`${sample.category}-${sample.wallet}-${sample.action}`} style={{ justifyContent: 'space-between', width: '100%' }}>
                    <Space direction="vertical" size={0}>
                      <Text strong>{sample.wallet.slice(0, 12)}...</Text>
                      <Text type="secondary">
                        {sample.category} · {sample.totalEvents} events · {sample.distinctMarkets} markets · buy/sell {sample.buyEvents}/{sample.sellEvents}
                      </Text>
                      <Text type="secondary">
                        {sample.topMarkets.slice(0, 2).join(' · ') || 'no market sample'}
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
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无第二来源样本" />
                )}
                {marketPeerRelaxed && (
                  <Alert
                    type={marketPeerRelaxed.createdTotal > 0 ? 'success' : 'warning'}
                    showIcon
                    message={`relaxed finance: 选中 ${marketPeerRelaxed.selectedTotal}，新建 ${marketPeerRelaxed.createdTotal}，更新 ${marketPeerRelaxed.updatedTotal}`}
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
                        <Descriptions.Item label="profit">{detail.latestScore.profitSignal}</Descriptions.Item>
                        <Descriptions.Item label="repeatability">{detail.latestScore.repeatability}</Descriptions.Item>
                        <Descriptions.Item label="liquidity">{detail.latestScore.liquidityFit}</Descriptions.Item>
                        <Descriptions.Item label="entry">{detail.latestScore.entryPriceFit}</Descriptions.Item>
                        <Descriptions.Item label="slippage">{detail.latestScore.slippageRisk}</Descriptions.Item>
                        <Descriptions.Item label="drawdown">{detail.latestScore.drawdownRisk}</Descriptions.Item>
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
        title="导入外部 Analytics 钱包"
        onCancel={() => setExternalImportOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setExternalImportOpen(false)}>关闭</Button>,
          <Button key="officialDiagnose" loading={externalImportLoading} onClick={runOfficialLeaderboardDiagnose}>官方榜单诊断</Button>,
          <Button key="officialDryRun" loading={externalImportLoading} onClick={() => submitOfficialLeaderboardImport(true)}>官方榜单 Dry-run</Button>,
          <Button key="officialImport" loading={externalImportLoading} onClick={() => submitOfficialLeaderboardImport(false)}>官方榜单导入</Button>,
          <Button key="falconDryRun" loading={externalImportLoading} onClick={() => submitFalconLeaderboardImport(true)}>Falcon Dry-run</Button>,
          <Button key="falconImport" loading={externalImportLoading} onClick={() => submitFalconLeaderboardImport(false)}>Falcon 导入</Button>,
          <Button key="polymarketAnalyticsDryRun" loading={externalImportLoading} onClick={() => submitPolymarketAnalyticsCopyTradeImport(true)}>PolymarketAnalytics Dry-run</Button>,
          <Button key="polymarketAnalyticsImport" loading={externalImportLoading} onClick={() => submitPolymarketAnalyticsCopyTradeImport(false)}>PolymarketAnalytics 导入</Button>,
          <Button key="polyburgDryRun" loading={externalImportLoading} onClick={() => submitPolyburgTelegramImport(true)}>Polyburg Dry-run</Button>,
          <Button key="polyburgImport" loading={externalImportLoading} onClick={() => submitPolyburgTelegramImport(false)}>Polyburg 导入</Button>,
          <Button key="dryRun" loading={externalImportLoading} onClick={() => submitExternalImport(true)}>Dry-run</Button>,
          <Button key="import" type="primary" loading={externalImportLoading} onClick={() => submitExternalImport(false)}>正式导入</Button>
        ]}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            message="支持从 Polymarket Analytics / Dune / Polyburg 手工榜单直接粘贴"
            description="从 PolymarketAnalytics copy-trade 页面、榜单页面或 Polyburg Telegram bot 复制文本后粘贴即可；也可以用官方榜单或 Falcon 自动拉取候选。正式导入后仍会走系统评分、PAPER 和风控过滤。"
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
                <Form.Item label="默认分类" name="defaultCategory">
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
                <Form.Item label="来源名称" name="defaultSourceName">
                  <Input placeholder="polymarket_analytics_page_copy / dune / polyburg" />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item
              label="钱包列表"
              name="walletLines"
              rules={[{ required: true, message: '请输入钱包列表' }]}
            >
              <Input.TextArea
                rows={8}
                placeholder={'PolymarketAnalytics / Polyburg bot 消息或表格均可：\nSmart Wallet #1 copied 42 pnl $532 roi 18% finance\n0x9703676286b93c2eca71ca96e8757104519a69c2\n2 trader 0x1111111111111111111111111111111111111111 sports copied 9'}
              />
            </Form.Item>
          </Form>
          {polymarketAnalyticsCopyTradeResult && (
            <Card size="small" title="Polymarket Analytics copy-trade 解析结果">
              <Space direction="vertical" style={{ width: '100%' }}>
                <Row gutter={[12, 12]}>
                  <Col xs={12} sm={8}><Statistic title="解析" value={polymarketAnalyticsCopyTradeResult.parsedTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title="去重" value={polymarketAnalyticsCopyTradeResult.dedupedTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title="来源" value={polymarketAnalyticsCopyTradeResult.sourceName} /></Col>
                </Row>
                <Text type="secondary">当前采用粘贴导入。网页直连会遇到 Vercel Security Checkpoint，不建议作为后端定时抓取源。</Text>
              </Space>
            </Card>
          )}
          {polyburgTelegramResult && (
            <Card size="small" title="Polyburg Telegram 解析结果">
              <Space direction="vertical" style={{ width: '100%' }}>
                <Row gutter={[12, 12]}>
                  <Col xs={12} sm={8}><Statistic title="解析" value={polyburgTelegramResult.parsedTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title="去重" value={polyburgTelegramResult.dedupedTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title="来源" value={polyburgTelegramResult.sourceName} /></Col>
                </Row>
                <Text type="secondary">正式导入后会进入候选池，不会自动开启真钱跟单。</Text>
              </Space>
            </Card>
          )}
          {officialLeaderboardResult && (
            <Card size="small" title="官方榜单抓取结果">
              <Space direction="vertical" style={{ width: '100%' }}>
                <Row gutter={[12, 12]}>
                  <Col xs={12} sm={8}><Statistic title="抓取" value={officialLeaderboardResult.fetchedTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title="去重" value={officialLeaderboardResult.dedupedTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title="错误" value={officialLeaderboardResult.fetches.filter(item => item.error).length} /></Col>
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
            <Card size="small" title="Falcon 榜单抓取结果">
              <Space direction="vertical" style={{ width: '100%' }}>
                <Row gutter={[12, 12]}>
                  <Col xs={12} sm={8}><Statistic title="抓取" value={falconLeaderboardResult.fetchedTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title="去重" value={falconLeaderboardResult.dedupedTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title="错误" value={falconLeaderboardResult.fetches.filter(item => item.error).length} /></Col>
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
            <Card size="small" title="官方榜单质量诊断">
              <Space direction="vertical" style={{ width: '100%' }}>
                <Row gutter={[12, 12]}>
                  <Col xs={12} sm={8}><Statistic title="总数" value={officialLeaderboardDiagnose.total} /></Col>
                  <Col xs={12} sm={8}><Statistic title="PAPER" value={officialLeaderboardDiagnose.paperTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title="干净高分" value={officialLeaderboardDiagnose.cleanHighTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title="快速观察" value={officialLeaderboardDiagnose.fastWatchTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title="可进 PAPER" value={officialLeaderboardDiagnose.readyForPaperTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title="无活动样本" value={officialLeaderboardDiagnose.buckets.find(item => item.bucket === 'NO_ACTIVITY_SAMPLE')?.count || 0} /></Col>
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
                          <Text>总数 {item.total} · PAPER {item.paper} · 干净高分 {item.cleanHigh}</Text>
                          <Text type="secondary">可进 PAPER {item.readyForPaper} · 无活动 {item.noActivitySample} · 过期 {item.staleActivity}</Text>
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
                        <Text type="secondary">{item.bucket} · score {item.score || '-'} · age {item.lastSourceAgeHours ?? '-'}h</Text>
                      </Space>
                      <Tag>{item.researchState}</Tag>
                    </Space>
                  ))}
                </Space>
              </Space>
            </Card>
          )}
          {externalImportResult && (
            <Card size="small" title="最近导入结果">
              <Space direction="vertical" style={{ width: '100%' }}>
                <Row gutter={[12, 12]}>
                  <Col xs={12} sm={8}><Statistic title="请求" value={externalImportResult.requestedTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title="选中" value={externalImportResult.selectedTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title="新建" value={externalImportResult.createdTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title="更新" value={externalImportResult.updatedTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title="无效" value={externalImportResult.skippedInvalidTotal} /></Col>
                  <Col xs={12} sm={8}><Statistic title="重复/锁定" value={externalImportResult.skippedExistingTotal + externalImportResult.skippedLockedTotal} /></Col>
                </Row>
                <Space direction="vertical" style={{ width: '100%' }}>
                  {externalImportResult.previewItems.slice(0, 6).map(item => (
                    <Space key={`${item.wallet}-${item.action}`} style={{ justifyContent: 'space-between', width: '100%' }}>
                      <Space direction="vertical" size={0}>
                        <Text strong>{item.wallet.slice(0, 12)}...</Text>
                        <Text type="secondary">{item.category} · {item.sourceName} · score {item.externalScore || '-'}</Text>
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

const PaperTradeTable: React.FC<{ trades: LeaderPaperTrade[] }> = ({ trades }) => (
  <Table
    rowKey="id"
    size="small"
    dataSource={trades}
    columns={[
      { title: 'Time', dataIndex: 'eventTime', render: formatDate },
      { title: 'Side', dataIndex: 'side' },
      { title: 'Market', dataIndex: 'marketTitle', render: (value?: string, item?: LeaderPaperTrade) => value || item?.marketId },
      { title: 'Leader Price', dataIndex: 'leaderPrice' },
      { title: 'Sim Amount', dataIndex: 'simulatedAmount' },
      { title: 'Filter', dataIndex: 'filterResult' },
      { title: 'Quote', dataIndex: 'quoteConfidence' },
      { title: 'Valuation', dataIndex: 'valuationStatus', render: valuationTag }
    ]}
  />
)

const PaperPositionTable: React.FC<{ positions: LeaderPaperPosition[] }> = ({ positions }) => (
  <Table
    rowKey="id"
    size="small"
    dataSource={positions}
    columns={[
      { title: 'Market', dataIndex: 'marketId' },
      { title: 'Outcome', dataIndex: 'outcome' },
      { title: 'Qty', dataIndex: 'quantity' },
      { title: 'Cost', dataIndex: 'cost' },
      { title: 'Value', dataIndex: 'currentValue' },
      { title: 'PnL', dataIndex: 'unrealizedPnl' },
      { title: 'Quote', dataIndex: 'quoteConfidence' },
      { title: 'Valuation', dataIndex: 'valuationStatus', render: valuationTag }
    ]}
  />
)

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
