import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const content = readFileSync(new URL('./future-btc5m-extension/content.js', import.meta.url), 'utf8');
const context = vm.createContext({URL, Event});
vm.runInContext(content, context);
const {usableDraft, matchesMarket, prepareAmount, observationView, navigationTarget, followCurrentMarket, readPreflight} = context.FutureBtc5m;
const start = 1791650700;
const now = start + 65;
const draft = {
  slug: `btc-updown-5m-${start}`, series: '5m', period_start: start, period_end: start + 300,
  side: 'Up', token_id: 'up-token', condition_id: 'condition', amount_usd: 1,
  price_source: 'chainlink', price_observed_at: start + 60, created_at: start + 60,
  open_price_source: 'polymarket_crypto_price_fiveminute_twap60_openPrice', twap_lookback_seconds: 60,
  expires_at: start + 80, trade_ready: true, manual_submit_required: true,
  platform_amount_validation_required: true,
};
const status = {schema_version: 1, mode: 'ASSIST_ONLY', live_enabled: false, amount_usd: 1,
  status: 'READY', feed_status: 'CURRENT', geoblock: {blocked: false,
    source_url: 'https://polymarket.com/api/geoblock'}, server_time: now, draft,
  future_eligibility: {status: 'VERIFIED', venue: 'future.news', operation: 'PREPARE_USD_BUY_AMOUNT',
    source_url: 'https://future.news/test-fixture-eligibility'}};

test('Polymarket IP eligibility alone cannot authorize Future amount preparation', () => {
  for (const eligibility of [undefined, null,
    {...status.future_eligibility, status: 'UNKNOWN', source_url: null},
    {...status.future_eligibility, status: 'RESTRICTED'},
    {...status.future_eligibility, venue: 'polymarket.com'},
    {...status.future_eligibility, operation: 'SUBMIT_ORDER'},
    {...status.future_eligibility, source_url: 'https://polymarket.com/api/geoblock'},
    {...status.future_eligibility, source_url: 'https://future.news.evil.test/eligibility'},
    {...status.future_eligibility, source_url: 'http://future.news/eligibility'},
    {...status.future_eligibility, source_url: 'https://future.news/'},
    {...status.future_eligibility, source_url: 'https://user:secret@future.news/eligibility'},
  ]) assert.equal(usableDraft({...status, future_eligibility: eligibility}, now), null);
  assert.equal(usableDraft({...status, geoblock: {blocked: false}}, now), null);
});

test('only fresh, exact BTC5m $1 drafts can be prepared', () => {
  assert.equal(usableDraft(status, now), draft);
  for (const change of [{amount_usd: 2}, {series: '15m'}, {side: 'Yes'}, {expires_at: start + 90},
    {created_at: start + 59}, {price_observed_at: start + 54}, {manual_submit_required: false}]) {
    assert.equal(usableDraft({...status, draft: {...draft, ...change}}, now), null);
  }
  for (const change of [{live_enabled: true}, {status: 'STOPPED'}, {draft: null},
    {feed_status: 'UNAVAILABLE'}, {geoblock: {blocked: true}}, {geoblock: {blocked: null}}, {server_time: now - 4}]) {
    assert.equal(usableDraft({...status, ...change}, now), null);
  }
  assert.equal(usableDraft({...status, server_time: start + 81}, start + 81), null);
});

test('preparation requires the verified 60-second TWAP opening source and window', () => {
  for (const change of [
    {open_price_source: 'polymarket_crypto_price_fiveminute_openPrice'},
    {open_price_source: undefined}, {twap_lookback_seconds: undefined}, {twap_lookback_seconds: 30},
  ]) assert.equal(usableDraft({...status, draft: {...draft, ...change}}, now), null);
});

test('a different round, series or origin cannot receive the amount', () => {
  assert.equal(matchesMarket(`https://future.news/zh/event/${draft.slug}?m=condition`, draft), true);
  assert.equal(matchesMarket(`https://future.news/event/${draft.slug}`, draft), true);
  for (const url of ['https://future.news/zh/updown', `https://future.news/zh/event/btc-updown-5m-${start + 300}`,
    `https://future.news.evil.test/zh/event/${draft.slug}`]) assert.equal(matchesMarket(url, draft), false);
});

