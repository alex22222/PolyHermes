import { useEffect, useState } from 'react'
import { apiService } from '../services/api'
import type { BridgeRuntimeStatus } from '../types'
import './SystemFlow.css'

const researchSteps = [
  {
    code: 'R1',
    title: '多源发现与证据',
    body: 'Activity、市场 Peer、官方榜单、Falcon、Polyburg/Telegram、外部分析和手工导入。'
  },
  {
    code: 'R2',
    title: '去重、分类与策略识别',
    body: '归并钱包与 source evidence，标注市场分类、策略类型和风险特征。'
  },
  {
    code: 'R3',
    title: '评分与历史验证',
    body: '综合 PnL、ROI、胜率、频次、流动性、活跃度及可复制性。'
  },
  {
    code: 'R4',
    title: 'Paper 与回放',
    body: '纸上交易、历史回放和策略样本复核，识别尾部风险与不可执行信号。'
  },
  {
    code: 'R5',
    title: '人工审批与配置',
    body: '仅批准候选人进入 Trial；配置账户、分类、额度、价格与市场规则。'
  }
]

const executionSteps = [
  {
    code: 'E1',
    title: 'Leader 信号进入队列',
    body: '后端监听 leader 活动，Bridge 以有界队列接收并保留到达时序。'
  },
  {
    code: 'E2',
    title: '配置过滤与幂等',
    body: '校验 leader、市场分类、白名单、价格、订单大小、重复单与临期规则。'
  },
  {
    code: 'E3',
    title: '组合风控硬门',
    body: 'BUY 经过预检、资金预留与最终确认；异常时按配置进入 Shadow 或阻断。'
  },
  {
    code: 'E4',
    title: 'Bridge 浏览器执行',
    body: '持久登录会话完成下单；运行健康、浏览器上下文与队列状态持续探测。'
  },
  {
    code: 'E5',
    title: '成交核验与仓位同步',
    body: '核验订单结果，写入交易账本并同步账户、持仓与可用余额。'
  },
  {
    code: 'E6',
    title: '审计、回放与反馈',
    body: '执行审计、风险回放、人工减仓和结算结果回流到 leader/策略评分。'
  }
]

const gates = [
  {
    title: '准入门',
    body: '未通过 Paper、审批或配置未启用，不产生可执行跟单。'
  },
  {
    title: 'BUY 硬门',
    body: '价格、时效、账户、组合风控或 Bridge runtime 异常时禁止新增 BUY。'
  },
  {
    title: 'SELL / 减仓路径',
    body: '卖出与减仓独立处理，优先于新增 BUY，并保留执行审计。'
  }
]

const formatSyncedAt = (value?: number) => {
  if (!value) return '未同步'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

const SystemFlow: React.FC = () => {
  const [bridgeStatus, setBridgeStatus] = useState<BridgeRuntimeStatus | null>(null)
  const [statusError, setStatusError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [checkedAt, setCheckedAt] = useState<number | null>(null)

  const refreshBridgeStatus = async () => {
    setLoading(true)
    try {
      const response = await apiService.bridgeTradeRecords.status()
      if (response.data.code === 0 && response.data.data) {
        setBridgeStatus(response.data.data)
        setStatusError(null)
      } else {
        setBridgeStatus(null)
        setStatusError(response.data.msg || 'Bridge 状态暂不可用')
      }
    } catch (error: any) {
      setBridgeStatus(null)
      setStatusError(error.message || '无法连接后端状态接口')
    } finally {
      setCheckedAt(Date.now())
      setLoading(false)
    }
  }

  useEffect(() => {
    refreshBridgeStatus()
  }, [])

  const isReady = Boolean(bridgeStatus?.ready && bridgeStatus?.loggedIn)
  const hasWarning = Boolean(statusError || bridgeStatus?.lastError)
  const runtimeLabel = statusError ? 'STATUS UNAVAILABLE' : isReady ? (hasWarning ? 'RUNNING · WARNING' : 'RUNNING') : 'EXECUTION BLOCKED'

  return (
    <main className="system-flow-page" aria-label="PolyHermes 系统链路">
      <section className="system-flow-stage">
        <header className="system-flow-heading">
          <div>
            <p className="system-flow-eyebrow">POLYHERMES · OPERATING FLOW</p>
            <h1>研究准入与实盘执行闭环</h1>
            <p>研究链路负责发现与验证；执行链路负责在可审计、可阻断的边界内完成跟单。</p>
          </div>

          <aside className={`system-flow-runtime ${statusError ? 'is-error' : hasWarning ? 'is-warning' : isReady ? 'is-ready' : 'is-blocked'}`} aria-live="polite">
            <div className="system-flow-runtime-topline">
              <span>BRIDGE RUNTIME</span>
              <button type="button" onClick={refreshBridgeStatus} disabled={loading}>
                {loading ? 'CHECKING' : 'REFRESH'}
              </button>
            </div>
            <strong>{runtimeLabel}</strong>
            <span>登录 {bridgeStatus?.loggedIn ? '已就绪' : '未就绪'} · 配置 {bridgeStatus?.copyTradingConfigCount ?? 0}</span>
            <small>{statusError || bridgeStatus?.lastError || `最近检查 ${formatSyncedAt(checkedAt || undefined)}`}</small>
          </aside>
        </header>

        <section className="system-flow-lane research-lane" aria-labelledby="research-flow-title">
          <div className="system-flow-lane-title">
            <span>LANE 01</span>
            <h2 id="research-flow-title">研究、验证与准入</h2>
            <p>任何 leader 都必须经过可复制性检验，才有资格进入小额 Trial。</p>
          </div>
          <div className="system-flow-cards research-cards">
            {researchSteps.map((step) => (
              <article className="system-flow-step" key={step.code}>
                <span className="system-flow-code">{step.code}</span>
                <h3>{step.title}</h3>
                <p>{step.body}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="system-flow-handoff" aria-label="研究到执行的交接">
          <span>APPROVED TRIAL CONFIG</span>
          <i />
          <span>ONLY APPROVED SIGNALS ENTER EXECUTION</span>
        </section>

        <section className="system-flow-lane execution-lane" aria-labelledby="execution-flow-title">
          <div className="system-flow-lane-title">
            <span>LANE 02</span>
            <h2 id="execution-flow-title">信号、风控与执行</h2>
            <p>执行不是单点下单，而是一组可验证、可审计、异常可阻断的运行门。</p>
          </div>
          <div className="system-flow-cards execution-cards">
            {executionSteps.map((step) => (
              <article className="system-flow-step" key={step.code}>
                <span className="system-flow-code">{step.code}</span>
                <h3>{step.title}</h3>
                <p>{step.body}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="system-flow-gates" aria-label="执行门禁">
          {gates.map((gate) => (
            <article key={gate.title}>
              <strong>{gate.title}</strong>
              <p>{gate.body}</p>
            </article>
          ))}
        </section>

        <p className="system-flow-feedback">结算结果、执行失败、风控决策与人工复核持续回流至 Paper、回放、leader 与策略评分。</p>
      </section>
    </main>
  )
}

export default SystemFlow
