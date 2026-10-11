import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import ts from '../frontend/node_modules/typescript/lib/typescript.js';

const source = readFileSync(new URL('../frontend/src/utils/futureBtc5mPreflight.ts', import.meta.url), 'utf8');
const {outputText} = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS}});
const sandbox = {exports: {}};
vm.runInNewContext(outputText, sandbox);
const {signalIsFresh, preflightIsFresh, preflightReasonText} = sandbox.exports;
const start = 1791706200;
const second = start + 65;
const receipt = second * 1000;
const runtime = {
  bridgeId: 'future-btc5m', online: true, requestedEnabled: false, effectiveEnabled: false,
  amountUsd: 1, series: '5m', mode: 'DISABLED', serverTime: second,
  periodStart: start, feedStatus: 'CURRENT', executorReady: false,
  signal: {slug: `btc-updown-5m-${start}`, side: 'Up', period_start: start, period_end: start + 300,
    price_observed_at: second - 4, open_price: 82000, current_price: 82001,
    price_source: 'chainlink', open_price_source: 'polymarket_crypto_price_fiveminute_twap60_openPrice',
    twap_lookback_seconds: 60},
};

test('a current sample advances between polls and stops displaying after five seconds', () => {
  assert.equal(signalIsFresh(runtime, receipt, receipt), true);
  assert.equal(signalIsFresh(runtime, receipt, receipt + 1000), true);
  assert.equal(signalIsFresh(runtime, receipt, receipt + 1001), false);
});

test('the +80 second entry boundary expires between polls', () => {
  const at79 = {...runtime, serverTime: start + 79,
    signal: {...runtime.signal, price_observed_at: start + 79}};
  assert.equal(signalIsFresh(at79, (start + 79) * 1000, (start + 79) * 1000), true);
  assert.equal(signalIsFresh(at79, (start + 79) * 1000, (start + 80) * 1000), false);
});

test('a freshly received frozen source does not refresh stale server data', () => {
  const frozen = {...runtime, serverTime: second - 4,
    signal: {...runtime.signal, price_observed_at: second - 4}};
  assert.equal(signalIsFresh(frozen, receipt, receipt), false);
  assert.equal(signalIsFresh({...runtime, serverTime: second + 4}, receipt, receipt), false);
});

test('allowed transport delay cannot keep a sample or the entry window alive past wall time', () => {
  const sample = {...runtime, signal: {...runtime.signal, price_observed_at: second - 5}};
  assert.equal(signalIsFresh(sample, receipt + 1, receipt + 1), false);
  const at79 = {...runtime, serverTime: start + 79,
    signal: {...runtime.signal, price_observed_at: start + 79}};
  assert.equal(signalIsFresh(at79, (start + 81) * 1000, (start + 81) * 1000), false);
  const browser = {...runtime, preflight: {mode: 'READ_ONLY', noSubmission: true,
    browserConnected: true, checkedAt: second - 5, receivedAt: second - 5}};
  assert.equal(preflightIsFresh(browser, receipt + 1, receipt + 1), false);
});

test('unavailable feeds and invalid source or market metadata have no usable direction', () => {
  for (const change of [{feedStatus: 'UNAVAILABLE'}, {online: false}, {periodStart: start - 300}]) {
    assert.equal(signalIsFresh({...runtime, ...change}, receipt, receipt), false);
  }
  for (const change of [{price_source: 'binance'}, {open_price_source: 'legacy'}, {twap_lookback_seconds: 30},
    {period_end: start + 900}, {slug: `btc-updown-5m-${start - 300}`}, {side: 'Down'},
    {current_price: NaN}, {price_observed_at: second + 1}]) {
    assert.equal(signalIsFresh({...runtime, signal: {...runtime.signal, ...change}}, receipt, receipt), false);
  }
  assert.equal(signalIsFresh(runtime, receipt, receipt + 15001), false);
  assert.equal(signalIsFresh(runtime, receipt, receipt - 1), false);
});

test('browser evidence expires between polls and cannot be refreshed by a frozen source', () => {
  const preflight = {mode: 'READ_ONLY', noSubmission: true, browserConnected: true,
    checkedAt: second - 4, receivedAt: second - 4};
  const value = {...runtime, preflight};
  assert.equal(preflightIsFresh(value, receipt, receipt), true);
  assert.equal(preflightIsFresh(value, receipt, receipt + 1000), true);
  assert.equal(preflightIsFresh(value, receipt, receipt + 1001), false);
  assert.equal(preflightIsFresh({...value, serverTime: second - 4}, receipt, receipt), false);
  for (const change of [{mode: 'LIVE'}, {noSubmission: false}, {browserConnected: false}, {checkedAt: null},
    {receivedAt: NaN}, {checkedAt: second + 4}, {receivedAt: second + 1}]) {
    assert.equal(preflightIsFresh({...value, preflight: {...preflight, ...change}}, receipt, receipt), false);
  }
});

test('empty reasons cannot claim success once the signal or entry window expires', () => {
  assert.equal(preflightReasonText(true, true, true, []), '只读检查通过，未提交订单');
  assert.equal(preflightReasonText(false, true, false, []), '信号或入场窗口已过期，等待刷新核对');
  assert.equal(preflightReasonText(false, true, true, []), '等待满足当前只读预检条件');
  assert.equal(preflightReasonText(false, false, true, []), '等待当前真实页面的新鲜只读报告');
});
