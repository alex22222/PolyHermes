import { useEffect, useState } from 'react'
import { Card, Row, Col, Statistic, message, DatePicker, Space, Button, Typography, Select, Segmented, Empty } from 'antd'
import { ArrowUpOutlined, ArrowDownOutlined, ReloadOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import type { Dayjs } from 'dayjs'
import { apiService } from '../services/api'
import type { BridgeTradeStatistics, CopyTrading, CopyTradingStatistics, Leader, Statistics as StatisticsType } from '../types'
import { formatUSDC, formatNumber } from '../utils'
import { useMediaQuery } from 'react-responsive'

const { RangePicker } = DatePicker
const { Title } = Typography
type StatisticsScope = 'global' | 'leader' | 'category'

const toNumber = (value: string | number | null | undefined): number => {
  const numeric = Number(value || 0)
  return Number.isFinite(numeric) ? numeric : 0
}

const isZeroStatistics = (value: StatisticsType | null | undefined): boolean => {
  if (!value) return true
  return (
    toNumber(value.totalOrders) === 0 &&
    toNumber(value.totalPnl) === 0 &&
    toNumber(value.winRate) === 0 &&
    toNumber(value.avgPnl) === 0 &&
    toNumber(value.maxProfit) === 0 &&
    toNumber(value.maxLoss) === 0
  )
}

const aggregateDetailStatistics = (details: CopyTradingStatistics[]): StatisticsType | null => {
  if (details.length === 0) {
    return null
  }

  const totalOrders = details.reduce((sum, item) => sum + (item.totalBuyOrders || 0), 0)
  const totalPnl = details.reduce((sum, item) => sum + toNumber(item.totalPnl), 0)
  const pnlValues = details.map((item) => toNumber(item.totalPnl))
  const nonZeroDetails = pnlValues.filter((value) => value !== 0)
  const winningDetails = nonZeroDetails.filter((value) => value > 0).length

  return {
    totalOrders,
    totalPnl: totalPnl.toFixed(6),
    winRate: nonZeroDetails.length > 0 ? ((winningDetails / nonZeroDetails.length) * 100).toFixed(2) : '0',
    avgPnl: totalOrders > 0 ? (totalPnl / totalOrders).toFixed(6) : '0',
    maxProfit: Math.max(0, ...pnlValues).toFixed(6),
    maxLoss: Math.min(0, ...pnlValues).toFixed(6)
  }
}

const mapBridgeStatistics = (bridgeStats: BridgeTradeStatistics): StatisticsType | null => {
  if (bridgeStats.totalTrades === 0) {
    return null
  }

  const walletHistoricalOrders = bridgeStats.successTrades

  return {
    totalOrders: walletHistoricalOrders,
    totalPnl: bridgeStats.totalPnl,
    winRate: bridgeStats.successRate,
    avgPnl: walletHistoricalOrders > 0
      ? (toNumber(bridgeStats.totalPnl) / walletHistoricalOrders).toFixed(6)
      : '0',
    maxProfit: bridgeStats.maxPositionProfit,
    maxLoss: bridgeStats.maxPositionLoss,
    openPositionCount: bridgeStats.openPositionCount,
    openPositionValue: bridgeStats.openPositionValue,
    attemptedOrders: bridgeStats.totalTrades,
    failedOrders: bridgeStats.failedTrades,
    pendingOrders: bridgeStats.pendingTrades
  }
}

const Statistics: React.FC = () => {
  const { t } = useTranslation()
  const isMobile = useMediaQuery({ maxWidth: 768 })
  const [stats, setStats] = useState<StatisticsType | null>(null)
  const [loading, setLoading] = useState(false)
  const [leadersLoading, setLeadersLoading] = useState(false)
  const [leaders, setLeaders] = useState<Leader[]>([])
  const [scope, setScope] = useState<StatisticsScope>('global')
  const [leaderId, setLeaderId] = useState<number | undefined>()
  const [category, setCategory] = useState<'sports' | 'crypto'>('sports')
  const [dateRange, setDateRange] = useState<[Dayjs | null, Dayjs | null]>([null, null])

  useEffect(() => {
    if (scope === 'leader' && leaders.length === 0) {
      fetchLeaders()
    }
  }, [scope])

  useEffect(() => {
    if (scope !== 'leader' || leaderId) {
      fetchStatistics()
    }
  }, [scope, leaderId, category])

  const fetchLeaders = async () => {
    setLeadersLoading(true)
    try {
      const response = await apiService.leaders.list({})
      if (response.data.code === 0 && response.data.data) {
        const list = response.data.data.list || []
        setLeaders(list)
        if (!leaderId && list.length > 0) {
          setLeaderId(list[0].id)
        }
      } else {
        message.error(response.data.msg || t('statistics.fetchLeadersFailed') || '获取 Leader 列表失败')
      }
    } catch (error: any) {
      message.error(error.message || t('statistics.fetchLeadersFailed') || '获取 Leader 列表失败')
    } finally {
      setLeadersLoading(false)
    }
  }

  const fetchCopyTradingConfigsForScope = async (): Promise<CopyTrading[]> => {
    if (scope === 'leader') {
      if (!leaderId) return []
      const response = await apiService.copyTrading.list({ leaderId })
      return response.data.code === 0 && response.data.data ? response.data.data.list || [] : []
    }

    if (scope === 'category') {
      const leadersResponse = await apiService.leaders.list({ category })
      const categoryLeaders: Leader[] = leadersResponse.data.code === 0 && leadersResponse.data.data
        ? leadersResponse.data.data.list || []
        : []
      const configResponses = await Promise.allSettled(
        categoryLeaders
          .filter((leader) => leader.id)
          .map((leader) => apiService.copyTrading.list({ leaderId: leader.id }))
      )
      return configResponses.flatMap((result) => {
        if (result.status !== 'fulfilled') return []
        const response = result.value
        return response.data.code === 0 && response.data.data ? response.data.data.list || [] : []
      })
    }

    const response = await apiService.copyTrading.list({})
    return response.data.code === 0 && response.data.data ? response.data.data.list || [] : []
  }

  const fetchDetailAggregateStatistics = async (): Promise<StatisticsType | null> => {
    const configs = await fetchCopyTradingConfigsForScope()
    const uniqueConfigIds = Array.from(new Set(configs.map((config) => config.id).filter(Boolean)))
    if (uniqueConfigIds.length === 0) {
      return null
    }

    const detailResponses = await Promise.allSettled(
      uniqueConfigIds.map((copyTradingId) => apiService.statistics.detail({ copyTradingId }))
    )
    const details = detailResponses.flatMap((result) => {
      if (result.status !== 'fulfilled') return []
      const response = result.value
      return response.data.code === 0 && response.data.data ? [response.data.data as CopyTradingStatistics] : []
    })

    return aggregateDetailStatistics(details)
  }

  const fetchBridgeAggregateStatistics = async (startTime?: number, endTime?: number): Promise<StatisticsType | null> => {
    const response = await apiService.bridgeTradeRecords.statistics({ startTime, endTime })
    if (response.data.code !== 0 || !response.data.data) {
      return null
    }

    return mapBridgeStatistics(response.data.data)
  }

  const fetchStatistics = async () => {
    setLoading(true)
    try {
      const startTime = dateRange[0] ? dateRange[0].valueOf() : undefined
      const endTime = dateRange[1] ? dateRange[1].valueOf() : undefined

      if (scope === 'global') {
        const bridgeStats = await fetchBridgeAggregateStatistics(startTime, endTime)
        if (bridgeStats) {
          setStats(bridgeStats)
          return
        }
      }

      let response
      if (scope === 'leader') {
        if (!leaderId) {
          message.warning(t('statistics.selectLeaderFirst') || '请先选择 Leader')
          return
        }
        response = await apiService.statistics.leader({ leaderId, startTime, endTime })
      } else if (scope === 'category') {
        response = await apiService.statistics.category({ category, startTime, endTime })
      } else {
        response = await apiService.statistics.global({ startTime, endTime })
      }
      if (response.data.code === 0 && response.data.data) {
        let nextStats = response.data.data as StatisticsType
        if (!startTime && !endTime && isZeroStatistics(nextStats)) {
          const fallbackStats = await fetchDetailAggregateStatistics()
          if (fallbackStats) {
            nextStats = fallbackStats
          }
        }
        setStats(nextStats)
      } else {
        setStats(null)
        message.error(response.data.msg || t('statistics.fetchFailed') || '获取统计信息失败')
      }
    } catch (error: any) {
      setStats(null)
      message.error(error.message || t('statistics.fetchFailed') || '获取统计信息失败')
    } finally {
      setLoading(false)
    }
  }

  const handleDateRangeChange = (dates: [Dayjs | null, Dayjs | null] | null) => {
    setDateRange(dates || [null, null])
  }

  const handleReset = () => {
    setDateRange([null, null])
    // 重置后自动刷新
    setTimeout(() => {
      fetchStatistics()
    }, 100)
  }

  const handleScopeChange = (value: StatisticsScope) => {
    setScope(value)
    setStats(null)
  }

  return (
    <div>
      <div style={{ marginBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
        <Title level={2} style={{ margin: 0 }}>{t('statistics.title') || '统计信息'}</Title>
        <Space size="middle" wrap>
          <RangePicker
            value={dateRange}
            onChange={handleDateRangeChange}
            format="YYYY-MM-DD"
            placeholder={[t('statistics.startDate') || '开始日期', t('statistics.endDate') || '结束日期']}
            size={isMobile ? 'middle' : 'large'}
            allowClear
          />
          <Segmented
            value={scope}
            onChange={(value) => handleScopeChange(value as StatisticsScope)}
            options={[
              { label: t('statistics.scopeGlobal') || '全局', value: 'global' },
              { label: 'Leader', value: 'leader' },
              { label: t('statistics.scopeCategory') || '分类', value: 'category' }
            ]}
          />
          {scope === 'leader' && (
            <Select
              showSearch
              value={leaderId}
              placeholder={t('statistics.selectLeader') || '选择 Leader'}
              loading={leadersLoading}
              style={{ minWidth: isMobile ? 180 : 260 }}
              optionFilterProp="label"
              onChange={setLeaderId}
              options={leaders.map((leader) => ({
                value: leader.id,
                label: leader.leaderName || `${leader.leaderAddress.slice(0, 10)}...`
              }))}
            />
          )}
          {scope === 'category' && (
            <Select
              value={category}
              style={{ minWidth: 140 }}
              onChange={setCategory}
              options={[
                { value: 'sports', label: t('statistics.categorySports') || '体育' },
                { value: 'crypto', label: t('statistics.categoryCrypto') || '加密' }
              ]}
            />
          )}
          <Button
            type="primary"
            icon={<ReloadOutlined />}
            onClick={fetchStatistics}
            loading={loading}
            size={isMobile ? 'middle' : 'large'}
          >
            {t('statistics.refresh') || '刷新'}
          </Button>
          {(dateRange[0] || dateRange[1]) && (
            <Button
              onClick={handleReset}
              size={isMobile ? 'middle' : 'large'}
            >
              {t('statistics.reset') || '重置'}
            </Button>
          )}
        </Space>
      </div>

      {!loading && !stats && (
        <Card>
          <Empty description={t('statistics.noData') || '暂无统计数据'} />
        </Card>
      )}

      {(loading || stats) && (
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} md={8}>
            <Card>
              <Statistic
                title={t('statistics.totalOrders') || '总订单数'}
                value={formatNumber(stats?.totalOrders || 0)}
                loading={loading}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={8}>
            <Card>
              <Statistic
                title={t('statistics.totalPnl') || '总盈亏'}
                value={formatUSDC(stats?.totalPnl || '0')}
                prefix={<>{stats?.totalPnl && parseFloat(stats.totalPnl) >= 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />} $</>}
                valueStyle={{ color: stats?.totalPnl && parseFloat(stats.totalPnl || '0') >= 0 ? '#3f8600' : '#cf1322' }}
                loading={loading}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={8}>
            <Card>
              <Statistic
                title={t('statistics.winRate') || '胜率'}
                value={stats?.winRate || '0'}
                precision={2}
                suffix="%"
                loading={loading}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={8}>
            <Card>
              <Statistic
                title={t('statistics.avgPnl') || '平均盈亏'}
                value={formatUSDC(stats?.avgPnl || '0')}
                prefix={<>{stats?.avgPnl && parseFloat(stats.avgPnl || '0') >= 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />} $</>}
                valueStyle={{ color: stats?.avgPnl && parseFloat(stats.avgPnl || '0') >= 0 ? '#3f8600' : '#cf1322' }}
                loading={loading}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={8}>
            <Card>
              <Statistic
                title={t('statistics.maxProfit') || '最大盈利'}
                value={formatUSDC(stats?.maxProfit || '0')}
                prefix={<><ArrowUpOutlined /> $</>}
                valueStyle={{ color: '#3f8600' }}
                loading={loading}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={8}>
            <Card>
              <Statistic
                title={t('statistics.maxLoss') || '最大亏损'}
                value={formatUSDC(stats?.maxLoss || '0')}
                prefix={<><ArrowDownOutlined /> $</>}
                valueStyle={{ color: '#cf1322' }}
                loading={loading}
              />
            </Card>
          </Col>
          {typeof stats?.openPositionCount === 'number' && (
            <Col xs={24} sm={12} md={8}>
              <Card>
                <Statistic
                  title={t('statistics.openPositions') || '当前持仓数'}
                  value={formatNumber(stats.openPositionCount)}
                  loading={loading}
                />
              </Card>
            </Col>
          )}
          {typeof stats?.openPositionValue === 'string' && (
            <Col xs={24} sm={12} md={8}>
              <Card>
                <Statistic
                  title={t('statistics.openPositionValue') || '当前持仓价值'}
                  value={formatUSDC(stats.openPositionValue)}
                  prefix="$"
                  loading={loading}
                />
              </Card>
            </Col>
          )}
          {typeof stats?.attemptedOrders === 'number' && (
            <Col xs={24} sm={12} md={8}>
              <Card>
                <Statistic
                  title={t('statistics.attemptedOrders') || 'Bridge 尝试订单'}
                  value={formatNumber(stats.attemptedOrders)}
                  loading={loading}
                />
              </Card>
            </Col>
          )}
          {typeof stats?.failedOrders === 'number' && (
            <Col xs={24} sm={12} md={8}>
              <Card>
                <Statistic
                  title={t('statistics.failedOrders') || 'Bridge 失败订单'}
                  value={formatNumber(stats.failedOrders)}
                  valueStyle={{ color: stats.failedOrders > 0 ? '#cf1322' : undefined }}
                  loading={loading}
                />
              </Card>
            </Col>
          )}
          {typeof stats?.pendingOrders === 'number' && stats.pendingOrders > 0 && (
            <Col xs={24} sm={12} md={8}>
              <Card>
                <Statistic
                  title={t('statistics.pendingOrders') || 'Bridge Pending'}
                  value={formatNumber(stats.pendingOrders)}
                  loading={loading}
                />
              </Card>
            </Col>
          )}
        </Row>
      )}
    </div>
  )
}

export default Statistics
