export interface PaperObserverStats {
  rule: string
  trades: number
  pending: number
  settled: number
  wins: number
  losses: number
  winRate: number | null
  netPnlUsd: number | null
  roiPerDollar: number | null
  filteredLosses?: number
  filteredWins?: number
}

export interface PaperObserverStatus {
  paperOnly: true
  fresh: boolean
  startedAt: number
  heartbeat: number | null
  assets: Array<{
    asset: 'ETH' | 'SOL'
    baseline: PaperObserverStats
    strategies: PaperObserverStats[]
    latest: { periodStart: number, checkedAt: number, reason: string } | null
    recent: Array<{ periodStart: number, side: string, priceCents: number, rules: string[], win: boolean | null, netPnlUsd: number | null }>
  }>
}
