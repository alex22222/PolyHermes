import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Alert, Card, Table, Button, Space, Tag, Popconfirm, message, List, Empty, Spin, Divider, Typography, Modal, Descriptions, Statistic, Row, Col, Tooltip, Badge, Segmented, Input } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, GlobalOutlined, EyeOutlined, ReloadOutlined, WalletOutlined, CopyOutlined, LineChartOutlined, TeamOutlined, SearchOutlined, InfoCircleOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { apiService } from '../services/api'
import type { Leader, LeaderBalanceResponse, LeaderScanBatchResponse } from '../types'
import { useMediaQuery } from 'react-responsive'
import { formatUSDC } from '../utils'

const { Text } = Typography
type CopyabilityScoreKey = 'conviction' | 'execution' | 'category' | 'zombie'

const LeaderList: React.FC = () => {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const isMobile = useMediaQuery({ maxWidth: 768 })
  const [leaders, setLeaders] = useState<Leader[]>([])
  const [loading, setLoading] = useState(false)
  const [balanceMap, setBalanceMap] = useState<Record<number, { total: string; available: string; position: string }>>({})
  const [balanceLoading, setBalanceLoading] = useState<Record<number, boolean>>({})
  const [addingToPool, setAddingToPool] = useState<Record<number, boolean>>({})
  const [scanLoading, setScanLoading] = useState(false)
  const [scoreLoading, setScoreLoading] = useState(false)
  const [categoryFilter, setCategoryFilter] = useState<string>('all')
  const [nameQuery, setNameQuery] = useState<string>('')
  const [currentPage, setCurrentPage] = useState<number>(1)
  const [pageSize, setPageSize] = useState<number>(20)
  const [lastScanResult, setLastScanResult] = useState<LeaderScanBatchResponse | null>(null)

  // 详情 Modal
  const [detailModalVisible, setDetailModalVisible] = useState(false)
  const [detailLeader, setDetailLeader] = useState<Leader | null>(null)
  const [detailBalance, setDetailBalance] = useState<LeaderBalanceResponse | null>(null)
  const [detailBalanceLoading, setDetailBalanceLoading] = useState(false)

  useEffect(() => {
    setCurrentPage(1)
    fetchLeaders()
  }, [categoryFilter])

  const buildListRequest = (currentNameQuery?: string) => {
    const request: { category?: string; name?: string } = {}
    if (categoryFilter !== 'all') {
      request.category = categoryFilter
    }
    const name = (currentNameQuery !== undefined ? currentNameQuery : nameQuery).trim()
    if (name) {
      request.name = name
    }
    return request
  }

  const categoryOptions = [
    { label: t('leaderList.categoryAll') || '全部', value: 'all' },
    { label: t('leaderList.categoryPolitics') || '政治', value: 'politics' },
    { label: t('leaderList.categorySports') || '体育', value: 'sports' },
    { label: t('leaderList.categoryCrypto') || '加密货币', value: 'crypto' },
    { label: t('leaderList.categoryFinance') || '金融', value: 'finance' }
  ]

  const getCategoryLabel = (category?: string) => {
    const option = categoryOptions.find((item) => item.value === category)
    return option?.label || category || '-'
  }

  const getCategoryColor = (category?: string) => {
    switch (category) {
      case 'politics':
        return 'purple'
      case 'sports':
        return 'blue'
      case 'crypto':
        return 'green'
      case 'finance':
        return 'gold'
      default:
        return 'default'
    }
  }

  const getResearchTagColor = (tag?: string) => {
    switch (tag) {
      case 'ELITE':
        return 'green'
      case 'TRADEABLE':
        return 'blue'
      case 'CANDIDATE':
        return 'orange'
      case 'WATCH':
        return 'gold'
      case 'RISKY':
        return 'red'
      default:
        return 'default'
    }
  }

  const getResearchTagLabel = (tag?: string) => {
    switch (tag) {
      case 'ELITE':
        return t('leaderList.researchTagElite') || '优质'
      case 'TRADEABLE':
        return t('leaderList.researchTagTradeable') || '可跟单'
      case 'CANDIDATE':
        return t('leaderList.researchTagCandidate') || '候选'
      case 'WATCH':
        return t('leaderList.researchTagWatch') || '观察'
      case 'RISKY':
        return t('leaderList.researchTagRisky') || '风险'
      default:
        return t('leaderList.researchTagUnscored') || '未评分'
    }
  }

  const getScoreColor = (score?: number, inverse = false) => {
    if (score == null) return 'default'
    if (inverse) {
      return score >= 70 ? 'red' : score >= 40 ? 'orange' : 'green'
    }
    return score >= 70 ? 'green' : score >= 40 ? 'blue' : score >= 20 ? 'orange' : 'red'
  }

  const copyabilityScoreInfo: Record<CopyabilityScoreKey, { label: string; description: string; inverse?: boolean }> = {
    conviction: {
      label: t('leaderList.convictionScore') || '信念',
      description: t('leaderList.convictionScoreDesc') || '看 Leader 单笔平均金额，越高代表下注更有分量，越低越可能是长尾低价铺单。'
    },
    execution: {
      label: t('leaderList.executionScore') || '执行',
      description: t('leaderList.executionScoreDesc') || '看真实跟单链路的 BUY/SELL 成功率、过滤记录、Bridge 失败记录和未卖出积压，越高越适合复制。'
    },
    category: {
      label: t('leaderList.categoryScore') || '领域',
      description: t('leaderList.categoryScoreDesc') || '按策略目标给政治、金融更高权重，体育、加密货币较低权重，并结合聪明钱排名加分。'
    },
    zombie: {
      label: t('leaderList.zombieRiskScore') || '僵尸',
      description: t('leaderList.zombieRiskScoreDesc') || '衡量僵尸仓位和不可复制风险，越高越危险；高分通常来自亏损、回测无交易、高回撤或没有卖出。',
      inverse: true
    }
  }

  const copyabilityScoreItems: CopyabilityScoreKey[] = ['conviction', 'execution', 'category', 'zombie']

  const renderScoreExplanation = (key: CopyabilityScoreKey) => {
    const info = copyabilityScoreInfo[key]
    return (
      <Space direction="vertical" size={2}>
        <Text strong>{info.label}</Text>
        <Text style={{ fontSize: 12 }}>{info.description}</Text>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {info.inverse ? (t('leaderList.scoreLowerBetter') || '越低越好') : (t('leaderList.scoreHigherBetter') || '越高越好')}
        </Text>
      </Space>
    )
  }

  const renderScoreTag = (label: string, score?: number, inverse = false, scoreKey?: CopyabilityScoreKey) => {
    const tag = (
      <Tag color={getScoreColor(score, inverse)} style={{ marginRight: 0, cursor: scoreKey ? 'help' : 'default' }}>
        {label} {score != null ? score.toFixed(0) : '-'}
      </Tag>
    )
    return scoreKey ? <Tooltip title={renderScoreExplanation(scoreKey)}>{tag}</Tooltip> : tag
  }

  const hasCopyabilityScores = (leader: Leader) => (
    leader.convictionScore != null ||
    leader.executionScore != null ||
    leader.categoryScore != null ||
    leader.zombieRiskScore != null
  )

  const renderCopyabilityScores = (leader: Leader) => (
    <Space size={[4, 4]} wrap>
      {renderScoreTag(copyabilityScoreInfo.conviction.label, leader.convictionScore, false, 'conviction')}
      {renderScoreTag(copyabilityScoreInfo.execution.label, leader.executionScore, false, 'execution')}
      {renderScoreTag(copyabilityScoreInfo.category.label, leader.categoryScore, false, 'category')}
      {renderScoreTag(copyabilityScoreInfo.zombie.label, leader.zombieRiskScore, true, 'zombie')}
    </Space>
  )

  const fetchLeaders = async (currentNameQuery?: string) => {
    setLoading(true)
    try {
      const response = await apiService.leaders.list(buildListRequest(currentNameQuery))
      if (response.data.code === 0 && response.data.data) {
        setLeaders(response.data.data.list || [])
      } else {
        message.error(response.data.msg || t('leaderList.fetchFailed'))
      }
    } catch (error: any) {
      message.error(error.message || t('leaderList.fetchFailed'))
    } finally {
      setLoading(false)
    }
  }

  const handleNameSearch = (value: string) => {
    setNameQuery(value)
    setCurrentPage(1)
    fetchLeaders(value)
  }

  const paginationConfig = {
    current: currentPage,
    pageSize: pageSize,
    showSizeChanger: true,
    pageSizeOptions: ['20', '50', '100'],
    showTotal: (total: number) => `共 ${total} 条`,
    onChange: (page: number, size?: number) => {
      setCurrentPage(page)
      if (size && size !== pageSize) {
        setPageSize(size)
        setCurrentPage(1)
      }
    },
    onShowSizeChange: (_current: number, size: number) => {
      setPageSize(size)
      setCurrentPage(1)
    }
  }

  const handleScan = async () => {
    setScanLoading(true)
    try {
      const response = await apiService.leaderScanner.run(categoryFilter === 'all' ? { dryRun: false } : { category: categoryFilter, dryRun: false })
      if (response.data.code === 0 && response.data.data) {
        const result = response.data.data
        setLastScanResult(result)
        const totalCandidates = result.totalCandidateCount ?? result.previews?.reduce((sum, item) => sum + item.candidates.length, 0) ?? 0
        const analyzedWallets = result.totalAnalyzedWalletCount ?? result.previews?.reduce((sum, item) => sum + item.analyzedWalletCount, 0) ?? 0
        message.success(t('leaderList.scanComplete', {
          candidates: totalCandidates,
          analyzed: analyzedWallets,
          created: result.createdCount,
          updated: result.updatedCount,
          duration: result.durationMs || 0
        }))

        if (categoryFilter !== 'all' && totalCandidates === 0) {
          message.info(t('leaderList.scanNoCategoryCandidates'))
          setCategoryFilter('all')
        } else {
          fetchLeaders()
        }
      } else {
        message.error(response.data.msg || t('leaderList.scanFailed'))
      }
    } catch (error: any) {
      message.error(error.message || t('leaderList.scanFailed'))
    } finally {
      setScanLoading(false)
    }
  }

  const handleScoreLeaders = async () => {
    setScoreLoading(true)
    try {
      const response = await apiService.leaderScanner.researchScore()
      if (response.data.code === 0 && response.data.data) {
        message.success(t('leaderList.scoreLeaderComplete', { count: response.data.data.scoredCount }))
        fetchLeaders()
      } else {
        message.error(response.data.msg || t('leaderList.scoreLeaderFailed'))
      }
    } catch (error: any) {
      message.error(error.message || t('leaderList.scoreLeaderFailed'))
    } finally {
      setScoreLoading(false)
    }
  }

  // 加载所有 Leader 的余额
  useEffect(() => {
    const loadBalances = async () => {
      for (const leader of leaders) {
        if (!balanceMap[leader.id] && !balanceLoading[leader.id]) {
          setBalanceLoading(prev => ({ ...prev, [leader.id]: true }))
          try {
            const balanceData = await apiService.leaders.balance({ leaderId: leader.id })
            if (balanceData.data.code === 0 && balanceData.data.data) {
              setBalanceMap(prev => ({
                ...prev,
                [leader.id]: {
                  total: balanceData.data.data.totalBalance || '0',
                  available: balanceData.data.data.availableBalance || '0',
                  position: balanceData.data.data.positionBalance || '0'
                }
              }))
            }
          } catch (error) {
            console.error(`获取 Leader ${leader.id} 余额失败:`, error)
            setBalanceMap(prev => ({
              ...prev,
              [leader.id]: { total: '-', available: '-', position: '-' }
            }))
          } finally {
            setBalanceLoading(prev => ({ ...prev, [leader.id]: false }))
          }
        }
      }
    }

    if (leaders.length > 0) {
      loadBalances()
    }
  }, [leaders])

  const handleDelete = async (leaderId: number) => {
    try {
      const response = await apiService.leaders.delete({ leaderId })
      if (response.data.code === 0) {
        message.success(t('leaderList.deleteSuccess'))
        fetchLeaders()
      } else {
        message.error(response.data.msg || t('leaderList.deleteFailed'))
      }
    } catch (error: any) {
      message.error(error.message || t('leaderList.deleteFailed'))
    }
  }

  const handleAddToPool = async (leader: Leader) => {
    setAddingToPool(prev => ({ ...prev, [leader.id]: true }))
    try {
      const response = await apiService.leaderPool.add({ leaderId: leader.id })
      if (response.data.code === 0) {
        message.success({
          content: (
            <Space>
              <span>{t('leaderList.addToPoolSuccess')}</span>
              <Button type="link" size="small" onClick={() => navigate('/leader-pool')}>
                {t('leaderList.goLeaderPool')}
              </Button>
            </Space>
          )
        })
      } else {
        message.warning(response.data.msg || t('leaderList.addToPoolExists'))
      }
    } catch (error: any) {
      message.error(error.message || t('leaderList.addToPoolFailed'))
    } finally {
      setAddingToPool(prev => ({ ...prev, [leader.id]: false }))
    }
  }

  const handleShowDetail = async (leader: Leader) => {
    try {
      setDetailModalVisible(true)
      setDetailLeader(leader)
      setDetailBalance(null)
      setDetailBalanceLoading(false)

      // 加载详情和余额
      try {
        const leaderDetail = await apiService.leaders.detail({ leaderId: leader.id })
        if (leaderDetail.data.code === 0 && leaderDetail.data.data) {
          setDetailLeader(leaderDetail.data.data)
        }

        // 加载余额
        setDetailBalanceLoading(true)
        try {
          const balanceData = await apiService.leaders.balance({ leaderId: leader.id })
          if (balanceData.data.code === 0 && balanceData.data.data) {
            setDetailBalance(balanceData.data.data)
          }
        } catch (error) {
          console.error('获取余额失败:', error)
          setDetailBalance(null)
        } finally {
          setDetailBalanceLoading(false)
        }
      } catch (error: any) {
        console.error('获取 Leader 详情失败:', error)
        message.error(error.message || t('leaderList.fetchFailed'))
        setDetailModalVisible(false)
        setDetailLeader(null)
      }
    } catch (error: any) {
      console.error('打开详情失败:', error)
      message.error(error.message || t('leaderList.openDetailFailed'))
      setDetailModalVisible(false)
      setDetailLeader(null)
    }
  }

  const handleRefreshDetailBalance = async () => {
    if (!detailLeader) return

    setDetailBalanceLoading(true)
    try {
      const balanceData = await apiService.leaders.balance({ leaderId: detailLeader.id })
      if (balanceData.data.code === 0 && balanceData.data.data) {
        setDetailBalance(balanceData.data.data)
        message.success(t('leaderDetail.refresh'))
      }
    } catch (error: any) {
      message.error(error.message || t('leaderDetail.fetchBalanceFailed'))
    } finally {
      setDetailBalanceLoading(false)
    }
  }

  const formatTimestamp = (timestamp: number) => {
    const date = new Date(timestamp)
    return date.toLocaleString(i18n.language || 'zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  const getPositionColumns = () => {
    return [
      {
        title: t('leaderDetail.market'),
        dataIndex: 'title',
        key: 'title',
        render: (title: string) => {
          if (!title) return <Text type="secondary">-</Text>
          const displayText = isMobile && title.length > 20 ? `${title.slice(0, 20)}...` : title
          return <Text style={{ fontSize: isMobile ? '12px' : '13px' }}>{displayText}</Text>
        }
      },
      {
        title: t('leaderDetail.side'),
        dataIndex: 'side',
        key: 'side',
        render: (side: string) => {
          const color = side === 'YES' ? 'green' : 'red'
          return <Tag color={color}>{side}</Tag>
        }
      },
      {
        title: t('leaderDetail.quantity'),
        dataIndex: 'quantity',
        key: 'quantity',
        render: (quantity: string) => formatUSDC(quantity)
      },
      {
        title: t('leaderDetail.avgPrice'),
        dataIndex: 'avgPrice',
        key: 'avgPrice',
        render: (price: string) => formatUSDC(price)
      },
      {
        title: t('leaderDetail.currentValue'),
        dataIndex: 'currentValue',
        key: 'currentValue',
        render: (value: string) => formatUSDC(value)
      },
      {
        title: t('leaderDetail.pnl'),
        dataIndex: 'pnl',
        key: 'pnl',
        render: (pnl: string | undefined) => {
          if (!pnl || pnl === '0') {
            return <Text type="secondary">-</Text>
          } else {
            const numPnl = parseFloat(pnl)
            const color = numPnl > 0 ? '#52c41a' : '#ff4d4f'
            return <Text style={{ color }}>{formatUSDC(pnl)}</Text>
          }
        }
      }
    ]
  }

  const columns = [
    {
      title: t('leaderList.leaderName'),
      dataIndex: 'leaderName',
      key: 'leaderName',
      width: 240,
      render: (text: string, record: Leader) => (
        <Space direction="vertical" size={0}>
          <Space size={4} align="center">
            <Text strong style={{ fontSize: '14px' }}>{text || `Leader ${record.id}`}</Text>
            {record.remark && (
              <Tooltip title={record.remark} placement="top">
                <Tag color="orange" style={{ cursor: 'help', fontSize: '11px', padding: '0 4px', lineHeight: '16px', margin: 0 }}>
                  {t('leaderList.remark')}
                </Tag>
              </Tooltip>
            )}
          </Space>
          <Text type="secondary" style={{ fontSize: '12px', fontFamily: 'monospace' }}>{record.leaderAddress}</Text>
        </Space>
      )
    },
    {
      title: t('leaderList.category') || '分类',
      dataIndex: 'category',
      key: 'category',
      width: 100,
      align: 'center' as const,
      render: (category: string | undefined) => (
        <Tag color={getCategoryColor(category)}>{getCategoryLabel(category)}</Tag>
      )
    },
    {
      title: t('leaderDetail.availableBalance'),
      key: 'balance',
      width: 180,
      render: (_: any, record: Leader) => {
        const balance = balanceMap[record.id]
        if (!balance) return <Spin size="small" />
        return (
          <Space direction="vertical" size={0}>
            <Text style={{ color: '#52c41a', fontSize: '14px', fontWeight: '500' }}>
              {balance.available === '-' ? '-' : `$${formatUSDC(balance.available)}`}
            </Text>
            <Text type="secondary" style={{ fontSize: '12px' }}>
              {t('leaderDetail.positionBalance')}: {formatUSDC(balance.position)}
            </Text>
          </Space>
        )
      }
    },
    {
      title: t('leaderList.smartMoneyRank'),
      dataIndex: 'smartMoneyRank',
      key: 'smartMoneyRank',
      width: 100,
      align: 'center' as const,
      sorter: (a: Leader, b: Leader) => (a.smartMoneyRank ?? Number.MAX_VALUE) - (b.smartMoneyRank ?? Number.MAX_VALUE),
      render: (rank: number | undefined) => {
        if (!rank) return <Text type="secondary">-</Text>
        const color = rank <= 3 ? 'gold' : rank <= 6 ? 'blue' : 'default'
        return (
          <Badge count={rank} style={{ backgroundColor: color === 'gold' ? '#faad14' : color === 'blue' ? '#1890ff' : undefined }} />
        )
      }
    },
    {
      title: t('leaderList.researchTag') || '研究标签',
      key: 'researchTag',
      width: 110,
      align: 'center' as const,
      sorter: (a: Leader, b: Leader) => (a.researchScore ?? -1) - (b.researchScore ?? -1),
      render: (_: any, record: Leader) => {
        const tag = record.researchTag
        const score = record.researchScore
        const flags = record.researchRiskFlags
        return (
          <Tooltip title={flags ? `${t('leaderList.riskFlags') || '风险'}: ${flags}` : ''}>
            <Tag color={getResearchTagColor(tag)} style={{ fontSize: '12px', fontWeight: 600 }}>
              {getResearchTagLabel(tag)}
              {score != null && <span style={{ marginLeft: 4, opacity: 0.85 }}>{score.toFixed(0)}</span>}
            </Tag>
          </Tooltip>
        )
      }
    },
    {
      title: t('leaderList.copyabilityComponents') || '复制评分',
      key: 'copyabilityComponents',
      width: 190,
      render: (_: any, record: Leader) => (
        renderCopyabilityScores(record)
      )
    },
    {
      title: t('leaderList.winRate'),
      dataIndex: 'winRate',
      key: 'winRate',
      width: 100,
      align: 'center' as const,
      sorter: (a: Leader, b: Leader) => (a.winRate ?? -1) - (b.winRate ?? -1),
      render: (winRate: number | undefined) => {
        if (winRate == null) return <Text type="secondary">-</Text>
        const color = winRate >= 60 ? '#52c41a' : winRate >= 40 ? '#faad14' : '#ff4d4f'
        return <Text style={{ color, fontWeight: 600 }}>{winRate.toFixed(1)}%</Text>
      }
    },
    {
      title: t('leaderList.totalPnl'),
      dataIndex: 'totalPnl',
      key: 'totalPnl',
      width: 120,
      align: 'right' as const,
      sorter: (a: Leader, b: Leader) => parseFloat(a.totalPnl || '0') - parseFloat(b.totalPnl || '0'),
      render: (pnl: string | undefined) => {
        if (!pnl) return <Text type="secondary">-</Text>
        const num = parseFloat(pnl)
        const color = num > 0 ? '#52c41a' : num < 0 ? '#ff4d4f' : '#8c8c8c'
        return <Text style={{ color, fontWeight: 500 }}>${formatUSDC(pnl)}</Text>
      }
    },
    {
      title: t('leaderList.totalTrades'),
      dataIndex: 'totalTrades',
      key: 'totalTrades',
      width: 90,
      align: 'center' as const,
      sorter: (a: Leader, b: Leader) => (a.totalTrades ?? -1) - (b.totalTrades ?? -1),
      render: (trades: number | undefined) => {
        if (trades == null) return <Text type="secondary">-</Text>
        return <Tag color="processing">{trades}</Tag>
      }
    },
    {
      title: t('leaderList.activityScore'),
      dataIndex: 'activityScore',
      key: 'activityScore',
      width: 100,
      align: 'center' as const,
      sorter: (a: Leader, b: Leader) => (a.activityScore ?? -1) - (b.activityScore ?? -1),
      render: (score: number | undefined) => {
        if (score == null) return <Text type="secondary">-</Text>
        const color = score >= 70 ? 'success' : score >= 40 ? 'warning' : 'error'
        return <Badge status={color as any} text={score.toFixed(0)} />
      }
    },
    {
      title: t('common.actions'),
      key: 'action',
      width: 200,
      fixed: 'right' as const,
      render: (_: any, record: Leader) => (
        <Space size={4}>
          <Tooltip title={t('common.viewDetail')}>
            <div
              onClick={() => handleShowDetail(record)}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '32px',
                height: '32px',
                cursor: 'pointer',
                borderRadius: '6px',
                transition: 'background-color 0.2s'
              }}
              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#f0f0f0'}
              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
            >
              <EyeOutlined style={{ fontSize: '16px', color: '#1890ff' }} />
            </div>
          </Tooltip>

          {record.website && (
            <Tooltip title={t('leaderList.openWebsite')}>
              <div
                onClick={() => window.open(record.website, '_blank', 'noopener,noreferrer')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '32px',
                  height: '32px',
                  cursor: 'pointer',
                  borderRadius: '6px',
                  transition: 'background-color 0.2s'
                }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#f0f0f0'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
              >
                <GlobalOutlined style={{ fontSize: '16px', color: '#1890ff' }} />
              </div>
            </Tooltip>
          )}

          <Tooltip title={t('common.edit')}>
            <div
              onClick={() => navigate(`/leaders/edit?id=${record.id}`)}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '32px',
                height: '32px',
                cursor: 'pointer',
                borderRadius: '6px',
                transition: 'background-color 0.2s'
              }}
              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#f0f0f0'}
              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
            >
              <EditOutlined style={{ fontSize: '16px', color: '#1890ff' }} />
            </div>
          </Tooltip>

          <Tooltip title={`${t('leaderList.viewCopyTradings')} (${record.copyTradingCount})`}>
            <div
              onClick={() => {
                if (record.copyTradingCount > 0) {
                  navigate(`/copy-trading?leaderId=${record.id}`)
                }
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '32px',
                height: '32px',
                cursor: record.copyTradingCount === 0 ? 'not-allowed' : 'pointer',
                borderRadius: '6px',
                opacity: record.copyTradingCount === 0 ? 0.4 : 1,
                transition: 'background-color 0.2s'
              }}
              onMouseEnter={(e) => record.copyTradingCount > 0 && (e.currentTarget.style.backgroundColor = '#f0f0f0')}
              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
            >
              <Badge count={record.copyTradingCount} size="small" offset={[-4, -4]}>
                <CopyOutlined style={{ fontSize: '16px', color: '#1890ff' }} />
              </Badge>
            </div>
          </Tooltip>

          <Tooltip title={`${t('leaderList.viewBacktests')} (${record.backtestCount})`}>
            <div
              onClick={() => {
                if (record.backtestCount > 0) {
                  navigate(`/backtest?leaderId=${record.id}`)
                }
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '32px',
                height: '32px',
                cursor: record.backtestCount === 0 ? 'not-allowed' : 'pointer',
                borderRadius: '6px',
                opacity: record.backtestCount === 0 ? 0.4 : 1,
                transition: 'background-color 0.2s'
              }}
              onMouseEnter={(e) => record.backtestCount > 0 && (e.currentTarget.style.backgroundColor = '#f0f0f0')}
              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
            >
              <Badge count={record.backtestCount} size="small" offset={[-4, -4]}>
                <LineChartOutlined style={{ fontSize: '16px', color: '#1890ff' }} />
              </Badge>
            </div>
          </Tooltip>

          <Tooltip title={t('leaderList.addToPool')}>
            <div
              onClick={() => !addingToPool[record.id] && handleAddToPool(record)}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '32px',
                height: '32px',
                cursor: addingToPool[record.id] ? 'wait' : 'pointer',
                borderRadius: '6px',
                transition: 'background-color 0.2s'
              }}
              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#f0f0f0'}
              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
            >
              <TeamOutlined style={{ fontSize: '16px', color: '#52c41a' }} />
            </div>
          </Tooltip>

          <Popconfirm
            title={t('leaderList.deleteConfirm')}
            description={record.copyTradingCount > 0 ? t('leaderList.deleteConfirmDesc', { count: record.copyTradingCount }) : undefined}
            onConfirm={() => handleDelete(record.id)}
            okText={t('common.confirm')}
            cancelText={t('common.cancel')}
          >
            <Tooltip title={t('common.delete')}>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '32px',
                  height: '32px',
                  cursor: 'pointer',
                  borderRadius: '6px',
                  transition: 'background-color 0.2s'
                }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#fff1f0'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
              >
                <DeleteOutlined style={{ fontSize: '16px', color: '#ff4d4f' }} />
              </div>
            </Tooltip>
          </Popconfirm>
        </Space>
      )
    }
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: '12px' }}>
        <h2 style={{ margin: 0, fontSize: isMobile ? '20px' : '24px' }}>{t('leaderList.title')}</h2>
        <Space wrap>
          <Segmented
            value={categoryFilter}
            onChange={(value) => setCategoryFilter(value as string)}
            options={categoryOptions}
          />
          <Input.Search
            placeholder={t('leaderList.searchPlaceholder') || '搜索 Leader 名称'}
            value={nameQuery}
            onChange={(e) => setNameQuery(e.target.value)}
            onSearch={handleNameSearch}
            allowClear
            style={{ width: isMobile ? 180 : 260 }}
          />
          <Tooltip title={t('leaderList.scanTooltip') || '扫描 Polymarket 活跃 Leader'}>
            <Button
              icon={<SearchOutlined />}
              onClick={handleScan}
              loading={scanLoading}
              size={isMobile ? 'middle' : 'large'}
              style={{ borderRadius: '8px', height: isMobile ? '40px' : '48px', fontSize: isMobile ? '14px' : '16px' }}
            >
              {t('leaderList.scan') || '扫链'}
            </Button>
          </Tooltip>
          <Tooltip title={t('leaderList.scoreLeaderTooltip') || '为所有 Leader 计算研究模块 copyability 评分'}>
            <Button
              icon={<LineChartOutlined />}
              onClick={handleScoreLeaders}
              loading={scoreLoading}
              size={isMobile ? 'middle' : 'large'}
              style={{ borderRadius: '8px', height: isMobile ? '40px' : '48px', fontSize: isMobile ? '14px' : '16px' }}
            >
              {t('leaderList.scoreLeader') || '研究评分'}
            </Button>
          </Tooltip>
          <Tooltip title={t('leaderList.addLeader')}>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/leaders/add')} size={isMobile ? 'middle' : 'large'} style={{ borderRadius: '8px', height: isMobile ? '40px' : '48px', fontSize: isMobile ? '14px' : '16px' }} />
          </Tooltip>
        </Space>
      </div>

      {lastScanResult && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: '16px' }}
          message={t('leaderList.lastScanResult')}
          description={
            <Space direction="vertical" size={6} style={{ width: '100%' }}>
              <Space wrap>
                <Tag color="blue">{t('leaderList.scanCandidates', { count: lastScanResult.totalCandidateCount ?? 0 })}</Tag>
                <Tag color="cyan">{t('leaderList.scanAnalyzed', { count: lastScanResult.totalAnalyzedWalletCount ?? 0 })}</Tag>
                <Tag color="green">{t('leaderList.scanCreated', { count: lastScanResult.createdCount })}</Tag>
                <Tag color="orange">{t('leaderList.scanUpdated', { count: lastScanResult.updatedCount })}</Tag>
              </Space>
              <Space wrap>
                {(lastScanResult.previews || []).map((preview) => (
                  <Tag key={preview.category} color={preview.candidates.length > 0 ? getCategoryColor(preview.category) : 'default'}>
                    {getCategoryLabel(preview.category)}: {preview.candidates.length}/{preview.analyzedWalletCount}
                  </Tag>
                ))}
              </Space>
            </Space>
          }
        />
      )}

      <Alert
        type="info"
        showIcon
        icon={<InfoCircleOutlined />}
        style={{ marginBottom: '16px' }}
        message={t('leaderList.copyabilityGuideTitle') || '复制评分说明'}
        description={
          <Row gutter={[12, 8]}>
            {copyabilityScoreItems.map((key) => {
              const info = copyabilityScoreInfo[key]
              return (
                <Col key={key} xs={24} sm={12} lg={6}>
                  <Space direction="vertical" size={2}>
                    <Space size={4}>
                      <Tag color={getScoreColor(info.inverse ? 20 : 80, info.inverse)} style={{ marginRight: 0 }}>{info.label}</Tag>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {info.inverse ? (t('leaderList.scoreLowerBetter') || '越低越好') : (t('leaderList.scoreHigherBetter') || '越高越好')}
                      </Text>
                    </Space>
                    <Text style={{ fontSize: 12 }}>{info.description}</Text>
                  </Space>
                </Col>
              )
            })}
          </Row>
        }
      />

      <Card style={{ borderRadius: '12px', boxShadow: '0 2px 8px rgba(0,0,0,0.08)', border: '1px solid #e8e8e8' }} bodyStyle={{ padding: isMobile ? '12px' : '24px' }}>
        {isMobile ? (
          <div>
            {loading ? (
              <div style={{ textAlign: 'center', padding: '40px' }}>
                <Spin size="large" />
              </div>
            ) : leaders.length === 0 ? (
              <Empty description={t('leaderList.noData')} />
            ) : (
              <List
                dataSource={leaders}
                renderItem={(leader) => {
                  const balance = balanceMap[leader.id]

                  return (
                    <Card
                      key={leader.id}
                      style={{
                        marginBottom: '10px',
                        borderRadius: '10px',
                        boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
                        border: '1px solid #e8e8e8',
                        overflow: 'hidden'
                      }}
                      bodyStyle={{ padding: '0' }}
                    >
                      {/* 头部区域 - 名称和地址 */}
                      <div style={{
                        padding: '10px 12px',
                        background: 'var(--ant-color-primary, #1677ff)',
                        color: '#fff'
                      }}>
                        <div style={{ fontSize: '15px', fontWeight: '600', marginBottom: '2px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                          <Space size={6}>
                            <span>{leader.leaderName || `Leader ${leader.id}`}</span>
                            <Tag color={getCategoryColor(leader.category)} style={{ marginRight: 0 }}>{getCategoryLabel(leader.category)}</Tag>
                          </Space>
                          <Space size={6}>
                            {leader.researchTag && (
                              <Tag color={getResearchTagColor(leader.researchTag)} style={{ fontSize: '11px', fontWeight: 600, marginRight: 0 }}>
                                {getResearchTagLabel(leader.researchTag)}
                                {leader.researchScore != null && <span style={{ marginLeft: 3, opacity: 0.85 }}>{leader.researchScore.toFixed(0)}</span>}
                              </Tag>
                            )}
                            {leader.website && (
                              <GlobalOutlined
                                style={{ fontSize: '13px', cursor: 'pointer', opacity: 0.8 }}
                                onClick={() => window.open(leader.website, '_blank', 'noopener,noreferrer')}
                              />
                            )}
                          </Space>
                        </div>
                        <div style={{ fontSize: '10px', opacity: '0.85', fontFamily: 'monospace', wordBreak: 'break-all' }}>
                          {leader.leaderAddress}
                        </div>
                      </div>

                      {/* 资产区域 - 常驻显示 */}
                      <div style={{
                        padding: '8px 12px',
                        backgroundColor: '#fafafa',
                        borderBottom: '1px solid #f0f0f0',
                        minHeight: '42px',
                        display: 'flex',
                        alignItems: 'center'
                      }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
                          <div>
                            <div style={{ fontSize: '10px', color: '#8c8c8c' }}>
                              {t('leaderDetail.availableBalance')}
                            </div>
                            <div style={{ fontSize: '14px', fontWeight: '600', color: '#52c41a' }}>
                              {balance?.available && balance.available !== '-' ? `$${formatUSDC(balance.available)}` : '-'}
                            </div>
                          </div>
                          <div style={{ textAlign: 'right' }}>
                            <div style={{ fontSize: '10px', color: '#8c8c8c' }}>
                              {t('leaderDetail.positionBalance')}
                            </div>
                            <div style={{ fontSize: '14px', fontWeight: '500', color: '#722ed1' }}>
                              {balance?.position && balance.position !== '-' ? formatUSDC(balance.position) : '-'}
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* 扫描数据区域 - 移动端 */}
                      {(leader.smartMoneyRank != null || leader.winRate != null || leader.totalPnl != null) && (
                        <div style={{
                          padding: '8px 12px',
                          backgroundColor: '#f6ffed',
                          borderBottom: '1px solid #b7eb8f',
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          flexWrap: 'wrap',
                          gap: '4px'
                        }}>
                          {leader.smartMoneyRank != null && (
                            <div style={{ textAlign: 'center' }}>
                              <div style={{ fontSize: '10px', color: '#8c8c8c' }}>{t('leaderList.smartMoneyRank')}</div>
                              <div style={{ fontSize: '13px', fontWeight: '600', color: '#faad14' }}>#{leader.smartMoneyRank}</div>
                            </div>
                          )}
                          {leader.winRate != null && (
                            <div style={{ textAlign: 'center' }}>
                              <div style={{ fontSize: '10px', color: '#8c8c8c' }}>{t('leaderList.winRate')}</div>
                              <div style={{ fontSize: '13px', fontWeight: '600', color: leader.winRate >= 60 ? '#52c41a' : '#faad14' }}>{leader.winRate.toFixed(1)}%</div>
                            </div>
                          )}
                          {leader.totalPnl != null && (
                            <div style={{ textAlign: 'center' }}>
                              <div style={{ fontSize: '10px', color: '#8c8c8c' }}>{t('leaderList.totalPnl')}</div>
                              <div style={{ fontSize: '13px', fontWeight: '600', color: parseFloat(leader.totalPnl) > 0 ? '#52c41a' : '#ff4d4f' }}>${formatUSDC(leader.totalPnl)}</div>
                            </div>
                          )}
                          {leader.totalTrades != null && (
                            <div style={{ textAlign: 'center' }}>
                              <div style={{ fontSize: '10px', color: '#8c8c8c' }}>{t('leaderList.totalTrades')}</div>
                              <div style={{ fontSize: '13px', fontWeight: '600', color: '#1890ff' }}>{leader.totalTrades}</div>
                            </div>
                          )}
                          {leader.activityScore != null && (
                            <div style={{ textAlign: 'center' }}>
                              <div style={{ fontSize: '10px', color: '#8c8c8c' }}>{t('leaderList.activityScore')}</div>
                              <div style={{ fontSize: '13px', fontWeight: '600', color: leader.activityScore >= 70 ? '#52c41a' : '#faad14' }}>{leader.activityScore.toFixed(0)}</div>
                            </div>
                          )}
                        </div>
                      )}

                      {hasCopyabilityScores(leader) && (
                        <div style={{
                          padding: '8px 12px',
                          backgroundColor: '#f0f7ff',
                          borderBottom: '1px solid #d6e4ff'
                        }}>
                          <div style={{ fontSize: '10px', color: '#8c8c8c', marginBottom: 4 }}>
                            {t('leaderList.copyabilityComponents') || '复制评分'}
                          </div>
                          {renderCopyabilityScores(leader)}
                        </div>
                      )}

                      {/* 备注区域 */}
                      {leader.remark && (
                        <div style={{
                          padding: '6px 12px',
                          backgroundColor: '#fffbe6',
                          borderBottom: '1px solid #ffe58f',
                          fontSize: '11px',
                          color: '#8c8c8c'
                        }}>
                          <span style={{ color: '#d48806' }}>{t('leaderList.remark')}：</span>
                          <span>{leader.remark}</span>
                        </div>
                      )}

                      {/* 图标操作栏 */}
                      <div style={{
                        padding: '8px 12px',
                        display: 'flex',
                        justifyContent: 'space-around',
                        alignItems: 'center'
                      }}>
                        <Tooltip title={t('common.viewDetail')}>
                          <div
                            onClick={() => handleShowDetail(leader)}
                            style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', cursor: 'pointer', padding: '4px 8px' }}
                          >
                            <EyeOutlined style={{ fontSize: '18px', color: '#1890ff' }} />
                            <span style={{ fontSize: '10px', color: '#8c8c8c', marginTop: '2px' }}>{t('common.viewDetail')}</span>
                          </div>
                        </Tooltip>

                        <Tooltip title={t('common.edit')}>
                          <div
                            onClick={() => navigate(`/leaders/edit?id=${leader.id}`)}
                            style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', cursor: 'pointer', padding: '4px 8px' }}
                          >
                            <EditOutlined style={{ fontSize: '18px', color: '#1890ff' }} />
                            <span style={{ fontSize: '10px', color: '#8c8c8c', marginTop: '2px' }}>{t('common.edit')}</span>
                          </div>
                        </Tooltip>

                        <Tooltip title={t('leaderList.viewCopyTradings')}>
                          <div
                            onClick={() => navigate(`/copy-trading?leaderId=${leader.id}`)}
                            style={{
                              display: 'flex',
                              flexDirection: 'column',
                              alignItems: 'center',
                              cursor: leader.copyTradingCount === 0 ? 'not-allowed' : 'pointer',
                              padding: '4px 8px',
                              opacity: leader.copyTradingCount === 0 ? 0.4 : 1
                            }}
                          >
                            <Badge count={leader.copyTradingCount} size="small" offset={[-2, -2]}>
                              <CopyOutlined style={{ fontSize: '18px', color: '#1890ff' }} />
                            </Badge>
                            <span style={{ fontSize: '10px', color: '#8c8c8c', marginTop: '2px' }}>{t('leaderList.viewCopyTradings')}</span>
                          </div>
                        </Tooltip>

                        <Tooltip title={t('leaderList.viewBacktests')}>
                          <div
                            onClick={() => navigate(`/backtest?leaderId=${leader.id}`)}
                            style={{
                              display: 'flex',
                              flexDirection: 'column',
                              alignItems: 'center',
                              cursor: leader.backtestCount === 0 ? 'not-allowed' : 'pointer',
                              padding: '4px 8px',
                              opacity: leader.backtestCount === 0 ? 0.4 : 1
                            }}
                          >
                            <Badge count={leader.backtestCount} size="small" offset={[-2, -2]}>
                              <LineChartOutlined style={{ fontSize: '18px', color: '#1890ff' }} />
                            </Badge>
                            <span style={{ fontSize: '10px', color: '#8c8c8c', marginTop: '2px' }}>{t('leaderList.viewBacktests')}</span>
                          </div>
                        </Tooltip>

                        <Popconfirm
                          title={t('leaderList.deleteConfirm')}
                          description={leader.copyTradingCount > 0 ? t('leaderList.deleteConfirmDesc', { count: leader.copyTradingCount }) : undefined}
                          onConfirm={() => handleDelete(leader.id)}
                          okText={t('common.confirm')}
                          cancelText={t('common.cancel')}
                        >
                          <Tooltip title={t('common.delete')}>
                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', cursor: 'pointer', padding: '4px 8px' }}>
                              <DeleteOutlined style={{ fontSize: '18px', color: '#ff4d4f' }} />
                              <span style={{ fontSize: '10px', color: '#8c8c8c', marginTop: '2px' }}>{t('common.delete')}</span>
                            </div>
                          </Tooltip>
                        </Popconfirm>
                      </div>
                    </Card>
                  )
                }}
                pagination={paginationConfig}
              />
            )}
          </div>
        ) : (
          <Table
            dataSource={leaders}
            columns={columns}
            rowKey="id"
            loading={loading}
            pagination={paginationConfig}
            size="large"
            style={{ fontSize: '14px' }}
          />
        )}
      </Card>

      {/* 详情 Modal */}
      <Modal
        title={
          <Space>
            <WalletOutlined />
            <span>{t('leaderDetail.title')}</span>
          </Space>
        }
        open={detailModalVisible}
        onCancel={() => setDetailModalVisible(false)}
        footer={[
          <Button key="close" onClick={() => setDetailModalVisible(false)}>{t('common.close')}</Button>
        ]}
        width={isMobile ? '95%' : 1000}
        style={{ top: 20 }}
      >
        {!detailLeader ? (
          <div style={{ textAlign: 'center', padding: '40px' }}>
            <Spin size="large" />
          </div>
        ) : (
          <>
            {/* 基本信息 */}
            <Descriptions
              title={
                <Space>
                  <WalletOutlined />
                  <span style={{ fontSize: '16px', fontWeight: 'bold' }}>{t('leaderDetail.basicInfo')}</span>
                </Space>
              }
              bordered
              column={isMobile ? 1 : 2}
              size={isMobile ? 'small' : 'default'}
            >
              <Descriptions.Item label={t('leaderDetail.leaderName')}>
                {detailLeader.leaderName || `Leader ${detailLeader.id}`}
              </Descriptions.Item>
              <Descriptions.Item label={t('leaderDetail.leaderAddress')}>
                <span style={{ fontFamily: 'monospace' }}>{detailLeader.leaderAddress}</span>
              </Descriptions.Item>
              <Descriptions.Item label={t('leaderDetail.copyTradingCount')}>
                <Tag color="cyan">{detailLeader.copyTradingCount || 0}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('leaderDetail.remark')}>
                {detailLeader.remark || <Text type="secondary">-</Text>}
              </Descriptions.Item>
              <Descriptions.Item label={t('leaderDetail.updatedAt')}>
                {formatTimestamp(detailLeader.updatedAt)}
              </Descriptions.Item>
              <Descriptions.Item label={t('leaderDetail.website')}>
                {detailLeader.website ? (
                  <Button type="link" icon={<GlobalOutlined />} onClick={() => window.open(detailLeader.website, '_blank', 'noopener,noreferrer')} style={{ padding: 0 }}>
                    {t('leaderDetail.openWebsite')}
                  </Button>
                ) : <Text type="secondary">-</Text>}
              </Descriptions.Item>
            </Descriptions>

            <Divider />

            {/* 聪明钱分析 */}
            {(detailLeader.smartMoneyRank != null || detailLeader.winRate != null || detailLeader.totalPnl != null) && (
              <>
                <Descriptions
                  title={
                    <Space>
                      <SearchOutlined />
                      <span style={{ fontSize: '16px', fontWeight: 'bold' }}>{t('leaderDetail.smartMoneyAnalysis')}</span>
                    </Space>
                  }
                  bordered
                  column={isMobile ? 1 : 2}
                  size={isMobile ? 'small' : 'default'}
                >
                  <Descriptions.Item label={t('leaderDetail.smartMoneyRank')}>
                    {detailLeader.smartMoneyRank ? (
                      <Tag color={detailLeader.smartMoneyRank <= 3 ? 'gold' : detailLeader.smartMoneyRank <= 6 ? 'blue' : 'default'}>
                        #{detailLeader.smartMoneyRank}
                      </Tag>
                    ) : <Text type="secondary">-</Text>}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('leaderDetail.winRate')}>
                    {detailLeader.winRate != null ? (
                      <Text style={{ color: detailLeader.winRate >= 60 ? '#52c41a' : detailLeader.winRate >= 40 ? '#faad14' : '#ff4d4f', fontWeight: 600 }}>
                        {detailLeader.winRate.toFixed(1)}%
                      </Text>
                    ) : <Text type="secondary">-</Text>}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('leaderDetail.totalPnl')}>
                    {detailLeader.totalPnl ? (
                      <Text style={{ color: parseFloat(detailLeader.totalPnl) > 0 ? '#52c41a' : parseFloat(detailLeader.totalPnl) < 0 ? '#ff4d4f' : '#8c8c8c', fontWeight: 500 }}>
                        ${formatUSDC(detailLeader.totalPnl)}
                      </Text>
                    ) : <Text type="secondary">-</Text>}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('leaderDetail.totalVolume')}>
                    {detailLeader.totalVolume ? `$${formatUSDC(detailLeader.totalVolume)}` : <Text type="secondary">-</Text>}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('leaderDetail.totalTrades')}>
                    {detailLeader.totalTrades != null ? <Tag color="processing">{detailLeader.totalTrades}</Tag> : <Text type="secondary">-</Text>}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('leaderDetail.avgTradeSize')}>
                    {detailLeader.avgTradeSize ? `$${formatUSDC(detailLeader.avgTradeSize)}` : <Text type="secondary">-</Text>}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('leaderDetail.activityScore')}>
                    {detailLeader.activityScore != null ? (
                      <Badge status={detailLeader.activityScore >= 70 ? 'success' : detailLeader.activityScore >= 40 ? 'warning' : 'error'} text={detailLeader.activityScore.toFixed(0)} />
                    ) : <Text type="secondary">-</Text>}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('leaderDetail.scanSource')}>
                    <Tag color={detailLeader.scanSource === 'auto_scan' ? 'blue' : 'default'}>{detailLeader.scanSource || '-'}</Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label={t('leaderDetail.researchTag') || '研究标签'}>
                    {detailLeader.researchTag ? (
                      <Tag color={getResearchTagColor(detailLeader.researchTag)}>
                        {getResearchTagLabel(detailLeader.researchTag)}
                      </Tag>
                    ) : <Text type="secondary">-</Text>}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('leaderDetail.researchScore') || '研究评分'}>
                    {detailLeader.researchScore != null ? (
                      <Text strong>{detailLeader.researchScore.toFixed(1)}</Text>
                    ) : <Text type="secondary">-</Text>}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('leaderDetail.researchRiskFlags') || '风险标记'}>
                    {detailLeader.researchRiskFlags ? (
                      <Text type="warning">{detailLeader.researchRiskFlags}</Text>
                    ) : <Text type="secondary">-</Text>}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('leaderDetail.convictionScore') || '信念评分'}>
                    {renderScoreTag(copyabilityScoreInfo.conviction.label, detailLeader.convictionScore, false, 'conviction')}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('leaderDetail.executionScore') || '执行评分'}>
                    {renderScoreTag(copyabilityScoreInfo.execution.label, detailLeader.executionScore, false, 'execution')}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('leaderDetail.categoryScore') || '领域评分'}>
                    {renderScoreTag(copyabilityScoreInfo.category.label, detailLeader.categoryScore, false, 'category')}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('leaderDetail.zombieRiskScore') || '僵尸风险'}>
                    {renderScoreTag(copyabilityScoreInfo.zombie.label, detailLeader.zombieRiskScore, true, 'zombie')}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('leaderDetail.lastScan')}>
                    {detailLeader.scannedAt ? formatTimestamp(detailLeader.scannedAt) : <Text type="secondary">-</Text>}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('leaderDetail.lastTrade')}>
                    {detailLeader.lastTradeAt ? formatTimestamp(detailLeader.lastTradeAt) : <Text type="secondary">-</Text>}
                  </Descriptions.Item>
                </Descriptions>
                <Divider />
              </>
            )}

            {/* 余额信息 */}
            <div style={{ marginBottom: '16px' }}>
              <Space>
                <WalletOutlined />
                <span style={{ fontSize: '16px', fontWeight: 'bold' }}>{t('leaderDetail.balanceInfo')}</span>
                <Button type="text" size="small" icon={<ReloadOutlined />} onClick={handleRefreshDetailBalance} loading={detailBalanceLoading}>
                  {t('leaderDetail.refresh')}
                </Button>
              </Space>
            </div>

            {detailBalanceLoading && !detailBalance ? (
              <div style={{ textAlign: 'center', padding: '40px' }}>
                <Spin />
              </div>
            ) : detailBalance ? (
              <>
                <Row gutter={16} style={{ marginBottom: '16px' }}>
                  <Col xs={24} sm={8} md={6}>
                    <Card bordered={false} style={{ backgroundColor: '#f5f5f5', borderRadius: '8px' }}>
                      <Statistic
                        title={t('leaderDetail.availableBalance')}
                        value={parseFloat(detailBalance.availableBalance)}
                        precision={4}
                        valueStyle={{ color: '#1890ff' }}
                        prefix="$"
                        formatter={(value) => formatUSDC(value?.toString() || '0')}
                      />
                    </Card>
                  </Col>
                  <Col xs={24} sm={8} md={6}>
                    <Card bordered={false} style={{ backgroundColor: '#f5f5f5', borderRadius: '8px' }}>
                      <Statistic
                        title={t('leaderDetail.positionBalance')}
                        value={parseFloat(detailBalance.positionBalance)}
                        precision={4}
                        valueStyle={{ color: '#722ed1' }}
                        prefix="$"
                        formatter={(value) => formatUSDC(value?.toString() || '0')}
                      />
                    </Card>
                  </Col>
                  <Col xs={24} sm={8} md={6}>
                    <Card bordered={false} style={{ backgroundColor: '#f5f5f5', borderRadius: '8px' }}>
                      <Statistic
                        title={t('leaderDetail.totalBalance')}
                        value={parseFloat(detailBalance.totalBalance)}
                        precision={4}
                        valueStyle={{ color: '#52c41a', fontWeight: 'bold' }}
                        prefix="$"
                        formatter={(value) => formatUSDC(value?.toString() || '0')}
                      />
                    </Card>
                  </Col>
                </Row>

                {/* 持仓列表 */}
                <Divider />
                <div style={{ marginBottom: '16px' }}>
                  <Space>
                    <span style={{ fontSize: '16px', fontWeight: 'bold' }}>{t('leaderDetail.positions')}</span>
                    <Tag color="blue">{detailBalance.positions?.length || 0}</Tag>
                  </Space>
                </div>

                {detailBalance.positions && detailBalance.positions.length > 0 ? (
                  <Table
                    dataSource={detailBalance.positions}
                    columns={getPositionColumns()}
                    rowKey={(record, index) => `${record.title}-${record.side}-${index}`}
                    pagination={{ pageSize: 10, showSizeChanger: !isMobile }}
                    scroll={{ x: isMobile ? 800 : 'auto' }}
                    size={isMobile ? 'small' : 'middle'}
                  />
                ) : (
                  <Empty description={t('leaderDetail.noPositions')} />
                )}
              </>
            ) : (
              <Empty description={t('leaderDetail.noBalanceData')} />
            )}
          </>
        )}
      </Modal>
    </div>
  )
}

export default LeaderList
