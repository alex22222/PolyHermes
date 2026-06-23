import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Card, Table, Button, Input, message, Divider, Spin, Tag } from 'antd'
import { LeftOutlined } from '@ant-design/icons'
import { apiService } from '../services/api'
import { formatUSDC } from '../utils'
import { useMediaQuery } from 'react-responsive'
import { useTranslation } from 'react-i18next'
import type { MatchedOrderInfo, OrderTrackingRequest, OrderTrackingListResponse, BridgeTradeRecord, BridgeTradeRecordListResponse } from '../types'

const CopyTradingMatchedOrdersPage: React.FC = () => {
  const { t } = useTranslation()
  const { copyTradingId } = useParams<{ copyTradingId: string }>()
  const navigate = useNavigate()
  const isMobile = useMediaQuery({ maxWidth: 768 })
  const [loading, setLoading] = useState(false)
  const [orders, setOrders] = useState<MatchedOrderInfo[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [limit, setLimit] = useState(20)
  const [filters, setFilters] = useState<{
    sellOrderId?: string
    buyOrderId?: string
  }>({})

  // Bridge 执行记录（用于无 API 凭证的 Bridge 账户）
  const [bridgeRecords, setBridgeRecords] = useState<BridgeTradeRecord[]>([])
  const [bridgeLoading, setBridgeLoading] = useState(false)
  const [bridgePage, setBridgePage] = useState(1)
  const [bridgeLimit, setBridgeLimit] = useState(20)
  const [bridgeTotal, setBridgeTotal] = useState(0)
  
  useEffect(() => {
    if (copyTradingId) {
      fetchOrders()
    }
  }, [copyTradingId, page, limit, filters])

  useEffect(() => {
    if (copyTradingId) {
      fetchBridgeRecords()
    }
  }, [copyTradingId, bridgePage, bridgeLimit])
  
  const fetchOrders = async () => {
    if (!copyTradingId) return
    
    setLoading(true)
    try {
      const request: OrderTrackingRequest = {
        copyTradingId: parseInt(copyTradingId),
        type: 'matched',
        page,
        limit,
        ...filters
      }
      
      const response = await apiService.orderTracking.list(request)
      if (response.data.code === 0 && response.data.data) {
        const data = response.data.data as OrderTrackingListResponse
        setOrders((data.list || []) as MatchedOrderInfo[])
        setTotal(data.total || 0)
      } else {
        message.error(response.data.msg || '获取匹配关系列表失败')
      }
    } catch (error: any) {
      message.error(error.message || '获取匹配关系列表失败')
    } finally {
      setLoading(false)
    }
  }
  
  const fetchBridgeRecords = async () => {
    if (!copyTradingId) return

    setBridgeLoading(true)
    try {
      const response = await apiService.bridgeTradeRecords.byCopyTrading({
        copyTradingId: parseInt(copyTradingId),
        page: bridgePage,
        size: bridgeLimit
      })
      if (response.data.code === 0 && response.data.data) {
        const data = response.data.data as BridgeTradeRecordListResponse
        const nonFailedRecords = (data.list || []).filter(r => r.status !== 'FAILED')
        setBridgeRecords(nonFailedRecords)
        setBridgeTotal(nonFailedRecords.length)
      }
    } catch (error: any) {
      console.error('获取 Bridge 执行记录失败:', error)
    } finally {
      setBridgeLoading(false)
    }
  }

  const getBridgeStatusColor = (status: string) => {
    switch (status) {
      case 'SUCCESS': return 'success'
      case 'PENDING': return 'processing'
      case 'FAILED': return 'error'
      default: return 'default'
    }
  }

  const getPnlColor = (value: string): string => {
    const num = parseFloat(value)
    if (isNaN(num)) return '#666'
    return num >= 0 ? '#3f8600' : '#cf1322'
  }
  
  const columns = [
    {
      title: '卖出订单ID',
      dataIndex: 'sellOrderId',
      key: 'sellOrderId',
      width: isMobile ? 100 : 150,
      render: (text: string) => (
        <span style={{ fontFamily: 'monospace', fontSize: isMobile ? 11 : 12 }}>
          {isMobile 
            ? `${text.slice(0, 6)}...${text.slice(-4)}`
            : `${text.slice(0, 8)}...${text.slice(-6)}`
          }
        </span>
      )
    },
    {
      title: '买入订单ID',
      dataIndex: 'buyOrderId',
      key: 'buyOrderId',
      width: isMobile ? 100 : 150,
      render: (text: string) => (
        <span style={{ fontFamily: 'monospace', fontSize: isMobile ? 11 : 12 }}>
          {isMobile 
            ? `${text.slice(0, 6)}...${text.slice(-4)}`
            : `${text.slice(0, 8)}...${text.slice(-6)}`
          }
        </span>
      )
    },
    {
      title: '匹配数量',
      dataIndex: 'matchedQuantity',
      key: 'matchedQuantity',
      width: isMobile ? 80 : 100,
      render: (value: string) => (
        <span style={{ fontSize: isMobile ? 12 : 14 }}>{formatUSDC(value)}</span>
      )
    },
    {
      title: '买入价格',
      dataIndex: 'buyPrice',
      key: 'buyPrice',
      width: isMobile ? 80 : 100,
      render: (value: string) => (
        <span style={{ fontSize: isMobile ? 12 : 14 }}>{formatUSDC(value)}</span>
      )
    },
    {
      title: '卖出价格',
      dataIndex: 'sellPrice',
      key: 'sellPrice',
      width: isMobile ? 80 : 100,
      render: (value: string) => (
        <span style={{ fontSize: isMobile ? 12 : 14 }}>{formatUSDC(value)}</span>
      )
    },
    {
      title: '盈亏',
      dataIndex: 'realizedPnl',
      key: 'realizedPnl',
      width: isMobile ? 100 : 120,
      render: (value: string) => (
        <span style={{ 
          color: getPnlColor(value), 
          fontWeight: 500,
          fontSize: isMobile ? 12 : 14
        }}>
          {isMobile ? formatUSDC(value) : `$${formatUSDC(value)}`}
        </span>
      )
    },
    {
      title: '匹配时间',
      dataIndex: 'matchedAt',
      key: 'matchedAt',
      width: isMobile ? 120 : 160,
      render: (timestamp: number) => (
        <span style={{ fontSize: isMobile ? 11 : 12 }}>
          {isMobile 
            ? new Date(timestamp).toLocaleDateString('zh-CN')
            : new Date(timestamp).toLocaleString('zh-CN')
          }
        </span>
      )
    }
  ]

  const bridgeColumns = [
    {
      title: t('copyTradingOrders.market') || '市场',
      dataIndex: 'marketTitle',
      key: 'marketTitle',
      width: isMobile ? 140 : 220,
      render: (title: string | undefined, record: BridgeTradeRecord) => {
        const displayTitle = title || record.marketId.slice(0, 16) + '...'
        return (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
            <span style={{ fontSize: isMobile ? 12 : 13, fontWeight: 500 }}>{displayTitle}</span>
            <span style={{ fontFamily: 'monospace', fontSize: isMobile ? 10 : 11, color: '#999' }}>
              {record.marketId.slice(0, isMobile ? 6 : 8)}...{record.marketId.slice(-6)}
            </span>
          </div>
        )
      }
    },
    {
      title: t('copyTradingOrders.side') || '方向',
      dataIndex: 'side',
      key: 'side',
      width: 80,
      render: (side: string) => <Tag color={side === 'BUY' ? 'green' : 'red'}>{side}</Tag>
    },
    {
      title: t('copyTradingOrders.outcome') || '结果',
      dataIndex: 'outcome',
      key: 'outcome',
      width: 100,
      render: (outcome: string | undefined, record: BridgeTradeRecord) =>
        outcome ? `${outcome} #${record.outcomeIndex ?? '-'}` : '-'
    },
    {
      title: t('copyTradingOrders.quantity') || '数量',
      dataIndex: 'quantity',
      key: 'quantity',
      width: 100,
      align: 'right' as const,
      render: (quantity: string) => formatUSDC(quantity)
    },
    {
      title: t('copyTradingOrders.price') || '价格',
      dataIndex: 'price',
      key: 'price',
      width: 100,
      align: 'right' as const,
      render: (price: string) => `$${formatUSDC(price)}`
    },
    {
      title: t('copyTradingOrders.amount') || '金额',
      dataIndex: 'amount',
      key: 'amount',
      width: 100,
      align: 'right' as const,
      render: (amount: string) => `$${formatUSDC(amount)}`
    },
    {
      title: t('copyTradingOrders.status') || '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => <Tag color={getBridgeStatusColor(status)}>{status}</Tag>
    },
    {
      title: t('copyTradingOrders.time') || '时间',
      dataIndex: 'createdAt',
      key: 'createdAt',
      width: 160,
      render: (timestamp: number | undefined) =>
        timestamp ? new Date(timestamp).toLocaleString('zh-CN') : '-'
    }
  ]
  
  return (
    <div>
      <Card>
        <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <Button icon={<LeftOutlined />} onClick={() => navigate(-1)}>
              {t('common.back') || '返回'}
            </Button>
            <h2 style={{ margin: 0 }}>匹配关系列表</h2>
          </div>
        </div>
        
        <div style={{ marginBottom: 16, display: 'flex', gap: 16, flexWrap: 'wrap' }}>
          <Input
            placeholder="筛选卖出订单ID"
            allowClear
            style={{ width: isMobile ? '100%' : 200 }}
            value={filters.sellOrderId}
            onChange={(e) => setFilters({ ...filters, sellOrderId: e.target.value || undefined })}
          />
          
          <Input
            placeholder="筛选买入订单ID"
            allowClear
            style={{ width: isMobile ? '100%' : 200 }}
            value={filters.buyOrderId}
            onChange={(e) => setFilters({ ...filters, buyOrderId: e.target.value || undefined })}
          />
          
          <Button onClick={fetchOrders}>查询</Button>
        </div>
        
        {isMobile ? (
          // 移动端卡片布局
          <div>
            {loading ? (
              <div style={{ textAlign: 'center', padding: '40px' }}>
                <Spin size="large" />
              </div>
            ) : orders.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '40px', color: '#999' }}>
                暂无匹配关系
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {orders.map((order) => {
                  const date = new Date(order.matchedAt)
                  const formattedDate = date.toLocaleString('zh-CN', {
                    year: 'numeric',
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit'
                  })
                  
                  return (
                    <Card
                      key={`${order.sellOrderId}-${order.buyOrderId}-${order.matchedAt}`}
                      style={{
                        borderRadius: '12px',
                        boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
                        border: '1px solid #e8e8e8'
                      }}
                      bodyStyle={{ padding: '16px' }}
                    >
                      {/* 订单ID */}
                      <div style={{ marginBottom: '12px' }}>
                        <div style={{ fontSize: '12px', color: '#666', marginBottom: '4px' }}>卖出订单ID</div>
                        <div style={{ 
                          fontSize: '13px', 
                          fontWeight: '500',
                          fontFamily: 'monospace',
                          marginBottom: '8px'
                        }}>
                          {order.sellOrderId.slice(0, 8)}...{order.sellOrderId.slice(-6)}
                        </div>
                        <div style={{ fontSize: '12px', color: '#666', marginBottom: '4px' }}>买入订单ID</div>
                        <div style={{ 
                          fontSize: '13px', 
                          fontWeight: '500',
                          fontFamily: 'monospace'
                        }}>
                          {order.buyOrderId.slice(0, 8)}...{order.buyOrderId.slice(-6)}
                        </div>
                      </div>
                      
                      <Divider style={{ margin: '12px 0' }} />
                      
                      {/* 匹配信息 */}
                      <div style={{ marginBottom: '12px' }}>
                        <div style={{ fontSize: '12px', color: '#666', marginBottom: '4px' }}>匹配数量</div>
                        <div style={{ fontSize: '14px', fontWeight: '500' }}>
                          {formatUSDC(order.matchedQuantity)}
                        </div>
                      </div>
                      
                      {/* 价格信息 */}
                      <div style={{ marginBottom: '12px' }}>
                        <div style={{ fontSize: '12px', color: '#666', marginBottom: '4px' }}>价格信息</div>
                        <div style={{ fontSize: '13px', color: '#333' }}>
                          买入: {formatUSDC(order.buyPrice)} | 卖出: {formatUSDC(order.sellPrice)}
                        </div>
                      </div>
                      
                      {/* 盈亏 */}
                      <div style={{ marginBottom: '16px' }}>
                        <div style={{ fontSize: '12px', color: '#666', marginBottom: '4px' }}>盈亏</div>
                        <div style={{ 
                          fontSize: '16px', 
                          fontWeight: 'bold',
                          color: getPnlColor(order.realizedPnl)
                        }}>
                          ${formatUSDC(order.realizedPnl)}
                        </div>
                      </div>
                      
                      {/* 匹配时间 */}
                      <div style={{ marginBottom: '16px' }}>
                        <div style={{ fontSize: '12px', color: '#999' }}>
                          匹配时间: {formattedDate}
                        </div>
                      </div>
                    </Card>
                  )
                })}
              </div>
            )}
          </div>
        ) : (
          // 桌面端表格布局
          <Table
            columns={columns}
            dataSource={orders}
            rowKey={(record) => `${record.sellOrderId}-${record.buyOrderId}-${record.matchedAt}`}
            loading={loading}
            pagination={{
              current: page,
              pageSize: limit,
              total,
              showSizeChanger: true,
              showTotal: (total) => `共 ${total} 条`,
              onChange: (newPage, newLimit) => {
                setPage(newPage)
                setLimit(newLimit)
              }
            }}
          />
        )}

        {/* Bridge 执行记录（无 API 凭证的 Bridge 账户） */}
        {(bridgeTotal > 0 || bridgeLoading) && (
          <div style={{ marginTop: 32 }}>
            <Divider orientation="left" style={{ marginBottom: 16 }}>
              {t('copyTradingOrders.bridgeExecutions') || 'Bridge 执行记录'}
            </Divider>
            <Table
              columns={bridgeColumns}
              dataSource={bridgeRecords}
              rowKey="id"
              loading={bridgeLoading}
              scroll={isMobile ? { x: 900 } : undefined}
              pagination={{
                current: bridgePage,
                pageSize: bridgeLimit,
                total: bridgeTotal,
                showSizeChanger: true,
                showTotal: (total) => `共 ${total} 条`,
                onChange: (newPage, newLimit) => {
                  setBridgePage(newPage)
                  setBridgeLimit(newLimit)
                }
              }}
            />
          </div>
        )}
      </Card>
    </div>
  )
}

export default CopyTradingMatchedOrdersPage

