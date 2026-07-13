import { useCallback, useEffect, useState } from 'react'
import { Alert, Avatar, Button, Card, Empty, List, Popconfirm, Skeleton, Space, Statistic, Switch, Tag, Typography, message } from 'antd'
import { ClockCircleOutlined, FallOutlined, ReloadOutlined, RiseOutlined, SafetyCertificateOutlined, WalletOutlined } from '@ant-design/icons'
import { apiService } from '../services/api'
import type { AccountPosition, BridgePortfolioPosition, BridgePortfolioResponse, PortfolioBuyControl } from '../types'

const { Text, Title } = Typography

const money = (value?: number | null) => value == null ? '—' : `$${value.toFixed(2)}`
const number = (value?: number | null) => value == null ? '—' : value.toLocaleString(undefined, { maximumFractionDigits: 4 })

const MobilePortfolio: React.FC = () => {
  const [portfolio, setPortfolio] = useState<BridgePortfolioResponse | null>(null)
  const [snapshotPositions, setSnapshotPositions] = useState<AccountPosition[]>([])
  const [buyControl, setBuyControl] = useState<PortfolioBuyControl | null>(null)
  const [buyControlLoading, setBuyControlLoading] = useState(false)
  const [bridgeAccountId, setBridgeAccountId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const loadPortfolio = useCallback(async (manual = false) => {
    if (manual) setRefreshing(true)
    try {
      const response = await apiService.accounts.bridgePortfolio()
      if (response.data.code === 0 && response.data.data) {
        setPortfolio(response.data.data)
      } else if (manual) {
        message.error(response.data.msg || '投资组合暂时不可用')
      }
      setLoading(false)

      // Bridge is the authoritative source for this page. Load the broader
      // account list in the background only as a fallback for incomplete data.
      try {
        const positionsResponse = await apiService.accounts.positionsList()
        if (positionsResponse.data.code === 0) {
          setSnapshotPositions(positionsResponse.data.data?.currentPositions || [])
        }
      } catch (error) {
        console.debug('后台补充账户仓位失败:', error)
      }
    } catch (error: any) {
      if (manual) message.error(error?.message || '投资组合暂时不可用')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  const loadBuyControl = useCallback(async () => {
    try {
      const current = await apiService.accounts.bridgeCurrent()
      const id = current.data.data?.accountId || current.data.data?.copyTradingAccountId
      if (!id) return
      setBridgeAccountId(id)
      const response = await apiService.accounts.portfolioBuyControl(id)
      if (response.data.code === 0 && response.data.data) setBuyControl(response.data.data)
    } catch (error) {
      console.debug('获取移动端 BUY 控制状态失败:', error)
    }
  }, [])

  const updateBuyControl = async (paused: boolean) => {
    if (!bridgeAccountId || buyControlLoading) return
    setBuyControlLoading(true)
    try {
      const response = await apiService.accounts.updatePortfolioBuyControl({
        accountId: bridgeAccountId,
        paused,
        reason: paused ? '移动端手动暂停新增 BUY' : '移动端手动恢复 BUY'
      })
      if (response.data.code === 0 && response.data.data) {
        setBuyControl(response.data.data)
        message.success(paused ? '已暂停新增 BUY，SELL 不受影响' : '已恢复新增 BUY')
      } else {
        message.error(response.data.msg || '更新跟单开关失败')
      }
    } catch (error: any) {
      message.error(error?.message || '更新跟单开关失败')
    } finally {
      setBuyControlLoading(false)
    }
  }

  useEffect(() => {
    loadPortfolio()
    loadBuyControl()
    const timer = window.setInterval(() => loadPortfolio(), 30000)
    return () => window.clearInterval(timer)
  }, [loadPortfolio, loadBuyControl])

  const renderPosition = (position: BridgePortfolioPosition) => {
    const pnlPositive = (position.pnl || 0) >= 0
    return (
      <List.Item style={{ padding: '16px 0', alignItems: 'flex-start' }}>
        <List.Item.Meta
          avatar={position.marketIcon ? <Avatar src={position.marketIcon} /> : <Avatar icon={<WalletOutlined />} />}
          title={<Text strong style={{ fontSize: 15 }}>{position.marketTitle}</Text>}
          description={
            <Space direction="vertical" size={4} style={{ width: '100%', marginTop: 5 }}>
              <Space size={6} wrap>
                <Tag color={position.side.toLowerCase() === 'yes' || position.side.toLowerCase() === 'up' ? 'green' : 'blue'}>{position.side}</Tag>
                <Text type="secondary">{number(position.quantity)} shares</Text>
              </Space>
              <Space size={16} wrap>
                <Text>当前 {money(position.currentValue)}</Text>
                <Text style={{ color: pnlPositive ? '#16a34a' : '#dc2626' }}>
                  {pnlPositive ? <RiseOutlined /> : <FallOutlined />} {money(position.pnl)} ({position.percentPnl == null ? '—' : `${position.percentPnl.toFixed(1)}%`})
                </Text>
              </Space>
            </Space>
          }
        />
      </List.Item>
    )
  }

  const fallbackPositions: BridgePortfolioPosition[] = bridgeAccountId == null
    ? []
    : snapshotPositions
      .filter(position => position.accountId === bridgeAccountId && position.isCurrent)
      .map(position => ({
        marketTitle: position.marketTitle || position.marketId,
        side: position.side,
        quantity: Number(position.quantity) || 0,
        currentValue: Number(position.currentValue) || 0,
        pnl: Number(position.pnl) || 0,
        percentPnl: Number(position.percentPnl) || 0,
        marketIcon: position.marketIcon,
        marketSlug: position.marketSlug,
        eventSlug: position.eventSlug,
        redeemable: position.redeemable
      }))
  const visiblePositions = portfolio?.positions.length ? portfolio.positions : fallbackPositions
  const positionValueConfirmed = Boolean(portfolio?.portfolioComplete || visiblePositions.length)
  const currentValue = portfolio && positionValueConfirmed
    ? visiblePositions.reduce((total, position) => total + (position.currentValue || 0), 0)
    : null
  const totalAssets = portfolio?.availableBalance != null && currentValue != null
    ? portfolio.availableBalance + currentValue
    : null

  return (
    <main style={{ minHeight: '100vh', background: '#f5f7fb', padding: '16px 12px 32px' }}>
      <div style={{ maxWidth: 520, margin: '0 auto' }}>
        <Space align="center" style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>POLYHERMES</Text>
            <Title level={3} style={{ margin: '2px 0 0' }}>投资组合</Title>
          </div>
          <Button aria-label="刷新投资组合" shape="circle" icon={<ReloadOutlined />} loading={refreshing} onClick={() => loadPortfolio(true)} />
        </Space>

        {loading ? <Skeleton active paragraph={{ rows: 6 }} /> : portfolio ? (
          <>
            <Card bordered={false} style={{ borderRadius: 18, marginBottom: 12, background: 'linear-gradient(135deg, #172554, #2563eb)', color: '#fff' }}>
              <Space direction="vertical" size={12} style={{ width: '100%' }}>
                <div>
                  <Text style={{ color: 'rgba(255,255,255,.72)' }}>总资产</Text>
                  <Statistic value={totalAssets == null ? undefined : totalAssets} precision={2} prefix="$" valueStyle={{ color: '#fff', fontSize: 34, fontWeight: 700 }} />
                </div>
                <Space size={28} wrap>
                  <div>
                    <Text style={{ color: 'rgba(255,255,255,.72)', fontSize: 12 }}>可用余额</Text>
                    <div style={{ color: '#fff', fontSize: 18, fontWeight: 600 }}>{money(portfolio.availableBalance)}</div>
                  </div>
                  <div>
                  <Text style={{ color: 'rgba(255,255,255,.72)', fontSize: 12 }}>当前价值（仓位）</Text>
                  <div style={{ color: '#fff', fontSize: 18, fontWeight: 600 }}>{money(currentValue)}</div>
                </div>
                </Space>
                <Text style={{ color: 'rgba(255,255,255,.72)', fontSize: 12 }}>
                  计算：余额 {money(portfolio.availableBalance)} + 当前价值 {money(currentValue)} = 总资产 {money(totalAssets)}
                </Text>
                <Text style={{ color: 'rgba(255,255,255,.68)', fontSize: 12 }}><ClockCircleOutlined /> 最近同步 {portfolio.syncedAt ? new Date(portfolio.syncedAt).toLocaleTimeString() : '未知'}</Text>
              </Space>
            </Card>

            <Card bordered={false} style={{ borderRadius: 18, marginBottom: 12 }} bodyStyle={{ padding: '16px' }}>
              <Space align="center" style={{ width: '100%', justifyContent: 'space-between' }}>
                <div>
                  <Text strong style={{ fontSize: 16 }}>跟单控制</Text>
                  <div style={{ marginTop: 4 }}><Text type="secondary" style={{ fontSize: 12 }}>暂停仅阻止新增 BUY，SELL 不受影响</Text></div>
                  {buyControl?.paused && <Tag color="red" style={{ marginTop: 8 }}>新增 BUY 已暂停</Tag>}
                </div>
                <Popconfirm
                  title={buyControl?.paused ? '恢复新增 BUY？' : '暂停新增 BUY？'}
                  description={buyControl?.paused ? '恢复后将允许通过风控的 BUY。' : '暂停后不会再执行新的 BUY，已有仓位仍可 SELL。'}
                  okText="确认"
                  cancelText="取消"
                  onConfirm={() => updateBuyControl(!buyControl?.paused)}
                >
                  <Switch checked={Boolean(buyControl?.paused)} loading={buyControlLoading} disabled={!bridgeAccountId} />
                </Popconfirm>
              </Space>
            </Card>

            {!portfolio.portfolioComplete && (
              <Alert
                type="warning"
                showIcon
                icon={<SafetyCertificateOutlined />}
                message="投资组合数据尚未完整确认"
                description="Bridge 正在同步页面持仓，当前列表可能不是完整快照。"
                style={{ marginBottom: 12, borderRadius: 12 }}
              />
            )}

            <Card bordered={false} style={{ borderRadius: 18 }} bodyStyle={{ padding: '8px 16px 12px' }}>
              <Space align="center" style={{ width: '100%', justifyContent: 'space-between', padding: '8px 0' }}>
                <Text strong style={{ fontSize: 17 }}>当前持仓</Text>
                <Tag color={portfolio.portfolioComplete ? 'green' : 'orange'}>{visiblePositions.length} 个仓位</Tag>
              </Space>
              {visiblePositions.length ? <List dataSource={visiblePositions} renderItem={renderPosition} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={portfolio.portfolioComplete ? '暂无持仓' : '等待持仓确认'} style={{ padding: '22px 0' }} />}
            </Card>
          </>
        ) : (
          <Empty description="投资组合暂时不可用" />
        )}
      </div>
    </main>
  )
}

export default MobilePortfolio
