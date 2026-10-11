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
const setup = ({ticket = ticketFixture(), storage = memoryStorage(), read = () => ready(),
  time = now, withLock = mutex(), url = marketUrl} = {}) => {
  let currentTime = time;
  let currentUrl = url;
  const intervals = new Map();
  const reads = [];
  const watcher = createWatcher({core, document: ticket.doc, readUrl: () => currentUrl,
    storage, readPreparation: async () => {reads.push(currentTime); return read(reads.length);},
    nowFn: () => currentTime, withLock,
    setIntervalFn(callback) {const id = intervals.size + 1; intervals.set(id, callback); return id;},
    clearIntervalFn(id) {intervals.delete(id);}});
  return {watcher, ticket, storage, intervals, reads,
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
    assert.equal(env.reads.length, 2, 're-read READY inside the origin lock before clicking');
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
  read = () => waiting(start + 30)} = {}) => {
  let currentTime = start + 30;
  let currentUrl = marketUrl;
  let currentRead = read;
  let nextId = 0;
  const intervals = new Map();
  const reads = [];
  const buyer = createAutoBuyer({core, document: ticket.doc, readUrl: () => currentUrl, storage,
    readPreparation: async () => {reads.push(currentTime); return currentRead(reads.length);},
    nowFn: () => currentTime, withLock,
    setIntervalFn(callback) {intervals.set(++nextId, callback); return nextId;},
    clearIntervalFn(id) {intervals.delete(id);}});
  return {buyer, ticket, storage, intervals, reads,
    setTime(value) {currentTime = value;}, setUrl(value) {currentUrl = value;}, setRead(value) {currentRead = value;},
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