const signal = {...draft, open_price: 82980.01, current_price: 82981.98};
const observing = {...status, status: 'OBSERVING', reason: 'GEOBLOCK_BLOCKED',
  geoblock: {blocked: true}, draft: null, period_start: start, signal,
  future_eligibility: {status: 'UNKNOWN', venue: 'future.news', operation: 'PREPARE_USD_BUY_AMOUNT', source_url: null}};
const marketUrl = `https://future.news/zh/event/${draft.slug}`;

function navigationFixture({buttons = ['前往实时市场'], hidden = false, disabled = false, storageError = false} = {}) {
  let clicks = 0;
  const values = new Map();
  const doc = {querySelectorAll: () => buttons.map((textContent) => ({textContent, disabled,
    getClientRects: () => hidden ? [] : [1], click() { clicks++; }}))};
  const storage = {getItem(key) { if (storageError) throw new Error('storage blocked'); return values.get(key) || null; },
    setItem(key, value) { if (storageError) throw new Error('storage blocked'); values.set(key, value); }};
  return {doc, storage, clicks: () => clicks};
}

test('ended BTC5m pages get only the current validated public navigation target', () => {
  const oldUrl = `https://future.news/zh/event/btc-updown-5m-${start - 300}`;
  assert.equal(navigationTarget(observing, oldUrl, now), marketUrl);
  assert.equal(navigationTarget(observing, marketUrl, now), marketUrl);
  for (const url of ['https://future.news/zh/updown',
    `https://future.news/zh/event/eth-updown-5m-${start - 300}`,
    `https://future.news/zh/event/btc-updown-15m-${start - 300}`,
    `https://future.news/zh/event/btc-updown-5m-${start - 299}`,
    `https://future.news/zh/event/btc-updown-5m-${start + 300}`,
    `https://future.news.evil.test/zh/event/btc-updown-5m-${start - 300}`]) {
    assert.equal(navigationTarget(observing, url, now), null);
  }
  for (const change of [{status: 'STOPPED'}, {status: 'OFFLINE'}, {status: 'BOGUS'},
    {mode: 'LIVE'}, {live_enabled: true}, {amount_usd: 2}, {schema_version: 2},
    {server_time: now - 4}, {period_start: start - 300}, {period_start: undefined}]) {
    assert.equal(navigationTarget({...observing, ...change}, oldUrl, now), null);
  }
});

test('navigation clicks once per target round across reloads and verifies arrival', () => {
  const fixture = navigationFixture({buttons: ['买入 涨', '前往实时市场', '跌 37¢']});
  const oldUrl = `https://future.news/zh/event/btc-updown-5m-${start - 300}`;
  assert.match(followCurrentMarket(observing, oldUrl, fixture.doc, fixture.storage, now), /正在前往/);
  assert.equal(fixture.clicks(), 1);
  assert.match(followCurrentMarket(observing, oldUrl, fixture.doc, fixture.storage, now + 1), /正在前往/);
  assert.equal(fixture.clicks(), 1);
  assert.match(followCurrentMarket({...observing, server_time: now + 10}, oldUrl,
    fixture.doc, fixture.storage, now + 10), /跳转未完成/);
  assert.equal(fixture.clicks(), 1);
  assert.match(followCurrentMarket(observing, marketUrl, fixture.doc, fixture.storage, now), /已进入本轮/);
  assert.equal(fixture.clicks(), 1);
  const next = {...observing, period_start: start + 300, server_time: start + 301};
  assert.match(followCurrentMarket(next, marketUrl, fixture.doc, fixture.storage, start + 301), /正在前往/);
  assert.equal(fixture.clicks(), 2);
});

test('navigation never clicks hidden, disabled, ambiguous or financial controls', () => {
  const oldUrl = `https://future.news/zh/event/btc-updown-5m-${start - 300}`;
  for (const options of [{buttons: []}, {buttons: ['买入 涨']}, {hidden: true}, {disabled: true},
    {buttons: ['前往实时市场', '前往实时市场']}, {storageError: true}]) {
    const fixture = navigationFixture(options);
    assert.match(followCurrentMarket(observing, oldUrl, fixture.doc, fixture.storage, now), /等待|失败/);
    assert.equal(fixture.clicks(), 0);
  }
  const fixture = navigationFixture();
  assert.match(followCurrentMarket({...observing, status: 'STOPPED'}, oldUrl,
    fixture.doc, fixture.storage, now), /暂停/);
  assert.equal(fixture.clicks(), 0);
});

