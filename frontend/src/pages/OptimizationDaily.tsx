import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Col, Modal, Row, Space, Statistic, Table, Tag, Typography, message } from 'antd'
import { CheckCircleOutlined, ClockCircleOutlined, PauseCircleOutlined, PlayCircleOutlined, ReloadOutlined, SettingOutlined, WarningOutlined } from '@ant-design/icons'
import { apiService } from '../services/api'
import type { BridgeAuditBucket, BridgeAuditReconciliationSuggestion, BridgeAuditResponse, BridgeRuntimeStatus, LoopGoal, LoopGoalAction, LoopGoalControlStatus, LoopGoalStatus } from '../types'

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
  const [loading, setLoading] = useState(false)
  const [confirmingKey, setConfirmingKey] = useState<string | null>(null)
  const [goalModalOpen, setGoalModalOpen] = useState(false)
  const [updatingGoalKey, setUpdatingGoalKey] = useState<string | null>(null)

  const fetchData = async () => {
    setLoading(true)
    try {
      const sinceMs = Date.now() - 24 * 60 * 60 * 1000
      const [defaultAudit, recentAudit] = await Promise.allSettled([
        apiService.bridgeTradeRecords.audit({ limit: 500, failureLimit: 100, portfolioTimeout: 90 }),
        apiService.bridgeTradeRecords.audit({ sinceMs, limit: 500, failureLimit: 100, portfolioTimeout: 90 })
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
