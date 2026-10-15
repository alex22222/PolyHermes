import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const content = readFileSync(new URL('./future-btc5m-extension/content.js', import.meta.url), 'utf8');
const source = readFileSync(new URL('./future-btc5m-extension/buy_once.js', import.meta.url), 'utf8');
const context = vm.createContext({URL, Event});
vm.runInContext(content, context);
const core = context.FutureBtc5m;
vm.runInContext(source, context);
const {createWatcher, createAutoBuyer} = context.FutureBtc5mBuyOnce;
const start = 1791650700;
const now = start + 65;
const marketUrl = `https://future.news/zh/event/btc-updown-5m-${start}`;
const storageKey = 'polyhermes.future-btc5m.buy-once';
const auditKey = 'polyhermes.future-btc5m.buy-audit';
const resultKey = 'polyhermes.future-btc5m.buy-result';
const clone = (value) => JSON.parse(JSON.stringify(value));

const ready = (at = now, side = 'Down', round = start) => {
  const record = {schemaVersion: 2, id: `future-btc5m-prepare:${round}`, slug: `btc-updown-5m-${round}`,
    periodStart: round, periodEnd: round + 300, side, amountUsd: 1, createdAt: at,
    expiresAt: round + 80, priceObservedAt: at, openPrice: 82000, currentPrice: 82001,
    priceSource: 'chainlink', openPriceSource: 'polymarket_crypto_price_fiveminute_twap60_openPrice',
    twapLookbackSeconds: 60, mode: 'PREPARE_ONLY', noSubmission: true, operatorAuthorized: true,
    authorizationSource: 'USER_REQUEST', claimToken: 'a'.repeat(32),
    upQuoteCents: side === 'Down' ? 12 : 88, downQuoteCents: side === 'Down' ? 88 : 12,
    quoteObservedAt: at, selectionSource: 'HIGHER_BUTTON_PRICE', state: 'READY',
    updatedAt: at, claimedAt: at, reason: null,
    receipt: {checkedAt: at, marketUrl: `https://future.news/zh/event/btc-updown-5m-${round}`, amountUsd: 1, selectedSide: side}};
  return {bridgeId: 'future-btc5m', online: true, serverTime: at, periodStart: round, feedStatus: 'CURRENT',
    requestedEnabled: true, effectiveEnabled: false, executorReady: false, amountUsd: 1, series: '5m', mode: 'BLOCKED',
    signal: {slug: record.slug, period_start: round, period_end: round + 300, side: 'Up',
      price_observed_at: at, open_price: 82000, current_price: 82001, price_source: 'chainlink',
      open_price_source: record.openPriceSource, twap_lookback_seconds: 60},
    preparation: {mode: 'PREPARE_ONLY', noSubmission: true, operatorAuthorized: true,
      authorizationSource: 'USER_REQUEST', enabled: true, state: 'READY', intent: null, lastAttempt: record, reasons: []}};
};

// Same Chinese dollar market-ticket DOM shape as the existing content.js core tests.
// Stable nodes make it possible to detect replacing the final Buy button between reads.
const ticketFixture = ({side = 'Down', amount = '1', upQuote = side === 'Down' ? '12¢' : '88¢',
  downQuote = side === 'Down' ? '88¢' : '12¢', buyDisabled = false, buyDuplicate = false,
  duplicateAmount = false, currency = '金额 ($)', sell = false, marketOrder = true,
  inert = false, disabledFieldset = false, buyType = 'button', buyForm = null,
  title = 'Bitcoin Up or Down - October 10, 12:45PM-12:50PM ET', beforeBuy = () => {}} = {}) => {
  const actions = [];
  let writes = 0;
  class FakeInput {
    get value() {return amount;}
    set value(value) {writes++; amount = value;}
    getClientRects() {return [1];}
    dispatchEvent(event) {actions.push(`event:${event.type}`);}
  }
  const body = {};
  const parent = disabledFieldset ? {tagName: 'FIELDSET', disabled: true, parentElement: body} : body;
  const ticket = {textContent: currency, inert, parentElement: parent};
  const input = new FakeInput();
  const doc = {body, defaultView: {HTMLInputElement: FakeInput}};
  Object.assign(input, {parentElement: ticket, ownerDocument: doc});
  const labels = ['买入', '卖出', marketOrder ? '市价单' : '限价单', 'Up', 'Down', sell ? '卖出 涨' : 'BUY'];
  if (buyDuplicate) labels.push('BUY');
  const buttons = labels.map((label) => {
    const direction = label === 'Up' || label === 'Down';
    const buy = label === 'BUY';
    return {tagName: 'BUTTON', type: buy ? buyType : 'button', form: buy ? buyForm : null,
      parentElement: ticket, isConnected: true,
      get textContent() {return buy ? `买入 ${side === 'Up' ? '涨' : '跌'}` : direction ?
        `${label === 'Up' ? '涨' : '跌'} ${label === 'Up' ? upQuote : downQuote}` : label;},
      get disabled() {return buy && buyDisabled;},
      getAttribute(name) {return direction && name === 'aria-pressed' ? String(label === side) : null;},
      getClientRects() {return [1];},
      click() {
        actions.push(buy ? 'buy' : direction ? `direction:${label}` : label);
        if (buy) beforeBuy();
      }};
  });
  ticket.querySelectorAll = (query) => query === 'button' ? buttons :
    title ? [{textContent: title, getClientRects: () => [1]}] : [];
  const outsideBuy = {textContent: '买入 涨', getClientRects: () => [1],
    click() {actions.push('outside-buy');}};
  doc.querySelectorAll = (query) => query === 'button' ? [...buttons, outsideBuy] : duplicateAmount ? [input, input] : [input];
  return {doc, input, actions, writes: () => writes,
    setAmount(value) {amount = value;}, setQuotes(up, down) {upQuote = up; downQuote = down;},
    setTitle(value) {title = value;}, buyButtons: buttons.filter((button) => labels[buttons.indexOf(button)] === 'BUY')};
};

const memoryStorage = (values = new Map(), {failRead = false, failWrite = false, afterWrite = () => {}} = {}) => ({values,
  getItem(key) {
    assert.equal(key, storageKey, 'never inspect site auth or unrelated browser storage');
    if (failRead) throw new Error('storage unavailable');
    return values.get(key) || null;
  },
  setItem(key, value) {
    assert.equal(key, storageKey);
    if (failWrite) throw new Error('storage unavailable');
    values.set(key, value);
    afterWrite(key, value);
  }});
// The audit outbox may only use its own key; it is a separate handle so the consumption
// assertions above keep describing the consumption marker alone.
const auditMemory = (values = new Map(), {failWrite = false} = {}) => ({values,
  getItem(key) { assert.equal(key, auditKey); return values.get(key) ?? null; },
  setItem(key, value) { assert.equal(key, auditKey); if (failWrite) throw new Error('audit storage full'); values.set(key, value); },
  entries() { return JSON.parse(values.get(auditKey) ?? '[]'); }});
const resultMemory = (values = new Map(), {failWrite = false} = {}) => ({values,
  getItem(key) { assert.equal(key, resultKey); return values.get(key) ?? null; },
  setItem(key, value) { assert.equal(key, resultKey); if (failWrite) throw new Error('result storage full'); values.set(key, value); }});
const mutex = () => {
  let previous = Promise.resolve();
  return (callback) => {
    const result = previous.then(callback);
    previous = result.catch(() => {});
    return result;
  };
};
const deferred = () => {
  let resolve;
  const promise = new Promise((done) => {resolve = done;});
  return {promise, resolve};
};
// A consistent Polymarket CLOB book snapshot of a READY round, observed now: the READY
// favorite asks exactly its prepared quote and the other side asks 101 minus it.
const clobQuote = (record, at, overrides = {}) => {
  const sideAsk = record.side === 'Up' ? record.upQuoteCents : record.downQuoteCents;
  const [upAskCents, downAskCents] = record.side === 'Up' ? [sideAsk, 101 - sideAsk] : [101 - sideAsk, sideAsk];
  return {schemaVersion: 1, source: 'polymarket_clob_book', periodStart: record.periodStart, slug: record.slug,
    upAskCents, downAskCents, upBidCents: upAskCents - 1, downBidCents: downAskCents - 1,
    observedAt: at, serverTime: at, ...overrides};
};
// readMarketQuote is not async, so a market stub may also throw synchronously.
const marketStub = (market, reads, state) => () => {
  reads.push(state.time());
  return market({record: state.latest?.preparation?.lastAttempt, time: state.time(), index: reads.length});
};
const setup = ({ticket = ticketFixture(), storage = memoryStorage(), read = () => ready(),
  market = ({record, time}) => clobQuote(record, time),
  time = now, withLock = mutex(), url = marketUrl, auditStorage = auditMemory()} = {}) => {
  let currentTime = time;
  let currentUrl = url;
  const intervals = new Map();
  const reads = [];
  const marketReads = [];
  const state = {latest: null, time: () => currentTime};
  const watcher = createWatcher({core, document: ticket.doc, readUrl: () => currentUrl,
    storage, auditStorage, extensionVersion: '0.4.1',
    readPreparation: async () => {reads.push(currentTime); state.latest = await read(reads.length); return state.latest;},
    readMarketQuote: marketStub(market, marketReads, state),
    nowFn: () => currentTime, withLock,
    setIntervalFn(callback) {const id = intervals.size + 1; intervals.set(id, callback); return id;},
    clearIntervalFn(id) {intervals.delete(id);}});
  return {watcher, ticket, storage, auditStorage, intervals, reads, marketReads,
    setTime(value) {currentTime = value;}, setUrl(value) {currentUrl = value;}};
};
const assertUnchangedTicket = (fixture, buys = 0) => {
  assert.equal(fixture.writes(), 0, 'the watcher must never fill or change the amount');
  assert.deepEqual(fixture.actions, Array(buys).fill('buy'), 'only the final ticket Buy may be clicked');
};

test('loading the isolated definition never starts a watcher, reads, clicks or timers', () => {
  let timers = 0;
  const definition = vm.createContext({URL, Event,
    setInterval() {timers++;}, fetch() {assert.fail('no request at definition load');}});
  vm.runInContext(source, definition);
  assert.equal(typeof definition.FutureBtc5mBuyOnce.createWatcher, 'function');
  assert.equal(timers, 0);
  const {watcher, reads, intervals, ticket} = setup();
  assert.equal(watcher.status().state, 'IDLE');
  assert.equal(reads.length, 0);
  assert.equal(intervals.size, 0);
  assertUnchangedTicket(ticket);
});

test('default start is dry-run and reports READY without clicking or persisting a consumption mark', async () => {
  const env = setup();
  env.watcher.start();
  await env.watcher.poll();
  assert.equal(env.watcher.status().state, 'DRY_RUN_READY');
  assert.equal(env.watcher.status().side, 'Down');
  assert.equal(env.watcher.status().amountUsd, 1);
  assert.equal(env.intervals.size, 0);
  assert.equal(env.storage.values.size, 0);
  assertUnchangedTicket(env.ticket);
});