async function renderedPanel(value, url, time, ticketDoc, runtime = {}) {
  const body = ticketDoc?.body || {};
  body.append = function(panel) { this.panel = panel; };
  const document = Object.assign(ticketDoc || {}, {body, createElement: () => ({style: {}, children: [], listeners: {},
    append(...children) { this.children.push(...children); },
    addEventListener(type, listener) { this.listeners[type] = listener; }})});
  if (!document.querySelectorAll) document.querySelectorAll = () => [];
  let interval;
  class Clock extends Date { static now() { return (runtime.now ? runtime.now() : time) * 1000; } }
  vm.runInNewContext(content, {URL, Event, Date: Clock, document, location: runtime.location || {href: url},
    sessionStorage: runtime.storage || navigationFixture().storage,
    setInterval(listener) { interval = listener; }, chrome: {runtime: {sendMessage: async (message) => {
      runtime.messages?.push(message);
      return runtime.reply ? runtime.reply(message) : ({ok: true, status: value});
    }}}});
  await new Promise((resolve) => setImmediate(resolve));
  body.panel.children.poll = async () => {
    interval();
    await new Promise((resolve) => setImmediate(resolve));
  };
  return body.panel.children;
}

test('the rendered panel rejects another page round and stale samples', async () => {
  const wrongPage = await renderedPanel(observing,
    `https://future.news/zh/event/btc-updown-5m-${start - 300}`, now);
  assert.match(wrongPage[1].textContent, /页面轮次不匹配/);
  assert.doesNotMatch(wrongPage[1].textContent, /观察方向 Up|本轮采样方向/);
  assert.equal(wrongPage[2].href, marketUrl);
  assert.equal(wrongPage[3].disabled, true);
  const stale = await renderedPanel({...observing, server_time: now + 1}, marketUrl, now + 1);
  assert.match(stale[1].textContent, /采样已陈旧/);
  assert.doesNotMatch(stale[1].textContent, /观察方向 Up|本轮采样方向/);
});

test('only a fresh draft on its own market enables the preparation control', async () => {
  const fresh = await renderedPanel({...status, signal, period_start: start}, marketUrl, now);
  assert.match(fresh[1].textContent, /本轮采样方向：涨 Up/);
  assert.equal(fresh[3].disabled, false);
  const expired = await renderedPanel({...status, signal, period_start: start,
    server_time: start + 81}, marketUrl, start + 81);
  assert.match(expired[1].textContent, /入场窗口已过期/);
  assert.doesNotMatch(expired[1].textContent, /本轮采样方向/);
  assert.equal(expired[3].disabled, true);
});

test('observation identifies the matching round, sampling time and price sources', () => {
  const view = observationView(observing, marketUrl, now);
  assert.match(view.text, /本轮采样方向：涨 Up/);
  assert.match(view.text, new RegExp(new Date(signal.price_observed_at * 1000).toISOString()));
  assert.match(view.text, /Chainlink 采样价 \$82981\.98/);
  assert.match(view.text, /Polymarket 60秒 TWAP 开盘参考价 \$82980\.01/);
  assert.equal(view.marketUrl, marketUrl);
});

test('the panel labels unverified Future preparation evidence without enabling the amount', async () => {
  const unverified = {...status, future_eligibility: observing.future_eligibility, signal, period_start: start};
  const children = await renderedPanel(unverified, marketUrl, now);
  assert.match(children[1].textContent, /Future 金额准备依据：未核实/);
  assert.equal(children[3].disabled, true);
});

test('legacy or incomplete opening sources are unverified observation data', () => {
  for (const change of [{open_price_source: 'polymarket_crypto_price_fiveminute_openPrice'},
    {twap_lookback_seconds: undefined}, {twap_lookback_seconds: 30}]) {
    const view = observationView({...observing, signal: {...signal, ...change}}, marketUrl, now);
    assert.match(view.text, /开盘参考价未核实/);
    assert.doesNotMatch(view.text, /本轮采样方向|Polymarket 60秒 TWAP 开盘参考价/);
  }
});

