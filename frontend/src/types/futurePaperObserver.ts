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
  btc?: BtcPaperValidationStatus
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

export interface BtcPaperStats extends PaperObserverStats {
  verified?: number
  feeVerifiedSettled?: number
  netPnlWithExtraCentUsd?: number | null
  netPnlWithAdverseCentUsd?: number | null
  adverseCentVerifiedTrades?: number
}

export interface BtcForwardPaperRow {
  periodStart: number
  side: string
  priceCents: number
  preparedPriceCents: number
  trend60Bp: number
  volatilityBp: number
  signedDistanceBp: number
  rules: string[]
  firstObservedAt: number
  verifiedAt: number
  backfilled: false
  actualFill: null
  win: boolean | null
  netPnlUsd: number | null
}

export interface BtcLegacyPaperRow {
  periodStart: number
  side: string
  priceCents: number
  originalWin: boolean | null
  originalRoi: number | null
  correctedWin: boolean | null
  netPnlUsd: number | null
  mismatch: boolean | null
  feesFetchedAt: number | null
}

export interface BtcPaperValidationStatus {
  forward: {
    schemaVersion: 1
    paperOnly: true
    version: string
    startedAt: number
    rulesFrozenAt: number
    heartbeat: number | null
    fresh: boolean
    latest: { periodStart: number, checkedAt: number, reason: string } | null
    signalCount: number
    baseline: BtcPaperStats
    strategies: BtcPaperStats[]
    recent: BtcForwardPaperRow[]
    lastResolveError: string | null
  } | null
  legacy: {
    schemaVersion: 1
    source: 'LEGACY_PREPARE'
    historical: true
    fresh: boolean
    fetchedAt: number | null
    lastError: string | null
    total: number
    verified: number
    mismatches: number
    baseline: BtcPaperStats
    strategies: BtcPaperStats[]
    priceEligibleStats: { baseline: BtcPaperStats, strategies: BtcPaperStats[] }
    recent: BtcLegacyPaperRow[]
  } | null
}