test('explicit live start clicks the exact prepared final Buy once and records only an attempt', async () => {
  for (const side of ['Up', 'Down']) {
    const env = setup({ticket: ticketFixture({side}), read: () => ready(now, side)});
    env.watcher.start({live: true});
    await env.watcher.poll();
    await env.watcher.poll();
    assert.equal(env.watcher.status().state, 'CLICK_ATTEMPTED');
    assert.equal(env.watcher.status().periodStart, start);
    assert.equal(env.watcher.status().side, side);
    assert.equal(env.reads.length, 3, 're-read READY inside the origin lock, again after the order book, before clicking');
    assert.equal(env.intervals.size, 0);
    assert.deepEqual(JSON.parse(env.storage.values.get(storageKey)), {schemaVersion: 1,
      periodStart: start, id: `future-btc5m-prepare:${start}`, side, amountUsd: 1, state: 'CLICK_ATTEMPTED'});
    assertUnchangedTicket(env.ticket, 1);
    assert.equal('platformOrderId' in env.watcher.status(), false);
    assert.equal('filledAt' in env.watcher.status(), false);
  }
});

test('the consumption mark exists before click and a click exception remains consumed without retry', async () => {
  const storage = memoryStorage();
  const ticket = ticketFixture({beforeBuy() {
    assert.equal(JSON.parse(storage.values.get(storageKey)).state, 'CLICK_ATTEMPTED');
    throw new Error('ambiguous browser click result');
  }});
  const env = setup({ticket, storage});
  env.watcher.start({live: true});
  await env.watcher.poll();
  await env.watcher.poll();
  assert.equal(env.watcher.status().state, 'CLICK_ATTEMPTED');
  assertUnchangedTicket(ticket, 1);
  const reload = setup({storage});
  reload.watcher.start({live: true});
  await reload.watcher.poll();
  assert.equal(reload.watcher.status().reason, 'ALREADY_CONSUMED');
  assertUnchangedTicket(reload.ticket);
});

test('reload and copied tab storage both refuse another click in the consumed period', async () => {
  const first = setup();
  first.watcher.start({live: true});
  await first.watcher.poll();
  for (const storage of [first.storage, memoryStorage(new Map(first.storage.values))]) {
    const next = setup({storage});
    next.watcher.start({live: true});
    await next.watcher.poll();
    assert.equal(next.watcher.status().state, 'BLOCKED');
    assert.equal(next.watcher.status().reason, 'ALREADY_CONSUMED');
    assertUnchangedTicket(next.ticket);
  }
});

test('two watchers sharing persistent storage and an origin lock can make only one click', async () => {
  const storage = memoryStorage();
  const withLock = mutex();
  const first = setup({storage, withLock});
  const second = setup({storage, withLock});
  first.watcher.start({live: true});
  second.watcher.start({live: true});
  await Promise.all([first.watcher.poll(), second.watcher.poll()]);
  assert.equal(first.ticket.actions.filter((action) => action === 'buy').length +
    second.ticket.actions.filter((action) => action === 'buy').length, 1);
  assert.deepEqual([first.watcher.status().state, second.watcher.status().state].sort(), ['BLOCKED', 'CLICK_ATTEMPTED']);
  assert.equal([first.watcher.status().reason, second.watcher.status().reason].includes('ALREADY_CONSUMED'), true);
});

test('live start requires an origin lock and storage failures fail before any click', async () => {
  const noLock = setup({withLock: null});
  assert.throws(() => noLock.watcher.start({live: true}), /WEB_LOCKS_REQUIRED/);
  await noLock.watcher.poll();
  assert.equal(noLock.watcher.status().state, 'IDLE');
  assertUnchangedTicket(noLock.ticket);
  for (const options of [{failRead: true}, {failWrite: true}]) {
    const env = setup({storage: memoryStorage(new Map(), options)});
    env.watcher.start({live: true});
    await env.watcher.poll();
    assert.equal(env.watcher.status().state, 'BLOCKED');
    assert.equal(env.watcher.status().reason, 'STORAGE_FAILED');
    assert.equal(env.storage.values.size, 0);
    assertUnchangedTicket(env.ticket);
  }
});

test('an existing READY record created before arming is ignored without catch-up', async () => {
  const env = setup({read: () => ready(now - 0.1)});
  env.watcher.start({live: true});
  await env.watcher.poll();
  assert.equal(env.watcher.status().state, 'WATCHING');
  assert.equal(env.storage.values.size, 0);
  assertUnchangedTicket(env.ticket);
});

test('invalid READY scope, history, receipt, original samples and entry boundary never click', async () => {
  const changes = [
    (value) => {value.preparation.enabled = false;},
    (value) => {value.preparation.state = 'WAITING_SIGNAL';},
    (value) => {value.preparation.intent = value.preparation.lastAttempt;},
    (value) => {value.preparation.noSubmission = false;},
    (value) => {value.preparation.lastAttempt.schemaVersion = 1;},
    (value) => {value.preparation.lastAttempt.amountUsd = 2;},
    (value) => {value.preparation.lastAttempt.receipt = null;},
    (value) => {value.preparation.lastAttempt.receipt.amountUsd = 2;},
    (value) => {value.preparation.lastAttempt.receipt.selectedSide = 'Up';},
    (value) => {value.preparation.lastAttempt.priceObservedAt = now - 5.001;},
    (value) => {value.preparation.lastAttempt.quoteObservedAt = now - 5.001;},
    (value) => {value.preparation.lastAttempt.selectionSource = 'CHAINLINK';},
    (value) => {value.preparation.lastAttempt.downQuoteCents = 12;},
    (value) => {value.preparation.lastAttempt.upQuoteCents = 12.345;},
    (value) => {value.serverTime = now - 3.001;},
  ];
  for (const change of changes) {
    const value = ready();
    change(value);
    const env = setup({read: () => value});
    env.watcher.start({live: true});
    await env.watcher.poll();
    assert.equal(env.storage.values.size, 0);
    assertUnchangedTicket(env.ticket);
  }
  for (const time of [start + 59, start + 80]) {
    const env = setup({time, read: () => ready(time)});
    env.watcher.start({live: true});
    await env.watcher.poll();
    assertUnchangedTicket(env.ticket);
  }
});

test('real core inspection rejects changed amount side quotes or unsafe/ambiguous final ticket', async () => {
  for (const options of [{amount: '2'}, {side: 'Up'}, {upQuote: '90¢', downQuote: '10¢'},
    {upQuote: '88¢', downQuote: '88¢'}, {upQuote: '--'}, {buyDisabled: true}, {buyDuplicate: true},
    {duplicateAmount: true}, {currency: '金额 (¥)'}, {sell: true}, {marketOrder: false},
    {inert: true}, {disabledFieldset: true}, {buyType: 'submit'},
    {title: 'Bitcoin Up or Down - October 10, 12:40PM-12:45PM ET'}]) {
    const env = setup({ticket: ticketFixture(options)});
    env.watcher.start({live: true});
    await env.watcher.poll();
    assert.equal(env.storage.values.size, 0);
    assertUnchangedTicket(env.ticket);
  }
  for (const url of [`https://future.news/zh/event/btc-updown-5m-${start - 300}`,
    `https://future.news.evil.test/zh/event/btc-updown-5m-${start}`, 'https://future.news/zh/updown']) {
    const env = setup({url});
    env.watcher.start({live: true});
    await env.watcher.poll();
    assertUnchangedTicket(env.ticket);
  }
});

test('stop while either asynchronous preparation read is pending forbids the final click', async () => {
  for (const pendingRead of [1, 2]) {
    const wait = deferred();
    const entered = deferred();
    const env = setup({read(index) {if (index === pendingRead) {entered.resolve(); return wait.promise;} return ready();}});
    env.watcher.start({live: true});
    const poll = env.watcher.poll();
    await entered.promise;
    env.watcher.stop();
    wait.resolve(ready());
    await poll;
    assert.equal(env.watcher.status().state, 'STOPPED');
    assert.equal(env.intervals.size, 0);
    assert.equal(env.storage.values.size, 0);
    assertUnchangedTicket(env.ticket);
  }
});

test('a STOP or new quote winner on the final preparation re-read prevents clicking', async () => {
  for (const change of [
    (value) => {value.preparation.enabled = false; value.preparation.state = 'DISABLED';},
    (value) => {value.preparation.lastAttempt.side = 'Up'; value.preparation.lastAttempt.upQuoteCents = 88;
      value.preparation.lastAttempt.downQuoteCents = 12; value.preparation.lastAttempt.receipt.selectedSide = 'Up';},
  ]) {
    const changed = ready();
    change(changed);
    const env = setup({read(index) {return index === 1 ? ready() : changed;}});
    env.watcher.start({live: true});
    await env.watcher.poll();
    assert.equal(env.reads.length, 2);
    assert.equal(env.storage.values.size, 0);
    assertUnchangedTicket(env.ticket);
  }
});

test('DOM quote, amount or market changes during the final read are rechecked before clicking', async () => {
  for (const change of [(env) => env.ticket.setQuotes('90¢', '10¢'), (env) => env.ticket.setAmount('2'),
    (env) => env.setUrl(`https://future.news/zh/event/btc-updown-5m-${start - 300}`)]) {
    let env;
    env = setup({read(index) {if (index === 2) change(env); return ready();}});
    env.watcher.start({live: true});
    await env.watcher.poll();
    assert.equal(env.storage.values.size, 0);
    assertUnchangedTicket(env.ticket);
  }
});

test('a failed preparation read stops monitoring with READ_FAILED and no click', async () => {
  for (const failedRead of [1, 2]) {
    const env = setup({read(index) {if (index === failedRead) throw new Error('unavailable'); return ready();}});
    env.watcher.start({live: true});
    await env.watcher.poll();
    assert.equal(env.watcher.status().state, 'BLOCKED');
    assert.equal(env.watcher.status().reason, 'READ_FAILED');
    assert.equal(env.intervals.size, 0);
    assert.equal(env.storage.values.size, 0);
    assertUnchangedTicket(env.ticket);
  }
});

test('overlapping polls of a single watcher cannot duplicate the final Buy', async () => {
  const wait = deferred();
  const env = setup({read(index) {return index === 1 ? wait.promise : ready();}});
  env.watcher.start({live: true});
  const first = env.watcher.poll();
  const second = env.watcher.poll();
  wait.resolve(ready());
  await Promise.all([first, second]);
  assertUnchangedTicket(env.ticket, 1);
  assert.equal(env.watcher.status().state, 'CLICK_ATTEMPTED');
});