test('another page or signal round cannot display a usable direction', () => {
  const wrongPage = observationView(observing,
    `https://future.news/zh/event/btc-updown-5m-${start - 300}`, now);
  assert.match(wrongPage.text, /页面轮次不匹配/);
  assert.doesNotMatch(wrongPage.text, /本轮采样方向/);
  assert.equal(wrongPage.marketUrl, marketUrl);
  const oldSignal = observationView({...observing, signal: {...signal, period_start: start - 300,
    period_end: start, slug: `btc-updown-5m-${start - 300}`}}, marketUrl, now);
  assert.match(oldSignal.text, /信号轮次已结束/);
  assert.doesNotMatch(oldSignal.text, /本轮采样方向/);
  assert.equal(oldSignal.marketUrl, marketUrl);
});

test('stale, expired, disconnected or unverified observation samples have no usable direction', () => {
  for (const {value, time, reason} of [
    {value: {...observing, server_time: now + 1}, time: now + 1, reason: /采样已陈旧/},
    {value: {...observing, server_time: start + 81,
      signal: {...signal, price_observed_at: start + 79}}, time: start + 81, reason: /入场窗口已过期/},
    {value: {...observing, feed_status: 'UNAVAILABLE'}, time: now, reason: /实时行情不可用/},
    {value: {...observing, signal: {...signal, price_observed_at: now + 1}}, time: now, reason: /采样时间无效/},
    {value: {...observing, server_time: now - 4}, time: now, reason: /本地状态已陈旧/},
  ]) {
    const view = observationView(value, marketUrl, time);
    assert.match(view.text, reason);
    assert.doesNotMatch(view.text, /本轮采样方向/);
  }
});

function ticketFixture({currency = '金额 ($)', duplicate = false, marketOrder = true, sell = false, openDropdown = false,
  buySide = '涨', buyDisabled = false, buyDuplicate = false,
  title = 'Bitcoin Up or Down - October 10, 12:45PM-12:50PM ET', inert = false, disabledFieldset = false} = {}) {
  let clicks = 0;
  let writes = 0;
  class FakeInput {
    get value() { return this.amount; }
    set value(value) { writes++; this.amount = value; }
    getClientRects() { return [1]; }
    dispatchEvent(event) { this.events.push(event.type); }
  }
  const labels = ['买入', '卖出', marketOrder ? '市价单' : '限价单', '涨 64¢', '跌 37¢', sell ? '卖出 涨' : `买入 ${buySide}`];
  if (buyDuplicate) labels.push(`买入 ${buySide}`);
  if (openDropdown) labels.push(marketOrder ? '限价单' : '市价单');
  const body = {};
  const ticket = {textContent: currency, inert, parentElement: disabledFieldset ? {tagName: 'FIELDSET', disabled: true, parentElement: body} : body,
    querySelectorAll: (selector) => selector === 'button' ? [
      ...labels.map((textContent) => ({textContent, disabled: /^买入\s+(涨|跌)$/.test(textContent) && buyDisabled,
        parentElement: ticket, getClientRects: () => [1], click() { clicks++; }})),
      // Closed dropdown options stay in some DOM implementations.
      {textContent: '市价单', getClientRects: () => [], click() { clicks++; }},
    ] : title ? [{textContent: title, getClientRects: () => [1]}] : []};
  const doc = {body, defaultView: {HTMLInputElement: FakeInput}};
  const input = new FakeInput();
  input.amount = '10'; input.events = []; input.parentElement = ticket; input.ownerDocument = doc;
  doc.querySelectorAll = (selector) => selector === 'button' ? ticket.querySelectorAll() : duplicate ? [input, input] : [input];
  return {doc, input, setTitle(value) { title = value; }, clicks: () => clicks, writes: () => writes};
}

