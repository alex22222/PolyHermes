import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Card, Tabs, Button, Space, Typography, Spin, message, Tag } from 'antd'
import { ArrowLeftOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { useMediaQuery } from 'react-responsive'
import { useAccountStore } from '../store/accountStore'
import BuyOrdersTab from './CopyTradingOrders/BuyOrdersTab'
import SellOrdersTab from './CopyTradingOrders/SellOrdersTab'
import MatchedOrdersTab from './CopyTradingOrders/MatchedOrdersTab'
import type { Account } from '../types'

const { Title } = Typography

type TabType = 'buy' | 'sell' | 'matched'

const AccountOrders: React.FC = () => {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const isMobile = useMediaQuery({ maxWidth: 768 })
  const accountId = searchParams.get('id')
  
  const { fetchAccountDetail } = useAccountStore()
  const [account, setAccount] = useState<Account | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<TabType>('buy')
  
  useEffect(() => {
    if (!accountId) {
      message.error(t('account.accountIdRequired'))
      navigate('/accounts')
      return
    }
    
    loadAccountDetail()
  }, [accountId])
  
  const loadAccountDetail = async () => {
    if (!accountId) return
    
    setLoading(true)
    try {
      const accountData = await fetchAccountDetail(Number(accountId))
      setAccount(accountData)
    } catch (error: any) {
      message.error(error.message || t('account.getDetailFailed'))
      navigate('/accounts')
    } finally {
      setLoading(false)
    }
  }
  
  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '50px' }}>
        <Spin size="large" />
      </div>
    )
  }
  
  if (!account) {
    return null
  }
  
  return (
    <div style={{ padding: isMobile ? '0' : undefined }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: isMobile ? '12px' : '16px',
        flexWrap: 'wrap',
        gap: '12px',
        padding: isMobile ? '0 8px' : '0'
      }}>
        <Space wrap>
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate('/accounts')}
            size={isMobile ? 'middle' : 'large'}
          >
            {t('common.back')}
          </Button>
          <Title level={isMobile ? 4 : 2} style={{ margin: 0, fontSize: isMobile ? '16px' : undefined }}>
            {t('accountList.historyOrders') || '历史订单'}
          </Title>
        </Space>
      </div>
      
      <Card style={{
        margin: isMobile ? '0 -8px' : '0',
        borderRadius: isMobile ? '0' : undefined
      }}>
        <div style={{ marginBottom: 16 }}>
          <Space wrap size="middle">
            <span style={{ fontSize: isMobile ? 14 : 16, fontWeight: 500 }}>
              {account.accountName || `${t('accountList.accountName')} ${account.id}`}
            </span>
            {account.walletType && (
              <Tag color={account.walletType.toLowerCase() === 'magic' ? 'purple' : 'blue'}>
                {account.walletType.toLowerCase() === 'magic' ? 'Magic' : 'Safe'}
              </Tag>
            )}
            <span style={{
              fontFamily: 'monospace',
              fontSize: isMobile ? 11 : 13,
              color: '#666',
              wordBreak: 'break-all'
            }}>
              {account.walletAddress}
            </span>
          </Space>
        </div>
        
        <Tabs
          activeKey={activeTab}
          onChange={(key) => setActiveTab(key as TabType)}
          items={[
            {
              key: 'buy',
              label: t('copyTradingOrders.buyOrders') || '买入订单',
              children: <BuyOrdersTab accountId={accountId!} active={activeTab === 'buy'} />
            },
            {
              key: 'sell',
              label: t('copyTradingOrders.sellOrders') || '卖出订单',
              children: <SellOrdersTab accountId={accountId!} active={activeTab === 'sell'} />
            },
            {
              key: 'matched',
              label: t('copyTradingOrders.matchedOrders') || '匹配关系',
              children: <MatchedOrdersTab accountId={accountId!} active={activeTab === 'matched'} />
            }
          ]}
        />
      </Card>
    </div>
  )
}

export default AccountOrders