test('malformed durable consumption marks fail closed rather than being reset or ignored', async () => {
  for (const raw of ['broken-json', 'null', '{}', JSON.stringify({schemaVersion: 1, periodStart: start,
    id: `future-btc5m-prepare:${start}`, side: 'Down', amountUsd: 2, state: 'CLICK_ATTEMPTED'})]) {
    const storage = memoryStorage(new Map([[storageKey, raw]]));
    const env = setup({storage});
    env.watcher.start({live: true});
    await env.watcher.poll();
    assert.equal(env.watcher.status().reason, 'STORAGE_FAILED');
    assert.equal(storage.values.get(storageKey), raw);
    assertUnchangedTicket(env.ticket);
  }
});

test('an attempted process cannot be armed for another automatic click after stop', async () => {
  const env = setup();
  env.watcher.start({live: true});
  await env.watcher.poll();
  env.watcher.stop();
  assert.throws(() => env.watcher.start({live: true}), /CONSUMED/);
  await env.watcher.poll();
  assertUnchangedTicket(env.ticket, 1);
});

test('a stopped pending read cannot complete a newly armed generation', async () => {
  const wait = deferred();
  const env = setup({read(index) {return index === 1 ? wait.promise : ready();}});
  env.watcher.start({live: true});
  const oldPoll = env.watcher.poll();
  env.watcher.stop();
  env.watcher.start({live: true});
  wait.resolve(ready());
  await oldPoll;
  assert.equal(env.watcher.status().state, 'WATCHING');
  assertUnchangedTicket(env.ticket);
  await env.watcher.poll();
  assert.equal(env.watcher.status().state, 'CLICK_ATTEMPTED');
  assertUnchangedTicket(env.ticket, 1);
});

test('original samples and the entry window are checked again after an awaited read', async () => {
  for (const time of [now + 5.001, start + 80]) {
    let env;
    env = setup({read(index) {
      if (index === 2) env.setTime(time);
      return {...ready(), serverTime: index === 2 ? time : now};
    }});
    env.watcher.start({live: true});
    await env.watcher.poll();
    assert.equal(env.storage.values.size, 0);
    assertUnchangedTicket(env.ticket);
  }
});

test('READY receipt checkedAt cannot precede updatedAt by more than three seconds', async () => {
  const at = start + 61;
  const value = ready(at);
  value.serverTime = now;
  value.preparation.lastAttempt.updatedAt = now;
  value.preparation.lastAttempt.receipt.checkedAt = at + 0.5;
  const env = setup({time: at, read: () => value});
  env.watcher.start({live: true});
  env.setTime(now);
  await env.watcher.poll();
  assert.equal(env.storage.values.size, 0);
  assertUnchangedTicket(env.ticket);
});

test('claimedAt must still be within five seconds of both immutable original samples', async () => {
  for (const sample of ['priceObservedAt', 'quoteObservedAt']) {
    const at = start + 61;
    const value = ready(at + 1);
    value.serverTime = now + 2;
    value.preparation.lastAttempt[sample] = at;
    value.preparation.lastAttempt.claimedAt = now + 2;
    value.preparation.lastAttempt.updatedAt = now + 2;
    value.preparation.lastAttempt.receipt.checkedAt = now + 2;
    const env = setup({time: at, read: () => value});
    env.watcher.start({live: true});
    env.setTime(now);
    await env.watcher.poll();
    assert.equal(env.storage.values.size, 0, `${sample}: client clock lag cannot legitimize a claim after its original sample expires`);
    assertUnchangedTicket(env.ticket);
  }
});

test('READY updatedAt must still be within five seconds of both immutable original samples', async () => {
  for (const sample of ['priceObservedAt', 'quoteObservedAt']) {
    const at = start + 61;
    const value = ready(at + 1);
    value.serverTime = now + 2;
    value.preparation.lastAttempt[sample] = at;
    value.preparation.lastAttempt.claimedAt = now;
    value.preparation.lastAttempt.updatedAt = now + 2;
    value.preparation.lastAttempt.receipt.checkedAt = now + 2;
    const env = setup({time: at, read: () => value});
    env.watcher.start({live: true});
    env.setTime(now);
    await env.watcher.poll();
    assert.equal(env.storage.values.size, 0, `${sample}: a later READY cannot refresh its immutable original permission`);
    assertUnchangedTicket(env.ticket);
  }
});

test('stopping an already consumed watcher preserves its click-attempt fact and unknown platform result', async () => {
  const env = setup();
  env.watcher.start({live: true});
  await env.watcher.poll();
  const attempted = clone(env.watcher.status());
  env.watcher.stop();
  assert.deepEqual(clone(env.watcher.status()), attempted);
  assert.equal(env.watcher.status().state, 'CLICK_ATTEMPTED');
  assert.equal(env.watcher.status().periodStart, start);
  assert.equal(env.watcher.status().side, 'Down');
  assert.equal(env.watcher.status().amountUsd, 1);
  assert.equal(env.intervals.size, 0);
  assertUnchangedTicket(env.ticket, 1);
});


test('a blocking marker write cannot extend sample freshness or the entry window before clicking', async () => {
  for (const time of [now + 6, start + 80]) {
    let env;
    const storage = memoryStorage(new Map(), {afterWrite() {env.setTime(time);}});
    env = setup({storage});
    env.watcher.start({live: true});
    await env.watcher.poll();
    assert.equal(env.watcher.status().state, 'BLOCKED');
    assert.equal(env.watcher.status().reason, 'FINAL_CHECK_FAILED');
    assert.equal(JSON.parse(storage.values.get(storageKey)).state, 'CLICK_ATTEMPTED', 'keep the consumed marker despite rejecting a late click');
    assert.throws(() => env.watcher.start({live: true}), /CONSUMED/);
    assertUnchangedTicket(env.ticket);
  }
});

test('DOM direction or amount changes during the marker write are checked before clicking', async () => {
  for (const change of [(env) => env.ticket.setQuotes('90¢', '10¢'), (env) => env.ticket.setAmount('2')]) {
    let env;
    const storage = memoryStorage(new Map(), {afterWrite() {change(env);}});
    env = setup({storage});
    env.watcher.start({live: true});
    await env.watcher.poll();
    assert.equal(env.watcher.status().state, 'BLOCKED');
    assert.equal(env.watcher.status().reason, 'FINAL_CHECK_FAILED');
    assert.equal(storage.values.size, 1);
    assert.throws(() => env.watcher.start({live: true}), /CONSUMED/);
    assertUnchangedTicket(env.ticket);
  }
});

test('a detached final Buy button after persisting the marker is never clicked', async () => {
  let env;
  const storage = memoryStorage(new Map(), {afterWrite() {env.ticket.buyButtons[0].isConnected = false;}});
  env = setup({storage});
  env.watcher.start({live: true});
  await env.watcher.poll();
  assert.equal(env.watcher.status().state, 'BLOCKED');
  assert.equal(env.watcher.status().reason, 'FINAL_CHECK_FAILED');
  assert.equal(storage.values.size, 1);
  assertUnchangedTicket(env.ticket);
});

test('stop during a synchronous marker write cancels the click and preserves consumption', async () => {
  let env;
  const storage = memoryStorage(new Map(), {afterWrite() {env.watcher.stop();}});
  env = setup({storage});
  env.watcher.start({live: true});
  await env.watcher.poll();
  assert.equal(env.watcher.status().state, 'STOPPED');
  assert.equal(env.intervals.size, 0);
  assert.equal(storage.values.size, 1);
  assert.throws(() => env.watcher.start({live: true}), /CONSUMED/);
  assertUnchangedTicket(env.ticket);
});

test('canonical zh and plain receipt market URLs accept an optional trailing slash', async () => {
  for (const path of ['/zh/event/', '/event/']) {
    for (const suffix of ['', '/']) {
      const url = `https://future.news${path}btc-updown-5m-${start}${suffix}`;
      const value = ready();
      value.preparation.lastAttempt.receipt.marketUrl = url;
      const env = setup({url, read: () => value});
      env.watcher.start({live: true});
      await env.watcher.poll();
      assert.equal(env.watcher.status().state, 'CLICK_ATTEMPTED');
      assertUnchangedTicket(env.ticket, 1);
    }
  }
});

test('receipt URL compatibility never accepts query hash credentials or another origin', async () => {
  for (const url of [`${marketUrl}?token=private`, `${marketUrl}#hash`,
    marketUrl.replace('https://', 'https://user:secret@'), marketUrl.replace('future.news', 'future.news.evil.test'),
    marketUrl.replace('https://', 'http://')]) {
    const value = ready();
    value.preparation.lastAttempt.receipt.marketUrl = url;
    const env = setup({read: () => value});
    env.watcher.start({live: true});
    await env.watcher.poll();
    assert.equal(env.storage.values.size, 0);
    assertUnchangedTicket(env.ticket);
  }
});

const waiting = (at) => {
  const value = ready(at);
  value.preparation = {...value.preparation, state: 'WAITING_SIGNAL', lastAttempt: null, reasons: ['WAITING_CURRENT_SIGNAL']};
  return value;
};
// The switch-following controller owns its watchers; ticks run their scheduled polls.
const setupAuto = ({ticket = ticketFixture(), storage = memoryStorage(), withLock = mutex(),
  read = () => waiting(start + 30), market = ({record, time}) => clobQuote(record, time),
  positionReader = () => null, resultStorage = resultMemory(),
  auditStorage = auditMemory(), reportAudit = async (entry) =>
    ({bridgeId: 'future-btc5m', auditId: entry.auditId, stored: true, duplicate: false})} = {}) => {
  let currentTime = start + 30;
  let currentUrl = marketUrl;
  let currentRead = read;
  let currentMarket = market;
  let nextId = 0;
  const intervals = new Map();
  const reads = [];
  const marketReads = [];
  const state = {latest: null, time: () => currentTime};
  const buyer = createAutoBuyer({core: {...core, readPositionSnapshot: positionReader}, document: ticket.doc, readUrl: () => currentUrl, storage,
    resultStorage,
    auditStorage, extensionVersion: '0.4.1', reportAudit,
    readPreparation: async () => {reads.push(currentTime); state.latest = await currentRead(reads.length); return state.latest;},
    readMarketQuote: marketStub((context) => currentMarket(context), marketReads, state),
    nowFn: () => currentTime, withLock,
    setIntervalFn(callback) {intervals.set(++nextId, callback); return nextId;},
    clearIntervalFn(id) {intervals.delete(id);}});
  return {buyer, ticket, storage, auditStorage, resultStorage, intervals, reads, marketReads,
    setTime(value) {currentTime = value;}, setUrl(value) {currentUrl = value;}, setRead(value) {currentRead = value;},
    setMarket(value) {currentMarket = value;},
    async tick() {
      for (const callback of [...intervals.values()]) callback();
      for (let i = 0; i < 5; i++) await new Promise((resolve) => setImmediate(resolve));
    }};
};