test('the polling flow navigates an ended round once, clears old inspection and checks the new ticket', async () => {
  const fixture = ticketFixture();
  const navigate = navigationFixture();
  let time = now;
  let connected = true;
  const location = {href: marketUrl};
  const selector = fixture.doc.querySelectorAll;
  fixture.doc.querySelectorAll = (query) => query === 'button' ?
    location.href.endsWith(`-${Math.floor(time / 300) * 300}`) ? [] : navigate.doc.querySelectorAll(query) : selector(query);
  const children = await renderedPanel(observing, marketUrl, now, fixture.doc, {location, storage: navigate.storage,
    now: () => time, reply: () => connected ? {ok: true, status: {...observing, server_time: time,
      period_start: Math.floor(time / 300) * 300}} : {ok: false}});
  const inspection = children[5];
  assert.match(inspection.textContent, /检查时金额为 10/);
  assert.equal(navigate.clicks(), 0);
  time = start + 301;
  await children.poll();
  assert.match(children[6].textContent, /正在前往/);
  assert.equal(navigate.clicks(), 1);
  assert.equal(inspection.textContent, '', 'an ended round must not retain a passed ticket inspection');
  await children.poll();
  assert.equal(navigate.clicks(), 1);
  fixture.input.amount = '1';
  location.href = `https://future.news/zh/event/btc-updown-5m-${start + 300}`;
  fixture.setTitle('Bitcoin Up or Down - October 10, 12:50PM-12:55PM ET');
  await children.poll();
  assert.match(children[6].textContent, /已进入本轮/);
  assert.match(inspection.textContent, /检查时金额为 \$1/);
  assert.equal(children[3].disabled, true);
  assert.equal(fixture.writes(), 0);
  assert.equal(fixture.clicks(), 0);
  assert.deepEqual(fixture.input.events, []);
  connected = false;
  await children.poll();
  assert.match(children[6].textContent, /本地助手未连接/);
  assert.equal(inspection.textContent, '');
  assert.equal(navigate.clicks(), 1);
});

test('a changed SPA URL does not validate the old ticket while the ended-market control remains', async () => {
  const fixture = ticketFixture();
  const location = {href: `https://future.news/zh/event/btc-updown-5m-${start - 300}`};
  let ended = true;
  let clicks = 0;
  const selector = fixture.doc.querySelectorAll;
  fixture.doc.querySelectorAll = (query) => query === 'button' ? ended ? [{textContent: '前往实时市场',
    getClientRects: () => [1], click() { clicks++; location.href = marketUrl; }}] : [] : selector(query);
  const children = await renderedPanel(observing, location.href, now, fixture.doc, {location});
  assert.equal(clicks, 1);
  assert.equal(location.href, marketUrl);
  assert.equal(children[5].textContent, '');
  await children.poll();
  assert.equal(children[5].textContent, '', 'wait for the ended market DOM to disappear');
  ended = false;
  fixture.input.amount = '1';
  await children.poll();
  assert.match(children[5].textContent, /检查时金额为 \$1/);
  assert.equal(fixture.writes(), 0);
  assert.equal(fixture.clicks(), 0);
  assert.equal(clicks, 1);
});

test('page inspection reports $1 without changing input, sending events or enabling a blocked draft', async () => {
  const fixture = ticketFixture();
  fixture.input.amount = '1';
  const children = await renderedPanel(observing, marketUrl, now, fixture.doc);
  const inspect = children.find((element) => element.textContent === '检查页面');
  assert.ok(inspect, 'a read-only page inspection button is available');
  await inspect.listeners.click();
  const result = children.find((element) => /页面检查通过/.test(element.textContent));
  assert.ok(result);
  assert.match(result.textContent, /检查时金额为 \$1/);
  await children.poll();
  assert.match(result.textContent, /检查时金额为 \$1/);
  assert.equal(children[3].disabled, true);
  assert.equal(usableDraft(observing, now), null);
  assert.equal(observing.draft, null);
  assert.equal(fixture.input.value, '1');
  assert.equal(fixture.writes(), 0);
  assert.deepEqual(fixture.input.events, []);
  assert.equal(fixture.clicks(), 0);
});

