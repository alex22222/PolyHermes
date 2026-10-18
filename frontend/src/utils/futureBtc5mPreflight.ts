import type { FutureBtc5mBridgeStatus } from '../types'

// Round series of the strategies (same table as scripts/future_btc5m_series.py).
export const FUTURE_SERIES = {
  '5m': { period: 300, entry: [60, 80], slug: 'btc-updown-5m-', openSource: 'polymarket_crypto_price_fiveminute_twap60_openPrice' },
  '15m': { period: 900, entry: [150, 170], slug: 'btc-updown-15m-', openSource: 'polymarket_crypto_price_fifteen_twap60_openPrice' },
  '4h': { period: 14400, entry: null, slug: 'btc-updown-4h-', openSource: 'polymarket_crypto_price_fourhour_twap60_openPrice' },
} as const

// Absolute entry window containing `at`. A 4h window is the 2-minute window of a decision checkpoint
// at minute 5 or 10 of a quarter hour (future_btc5m_series.checkpoint_window); otherwise null.
export const futureEntryWindow = (series: keyof typeof FUTURE_SERIES, start: number, at: number): [number, number] | null => {
  const entry = FUTURE_SERIES[series].entry
  if (entry) return [start + entry[0], start + entry[1]]
  const offset = at - start
  const minute = Math.floor(offset / 300) * 5
  if (!Number.isFinite(offset) || minute < 5 || minute > 235 || minute % 15 === 0 || offset - minute * 60 >= 120) return null
  return [start + minute * 60, start + minute * 60 + 120]
}

export const referenceIsFresh = (runtime: FutureBtc5mBridgeStatus | null, receivedAt: number, now: number): boolean => {
  const signal = runtime?.signal
  const elapsed = (now - receivedAt) / 1000
  if (!runtime || !Number.isFinite(elapsed) || elapsed < 0 || elapsed > 15 ||
      !Number.isFinite(runtime.serverTime) || Math.abs(runtime.serverTime - receivedAt / 1000) > 3 ||
      !runtime.online || runtime.feedStatus !== 'CURRENT' || !signal) return false
  const seriesName = runtime.series in FUTURE_SERIES ? runtime.series : '5m'
  const series = FUTURE_SERIES[seriesName]
  const serverNow = Math.max(runtime.serverTime + elapsed, now / 1000)
  const start = Math.floor(serverNow / series.period) * series.period
  const window = futureEntryWindow(seriesName, start, serverNow)
  const expected = signal.current_price > signal.open_price ? 'Up' : signal.current_price < signal.open_price ? 'Down' : null
  return Number.isSafeInteger(signal.period_start) && signal.period_start >= 0 && signal.period_start % series.period === 0 &&
    runtime.periodStart === start && signal.period_start === start && signal.period_end === start + series.period &&
    signal.slug === `${series.slug}${start}` && signal.price_source === 'chainlink' &&
    signal.open_price_source === series.openSource && signal.twap_lookback_seconds === 60 &&
    Number.isFinite(signal.open_price) && signal.open_price > 0 && Number.isFinite(signal.current_price) && signal.current_price > 0 &&
    signal.side === expected && window !== null && serverNow >= window[0] && serverNow < window[1] &&
    Number.isFinite(signal.price_observed_at) && signal.price_observed_at <= runtime.serverTime &&
    serverNow >= signal.price_observed_at && serverNow - signal.price_observed_at <= 5
}

export const signalIsFresh = (runtime: FutureBtc5mBridgeStatus | null, receivedAt: number, now: number): boolean =>
  runtime?.signal?.side != null && referenceIsFresh(runtime, receivedAt, now)

export const higherButtonSide = (up: number | null | undefined, down: number | null | undefined): 'Up' | 'Down' | null => {
  if (typeof up !== 'number' || typeof down !== 'number' || !Number.isFinite(up) || !Number.isFinite(down) ||
      up < 0 || up > 100 || down < 0 || down > 100 || Math.round(up * 100) / 100 !== up ||
      Math.round(down * 100) / 100 !== down || up === down) return null
  return up > down ? 'Up' : 'Down'
}

export const preflightIsFresh = (runtime: FutureBtc5mBridgeStatus | null, receivedAt: number, now: number): boolean => {
  const preflight = runtime?.preflight
  if (!runtime || !preflight || preflight.mode !== 'READ_ONLY' || preflight.noSubmission !== true ||
      !preflight.browserConnected || !Number.isFinite(runtime.serverTime) ||
      Math.abs(runtime.serverTime - receivedAt / 1000) > 3 || now < receivedAt || now - receivedAt > 15000 ||
      preflight.checkedAt == null || preflight.receivedAt == null ||
      !Number.isFinite(preflight.checkedAt) || !Number.isFinite(preflight.receivedAt)) return false
  const serverNow = Math.max(runtime.serverTime + (now - receivedAt) / 1000, now / 1000)
  return serverNow >= preflight.receivedAt && serverNow - preflight.receivedAt <= 5 &&
    preflight.checkedAt <= serverNow + 3 && serverNow - preflight.checkedAt <= 5
}

export const preflightReasonText = (ready: boolean, browserFresh: boolean, signalFresh: boolean, reasons: string[]): string => {
  if (ready) return '只读检查通过，未提交订单'
  if (!browserFresh) return '等待当前真实页面的新鲜只读报告'
  if (!signalFresh) return '信号或入场窗口已过期，等待刷新核对'
  return reasons.join('；') || '等待满足当前只读预检条件'
}