test('the automatic-ticket switch keeps one live watcher armed and clicks each new READY round once', async () => {
  const env = setupAuto();
  assert.equal(env.buyer.status().state, 'OFF');
  assert.equal(env.buyer.sync(true).state, 'WATCHING');
  assert.equal(env.intervals.size, 1);
  await env.tick();
  assert.equal(env.buyer.sync(true).state, 'WATCHING');
  assertUnchangedTicket(env.ticket);

  env.setTime(now);
  env.setRead(() => ready());
  await env.tick();
  assert.equal(env.buyer.status().state, 'PAUSED', 'a finished watcher is not reported as still watching');
  assert.equal(env.buyer.status().last.state, 'CLICK_ATTEMPTED');
  assertUnchangedTicket(env.ticket, 1);

  // Re-armed after the click: the same round's READY predates arming and is never retried.
  env.setTime(now + 1);
  const view = env.buyer.sync(true);
  assert.equal(view.state, 'WATCHING');
  assert.equal(view.last.periodStart, start);
  assert.equal(view.last.side, 'Down');
  assert.equal(env.intervals.size, 1);
  await env.tick();
  await env.tick();
  assert.equal(env.buyer.sync(true).state, 'WATCHING');
  assertUnchangedTicket(env.ticket, 1);

  const next = start + 300;
  env.setTime(next + 65);
  env.setUrl(`https://future.news/zh/event/btc-updown-5m-${next}`);
  env.ticket.setTitle('Bitcoin Up or Down - October 10, 12:50PM-12:55PM ET');
  env.setRead(() => ready(next + 65, 'Down', next));
  await env.tick();
  assert.equal(env.buyer.sync(true).last.periodStart, next);
  assert.equal(JSON.parse(env.storage.values.get(storageKey)).periodStart, next);
  assertUnchangedTicket(env.ticket, 2);
});

test('turning the switch off stops the watcher and re-enabling never catches up an existing READY', async () => {
  const env = setupAuto();
  env.buyer.sync(true);
  assert.equal(env.buyer.sync(false).state, 'OFF');
  assert.equal(env.intervals.size, 0);
  env.setTime(now);
  env.setRead(() => ready());
  await env.tick();
  assert.equal(env.reads.length, 0);
  env.setTime(now + 1);
  assert.equal(env.buyer.sync(true).state, 'WATCHING');
  await env.tick();
  await env.tick();
  assert.equal(env.buyer.sync(true).state, 'WATCHING');
  assert.equal(env.buyer.sync(false).state, 'OFF');
  assert.equal(env.intervals.size, 0);
  assert.equal(env.storage.values.size, 0);
  assertUnchangedTicket(env.ticket);
});

test('a confirmed READY notification checks immediately without waiting for the 500 ms timer or a discovery GET', async () => {
  const env = setupAuto();
  env.buyer.sync(true);
  env.setTime(now);
  env.setRead(() => ready());
  await env.buyer.notifyReady(ready());
  assert.equal(env.reads.length, 2, 'retain the in-lock and post-book READY reads');
  assert.equal(env.buyer.status().last.state, 'CLICK_ATTEMPTED');
  assertUnchangedTicket(env.ticket, 1);
  await env.buyer.notifyReady(ready());
  await env.tick();
  assertUnchangedTicket(env.ticket, 1);
  env.buyer.sync(false);
  await env.buyer.notifyReady(ready());
  assert.equal(env.reads.length, 2, 'notification does not arm a disabled watcher');
});

test('the order-book read overlaps the in-lock READY read but never replaces the post-book check', async () => {
  const second = deferred();
  const market = deferred();
  let started = false;
  const env = setup({read: (index) => index === 2 ? second.promise : ready(),
    market: () => { started = true; return market.promise; }});
  env.watcher.start({live: true});
  const poll = env.watcher.poll();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(started, true, 'book I/O must start before the second READY request finishes');
  assert.equal(env.reads.length, 2);
  assertUnchangedTicket(env.ticket);
  second.resolve(ready());
  market.resolve(clobQuote(ready().preparation.lastAttempt, now));
  await poll;
  assert.equal(env.reads.length, 3);
  assertUnchangedTicket(env.ticket, 1);
});

test('a READY notification arriving during a pending timer read is processed as soon as that read finishes', async () => {
  const wait = deferred();
  const env = setupAuto({read: (index) => index === 1 ? wait.promise : ready()});
  env.buyer.sync(true);
  await env.tick();
  env.setTime(now);
  await env.buyer.notifyReady(ready());
  wait.resolve(waiting(now));
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(env.buyer.status().last?.state, 'CLICK_ATTEMPTED');
  assert.equal(env.reads.length, 3, 'one old timer GET and two current permission checks');
  assertUnchangedTicket(env.ticket, 1);
});

test('the immediate READY path still refuses STOP, expired evidence and a price move above five cents', async () => {
  for (const reason of ['READY_CHANGED', 'PRICE_ABOVE_MAX']) {
    const round = pricedRound(62, 39);
    const env = setupAuto({ticket: round.ticket});
    env.buyer.sync(true);
    env.setTime(now);
    env.setRead((index) => {
      const value = clone(round.read());
      if (reason === 'READY_CHANGED' && index === 2) {
        value.preparation.enabled = false;
        value.preparation.state = 'DISABLED';
      }
      return value;
    });
    if (reason === 'PRICE_ABOVE_MAX') {
      env.ticket.setQuotes('68¢', '33¢');
      env.setMarket(book({upAskCents: 68, downAskCents: 33}));
    }
    await env.buyer.notifyReady(round.read());
    assert.equal(env.buyer.status().last.reason, reason);
    assert.equal(env.storage.values.size, 0);
    assertUnchangedTicket(env.ticket);
  }
  const expired = setupAuto();
  expired.buyer.sync(true);
  expired.setTime(now + 5.01);
  await expired.buyer.notifyReady(ready());
  assert.equal(expired.reads.length, 0);
  assertUnchangedTicket(expired.ticket);
});

test('a queued READY notification is discarded when the switch is turned off', async () => {
  const wait = deferred();
  const env = setupAuto({read: () => wait.promise});
  env.buyer.sync(true);
  await env.tick();
  env.setTime(now);
  await env.buyer.notifyReady(ready());
  env.buyer.sync(false);
  wait.resolve(waiting(now));
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(env.buyer.status().state, 'OFF');
  assert.equal(env.reads.length, 1);
  assertUnchangedTicket(env.ticket);
});

test('parallel notification and timer polling cannot consume a round twice', async () => {
  const wait = deferred();
  const env = setupAuto({read: (index) => index === 1 ? wait.promise : ready(),
    market: ({time}) => clobQuote(ready().preparation.lastAttempt, time)});
  env.buyer.sync(true);
  env.setTime(now);
  const immediate = env.buyer.notifyReady(ready());
  await env.buyer.notifyReady(ready());
  await env.tick();
  wait.resolve(ready());
  await immediate;
  assertUnchangedTicket(env.ticket, 1);
  assert.equal(env.reads.length, 2);
});

test('start failures and transient read failures re-arm without clicking or hiding the last attempt', async () => {
  const noLock = setupAuto({withLock: null});
  const blocked = noLock.buyer.sync(true);
  assert.equal(blocked.state, 'BLOCKED');
  assert.equal(blocked.reason, 'WEB_LOCKS_REQUIRED');
  assert.equal(noLock.intervals.size, 0);
  assert.equal(noLock.buyer.sync(false).reason, null);
  assertUnchangedTicket(noLock.ticket);

  const env = setupAuto({read: () => {throw new Error('bridge timeout');}});
  env.buyer.sync(true);
  await env.tick();
  assert.equal(env.buyer.status().state, 'PAUSED');
  assert.equal(env.buyer.status().last, null, 'a transient read failure is not a ticket result');
  assert.equal(env.buyer.sync(true).state, 'WATCHING');
  env.setTime(now);
  env.setRead(() => ready());
  await env.tick();
  assertUnchangedTicket(env.ticket, 1);
  env.setTime(now + 1);
  env.setRead(() => {throw new Error('bridge timeout');});
  env.buyer.sync(true);
  await env.tick();
  assert.equal(env.buyer.sync(true).last.state, 'CLICK_ATTEMPTED');
  assertUnchangedTicket(env.ticket, 1);
});

test('a live click queues one audit after the click with the final ticket facts bound to READY', async () => {
  let env;
  const auditStorage = auditMemory();
  const ticket = ticketFixture({beforeBuy() {
    assert.deepEqual(auditStorage.entries(), [], 'the audit write never delays the click');
  }});
  env = setup({ticket, auditStorage});
  env.watcher.start({live: true});
  await env.watcher.poll();
  assertUnchangedTicket(ticket, 1);
  assert.equal(env.watcher.status().audit, 'QUEUED');
  const record = ready().preparation.lastAttempt;
  assert.deepEqual(auditStorage.entries(), [{schemaVersion: 2,
    auditId: `${record.id}:${Math.floor(now * 1000)}`, id: record.id, claimToken: record.claimToken,
    periodStart: start, side: 'Down', amountUsd: 1, state: 'CLICK_ATTEMPTED', reason: 'PLATFORM_RESULT_UNKNOWN',
    armedAt: now, attemptedAt: now, marketUrl, upQuoteCents: 12, downQuoteCents: 88,
    selectedSide: 'Down', ticketAmountUsd: 1, extensionVersion: '0.4.1',
    marketUpAskCents: 13, marketDownAskCents: 88, marketQuoteObservedAt: now}]);
});

test('READY refusals are audited while read failures, dry runs and stale READY leave no audit', async () => {
  for (const [options, reason] of [
    [{ticket: ticketFixture({buyDisabled: true})}, 'TICKET_CHANGED'],
    [{storage: memoryStorage(new Map([[storageKey, JSON.stringify({schemaVersion: 1, periodStart: start,
      id: `future-btc5m-prepare:${start}`, side: 'Down', amountUsd: 1, state: 'CLICK_ATTEMPTED'})]]))}, 'ALREADY_CONSUMED'],
  ]) {
    const env = setup(options);
    env.watcher.start({live: true});
    await env.watcher.poll();
    assert.equal(env.watcher.status().reason, reason);
    assert.deepEqual(env.auditStorage.entries().map((entry) => [entry.state, entry.reason, entry.periodStart]),
      [['BLOCKED', reason, start]]);
    assertUnchangedTicket(env.ticket);
  }
  let env;
  const storage = memoryStorage(new Map(), {afterWrite() {env.ticket.buyButtons[0].isConnected = false;}});
  env = setup({storage});
  env.watcher.start({live: true});
  await env.watcher.poll();
  assert.deepEqual(env.auditStorage.entries().map((entry) => entry.reason), ['FINAL_CHECK_FAILED']);

  for (const options of [{read: () => {throw new Error('bridge timeout');}}, {read: () => ready(now - 0.1)}]) {
    const quiet = setup(options);
    quiet.watcher.start({live: true});
    await quiet.watcher.poll();
    assert.deepEqual(quiet.auditStorage.entries(), []);
  }
  const dryRun = setup();
  dryRun.watcher.start();
  await dryRun.watcher.poll();
  assert.equal(dryRun.watcher.status().state, 'DRY_RUN_READY');
  assert.deepEqual(dryRun.auditStorage.entries(), []);
});