test('page inspection identifies a different amount and rejects non-buy or ambiguous tickets', async () => {
  for (const options of [{}, {sell: true}, {duplicate: true}]) {
    const fixture = ticketFixture(options);
    const children = await renderedPanel(observing, marketUrl, now, fixture.doc);
    const inspect = children.find((element) => element.textContent === '检查页面');
    assert.ok(inspect, 'a read-only page inspection button is available');
    await inspect.listeners.click();
    const result = children.find((element) => /页面检查/.test(element.textContent));
    assert.match(result.textContent, options.sell ? /页面检查失败：当前不是已核对的中文美元市价买入栏/ :
      options.duplicate ? /页面检查失败：找不到唯一的可见订单金额框/ : /检查时金额为 10，尚未设为 \$1/);
    assert.equal(children[3].disabled, true);
    assert.equal(fixture.input.value, '10');
    assert.equal(fixture.writes(), 0);
    assert.deepEqual(fixture.input.events, []);
    assert.equal(fixture.clicks(), 0);
  }
});

test('preparation only fills the amount, with no side selection or buy click', () => {
  const fixture = ticketFixture();
  assert.equal(prepareAmount(status, `https://future.news/zh/event/${draft.slug}`, fixture.doc, now), 'Up');
  assert.equal(fixture.input.value, '1');
  assert.deepEqual(fixture.input.events, ['input', 'change']);
  assert.equal(fixture.clicks(), 0);
});

test('amount preparation refuses an old ticket under the new market URL before any write', () => {
  for (const title of ['Bitcoin Up or Down - October 10, 12:40PM-12:45PM ET', null]) {
    const fixture = ticketFixture({title});
    assert.throws(() => prepareAmount(status, marketUrl, fixture.doc, now), /票据|轮次/);
    assert.equal(fixture.input.value, '10');
    assert.equal(fixture.writes(), 0);
    assert.deepEqual(fixture.input.events, []);
    assert.equal(fixture.clicks(), 0);
  }
});

test('ambiguous, non-dollar and limit-order tickets fail before changing the amount', () => {
  for (const options of [{duplicate: true}, {currency: '金额 (¥)'}, {marketOrder: false}, {sell: true},
    {marketOrder: false, openDropdown: true}]) {
    const fixture = ticketFixture(options);
    assert.throws(() => prepareAmount(status, `https://future.news/zh/event/${draft.slug}`, fixture.doc, now));
    assert.equal(fixture.input.value, '10');
    assert.equal(fixture.clicks(), 0);
  }
});

test('the service worker reads only a fixed localhost URL for Future top-frame messages', async () => {
  let handler;
  const requests = [];
  const sandbox = {URL, AbortSignal, chrome: {runtime: {onMessage: {addListener(fn) { handler = fn; }}}},
    fetch: async (url, options) => { requests.push({url, options}); return {ok: true, json: async () => status}; }};
  vm.runInNewContext(readFileSync(new URL('./future-btc5m-extension/background.js', import.meta.url), 'utf8'), sandbox);
  const sender = {url: 'https://future.news/zh/updown', frameId: 0, tab: {id: 1}};
  await new Promise((resolve) => {
    assert.equal(handler({type: 'FUTURE_BTC5M_STATUS', url: 'https://evil.test'}, sender,
      (reply) => { assert.equal(reply.ok, true); resolve(); }), true);
  });
  assert.equal(requests[0].url, 'http://127.0.0.1:8766/status');
  assert.equal(requests[0].options.method, 'GET');
  assert.equal(requests[0].options.credentials, 'omit');
  handler({type: 'FUTURE_BTC5M_STATUS'}, {...sender, url: 'https://evil.test'}, () => assert.fail());
  handler({type: 'FUTURE_BTC5M_STATUS'}, {...sender, frameId: 1}, () => assert.fail());
  handler({type: 'BUY'}, sender, () => assert.fail());
  assert.equal(requests.length, 1);
});

test('preflight reports only current read-only ticket values and never writes or clicks', () => {
  const fixture = ticketFixture({buySide: '跌', buyDisabled: true});
  fixture.input.amount = '1';
  const report = readPreflight(fixture.doc, marketUrl, now);
  assert.equal(report.schemaVersion, 1);
  assert.equal(report.marketUrl, marketUrl);
  assert.equal(report.pagePeriodStart, start);
  assert.equal(report.checkedAt, now);
  assert.equal(report.navigation, 'CURRENT');
  assert.equal(report.ticketStatus, 'PASS');
  assert.equal(report.amountUsd, 1);
  assert.equal(report.selectedSide, 'Down');
  assert.equal(report.buyButtonEnabled, false);
  assert.equal(fixture.writes(), 0);
  assert.equal(fixture.clicks(), 0);
  assert.deepEqual(fixture.input.events, []);
});

