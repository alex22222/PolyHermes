import type { FutureBtc5mBridgeStatus } from '../types'

export const referenceIsFresh = (runtime: FutureBtc5mBridgeStatus | null, receivedAt: number, now: number): boolean => {
  const signal = runtime?.signal
  const elapsed = (now - receivedAt) / 1000
  if (!runtime || !Number.isFinite(elapsed) || elapsed < 0 || elapsed > 15 ||
      !Number.isFinite(runtime.serverTime) || Math.abs(runtime.serverTime - receivedAt / 1000) > 3 ||
      !runtime.online || runtime.feedStatus !== 'CURRENT' || !signal) return false
  const serverNow = Math.max(runtime.serverTime + elapsed, now / 1000)
  const start = Math.floor(serverNow / 300) * 300
  const expected = signal.current_price > signal.open_price ? 'Up' : signal.current_price < signal.open_price ? 'Down' : null
  return Number.isSafeInteger(signal.period_start) && signal.period_start >= 0 && signal.period_start % 300 === 0 &&
    runtime.periodStart === start && signal.period_start === start && signal.period_end === start + 300 &&
    signal.slug === `btc-updown-5m-${start}` && signal.price_source === 'chainlink' &&
    signal.open_price_source === 'polymarket_crypto_price_fiveminute_twap60_openPrice' && signal.twap_lookback_seconds === 60 &&
    Number.isFinite(signal.open_price) && signal.open_price > 0 && Number.isFinite(signal.current_price) && signal.current_price > 0 &&
    signal.side === expected && serverNow >= start + 60 && serverNow < start + 80 &&
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