test('an audit storage failure never blocks the click and is reported as an audit failure', async () => {
  const env = setup({auditStorage: auditMemory(new Map(), {failWrite: true})});
  env.watcher.start({live: true});
  await env.watcher.poll();
  assert.equal(env.watcher.status().state, 'CLICK_ATTEMPTED');
  assert.equal(env.watcher.status().audit, 'FAILED');
  assertUnchangedTicket(env.ticket, 1);
});

test('the auto buyer flushes audits, removes only acknowledged entries and keeps the rest pending', async () => {
  const sent = [];
  let accept = () => true;
  const env = setupAuto({reportAudit: async (entry) => {
    sent.push(entry.auditId);
    if (!accept(entry)) throw new Error('bridge offline');
    return {bridgeId: 'future-btc5m', auditId: entry.auditId, stored: true, duplicate: false};
  }});
  env.buyer.sync(true);
  env.setTime(now);
  env.setRead(() => ready());
  accept = () => false;
  await env.tick();
  env.setTime(now + 1);
  const view = env.buyer.sync(true);
  await env.tick();
  assert.equal(env.auditStorage.entries().length, 1, 'kept locally while the bridge is unavailable');
  assert.equal(env.buyer.status().pendingAudits, 1);
  assert.equal(env.buyer.status().auditError, 'AUDIT_REPORT_PENDING');
  assert.equal(view.last.audit, 'QUEUED');
  accept = () => true;
  await env.buyer.flushAudits();
  assert.deepEqual(env.auditStorage.entries(), []);
  assert.equal(env.buyer.status().pendingAudits, 0);
  assert.equal(env.buyer.status().auditError, null);
  assert.equal(new Set(sent).size, 1, 'every retry resends the same audit id');

  // A wrong acknowledgement is not proof of storage.
  env.auditStorage.values.set(auditKey, JSON.stringify([{auditId: 'a'}, {auditId: 'b'}]));
  const partial = setupAuto({auditStorage: env.auditStorage, reportAudit: async (entry) =>
    ({bridgeId: 'future-btc5m', auditId: entry.auditId === 'a' ? 'other' : entry.auditId, stored: true})});
  await partial.buyer.flushAudits();
  assert.deepEqual(env.auditStorage.entries(), [{auditId: 'a'}]);
  assert.equal(partial.buyer.status().pendingAudits, 1);
});

// Price gates: a READY round prepared at the given button quotes, shown with the same
// quotes on the page unless a ticket option overrides them.
const pricedRound = (up, down, ticketOptions = {}) => {
  const side = up > down ? 'Up' : 'Down';
  const value = ready(now, side);
  Object.assign(value.preparation.lastAttempt, {upQuoteCents: up, downQuoteCents: down});
  return {side, record: value.preparation.lastAttempt, read: () => value,
    ticket: ticketFixture({side, upQuote: `${up}¢`, downQuote: `${down}¢`, ...ticketOptions})};
};
const book = (overrides) => ({record, time}) => clobQuote(record, time, overrides);
const liveOnce = async (options) => {
  const env = setup(options);
  env.watcher.start({live: true});
  await env.watcher.poll();
  return env;
};
const assertRefused = (env, reason) => {
  assert.equal(env.watcher.status().state, 'BLOCKED');
  assert.equal(env.watcher.status().reason, reason);
  assert.equal(env.storage.values.size, 0, 'a refused round is never marked consumed');
  assertUnchangedTicket(env.ticket);
};
const assertClicked = (env) => {
  assert.equal(env.watcher.status().state, 'CLICK_ATTEMPTED');
  assert.equal(env.marketReads.length, 1);
  assertUnchangedTicket(env.ticket, 1);
};
const auditFacts = (env) => env.auditStorage.entries().map((entry) => ({schemaVersion: entry.schemaVersion,
  state: entry.state, reason: entry.reason, upQuoteCents: entry.upQuoteCents, downQuoteCents: entry.downQuoteCents,
  marketUpAskCents: entry.marketUpAskCents, marketDownAskCents: entry.marketDownAskCents,
  marketQuoteObservedAt: entry.marketQuoteObservedAt}));

test('a READY favorite below 60 cents skips the round without asking the order book', async () => {
  for (const [up, down] of [[45, 56], [56, 45], [40.01, 59.99]]) {
    const round = pricedRound(up, down);
    const env = await liveOnce({read: round.read, ticket: round.ticket});
    assertRefused(env, 'PRICE_BELOW_MIN');
    assert.equal(env.reads.length, 2, 'judged on the READY re-read inside the origin lock');
    assert.equal(env.marketReads.length, 0, 'no CLOB request for a skipped round');
    assert.deepEqual(env.auditStorage.entries(), [{schemaVersion: 2,
      auditId: `${round.record.id}:${Math.floor(now * 1000)}`, id: round.record.id, claimToken: round.record.claimToken,
      periodStart: start, side: round.side, amountUsd: 1, state: 'BLOCKED', reason: 'PRICE_BELOW_MIN',
      armedAt: now, attemptedAt: now, marketUrl, upQuoteCents: up, downQuoteCents: down,
      selectedSide: round.side, ticketAmountUsd: 1, extensionVersion: '0.4.1',
      marketUpAskCents: null, marketDownAskCents: null, marketQuoteObservedAt: null}]);
  }
  const low = pricedRound(45, 56);
  const dryRun = setup({read: low.read, ticket: low.ticket});
  dryRun.watcher.start();
  await dryRun.watcher.poll();
  assertRefused(dryRun, 'PRICE_BELOW_MIN');
  assert.equal(dryRun.marketReads.length, 0);
  assert.deepEqual(dryRun.auditStorage.entries(), [], 'a dry run never queues an audit');

  for (const [up, down] of [[41, 60], [60, 39.99]]) {
    const round = pricedRound(up, down);
    assertClicked(await liveOnce({read: round.read, ticket: round.ticket}));
  }
});

test('an unavailable, stale, foreign or malformed order book blocks with MARKET_QUOTE_UNAVAILABLE', async () => {
  const withKeys = (change) => ({record, time}) => {
    const value = clobQuote(record, time);
    change(value);
    return value;
  };
  for (const market of [
    () => Promise.reject(new Error('assistant offline')),
    () => {throw new Error('extension context lost');},
    () => null, () => undefined, () => [], () => ({}), () => 'snapshot',
    book({observedAt: now - 2.01}), book({observedAt: now + 0.51}), book({observedAt: NaN}), book({observedAt: null}),
    book({serverTime: now + 3.01}), book({serverTime: now - 3.01}), book({serverTime: String(now)}),
    book({periodStart: start - 300}), book({periodStart: String(start)}),
    book({slug: `btc-updown-5m-${start - 300}`}), book({periodStart: start + 300, slug: `btc-updown-5m-${start + 300}`}),
    book({schemaVersion: 2}), book({source: 'future_button'}),
    book({downAskCents: null}), book({upAskCents: null}), book({upAskCents: null, downAskCents: null}),
    book({downAskCents: 88.001}), book({upAskCents: 101}), book({upBidCents: -1}), book({downBidCents: '87'}),
    book({downAskCents: NaN}), book({upAskCents: Infinity}),
    withKeys((value) => {value.extra = 1;}), withKeys((value) => {delete value.upBidCents;}),
  ]) {
    const env = await liveOnce({market});
    assertRefused(env, 'MARKET_QUOTE_UNAVAILABLE');
    assert.equal(env.marketReads.length, 1, 'one order-book read per round and never a retry');
    assert.deepEqual(env.auditStorage.entries().map((entry) => [entry.schemaVersion, entry.state, entry.reason]),
      [[2, 'BLOCKED', 'MARKET_QUOTE_UNAVAILABLE']]);
  }
  const rejected = await liveOnce({market: () => Promise.reject(new Error('assistant offline'))});
  assert.deepEqual(auditFacts(rejected), [{schemaVersion: 2, state: 'BLOCKED', reason: 'MARKET_QUOTE_UNAVAILABLE',
    upQuoteCents: 12, downQuoteCents: 88, marketUpAskCents: null, marketDownAskCents: null, marketQuoteObservedAt: null}]);
  const emptySide = await liveOnce({market: book({downAskCents: null})});
  assert.deepEqual(auditFacts(emptySide), [{schemaVersion: 2, state: 'BLOCKED', reason: 'MARKET_QUOTE_UNAVAILABLE',
    upQuoteCents: 12, downQuoteCents: 88, marketUpAskCents: 13, marketDownAskCents: null, marketQuoteObservedAt: now}]);

  // Age and clock boundaries are inclusive.
  for (const market of [book({observedAt: now - 2}), book({observedAt: now + 0.5}),
    book({serverTime: now + 3}), book({serverTime: now - 3}), book({upBidCents: null, downBidCents: null})]) {
    assertClicked(await liveOnce({market}));
  }
});

test('order-book failures retain only safe detail codes without changing the refusal or audit schema', async () => {
  for (const detail of ['HTTP_SOURCE_TIMEOUT', 'HTTP_SOURCE_UNAVAILABLE', 'LOCAL_QUOTE_TIMEOUT', 'LOCAL_QUOTE_NOT_FOUND',
    'INVALID_MARKET_QUOTE', 'CLOB_BOOKS_MISMATCH', 'CLOB_BOOK_TIME_INVALID', 'ROUND_CHANGED_DURING_READ',
    'INVALID_BOOK', 'INVALID_BOOK_LEVEL', 'WRONG_MARKET_PRICE_CONFIG', 'MARKET_NOT_UNIQUE',
    'WRONG_OR_INACTIVE_EVENT', 'WRONG_OR_INACTIVE_MARKET', 'WRONG_MARKET_PERIOD', 'INVALID_OUTCOME_TOKENS',
    'private network detail', '__proto__', undefined]) {
    const env = await liveOnce({market: () => Promise.reject(Object.assign(new Error('private network detail'), {detail}))});
    assertRefused(env, 'MARKET_QUOTE_UNAVAILABLE');
    assert.equal(env.watcher.status().detail, ['private network detail', '__proto__', undefined].includes(detail) ?
      'MARKET_QUOTE_UNAVAILABLE' : detail);
    assert.equal(env.marketReads.length, 1);
    assert.equal(Object.hasOwn(env.auditStorage.entries()[0], 'detail'), false);
    assert.equal(env.auditStorage.entries()[0].reason, 'MARKET_QUOTE_UNAVAILABLE');
  }
  for (const [market, detail] of [[book({observedAt: now - 2.01}), 'MARKET_QUOTE_STALE'],
    [book({downAskCents: null}), 'MARKET_QUOTE_EMPTY'], [book({upAskCents: null}), 'MARKET_QUOTE_EMPTY'],
    [book({schemaVersion: 2}), 'INVALID_MARKET_QUOTE'], [book({observedAt: now + 0.51}), 'INVALID_MARKET_QUOTE']]) {
    const env = await liveOnce({market});
    assertRefused(env, 'MARKET_QUOTE_UNAVAILABLE');
    assert.equal(env.watcher.status().detail, detail);
  }
});