test('a new URL cannot validate the old ticket after the ended-market button disappears', () => {
  for (const title of ['Bitcoin Up or Down - October 10, 12:40PM-12:45PM ET', null]) {
    const fixture = ticketFixture({title});
    const report = readPreflight(fixture.doc, marketUrl, now);
    assert.equal(report.ticketStatus, 'FAIL');
    assert.equal(report.navigation, 'MISMATCH');
    assert.equal(report.amountUsd, null);
    assert.equal(report.selectedSide, null);
    assert.equal(fixture.writes(), 0);
    assert.equal(fixture.clicks(), 0);
  }
});

test('ticket titles bind the complete ET interval across midnight and DST changes', () => {
  for (const [period, title] of [
    [1791690900, 'Bitcoin Up or Down - October 10, 11:55PM-12:00AM ET'],
    [1793512500, 'Bitcoin Up or Down - November 1, 1:55AM-1:00AM ET'],
    [1772952900, 'Bitcoin Up or Down - March 8, 1:55AM-3:00AM ET'],
  ]) {
    const fixture = ticketFixture({title});
    const report = readPreflight(fixture.doc, `https://future.news/zh/event/btc-updown-5m-${period}`, period + 65);
    assert.equal(report.ticketStatus, 'PASS', title);
    assert.equal(report.navigation, 'CURRENT');
    fixture.setTitle(title.replace(/AM|PM/, (value) => value === 'AM' ? 'PM' : 'AM'));
    assert.equal(readPreflight(fixture.doc, `https://future.news/zh/event/btc-updown-5m-${period}`, period + 65).ticketStatus, 'FAIL');
  }
});

test('manual page inspection rejects a stale ticket despite a current URL and no ended button', async () => {
  const fixture = ticketFixture({title: 'Bitcoin Up or Down - October 10, 12:40PM-12:45PM ET'});
  const children = await renderedPanel(observing, marketUrl, now, fixture.doc);
  await children[4].listeners.click();
  assert.match(children[5].textContent, /当前票据标题或页面轮次未核对/);
  assert.doesNotMatch(children[5].textContent, /页面检查通过/);
  assert.equal(fixture.writes(), 0);
  assert.equal(fixture.clicks(), 0);
});

test('disabled fieldsets and inert ticket ancestors do not advertise a usable buy button', () => {
  for (const options of [{inert: true}, {disabledFieldset: true}]) {
    const fixture = ticketFixture(options);
    assert.equal(readPreflight(fixture.doc, marketUrl, now).buyButtonEnabled, false);
    assert.equal(fixture.clicks(), 0);
  }
});

test('preflight rejects old DOM under a new URL and ambiguous tickets without transmitting errors or DOM', () => {
  for (const options of [{buyDuplicate: true}, {duplicate: true}, {sell: true}, {marketOrder: false}]) {
    const fixture = ticketFixture(options);
    const report = readPreflight(fixture.doc, marketUrl, now);
    assert.equal(report.ticketStatus, 'FAIL');
    assert.equal(report.amountUsd, null);
    assert.equal(report.selectedSide, null);
    assert.equal(report.buyButtonEnabled, false);
    assert.equal(Object.keys(report).length, 9);
    assert.equal(fixture.writes(), 0);
    assert.equal(fixture.clicks(), 0);
  }
  const fixture = ticketFixture();
  const original = fixture.doc.querySelectorAll;
  fixture.doc.querySelectorAll = (selector) => selector === 'button' ? navigationFixture().doc.querySelectorAll(selector) : original(selector);
  const mismatch = readPreflight(fixture.doc, marketUrl, now);
  assert.equal(mismatch.navigation, 'MISMATCH');
  assert.equal(mismatch.ticketStatus, 'FAIL');
  assert.equal(readPreflight(ticketFixture().doc, `https://future.news/zh/event/btc-updown-5m-${start - 300}`, now).navigation, 'ENDED');
  for (const suffix of ['?m=public-market-id', '#fragment']) {
    const canonical = readPreflight(ticketFixture().doc, marketUrl + suffix, now);
    assert.equal(canonical.marketUrl, marketUrl);
    assert.equal(JSON.stringify(canonical).includes(suffix), false);
  }
  for (const url of ['https://evil.test/',
    marketUrl.replace('future.news', 'user:pass@future.news'), marketUrl.replace(`${start}`, `0${start}`)]) {
    assert.equal(readPreflight(fixture.doc, url, now), null);
  }
});

