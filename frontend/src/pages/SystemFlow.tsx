import './SystemFlow.css'

const steps = [
  {
    num: '01',
    title: '数据源发现',
    body: 'Polymarket Activity、Falcon、Polyburg、Dune、手工导入，多源捕捉候选钱包。'
  },
  {
    num: '02',
    title: '钱包去重入池',
    body: '标准化 wallet，去重合并，保留 source evidence，避免重复追踪。'
  },
  {
    num: '03',
    title: '分类识别',
    body: '按 politics、finance、sports、crypto 标注，政治/金融作为主权重。'
  },
  {
    num: '04',
    title: '评分模型',
    body: '综合胜率、ROI、PnL、频次、流动性、风险标签和最近活跃度。'
  },
  {
    num: '05',
    title: '回测与 Paper',
    body: '用历史订单与纸上交易验证，过滤极端低价、短周期和不可复制策略。'
  },
  {
    num: '06',
    title: '阈值决策',
    body: '高分进入 Trial Ready，低分冷却、告警或淘汰，保持 leader 池质量。'
  },
  {
    num: '07',
    title: '执行监控',
    body: 'BUY 风控，SELL 优先，Bridge 成功率和 Telegram 告警持续反馈。'
  }
]

const principles = ['高质量来源', '分类分配资金', '先验证再跟单', 'SELL 时效优先']

const SystemFlow: React.FC = () => {
  return (
    <main className="system-flow-page" aria-label="Leader 引入、打分与跟单筛选流程朋克风动画">
      <section className="system-flow-stage">
        <div className="system-flow-heading">
          <h1>Leader 引入、打分与跟单筛选流程</h1>
          <p>从数据源发现聪明钱，到评分验证，再到风控跟单执行的闭环系统</p>
        </div>

        <section className="system-flow-steps" aria-label="系统流程步骤">
          {steps.map((step, index) => (
            <article className="system-flow-step" key={step.num} style={{ animationDelay: `${0.1 + index * 0.7}s` }}>
              <div className="system-flow-num">{step.num}</div>
              <h2>{step.title}</h2>
              <p>{step.body}</p>
            </article>
          ))}
        </section>

        <div className="system-flow-arrows" aria-hidden="true">
          {Array.from({ length: 6 }, (_, index) => (
            <span key={index} />
          ))}
        </div>

        <div className="system-flow-feedback" aria-hidden="true">
          <span>执行结果反哺评分</span>
        </div>

        <section className="system-flow-principles" aria-label="核心原则">
          <strong>核心原则</strong>
          {principles.map((principle) => (
            <span className="system-flow-chip" key={principle}>
              {principle}
            </span>
          ))}
        </section>
      </section>
    </main>
  )
}

export default SystemFlow