test('the automatic buyer retains quote diagnostics after rearming and never retries the refused round', async () => {
  const env = setupAuto({market: () => Promise.reject(Object.assign(new Error('private network detail'), {detail: 'HTTP_SOURCE_TIMEOUT'}))});
  env.buyer.sync(true);
  env.setTime(now);
  env.setRead(() => ready());
  await env.tick();
  assert.equal(env.buyer.status().last.reason, 'MARKET_QUOTE_UNAVAILABLE');
  assert.equal(env.buyer.status().last.detail, 'HTTP_SOURCE_TIMEOUT');
  env.setTime(now + 1);
  assert.equal(env.buyer.sync(true).last.detail, 'HTTP_SOURCE_TIMEOUT');
  await env.tick();
  assert.equal(env.marketReads.length, 1);
  assert.equal(env.storage.values.size, 0);
  assertUnchangedTicket(env.ticket);
});

test('a flipped or tied CLOB favorite blocks with MARKET_QUOTE_MISMATCH, including the 2026-10-12 00:11 round', async () => {
  // Future showed Down 66 while the Polymarket book asked Down 37 / Up 64.
  const round = pricedRound(35, 66);
  const real = await liveOnce({read: round.read, ticket: round.ticket, market: book({upAskCents: 64, downAskCents: 37})});
  assertRefused(real, 'MARKET_QUOTE_MISMATCH');
  assert.deepEqual(auditFacts(real), [{schemaVersion: 2, state: 'BLOCKED', reason: 'MARKET_QUOTE_MISMATCH',
    upQuoteCents: 35, downQuoteCents: 66, marketUpAskCents: 64, marketDownAskCents: 37, marketQuoteObservedAt: now}]);
  for (const [roundQuotes, asks] of [[[35, 66], [66, 66]], [[35, 66], [66.01, 66]], [[66, 35], [37, 64]],
    [[66, 35], [66, 66]]]) {
    const priced = pricedRound(...roundQuotes);
    const env = await liveOnce({read: priced.read, ticket: priced.ticket,
      market: book({upAskCents: asks[0], downAskCents: asks[1]})});
    assertRefused(env, 'MARKET_QUOTE_MISMATCH');
  }
});

test('a price refusal preserves its READY round and the judged prices after rearming', async () => {
  const round = pricedRound(36, 65, {upQuote: '41¢', downQuote: '60¢'});
  const market = book({upAskCents: 37, downAskCents: 64});
  const env = setupAuto({ticket: round.ticket, market});
  env.buyer.sync(true);
  env.setTime(now);
  env.setRead(round.read);
  await env.tick();
  const refusal = env.buyer.status().last;
  assert.equal(refusal.reason, 'MARKET_QUOTE_MISMATCH');
  assert.equal(refusal.periodStart, start);
  assert.equal(refusal.side, 'Down');
  assert.equal(refusal.amountUsd, 1);
  assert.deepEqual(clone(refusal.priceCheck), {upQuoteCents: 41, downQuoteCents: 60,
    marketUpAskCents: 37, marketDownAskCents: 64});
  round.ticket.setQuotes('62¢', '39¢');
  env.setTime(now + 1);
  const rearmed = env.buyer.sync(true);
  assert.deepEqual(clone(rearmed.last), clone(refusal));
  await env.tick();
  assert.equal(env.marketReads.length, 1);
  assert.equal(env.storage.values.size, 0);
  assertUnchangedTicket(env.ticket);
});

test('the page button may differ from the CLOB ask of its side by at most 3 cents', async () => {
  for (const [ticketOptions, downAsk, expected] of [
    [{}, 62, 'MARKET_QUOTE_MISMATCH'], [{}, 70, 'MARKET_QUOTE_MISMATCH'], [{}, 63, null],
    [{downQuote: '61.01¢'}, 64.02, 'MARKET_QUOTE_MISMATCH'], [{downQuote: '61.01¢'}, 57.99, 'MARKET_QUOTE_MISMATCH'],
    // Float subtraction makes 64.01 - 61.01 exceed 3; the gate compares whole hundredths.
    [{downQuote: '61.01¢'}, 64.01, null],
  ]) {
    const round = pricedRound(35, ticketOptions.downQuote ? 62.01 : 66, ticketOptions);
    const env = await liveOnce({read: round.read, ticket: round.ticket, market: book({downAskCents: downAsk})});
    if (expected) assertRefused(env, expected);
    else assertClicked(env);
  }
});

test('page and CLOB prices allow exactly five cents above or below READY for either side', async () => {
  for (const side of ['Up', 'Down']) {
    for (const [page, ask, reason] of [
      [71, 71, null], [81, 81, null], [73, 71, null], [71, 73, null],
      [79, 81, null], [81, 79, null],
      [70.99, 73, 'PRICE_BELOW_MIN'], [73, 70.99, 'PRICE_BELOW_MIN'],
      [81.01, 79, 'PRICE_ABOVE_MAX'], [79, 81.01, 'PRICE_ABOVE_MAX'],
    ]) {
      const up = side === 'Up';
      const round = pricedRound(up ? 76 : 25, up ? 25 : 76,
        {[up ? 'upQuote' : 'downQuote']: `${page}¢`});
      const env = await liveOnce({read: round.read, ticket: round.ticket,
        market: book({[up ? 'upAskCents' : 'downAskCents']: ask})});
      if (reason) assertRefused(env, reason);
      else assertClicked(env);
    }
  }
  for (const cents of [67.01, 77.01]) {
    const round = pricedRound(28, 72.01, {downQuote: `${cents}¢`});
    assertClicked(await liveOnce({read: round.read, ticket: round.ticket,
      market: book({downAskCents: cents, upAskCents: 29, upBidCents: 28})}));
  }
});

test('neither the CLOB ask nor the page button may exceed the READY price by more than 5 cents', async () => {
  for (const [domDown, downAsk, expected] of [
    ['69¢', 71, null], ['71¢', 71, null], ['71¢', 69, null],
    ['69¢', 71.01, 'PRICE_ABOVE_MAX'], ['69¢', 72, 'PRICE_ABOVE_MAX'],
    ['72¢', 71, 'PRICE_ABOVE_MAX'], ['71.01¢', 69, 'PRICE_ABOVE_MAX'],
  ]) {
    const round = pricedRound(35, 66, {downQuote: domDown});
    const env = await liveOnce({read: round.read, ticket: round.ticket, market: book({downAskCents: downAsk})});
    if (expected) assertRefused(env, expected);
    else assertClicked(env);
  }
  const up = pricedRound(66, 35, {upQuote: '69¢'});
  const above = await liveOnce({read: up.read, ticket: up.ticket, market: book({upAskCents: 72})});
  assertRefused(above, 'PRICE_ABOVE_MAX');
  assert.deepEqual(auditFacts(above), [{schemaVersion: 2, state: 'BLOCKED', reason: 'PRICE_ABOVE_MAX',
    upQuoteCents: 69, downQuoteCents: 35, marketUpAskCents: 72, marketDownAskCents: 35, marketQuoteObservedAt: now}]);
  const decimal = pricedRound(35, 62.01, {downQuote: '67.01¢'});
  assertClicked(await liveOnce({read: decimal.read, ticket: decimal.ticket, market: book({downAskCents: 67.01})}));
});

test('page or CLOB prices more than five cents below READY refuse without consuming the round', async () => {
  for (const side of ['Up', 'Down']) {
    for (const [page, ask] of [[70.99, 73], [73, 70.99]]) {
      const up = side === 'Up';
      const round = pricedRound(up ? 76 : 25, up ? 25 : 76,
        {[up ? 'upQuote' : 'downQuote']: `${page}¢`});
      const env = await liveOnce({read: round.read, ticket: round.ticket,
        market: book({[up ? 'upAskCents' : 'downAskCents']: ask})});
      assertRefused(env, 'PRICE_BELOW_MIN');
      assert.equal(env.auditStorage.entries()[0].reason, 'PRICE_BELOW_MIN');
      await env.watcher.poll();
      assert.equal(env.marketReads.length, 1, 'a refused round is not retried');
    }
  }
});

test('a page button or CLOB ask below 60 cents at click time blocks a READY favorite of at least 60', async () => {
  for (const [domDown, downAsk] of [['58¢', 60], ['61¢', 59], ['59.99¢', 61]]) {
    const round = pricedRound(35, 61, {downQuote: domDown});
    const env = await liveOnce({read: round.read, ticket: round.ticket, market: book({downAskCents: downAsk})});
    assertRefused(env, 'PRICE_BELOW_MIN');
    assert.equal(env.marketReads.length, 1);
    assert.deepEqual(auditFacts(env), [{schemaVersion: 2, state: 'BLOCKED', reason: 'PRICE_BELOW_MIN',
      upQuoteCents: 35, downQuoteCents: Number(domDown.slice(0, -1)), marketUpAskCents: 40,
      marketDownAskCents: downAsk, marketQuoteObservedAt: now}]);
  }
});

test('a page change during the order-book read is checked again before the gates and the marker', async () => {
  for (const [change, reason] of [
    [(env) => env.ticket.setQuotes('35¢', '72¢'), 'PRICE_ABOVE_MAX'],
    [(env) => env.ticket.setQuotes('35¢', '62¢'), 'MARKET_QUOTE_MISMATCH'],
    [(env) => env.ticket.setQuotes('35¢', '59¢'), 'MARKET_QUOTE_MISMATCH'],
    [(env) => env.ticket.setQuotes('70¢', '35¢'), 'TICKET_CHANGED'],
    [(env) => env.ticket.setAmount('2'), 'TICKET_CHANGED'],
    // The core rejects a moved page as a market mismatch, which the watcher reports as READ_FAILED.
    [(env) => env.setUrl(`https://future.news/zh/event/btc-updown-5m-${start - 300}`), 'READ_FAILED'],
  ]) {
    const round = pricedRound(35, 66);
    let env;
    env = setup({read: round.read, ticket: round.ticket, market: ({record, time}) => {
      change(env);
      return clobQuote(record, time, reason === 'PRICE_ABOVE_MAX' ? {downAskCents: 69} : {});
    }});
    env.watcher.start({live: true});
    await env.watcher.poll();
    assertRefused(env, reason);
    assert.equal(env.marketReads.length, 1);
  }
  const round = pricedRound(35, 66);
  let env;
  env = setup({read: round.read, ticket: round.ticket, market: ({record, time}) => {
    env.ticket.setQuotes('35¢', '72¢');
    return clobQuote(record, time, {downAskCents: 69});
  }});
  env.watcher.start({live: true});
  await env.watcher.poll();
  assert.deepEqual(auditFacts(env), [{schemaVersion: 2, state: 'BLOCKED', reason: 'PRICE_ABOVE_MAX',
    upQuoteCents: 35, downQuoteCents: 72, marketUpAskCents: 35, marketDownAskCents: 69, marketQuoteObservedAt: now}],
  'the refusal records the page re-read after the order book, not the earlier check');
});