test('polling sends a preflight even when eligibility blocks all draft preparation', async () => {
  const fixture = ticketFixture();
  fixture.input.amount = '1';
  const messages = [];
  const children = await renderedPanel(observing, marketUrl, now, fixture.doc, {messages});
  const reports = messages.filter((item) => item.type === 'FUTURE_BTC5M_PREFLIGHT');
  assert.equal(reports.length, 1);
  assert.equal(reports[0].payload.ticketStatus, 'PASS');
  assert.equal(reports[0].payload.amountUsd, 1);
  assert.equal(children[3].disabled, true);
  assert.equal(fixture.writes(), 0);
  assert.equal(fixture.clicks(), 0);
});

test('the worker posts a strictly scoped top-frame preflight without credentials or page URLs as destinations', async () => {
  let handler;
  const requests = [];
  class Clock extends Date { static now() { return now * 1000; } }
  vm.runInNewContext(readFileSync(new URL('./future-btc5m-extension/background.js', import.meta.url), 'utf8'), {
    URL, AbortSignal, Date: Clock, chrome: {runtime: {onMessage: {addListener(fn) { handler = fn; }}}},
    fetch: async (url, options) => { requests.push({url, options}); return {ok: true, json: async () => ({})}; },
  });
  const payload = {schemaVersion: 1, marketUrl, pagePeriodStart: start, checkedAt: now, navigation: 'CURRENT',
    ticketStatus: 'PASS', amountUsd: 1, selectedSide: 'Up', buyButtonEnabled: true};
  const sender = {url: `${marketUrl}?m=public-market-id`, frameId: 0, tab: {id: 1}};
  await new Promise((resolve) => {
    assert.equal(handler({type: 'FUTURE_BTC5M_PREFLIGHT', payload}, sender, (reply) => {
      assert.equal(reply.ok, true);
      resolve();
    }), true);
  });
  assert.equal(requests[0].url, 'http://127.0.0.1:8766/bridge/preflight');
  assert.equal(requests[0].options.method, 'POST');
  assert.equal(requests[0].options.credentials, 'omit');
  assert.equal(requests[0].options.redirect, 'error');
  assert.equal(requests[0].options.headers['X-PolyHermes-Future-Preflight'], '1');
  assert.deepEqual(JSON.parse(requests[0].options.body), payload);
  for (const change of [{schemaVersion: 2}, {checkedAt: now - 4}, {amountUsd: Infinity}, {amountUsd: -1},
    {selectedSide: 'Yes'}, {buyButtonEnabled: 'true'}, {navigation: 'BOGUS'}, {ticketStatus: 'YES'},
    {marketUrl: `${marketUrl}?token=secret`}, {pagePeriodStart: start + 300}, {cookie: 'secret'}]) {
    handler({type: 'FUTURE_BTC5M_PREFLIGHT', payload: {...payload, ...change}}, sender, () => assert.fail());
  }
  handler({type: 'FUTURE_BTC5M_PREFLIGHT', payload, url: 'https://evil.test'}, sender, () => assert.fail());
  handler({type: 'FUTURE_BTC5M_PREFLIGHT', payload}, {...sender, frameId: 1}, () => assert.fail());
  handler({type: 'FUTURE_BTC5M_PREFLIGHT', payload}, {...sender, url: 'https://future.news/zh/updown'}, () => assert.fail());
  handler({type: 'FUTURE_BTC5M_PREFLIGHT', payload}, {...sender, url: 'https://evil.test'}, () => assert.fail());
  assert.equal(requests.length, 1);
});