test('stop while the order-book read is pending forbids the click', async () => {
  for (const settle of ['resolve', 'reject']) {
    const wait = deferred();
    const entered = deferred();
    let fail;
    const env = setup({market: () => {
      entered.resolve();
      return new Promise((resolve, reject) => {fail = reject; wait.promise.then(resolve);});
    }});
    env.watcher.start({live: true});
    const poll = env.watcher.poll();
    await entered.promise;
    env.watcher.stop();
    if (settle === 'resolve') wait.resolve(clobQuote(ready().preparation.lastAttempt, now));
    else fail(new Error('assistant offline'));
    await poll;
    assert.equal(env.watcher.status().state, 'STOPPED');
    assert.equal(env.intervals.size, 0);
    assert.equal(env.storage.values.size, 0);
    assert.deepEqual(env.auditStorage.entries(), []);
    assertUnchangedTicket(env.ticket);
  }
});

test('a price move or stale order book after the marker fails the final check, consumed and unclicked', async () => {
  for (const [change, downQuoteCents, downAskCents] of [
    [(env) => env.ticket.setQuotes('35¢', '72¢'), 72, 69],
    [(env) => env.ticket.setQuotes('35¢', '60.99¢'), 60.99, 63.99],
    [(env) => env.ticket.setQuotes('35¢', '62.5¢'), 62.5, 66],
    [(env) => env.setTime(now + 2.01), 66, 66],
  ]) {
    const round = pricedRound(35, 66);
    let env;
    const storage = memoryStorage(new Map(), {afterWrite() {change(env);}});
    env = setup({read: round.read, ticket: round.ticket, storage, market: book({downAskCents})});
    env.watcher.start({live: true});
    await env.watcher.poll();
    assert.equal(env.watcher.status().state, 'BLOCKED');
    assert.equal(env.watcher.status().reason, 'FINAL_CHECK_FAILED');
    assert.equal(JSON.parse(storage.values.get(storageKey)).state, 'CLICK_ATTEMPTED', 'the round stays consumed');
    assert.throws(() => env.watcher.start({live: true}), /CONSUMED/);
    assertUnchangedTicket(env.ticket);
    assert.deepEqual(auditFacts(env), [{schemaVersion: 2, state: 'BLOCKED', reason: 'FINAL_CHECK_FAILED',
      upQuoteCents: 35, downQuoteCents, marketUpAskCents: 35, marketDownAskCents: downAskCents, marketQuoteObservedAt: now}]);
  }
});

test('a dry run reports DRY_RUN_READY only when the price gates pass', async () => {
  const round = pricedRound(35, 66);
  for (const [market, reason, downQuote = '66¢'] of [
    [book({upAskCents: 64, downAskCents: 37}), 'MARKET_QUOTE_MISMATCH'],
    [book({downAskCents: 72}), 'PRICE_ABOVE_MAX', '69¢'],
    [book({downAskCents: 59}), 'MARKET_QUOTE_MISMATCH'],
    [book({observedAt: now - 3}), 'MARKET_QUOTE_UNAVAILABLE'],
    [() => Promise.reject(new Error('assistant offline')), 'MARKET_QUOTE_UNAVAILABLE'],
  ]) {
    const env = setup({read: round.read, ticket: ticketFixture({side: 'Down', upQuote: '35¢', downQuote}), market});
    env.watcher.start();
    await env.watcher.poll();
    assertRefused(env, reason);
    assert.equal(env.marketReads.length, 1);
    assert.deepEqual(env.auditStorage.entries(), []);
  }
  const env = setup({read: round.read, ticket: ticketFixture({side: 'Down', upQuote: '35¢', downQuote: '66¢'})});
  env.watcher.start();
  await env.watcher.poll();
  assert.equal(env.watcher.status().state, 'DRY_RUN_READY');
  assert.equal(env.marketReads.length, 1);
  assertUnchangedTicket(env.ticket);
});

test('every audit is schema 2 and carries the CLOB asks only once a valid order book was read', async () => {
  const changed = await liveOnce({ticket: ticketFixture({buyDisabled: true})});
  assert.equal(changed.marketReads.length, 0);
  assert.deepEqual(auditFacts(changed), [{schemaVersion: 2, state: 'BLOCKED', reason: 'TICKET_CHANGED',
    upQuoteCents: null, downQuoteCents: null, marketUpAskCents: null, marketDownAskCents: null, marketQuoteObservedAt: null}]);
  const consumed = await liveOnce({storage: memoryStorage(new Map([[storageKey, JSON.stringify({schemaVersion: 1,
    periodStart: start, id: `future-btc5m-prepare:${start}`, side: 'Down', amountUsd: 1, state: 'CLICK_ATTEMPTED'})]]))});
  assert.deepEqual(auditFacts(consumed), [{schemaVersion: 2, state: 'BLOCKED', reason: 'ALREADY_CONSUMED',
    upQuoteCents: null, downQuoteCents: null, marketUpAskCents: 13, marketDownAskCents: 88, marketQuoteObservedAt: now}]);
  const clicked = await liveOnce({market: book({downAskCents: 89.5, observedAt: now - 1.25})});
  assertClicked(clicked);
  assert.deepEqual(auditFacts(clicked), [{schemaVersion: 2, state: 'CLICK_ATTEMPTED', reason: 'PLATFORM_RESULT_UNKNOWN',
    upQuoteCents: 12, downQuoteCents: 88, marketUpAskCents: 13, marketDownAskCents: 89.5, marketQuoteObservedAt: now - 1.25}]);
});

test('the auto buyer re-arms after a price-gate refusal and never retries that round', async () => {
  for (const [quotes, market, reason] of [
    [[35, 66], book({upAskCents: 64, downAskCents: 37}), 'MARKET_QUOTE_MISMATCH'],
    [[45, 56], book({}), 'PRICE_BELOW_MIN'],
  ]) {
    const round = pricedRound(...quotes);
    const env = setupAuto({ticket: round.ticket, market});
    env.buyer.sync(true);
    env.setTime(now);
    env.setRead(round.read);
    await env.tick();
    assert.equal(env.buyer.status().state, 'PAUSED');
    assert.equal(env.buyer.status().last.state, 'BLOCKED');
    assert.equal(env.buyer.status().last.reason, reason);
    const marketReads = env.marketReads.length;
    assertUnchangedTicket(env.ticket);

    // Re-armed: the refused READY predates arming, so even a consistent book never retries it.
    env.setMarket(book({}));
    env.setTime(now + 1);
    assert.equal(env.buyer.sync(true).state, 'WATCHING');
    await env.tick();
    await env.tick();
    assert.equal(env.buyer.sync(true).state, 'WATCHING');
    assert.equal(env.marketReads.length, marketReads);
    assert.equal(env.storage.values.size, 0);
    assertUnchangedTicket(env.ticket);

    const next = start + 300;
    env.setTime(next + 65);
    env.setUrl(`https://future.news/zh/event/btc-updown-5m-${next}`);
    env.ticket.setTitle('Bitcoin Up or Down - October 10, 12:50PM-12:55PM ET');
    env.ticket.setQuotes('12¢', '88¢');
    env.setRead(() => ready(next + 65, 'Down', next));
    await env.tick();
    assert.equal(env.buyer.sync(true).last.state, 'CLICK_ATTEMPTED');
    assert.equal(JSON.parse(env.storage.values.get(storageKey)).periodStart, next);
    assertUnchangedTicket(env.ticket, 1);
  }
});

test('the default order-book read sends a bare typed worker message and fails closed', async () => {
  const sent = [];
  let reply = null;
  const chrome = {runtime: {lastError: undefined, sendMessage(message, callback) {
    sent.push(message);
    const [lastError, value] = reply;
    chrome.runtime.lastError = lastError;
    callback(value);
    chrome.runtime.lastError = undefined;
  }}};
  const isolated = vm.createContext({URL, Event, chrome});
  vm.runInContext(source, isolated);
  const snapshot = clobQuote(ready().preparation.lastAttempt, now);
  for (const [answer, expected, detail] of [
    [[undefined, {ok: true, status: snapshot}], 'DRY_RUN_READY', null],
    [[{message: 'Receiving end does not exist.'}, {ok: true, status: snapshot, errorCode: 'HTTP_SOURCE_TIMEOUT'}],
      'MARKET_QUOTE_UNAVAILABLE', 'MARKET_QUOTE_UNAVAILABLE'],
    [[undefined, {ok: false, error: '本地盘口服务未确认'}], 'MARKET_QUOTE_UNAVAILABLE', 'MARKET_QUOTE_UNAVAILABLE'],
    [[undefined, {ok: false, errorCode: 'HTTP_SOURCE_TIMEOUT'}], 'MARKET_QUOTE_UNAVAILABLE', 'HTTP_SOURCE_TIMEOUT'],
    [[undefined, {ok: false, errorCode: 'private network detail'}], 'MARKET_QUOTE_UNAVAILABLE', 'MARKET_QUOTE_UNAVAILABLE'],
    [[undefined, {ok: true}], 'MARKET_QUOTE_UNAVAILABLE', 'MARKET_QUOTE_UNAVAILABLE'],
    [[undefined, undefined], 'MARKET_QUOTE_UNAVAILABLE', 'MARKET_QUOTE_UNAVAILABLE'],
  ]) {
    reply = answer;
    const ticket = ticketFixture();
    const watcher = isolated.FutureBtc5mBuyOnce.createWatcher({core, document: ticket.doc, readUrl: () => marketUrl,
      readPreparation: async () => ready(), nowFn: () => now, setIntervalFn: () => 1, clearIntervalFn() {}});
    watcher.start();
    await watcher.poll();
    assert.equal(watcher.status().state, expected === 'DRY_RUN_READY' ? expected : 'BLOCKED');
    if (expected !== 'DRY_RUN_READY') assert.equal(watcher.status().reason, expected);
    assert.equal(watcher.status().detail, detail);
    assertUnchangedTicket(ticket);
  }
  assert.deepEqual(sent.map(clone), Array(7).fill({type: 'FUTURE_BTC5M_MARKET_QUOTE'}));
});

test('a switch-off or STOP during the order-book read refuses before the round is marked', async () => {
  const env = setup({read: (n) => {
    const value = ready();
    if (n >= 3) value.preparation = {...value.preparation, enabled: false, state: 'DISABLED'};
    return value;
  }});
  env.watcher.start({live: true});
  await env.watcher.poll();
  assert.equal(env.watcher.status().state, 'BLOCKED');
  assert.equal(env.watcher.status().reason, 'READY_CHANGED');
  assert.equal(env.marketReads.length, 1);
  assert.equal(env.storage.values.size, 0, 'the round is not consumed');
  assertUnchangedTicket(env.ticket);
});

test('a READY that ages out of its 5 s sample window during the order-book read is refused unmarked', async () => {
  let env;
  env = setup({read: (n) => {
    if (n === 3) env.setTime(now + 5.01);
    return ready();
  }});
  env.watcher.start({live: true});
  await env.watcher.poll();
  assert.equal(env.watcher.status().reason, 'READY_CHANGED');
  assert.equal(env.storage.values.size, 0);
  assertUnchangedTicket(env.ticket);
});

test('an absolute 97¢ ceiling refuses near-certain favorites whatever the READY price', async () => {
  const high = (cents) => () => {
    const value = ready();
    Object.assign(value.preparation.lastAttempt, {downQuoteCents: cents, upQuoteCents: 100 - cents + 1});
    return value;
  };
  const early = setup({read: high(98), ticket: ticketFixture({upQuote: '3¢', downQuote: '98¢'})});
  early.watcher.start({live: true});
  await early.watcher.poll();
  assert.equal(early.watcher.status().reason, 'PRICE_ABOVE_MAX');
  assert.equal(early.marketReads.length, 0, 'no order-book read above the ceiling');
  assertUnchangedTicket(early.ticket);
  for (const [dom, ask] of [['97.5¢', 96], ['96¢', 97.5]]) {
    const env = setup({read: high(96), ticket: ticketFixture({upQuote: '5¢', downQuote: dom}),
      market: ({record, time}) => ({...clobQuote(record, time), downAskCents: ask})});
    env.watcher.start({live: true});
    await env.watcher.poll();
    assert.equal(env.watcher.status().reason, 'PRICE_ABOVE_MAX', `${dom} / ${ask}`);
    assertUnchangedTicket(env.ticket);
  }
  const ok = setup({read: high(97), ticket: ticketFixture({upQuote: '4¢', downQuote: '97¢'})});
  ok.watcher.start({live: true});
  await ok.watcher.poll();
  assert.equal(ok.watcher.status().state, 'CLICK_ATTEMPTED', 'exactly 97¢ is allowed');
});

// Readback is separate from the click marker, the ticket and the attempt audit.
const positionSnapshot = (positions = [], round = start, side = 'Down') => ({periodStart: round, side, positions});
const position = {shares: 1.51, avgPriceCents: 66, costUsd: 1};
async function attemptWithPosition(options = {}) {
  const env = setupAuto(options);
  env.buyer.sync(true);
  env.setTime(now);
  env.setRead(() => ready());
  await env.tick();
  return env;
}

test('a newly appearing $1 position confirms shares and average without another Buy or fill audit', async () => {
  let snapshot = positionSnapshot();
  const env = await attemptWithPosition({positionReader: () => snapshot});
  assert.equal(env.buyer.status().last.fill, null);
  snapshot = positionSnapshot([position]);
  env.setTime(now + 24);
  const confirmed = env.buyer.status().last;
  assert.deepEqual(clone(confirmed.fill), {source: 'FUTURE_POSITION_PAGE', shares: 1.51, avgPriceCents: 66, confirmedAt: now + 24});
  assert.equal(confirmed.state, 'CLICK_ATTEMPTED', 'the platform readback does not rewrite the click fact');
  assert.equal('platformOrderId' in confirmed, false);
  for (let i = 0; i < 3; i++) { env.buyer.sync(true); await env.tick(); }
  assertUnchangedTicket(env.ticket, 1);
  assert.equal(JSON.parse(env.storage.values.get(storageKey)).state, 'CLICK_ATTEMPTED');
  const audits = env.auditStorage.entries();
  assert.equal(audits.every((entry) => ['CLICK_ATTEMPTED', 'BLOCKED'].includes(entry.state)), true);
  assert.equal(env.buyer.sync(false).last.fill.avgPriceCents, 66);
});

test('pre-existing or unreadable positions never confirm this click, even when the record later changes', async () => {
  for (const initial of [null, positionSnapshot([position])]) {
    let snapshot = initial;
    const env = await attemptWithPosition({positionReader: () => snapshot});
    snapshot = positionSnapshot([{...position, shares: 3.02, costUsd: 2}]);
    env.setTime(now + 1);
    assert.equal(env.buyer.sync(true).last.fill, null);
    snapshot = positionSnapshot([position]);
    assert.equal(env.buyer.status().last.fill, null);
    await env.tick();
    assertUnchangedTicket(env.ticket, 1);
  }
});

test('wrong round, side, partial amount, duplicate rows and invalid prices stay unconfirmed without retry', async () => {
  const bad = [null, positionSnapshot(), positionSnapshot([position], start - 300),
    positionSnapshot([position], start, 'Up'), positionSnapshot([position, position]),
    positionSnapshot([{...position, costUsd: 0.5}]), positionSnapshot([{...position, costUsd: 2}]),
    positionSnapshot([{...position, shares: 0}]), positionSnapshot([{...position, shares: NaN}]),
    positionSnapshot([{...position, avgPriceCents: 0}]), positionSnapshot([{...position, avgPriceCents: 101}]),
    positionSnapshot([{...position, avgPriceCents: 99}])];
  for (const invalid of bad) {
    let snapshot = positionSnapshot();
    const env = await attemptWithPosition({positionReader: () => snapshot});
    snapshot = invalid;
    env.setTime(now + 1);
    assert.equal(env.buyer.sync(true).last.fill, null);
    await env.tick();
    assertUnchangedTicket(env.ticket, 1);
  }
});

test('readback errors, a changed page or backwards clock retain the consumed round', async () => {
  let error = false, snapshot = positionSnapshot();
  const env = await attemptWithPosition({positionReader: () => { if (error) throw new Error('page rerender'); return snapshot; }});
  snapshot = positionSnapshot([position]);
  error = true;
  assert.equal(env.buyer.status().last.fill, null);
  error = false;
  env.setUrl(`https://future.news/zh/event/btc-updown-5m-${start + 300}`);
  assert.equal(env.buyer.status().last.fill, null);
  env.setUrl(marketUrl);
  env.setTime(now - 1);
  assert.equal(env.buyer.status().last.fill, null);
  env.setTime(now + 1);
  assert.equal(env.buyer.status().last.fill.shares, 1.51);
  assertUnchangedTicket(env.ticket, 1);
});

test('pending readback and confirmed receipt survive reload without clearing the click marker', async () => {
  let snapshot = positionSnapshot();
  const env = await attemptWithPosition({positionReader: () => snapshot});
  const restored = setupAuto({storage: env.storage, resultStorage: env.resultStorage, positionReader: () => snapshot});
  restored.setTime(now + 1);
  restored.setRead(() => ready(now + 1));
  restored.buyer.sync(true);
  await restored.tick();
  assert.equal(restored.buyer.status().last.state, 'CLICK_ATTEMPTED');
  assert.equal(restored.buyer.status().last.fill, null);
  snapshot = positionSnapshot([position]);
  restored.setTime(now + 24);
  assert.equal(restored.buyer.status().last.fill.shares, 1.51);
  const again = setupAuto({storage: env.storage, resultStorage: env.resultStorage});
  again.setTime(start + 301);
  assert.equal(again.buyer.status().last.fill.avgPriceCents, 66);
  assertUnchangedTicket(env.ticket, 1);
  assertUnchangedTicket(restored.ticket);
  assertUnchangedTicket(again.ticket);
});

test('result storage failure and click exceptions never permit a second attempt', async () => {
  for (const options of [{resultStorage: resultMemory(new Map(), {failWrite: true})},
    {ticket: ticketFixture({beforeBuy() {throw new Error('unknown click');}})}]) {
    let snapshot = positionSnapshot();
    const env = await attemptWithPosition({...options, positionReader: () => snapshot});
    snapshot = positionSnapshot([position]);
    env.setTime(now + 1);
    const view = env.buyer.sync(false);
    if (options.ticket) assert.equal(view.last.fill, null);
    else assert.equal(view.last.fill.shares, 1.51, 'memory readback remains usable if saving it failed');
    env.buyer.sync(true);
    await env.tick();
    assertUnchangedTicket(env.ticket, 1);
    assert.equal(JSON.parse(env.storage.values.get(storageKey)).state, 'CLICK_ATTEMPTED');
  }
});

test('malformed stored readback is ignored without touching the consumption key', () => {
  for (const raw of ['invalid-json', '{}', JSON.stringify({schemaVersion: 1, periodStart: start,
    side: 'Down', amountUsd: 2, state: 'CLICK_ATTEMPTED', reason: 'PLATFORM_RESULT_UNKNOWN',
    attemptedAt: now, baselineEmpty: true, fill: null})]) {
    const resultStorage = resultMemory(new Map([[resultKey, raw]]));
    const env = setupAuto({resultStorage});
    assert.equal(env.buyer.status().last, null);
    assert.equal(resultStorage.values.get(resultKey), raw);
    assert.equal(env.storage.values.size, 0);
    assertUnchangedTicket(env.ticket);
  }
});

test('Up confirmation uses the prepared Up side and preserves confirmed history across the next round', async () => {
  let snapshot = positionSnapshot([], start, 'Up');
  const env = setupAuto({ticket: ticketFixture({side: 'Up'}), positionReader: () => snapshot});
  env.buyer.sync(true);
  env.setTime(now);
  env.setRead(() => ready(now, 'Up'));
  await env.tick();
  snapshot = positionSnapshot([{shares: 1.14, avgPriceCents: 88, costUsd: 1}], start, 'Up');
  env.setTime(now + 1);
  assert.equal(env.buyer.status().last.fill.avgPriceCents, 88);
  env.buyer.sync(false);
  env.setTime(start + 301);
  env.setUrl(`https://future.news/zh/event/btc-updown-5m-${start + 300}`);
  const history = env.buyer.status().last;
  assert.equal(history.periodStart, start);
  assert.equal(history.side, 'Up');
  assert.equal(history.fill.shares, 1.14);
  assertUnchangedTicket(env.ticket, 1);
});
