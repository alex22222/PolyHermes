import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const content = readFileSync(new URL('./future-btc5m-extension/content.js', import.meta.url), 'utf8');
const context = vm.createContext({URL, Event});
vm.runInContext(content, context);
const {usableDraft, matchesMarket, prepareAmount, observationView, navigationTarget, followCurrentMarket, readPreflight,
  usablePreparation, readPreparationTicket, prepareOnlyOnce, parseButtonQuote} = context.FutureBtc5m;
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
    }}}, ...runtime.globals});
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
  buySide = '涨', buyDisabled = false, buyEnabledAfterAmount = false, buyDuplicate = false,
  upQuote = '12¢', downQuote = '88¢',
  title = 'Bitcoin Up or Down - October 10, 12:45PM-12:50PM ET', inert = false, disabledFieldset = false,
  selectedSide = buySide === '涨' ? 'Up' : 'Down', selectedAttribute = 'aria-pressed',
  classEvidence = false, selectedClass = 'text-text-hightlightbtn',
  unselectedClass = 'bg-panel-100 text-text-400 hover:bg-hover-200 border border-solid border-line-100',
  directionType = 'button', directionForm = false, directionDisabled = false,
  directionDuplicate = false, directionApplies = true, afterDirection = () => {}, afterAmount = () => {}} = {}) {
  let clicks = 0;
  let directionClicks = 0;
  let buyClicks = 0;
  let writes = 0;
  class FakeInput {
    get value() { return this.amount; }
    set value(value) { writes++; this.amount = value; }
    getClientRects() { return [1]; }
    dispatchEvent(event) { this.events.push(event.type); afterAmount(event); }
  }
  const labels = ['买入', '卖出', marketOrder ? '市价单' : '限价单', `涨 ${upQuote}`, `跌 ${downQuote}`, sell ? '卖出 涨' : `买入 ${buySide}`];
  if (buyDuplicate) labels.push(`买入 ${buySide}`);
  if (directionDuplicate) labels.push(`跌 ${downQuote}`);
  if (openDropdown) labels.push(marketOrder ? '限价单' : '市价单');
  const body = {};
  const ticket = {textContent: currency, inert, parentElement: disabledFieldset ? {tagName: 'FIELDSET', disabled: true, parentElement: body} : body,
    querySelectorAll: (selector) => selector === 'button' ? [
      ...labels.map((label) => {
        const side = /^涨(?:\s|\d|--)/.test(label) ? 'Up' : /^跌(?:\s|\d|--)/.test(label) ? 'Down' : null;
        const buy = /^买入\s+(涨|跌)$/.test(label);
        return {get textContent() { return buy ? `买入 ${buySide}` : side ?
          `${side === 'Up' ? '涨' : '跌'} ${side === 'Up' ? upQuote : downQuote}` : label; },
          tagName: 'BUTTON', type: side ? directionType : 'button', form: directionForm ? {} : null,
          get className() { return !classEvidence || !side ? '' : side === selectedSide ? selectedClass : unselectedClass; },
          get disabled() { return side ? directionDisabled : buy && buyDisabled && !(buyEnabledAfterAmount && input.amount === '1'); },
          getAttribute(name) { return side && name === selectedAttribute ? String(side === selectedSide) : null; },
          parentElement: ticket, getClientRects: () => [1], click() {
            clicks++;
            if (side) {
              directionClicks++;
              if (directionApplies) { selectedSide = side; buySide = side === 'Up' ? '涨' : '跌'; }
              afterDirection();
            }
            if (buy) buyClicks++;
          }};
      }),
      // Closed dropdown options stay in some DOM implementations.
      {textContent: '市价单', getClientRects: () => [], click() { clicks++; }},
    ] : title ? [{textContent: title, getClientRects: () => [1]}] : []};
  const doc = {body, defaultView: {HTMLInputElement: FakeInput}};
  const input = new FakeInput();
  input.amount = '10'; input.events = []; input.parentElement = ticket; input.ownerDocument = doc;
  doc.querySelectorAll = (selector) => selector === 'button' ? ticket.querySelectorAll() : duplicate ? [input, input] : [input];
  return {doc, input, setTitle(value) { title = value; },
    setQuotes(up, down) { upQuote = up; downQuote = down; }, clicks: () => clicks,
    directionClicks: () => directionClicks, buyClicks: () => buyClicks, writes: () => writes};
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
  assert.equal(report.schemaVersion, 2);
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
    assert.equal(Object.keys(report).length, 11);
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

test('SPA preflight matches the trusted current tab URL while retaining Future BTC5m sender guards', async () => {
  let handler;
  const requests = [];
  class Clock extends Date { static now() { return now * 1000; } }
  vm.runInNewContext(readFileSync(new URL('./future-btc5m-extension/background.js', import.meta.url), 'utf8'), {
    URL, AbortSignal, Date: Clock, chrome: {runtime: {onMessage: {addListener(fn) { handler = fn; }}}},
    fetch: async (url, options) => { requests.push({url, options}); return {ok: true}; },
  });
  const payload = {schemaVersion: 1, marketUrl, pagePeriodStart: start, checkedAt: now, navigation: 'CURRENT',
    ticketStatus: 'PASS', amountUsd: 1, selectedSide: 'Up', buyButtonEnabled: true};
  const message = {type: 'FUTURE_BTC5M_PREFLIGHT', payload};
  const oldDocument = `https://future.news/zh/event/btc-updown-5m-${start - 300}`;
  const sender = {url: oldDocument, frameId: 0, tab: {id: 1, url: `${marketUrl}?m=current-market-id`}};
  await new Promise((resolve) => {
    assert.equal(handler(message, sender, (reply) => { assert.equal(reply.ok, true); resolve(); }), true);
  });
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, 'http://127.0.0.1:8766/bridge/preflight');
  assert.deepEqual(JSON.parse(requests[0].options.body), payload);
  for (const invalid of [
    {...sender, frameId: 1},
    {...sender, url: 'https://evil.test/zh/event/btc-updown-5m-1'},
    {...sender, url: 'https://future.news/zh/updown'},
    {...sender, tab: {id: 1, url: 'https://evil.test/'}},
    {...sender, tab: {id: 1, url: 'https://future.news/zh/updown'}},
    {...sender, tab: {id: 1, url: oldDocument}},
    {...sender, tab: {id: 1}},
  ]) assert.equal(handler(message, invalid, () => {}), undefined);
  assert.equal(requests.length, 1);
});

const preparationIntent = {schemaVersion: 2, id: `future-btc5m-prepare:${start}`,
  slug: draft.slug, periodStart: start, periodEnd: start + 300, side: 'Down', amountUsd: 1,
  createdAt: now, expiresAt: start + 80, priceObservedAt: now, openPrice: 82980.01, currentPrice: 82981,
  upQuoteCents: 12, downQuoteCents: 88, quoteObservedAt: now, selectionSource: 'HIGHER_BUTTON_PRICE',
  priceSource: 'chainlink', openPriceSource: 'polymarket_crypto_price_fiveminute_twap60_openPrice',
  twapLookbackSeconds: 60, mode: 'PREPARE_ONLY', noSubmission: true, operatorAuthorized: true,
  authorizationSource: 'USER_REQUEST', claimToken: null};
const preparation = {bridgeId: 'future-btc5m', serverTime: now,
  preparation: {mode: 'PREPARE_ONLY', noSubmission: true, operatorAuthorized: true,
    authorizationSource: 'USER_REQUEST', enabled: true, state: 'PENDING',
    intent: preparationIntent, lastAttempt: null, reasons: []}};
const token = 'a'.repeat(32);

function preparationTransport({read = null, claim = null, preflightOk = true} = {}) {
  const acknowledgements = [];
  const reports = [];
  let claims = 0;
  const claimed = {...preparation, preparation: {...preparation.preparation, state: 'CLAIMED',
    intent: {...preparationIntent, claimToken: token}}};
  const transport = {
    async readPreparation() { return read ? read() : claimed; },
    async claimPreparation(payload) { claims++; assert.deepEqual(JSON.parse(JSON.stringify(payload)),
      {schemaVersion: 1, id: preparationIntent.id}); return claim ? claim() : claimed; },
    async reportPreflight(payload) { reports.push(payload); return {ok: preflightOk}; },
    async acknowledge(payload) { acknowledgements.push(payload); return {ok: true}; },
  };
  return {transport, acknowledgements, reports, claims: () => claims, claimed};
}

test('PREPARE_ONLY uses explicit user preparation authority without changing legacy eligibility guards', () => {
  assert.equal(usableDraft(observing, now), null);
  assert.equal(usablePreparation(preparation, now), preparationIntent);
  for (const change of [{mode: 'LIVE'}, {noSubmission: false}, {operatorAuthorized: false},
    {authorizationSource: 'OFFICIAL_VERIFIED'}, {enabled: false}, {state: 'READY'}]) {
    assert.equal(usablePreparation({...preparation, preparation: {...preparation.preparation, ...change}}, now), null);
  }
  for (const change of [{bridgeId: 'other'}, {serverTime: now - 4}]) {
    assert.equal(usablePreparation({...preparation, ...change}, now), null);
  }
  for (const change of [{amountUsd: 2}, {side: 'Up'}, {periodStart: start - 300}, {priceObservedAt: now - 6},
    {currentPrice: 0}, {expiresAt: start + 81}, {claimToken: 'unsafe'}, {priceSource: 'other'}]) {
    assert.equal(usablePreparation({...preparation, preparation: {...preparation.preparation,
      intent: {...preparationIntent, ...change}}}, now), null);
  }
  assert.equal(usablePreparation(preparation, start + 59), null);
  assert.equal(usablePreparation({...preparation, serverTime: start + 80}, start + 80), null);
});

test('direction controls require actual selected evidence and cannot be inferred solely from Buy text', () => {
  assert.equal(readPreparationTicket(ticketFixture().doc, marketUrl, start).selectedSide, 'Up');
  for (const options of [{selectedAttribute: null}, {selectedSide: null}, {selectedSide: 'Down'},
    {directionDuplicate: true}, {directionDisabled: true}, {directionType: 'submit', directionForm: true},
    {inert: true}, {currency: '金额 (¥)'}, {sell: true}, {marketOrder: false}]) {
    const fixture = ticketFixture(options);
    assert.throws(() => readPreparationTicket(fixture.doc, marketUrl, start));
    assert.equal(fixture.clicks(), 0);
    assert.equal(fixture.writes(), 0);
  }
  assert.equal(readPreparationTicket(ticketFixture({buyDisabled: true}).doc, marketUrl, start).selectedSide, 'Up');
});

test('observed Future selected class is unique and cross-checked with Buy text without guessing a color class', () => {
  const options = {selectedAttribute: null, classEvidence: true};
  assert.equal(readPreparationTicket(ticketFixture(options).doc, marketUrl, start).selectedSide, 'Up');
  assert.equal(readPreparationTicket(ticketFixture({...options, buySide: '跌'}).doc, marketUrl, start).selectedSide, 'Down');
  for (const change of [{selectedClass: 'bg-increase-100'}, {selectedClass: 'text-text-hightlightbtn text-text-400'},
    {unselectedClass: 'bg-panel-100'}, {unselectedClass: 'bg-panel-100 text-text-400 text-text-hightlightbtn'},
    {selectedSide: 'Down'}]) {
    const fixture = ticketFixture({...options, ...change});
    assert.throws(() => readPreparationTicket(fixture.doc, marketUrl, start));
    assert.equal(fixture.clicks(), 0);
    assert.equal(fixture.writes(), 0);
  }
});

test('first atomic claim prepares strategy direction and dollar 1 once without any Buy click', async () => {
  const fixture = ticketFixture();
  const storage = navigationFixture().storage;
  const flow = preparationTransport();
  const result = await prepareOnlyOnce(preparation, fixture.doc, () => marketUrl, storage, flow.transport, () => now);
  assert.equal(result.status, 'READY');
  assert.equal(fixture.input.value, '1');
  assert.equal(fixture.directionClicks(), 1);
  assert.equal(fixture.buyClicks(), 0);
  assert.deepEqual(fixture.input.events, ['input', 'change']);
  assert.equal(flow.claims(), 1);
  assert.equal(flow.reports.length, 1);
  assert.equal(flow.reports[0].selectedSide, 'Down');
  assert.equal(flow.reports[0].amountUsd, 1);
  assert.equal(flow.acknowledgements.length, 1);
  assert.deepEqual(JSON.parse(JSON.stringify(flow.acknowledgements[0])), {schemaVersion: 1,
    id: preparationIntent.id, claimToken: token, checkedAt: now, status: 'READY', marketUrl,
    amountUsd: 1, selectedSide: 'Down', reason: null, noSubmission: true});
  await prepareOnlyOnce(preparation, fixture.doc, () => marketUrl, storage, flow.transport, () => now);
  assert.equal(flow.claims(), 1, 'the same tab may not repeat even after a content script reload');
  assert.equal(fixture.directionClicks(), 1);
  assert.equal(fixture.writes(), 1);
});

test('a GET CLAIMED or disabled intent cannot restore a lost preparation claim', async () => {
  for (const wrapper of [
    {...preparation, preparation: {...preparation.preparation, enabled: false}},
    {...preparation, preparation: {...preparation.preparation, state: 'CLAIMED',
      intent: {...preparationIntent, claimToken: token}}},
  ]) {
    const fixture = ticketFixture();
    const flow = preparationTransport();
    await prepareOnlyOnce(wrapper, fixture.doc, () => marketUrl, navigationFixture().storage, flow.transport, () => now);
    assert.equal(flow.claims(), 0);
    assert.equal(fixture.clicks(), 0);
    assert.equal(fixture.writes(), 0);
    assert.equal(flow.acknowledgements.length, 0);
  }
});

test('STOP, expiry or ticket changes between direction and amount fail closed without writing amount', async () => {
  for (const reason of ['PREPARATION_REVOKED', 'INTENT_EXPIRED', 'MARKET_MISMATCH']) {
    let time = now;
    let revoked = false;
    const fixture = ticketFixture({afterDirection() {
      if (reason === 'INTENT_EXPIRED') time = start + 80;
      if (reason === 'PREPARATION_REVOKED') revoked = true;
      if (reason === 'MARKET_MISMATCH') fixture.setTitle('Bitcoin Up or Down - October 10, 12:40PM-12:45PM ET');
    }});
    const flow = preparationTransport({read: () => ({...flow.claimed, serverTime: time,
      preparation: {...flow.claimed.preparation, enabled: !revoked}})});
    const result = await prepareOnlyOnce(preparation, fixture.doc, () => marketUrl,
      navigationFixture().storage, flow.transport, () => time);
    assert.equal(result.reason, reason);
    assert.equal(result.status, reason === 'INTENT_EXPIRED' ? 'EXPIRED' : 'FAILED');
    assert.equal(fixture.writes(), 0);
    assert.equal(fixture.buyClicks(), 0);
    assert.equal(flow.acknowledgements.length, 1);
    assert.equal(flow.acknowledgements[0].reason, reason);
  }
});

test('readback and confirmed preflight are required before READY and failures never retry', async () => {
  for (const options of [{directionApplies: false}, {preflightOk: false}, {amountApplies: false}]) {
    let fixture;
    fixture = ticketFixture({directionApplies: options.directionApplies,
      afterAmount() { if (options.amountApplies === false) fixture.input.amount = '2'; }});
    const flow = preparationTransport({preflightOk: options.preflightOk});
    const storage = navigationFixture().storage;
    const result = await prepareOnlyOnce(preparation, fixture.doc, () => marketUrl, storage, flow.transport, () => now);
    assert.equal(result.status, 'FAILED');
    assert.equal(result.reason, options.directionApplies === false ? 'DIRECTION_WRITE_FAILED' :
      options.amountApplies === false ? 'AMOUNT_WRITE_FAILED' : 'POSTCHECK_FAILED');
    assert.equal(flow.acknowledgements.length, 1);
    assert.equal(fixture.buyClicks(), 0);
    await prepareOnlyOnce(preparation, fixture.doc, () => marketUrl, storage, flow.transport, () => now);
    assert.equal(flow.claims(), 1);
  }
});

test('polling independently prepares a USER_REQUEST ticket while legacy UNKNOWN remains blocked', async () => {
  const fixture = ticketFixture();
  const flow = preparationTransport();
  const messages = [];
  let claimed = false;
  const children = await renderedPanel(observing, marketUrl, now, fixture.doc, {messages,
    reply(message) {
      if (message.type === 'FUTURE_BTC5M_PREPARATION') return {ok: true, status: claimed ? flow.claimed : preparation};
      if (message.type === 'FUTURE_BTC5M_PREPARATION_CLAIM') {
        claimed = true;
        return {ok: true, status: flow.claimed};
      }
      if (message.type === 'FUTURE_BTC5M_PREPARATION_ACK') return {ok: true,
        status: {...flow.claimed, preparation: {...flow.claimed.preparation, state: message.payload.status}}};
      if (message.type === 'FUTURE_BTC5M_PREFLIGHT') return {ok: true};
      return {ok: true, status: observing};
    }});
  assert.equal(fixture.input.value, '1');
  assert.equal(fixture.directionClicks(), 1);
  assert.equal(fixture.buyClicks(), 0);
  assert.equal(children[3].disabled, true, 'the legacy eligibility path stays blocked');
  assert.match(children[1].textContent, /BTC参考价差（不决定票据方向）/);
  assert.doesNotMatch(children[1].textContent, /本轮采样方向/);
  assert.match(children[9].textContent, /已准备 \$1/);
  assert.doesNotMatch(children[9].textContent, /手动买入/);
  assert.match(children[9].textContent, /按按钮较大数值选择跌 Down/);
  assert.match(children[10].textContent, /自动买入：脚本未加载，不会点击/);
  const acknowledgement = messages.find((item) => item.type === 'FUTURE_BTC5M_PREPARATION_ACK');
  assert.equal(acknowledgement.payload.status, 'READY');
  await children.poll();
  assert.equal(messages.filter((item) => item.type === 'FUTURE_BTC5M_PREPARATION_CLAIM').length, 1);
  assert.equal(fixture.writes(), 1);
});

test('the panel arms automatic Buy from the project switch before preparing and only reports its state', async () => {
  const fixture = ticketFixture();
  const flow = preparationTransport();
  const events = [];
  let enabled = true;
  let offline = false;
  let claimed = false;
  let view = {state: 'WATCHING', reason: null, last: null};
  let buyerEnv;
  const autoBuyer = {
    sync(value) { events.push(`sync:${value}`); return value ? view : {state: 'OFF', reason: null, last: null}; },
    status() { events.push('status'); return view; }};
  const children = await renderedPanel(observing, marketUrl, now, fixture.doc, {
    globals: {FutureBtc5mBuyOnce: {createAutoBuyer(env) { buyerEnv = env; return autoBuyer; }}},
    reply(message) {
      events.push(message.type);
      if (message.type === 'FUTURE_BTC5M_PREPARATION') {
        if (offline) return {ok: false};
        return {ok: true, status: !enabled ? {...preparation, preparation: {...preparation.preparation,
          enabled: false, state: 'DISABLED', intent: null}} : claimed ? flow.claimed : preparation};
      }
      if (message.type === 'FUTURE_BTC5M_PREPARATION_CLAIM') {
        claimed = true;
        return {ok: true, status: flow.claimed};
      }
      if (message.type === 'FUTURE_BTC5M_PREPARATION_ACK') return {ok: true,
        status: {...flow.claimed, preparation: {...flow.claimed.preparation, state: message.payload.status}}};
      if (message.type === 'FUTURE_BTC5M_PREFLIGHT') return {ok: true};
      return {ok: true, status: observing};
    }});
  assert.ok(events.indexOf('sync:true') >= 0 &&
    events.indexOf('sync:true') < events.indexOf('FUTURE_BTC5M_PREPARATION_CLAIM'), 'armed before this round is prepared');
  assert.match(children[10].textContent, /自动买入：已开启.*每轮最多一次/);
  assert.equal(fixture.buyClicks(), 0, 'the panel itself never clicks Buy');
  events.length = 0;
  assert.equal((await buyerEnv.readPreparation()).bridgeId, 'future-btc5m');
  assert.deepEqual(events, ['FUTURE_BTC5M_PREPARATION']);

  view = {state: 'PAUSED', reason: null, last: {state: 'CLICK_ATTEMPTED', reason: 'PLATFORM_RESULT_UNKNOWN',
    periodStart: start, side: 'Down', amountUsd: 1}};
  await children.poll();
  assert.match(children[10].textContent, new RegExp(`最近：已点击“买入 跌” \\$1（btc-updown-5m-${start}），成交以 Future 订单为准`));
  view = {state: 'WATCHING', reason: null, last: {state: 'BLOCKED', reason: 'TICKET_CHANGED',
    periodStart: null, side: null, amountUsd: null}};
  await children.poll();
  assert.match(children[10].textContent, /最近：未点击（票据已改变）/);

  offline = true;
  events.length = 0;
  await children.poll();
  assert.equal(events.includes('status'), true);
  assert.equal(events.some((event) => event.startsWith('sync:')), false, 'an unreadable switch neither arms nor stops');
  offline = false;
  enabled = false;
  await children.poll();
  assert.equal(events.includes('sync:false'), true);
  assert.match(children[10].textContent, /跟随“自动准备票据”开关，当前关闭，不会点击/);
  assert.equal(fixture.buyClicks(), 0);
});

test('disabled automatic tickets explain the missing switch and show higher Up separately from selected Down', async () => {
  const fixture = ticketFixture({upQuote: '74¢', downQuote: '27¢', buySide: '跌'});
  fixture.input.amount = '1';
  const disabled = {...preparation, preparation: {...preparation.preparation,
    enabled: false, state: 'DISABLED', intent: null, reasons: ['AUTO_PREPARATION_DISABLED']}};
  const children = await renderedPanel({...observing, status: 'SKIPPED', reason: 'CHAINLINK_PRICE_STALE_OR_FUTURE'},
    marketUrl, now, fixture.doc, {reply(message) {
      if (message.type === 'FUTURE_BTC5M_PREPARATION') return {ok: true, status: disabled};
      if (message.type === 'FUTURE_BTC5M_PREFLIGHT') return {ok: true};
      return {ok: true, status: observing};
    }});
  assert.match(children[9].textContent, /已关闭.*未切换方向.*开启/);
  assert.match(children[7].textContent, /开启.*60.*80/);
  assert.match(children[7].textContent, /涨 74¢.*跌 27¢.*较大.*涨 Up.*当前选中.*跌 Down/);
  assert.doesNotMatch(children[9].textContent, /已准备/);
  assert.equal(fixture.directionClicks(), 0);
  assert.equal(fixture.writes(), 0);
  assert.equal(fixture.buyClicks(), 0);
});

test('restoring the automatic switch selects the higher Up button and immediately displays its actual readback', async () => {
  const fixture = ticketFixture({upQuote: '74¢', downQuote: '27¢', buySide: '跌'});
  const initial = {...preparation, preparation: {...preparation.preparation,
    intent: {...preparationIntent, side: 'Up', upQuoteCents: 74, downQuoteCents: 27}}};
  const claimed = {...initial, preparation: {...initial.preparation, state: 'CLAIMED',
    intent: {...initial.preparation.intent, claimToken: token}}};
  let enabled = false;
  let state = 'PENDING';
  const children = await renderedPanel(observing, marketUrl, now, fixture.doc, {reply(message) {
    if (message.type === 'FUTURE_BTC5M_PREPARATION') return {ok: true, status: enabled ?
      state === 'PENDING' ? initial : claimed : {...initial, preparation: {...initial.preparation,
        enabled: false, state: 'DISABLED', intent: null}}};
    if (message.type === 'FUTURE_BTC5M_PREPARATION_CLAIM') {
      state = 'CLAIMED';
      return {ok: true, status: claimed};
    }
    if (message.type === 'FUTURE_BTC5M_PREPARATION_ACK') return {ok: true,
      status: {...claimed, preparation: {...claimed.preparation, state: message.payload.status}}};
    if (message.type === 'FUTURE_BTC5M_PREFLIGHT') return {ok: true};
    return {ok: true, status: observing};
  }});
  assert.equal(fixture.directionClicks(), 0);
  assert.match(children[7].textContent, /当前选中：跌 Down/);
  enabled = true;
  await children.poll();
  assert.equal(fixture.directionClicks(), 1);
  assert.equal(fixture.input.value, '1');
  assert.equal(fixture.buyClicks(), 0);
  assert.match(children[9].textContent, /已准备.*选择涨 Up/);
  assert.match(children[7].textContent, /涨 74¢.*跌 27¢.*当前选中：涨 Up/);
});

test('waiting automatic tickets explain freshness and the entry window without claiming selection', async () => {
  for (const time of [now, start + 81]) {
    const fixture = ticketFixture({upQuote: '74¢', downQuote: '27¢', buySide: '跌'});
    const waiting = {...preparation, serverTime: time, preparation: {...preparation.preparation,
      state: 'WAITING_SIGNAL', intent: null, reasons: ['WAITING_CURRENT_SIGNAL']}};
    const source = {...observing, server_time: time, reason: 'CHAINLINK_PRICE_STALE_OR_FUTURE'};
    const children = await renderedPanel(source,
      marketUrl, time, fixture.doc, {reply(message) {
        if (message.type === 'FUTURE_BTC5M_PREPARATION') return {ok: true, status: waiting};
        if (message.type === 'FUTURE_BTC5M_PREFLIGHT') return {ok: true};
        return {ok: true, status: source};
      }});
    assert.match(children[9].textContent, time < start + 80 ? /行情过期.*未切换方向/ : /80.*等待下一轮.*未切换方向/);
    assert.doesNotMatch(children[9].textContent, /已准备/);
    assert.equal(fixture.directionClicks(), 0);
    assert.equal(fixture.writes(), 0);
    assert.equal(fixture.buyClicks(), 0);
  }
});

test('the worker exposes only fixed prepare/claim/ack endpoints and refuses financial or unscoped messages', async () => {
  let handler;
  const requests = [];
  class Clock extends Date { static now() { return now * 1000; } }
  vm.runInNewContext(readFileSync(new URL('./future-btc5m-extension/background.js', import.meta.url), 'utf8'), {
    URL, AbortSignal, Date: Clock, chrome: {runtime: {onMessage: {addListener(fn) { handler = fn; }}}},
    fetch: async (url, options) => { requests.push({url, options}); return {ok: true, json: async () => preparation}; },
  });
  const sender = {url: marketUrl, frameId: 0, tab: {id: 1, url: marketUrl}};
  const claim = {schemaVersion: 1, id: preparationIntent.id};
  const ack = {schemaVersion: 1, id: preparationIntent.id, claimToken: token, checkedAt: now,
    status: 'READY', marketUrl, amountUsd: 1, selectedSide: 'Down', reason: null, noSubmission: true};
  for (const [type, payload, suffix, method] of [
    ['FUTURE_BTC5M_PREPARATION', undefined, '', 'GET'],
    ['FUTURE_BTC5M_PREPARATION_CLAIM', claim, '/claim', 'POST'],
    ['FUTURE_BTC5M_PREPARATION_ACK', ack, '/ack', 'POST'],
  ]) {
    await new Promise((resolve) => {
      assert.equal(handler(payload ? {type, payload} : {type}, sender, (reply) => {
        assert.equal(reply.ok, true); resolve();
      }), true);
    });
    const request = requests.at(-1);
    assert.equal(request.url, `http://127.0.0.1:8766/bridge/preparation${suffix}`);
    assert.equal(request.options.method, method);
    assert.equal(request.options.credentials, 'omit');
    assert.equal(request.options.redirect, 'error');
    assert.equal(request.options.cache, 'no-store');
    assert.equal(request.options.headers['X-PolyHermes-Future-Preparation'], '1');
    if (payload) {
      assert.deepEqual(JSON.parse(request.options.body), payload);
    }
  }
  for (const message of [
    {type: 'FUTURE_BTC5M_PREPARATION', url: 'https://evil.test'},
    {type: 'FUTURE_BTC5M_PREPARATION_CLAIM', payload: {...claim, amountUsd: 2}},
    {type: 'FUTURE_BTC5M_PREPARATION_CLAIM', payload: {...claim, id: `future-btc5m-prepare:${start - 300}`}},
    ...[{noSubmission: false}, {claimToken: 'secret'}, {status: 'FILLED'}, {checkedAt: now - 4},
      {reason: 'raw-page-secret'}, {amountUsd: 2}, {marketUrl: `${marketUrl}?token=secret`},
      {status: 'FAILED', reason: 'INTENT_EXPIRED'}, {cookie: 'secret'}].map((change) =>
      ({type: 'FUTURE_BTC5M_PREPARATION_ACK', payload: {...ack, ...change}})),
    {type: 'BUY'}, {type: 'FUTURE_BTC5M_SUBMIT'},
  ]) assert.equal(handler(message, sender, () => assert.fail()), undefined);
  for (const change of [{frameId: 1}, {url: 'https://evil.test/'}, {tab: {id: 1, url: 'https://evil.test/'}},
    {url: 'https://future.news/zh/updown'}]) {
    assert.equal(handler({type: 'FUTURE_BTC5M_PREPARATION_CLAIM', payload: claim},
      {...sender, ...change}, () => assert.fail()), undefined);
  }
  assert.equal(requests.length, 3);
});

test('blocked storage, rejected claims and lost acknowledgements never permit retries or Buy clicks', async () => {
  for (const failure of ['storage', 'claim', 'ack']) {
    const fixture = ticketFixture();
    const storage = navigationFixture({storageError: failure === 'storage'}).storage;
    const flow = preparationTransport({claim: failure === 'claim' ? () => { throw new Error('HTTP409'); } : null});
    if (failure === 'ack') flow.transport.acknowledge = async () => { throw new Error('lost response'); };
    const result = await prepareOnlyOnce(preparation, fixture.doc, () => marketUrl, storage, flow.transport, () => now);
    assert.equal(result.status, 'FAILED');
    assert.equal(fixture.buyClicks(), 0);
    if (failure !== 'ack') {
      assert.equal(fixture.writes(), 0);
      assert.equal(fixture.directionClicks(), 0);
      assert.equal(flow.acknowledgements.length, 0);
    }
    await prepareOnlyOnce(preparation, fixture.doc, () => marketUrl, storage, flow.transport, () => now);
    assert.equal(flow.claims(), failure === 'storage' ? 0 : 1);
  }
});

test('concurrent calls share a persistent once-per-round attempt and claim mismatches never touch the ticket', async () => {
  const fixture = ticketFixture();
  const storage = navigationFixture().storage;
  const flow = preparationTransport();
  await Promise.all([1, 2].map(() => prepareOnlyOnce(preparation, fixture.doc, () => marketUrl,
    storage, flow.transport, () => now)));
  assert.equal(flow.claims(), 1);
  assert.equal(fixture.writes(), 1);
  assert.equal(fixture.buyClicks(), 0);
  for (const change of [{id: 'other'}, {side: 'Up'}, {claimToken: null}, {claimToken: 'invalid'}]) {
    const invalid = ticketFixture();
    const rejected = preparationTransport({claim: () => ({...flow.claimed,
      preparation: {...flow.claimed.preparation, intent: {...flow.claimed.preparation.intent, ...change}}})});
    await prepareOnlyOnce(preparation, invalid.doc, () => marketUrl, navigationFixture().storage,
      rejected.transport, () => now);
    assert.equal(invalid.clicks(), 0);
    assert.equal(invalid.writes(), 0);
    assert.equal(rejected.acknowledgements.length, 0);
  }
});

test('a claimed price sample cannot be replaced to extend its five-second write permission', async () => {
  let time = now;
  const fixture = ticketFixture({afterDirection() { time = now + 6; }});
  const flow = preparationTransport({read: () => ({...flow.claimed, serverTime: time,
    preparation: {...flow.claimed.preparation, intent: {...flow.claimed.preparation.intent,
      createdAt: time, priceObservedAt: time}}})});
  const result = await prepareOnlyOnce(preparation, fixture.doc, () => marketUrl,
    navigationFixture().storage, flow.transport, () => time);
  assert.equal(result.status, 'FAILED');
  assert.equal(result.reason, 'PREPARATION_REVOKED');
  assert.equal(fixture.writes(), 0);
  assert.equal(fixture.buyClicks(), 0);
});

test('the panel does not claim a prepared ticket from stale or malformed preparation state', async () => {
  for (const change of [{bridgeId: 'other'}, {serverTime: now - 4},
    {preparation: {...preparation.preparation, mode: 'LIVE', state: 'READY'}},
    {preparation: {...preparation.preparation, noSubmission: false, state: 'READY'}}]) {
    const fixture = ticketFixture();
    const children = await renderedPanel(observing, marketUrl, now, fixture.doc, {
      reply(message) {
        if (message.type === 'FUTURE_BTC5M_PREPARATION') return {ok: true,
          status: {...preparation, preparation: {...preparation.preparation, state: 'READY'}, ...change}};
        return message.type === 'FUTURE_BTC5M_PREFLIGHT' ? {ok: true} : {ok: true, status: observing};
      }});
    assert.doesNotMatch(children[9].textContent, /已准备/);
    assert.equal(fixture.writes(), 0);
    assert.equal(fixture.clicks(), 0);
  }
});

test('an empty amount and initially disabled Buy may be prepared but only enabled final readback can become READY', async () => {
  for (const enabledAfter of [true, false]) {
    const fixture = ticketFixture({buyDisabled: true, buyEnabledAfterAmount: enabledAfter});
    fixture.input.amount = '';
    const flow = preparationTransport();
    const result = await prepareOnlyOnce(preparation, fixture.doc, () => marketUrl,
      navigationFixture().storage, flow.transport, () => now);
    assert.equal(flow.claims(), 1);
    assert.equal(fixture.input.value, '1');
    assert.equal(fixture.directionClicks(), 1);
    assert.equal(fixture.buyClicks(), 0);
    assert.equal(result.status, enabledAfter ? 'READY' : 'FAILED');
    assert.equal(result.reason, enabledAfter ? null : 'POSTCHECK_FAILED');
    assert.equal(flow.reports.length, enabledAfter ? 1 : 0);
    assert.equal(flow.acknowledgements.length, 1);
  }
});

test('a disabled, inert or aria-disabled amount ancestor blocks preparation before claim while read-only inspection stays observable', async () => {
  for (const ancestor of [
    {tagName: 'FIELDSET', disabled: true},
    {tagName: 'DIV', inert: true},
    {tagName: 'DIV', getAttribute: (name) => name === 'aria-disabled' ? 'true' : null},
  ]) {
    const fixture = ticketFixture();
    fixture.input.parentElement = {...ancestor, textContent: '', querySelectorAll: () => [],
      parentElement: fixture.input.parentElement};
    const before = readPreflight(fixture.doc, marketUrl, now);
    assert.equal(before.ticketStatus, 'PASS');
    assert.equal(before.buyButtonEnabled, true);
    const flow = preparationTransport();
    const result = await prepareOnlyOnce(preparation, fixture.doc, () => marketUrl,
      navigationFixture().storage, flow.transport, () => now);
    assert.equal(result.status, 'FAILED');
    assert.equal(result.reason, 'TICKET_CHANGED');
    assert.equal(flow.claims(), 0);
    assert.equal(flow.acknowledgements.length, 0);
    assert.equal(fixture.writes(), 0);
    assert.equal(fixture.clicks(), 0);
    assert.deepEqual(fixture.input.events, []);
  }
});

test('Down 88 beats Up 12 even when BTC rises and the native ticket initially defaults to Up', async () => {
  const fixture = ticketFixture({upQuote: '12¢', downQuote: '88¢', buySide: '涨'});
  const flow = preparationTransport();
  const result = await prepareOnlyOnce(preparation, fixture.doc, () => marketUrl,
    navigationFixture().storage, flow.transport, () => now);
  assert.equal(result?.status, 'READY');
  assert.equal(fixture.directionClicks(), 1);
  assert.equal(flow.reports[0].selectedSide, 'Down');
  assert.equal(flow.reports[0].upQuoteCents, 12);
  assert.equal(flow.reports[0].downQuoteCents, 88);
  assert.equal(fixture.input.value, '1');
  assert.equal(fixture.buyClicks(), 0);
});

test('button quote parsing accepts only a single cents or percentage value on its exact direction', () => {
  for (const [text, side, amount] of [['涨 12¢', 'Up', 12], ['跌88%', 'Down', 88],
    ['涨\u00a050.25 ¢', 'Up', 50.25], ['跌\n100.00%', 'Down', 100], ['涨0¢', 'Up', 0]]) {
    assert.equal(parseButtonQuote(text, side), amount);
  }
  for (const text of ['跌12¢', '涨 --¢', '涨12', '涨$0.12', '涨-1¢', '涨101¢', '涨1e2¢',
    '涨05¢', '涨.5¢', '涨1,000¢', '涨12¢ 88¢', '涨12.123¢', '涨12%收益', '买入 涨']) {
    assert.equal(parseButtonQuote(text, 'Up'), null, text);
  }
});

test('schema1, unavailable, tied or stale quote intents never restore a default Up preparation', () => {
  for (const change of [{schemaVersion: 1}, {selectionSource: 'BTC_MOMENTUM'}, {upQuoteCents: null},
    {downQuoteCents: 101}, {upQuoteCents: 88}, {quoteObservedAt: now - 6},
    {quoteObservedAt: now + 1}, {side: 'Up'}, {cookie: 'secret'}]) {
    assert.equal(usablePreparation({...preparation, preparation: {...preparation.preparation,
      intent: {...preparationIntent, ...change}}}, now), null);
  }
  assert.ok(usablePreparation({...preparation, preparation: {...preparation.preparation,
    intent: {...preparationIntent, currentPrice: preparationIntent.openPrice}}}, now),
  'a flat BTC reference does not override the user button-price rule');
});

test('higher button selection is re-read at each phase and reversals or ties abort without a second direction click', async () => {
  for (const phase of ['beforeClaim', 'afterDirection', 'afterAmount']) {
    for (const quotes of [['90¢', '10¢'], ['50%', '50%'], ['--', '88¢']]) {
      let fixture;
      fixture = ticketFixture({afterDirection() {
        if (phase === 'afterDirection') fixture.setQuotes(...quotes);
      }, afterAmount() {
        if (phase === 'afterAmount') fixture.setQuotes(...quotes);
      }});
      if (phase === 'beforeClaim') fixture.setQuotes(...quotes);
      const flow = preparationTransport();
      const result = await prepareOnlyOnce(preparation, fixture.doc, () => marketUrl,
        navigationFixture().storage, flow.transport, () => now);
      assert.equal(result?.status, 'FAILED');
      assert.equal(result.reason, quotes[0] === '90¢' ? 'HIGHER_BUTTON_SIDE_CHANGED' :
        quotes[0] === '50%' ? 'BUTTON_QUOTES_TIED' : 'BUTTON_QUOTES_UNAVAILABLE');
      assert.equal(fixture.directionClicks(), phase === 'beforeClaim' ? 0 : 1);
      assert.equal(fixture.writes(), phase === 'afterAmount' ? 1 : 0);
      assert.equal(fixture.buyClicks(), 0);
      assert.equal(flow.claims(), phase === 'beforeClaim' ? 0 : 1);
    }
  }
});

test('same winning side may change quoted cents and must report current quotes without pretending the DOM sample is exchange time', async () => {
  let fixture;
  fixture = ticketFixture({afterDirection() { fixture.setQuotes('15%', '85%'); }});
  const flow = preparationTransport();
  const result = await prepareOnlyOnce(preparation, fixture.doc, () => marketUrl,
    navigationFixture().storage, flow.transport, () => now);
  assert.equal(result?.status, 'READY');
  assert.equal(flow.reports[0].upQuoteCents, 15);
  assert.equal(flow.reports[0].downQuoteCents, 85);
  assert.equal(flow.reports[0].checkedAt, now);
  assert.equal(fixture.buyClicks(), 0);
});

test('original quote receipt permission expires independently of a still-fresh BTC sample', async () => {
  let time = now;
  const initial = {...preparation, preparation: {...preparation.preparation,
    intent: {...preparationIntent, quoteObservedAt: now - 4}}};
  const claimed = {...initial, preparation: {...initial.preparation, state: 'CLAIMED',
    intent: {...initial.preparation.intent, claimToken: token}}};
  const fixture = ticketFixture({afterDirection() { time = now + 2; }});
  const flow = preparationTransport({claim: () => claimed, read: () => ({...claimed, serverTime: time})});
  const result = await prepareOnlyOnce(initial, fixture.doc, () => marketUrl,
    navigationFixture().storage, flow.transport, () => time);
  assert.equal(result?.status, 'FAILED');
  assert.equal(result.reason, 'BUTTON_QUOTES_NOT_FRESH');
  assert.equal(fixture.writes(), 0);
  assert.equal(fixture.buyClicks(), 0);
});

test('the higher Up button also overrides a falling BTC reference and an initially selected Down ticket', async () => {
  const initial = {...preparation, preparation: {...preparation.preparation,
    intent: {...preparationIntent, side: 'Up', upQuoteCents: 88, downQuoteCents: 12, currentPrice: 82979}}};
  const claimed = {...initial, preparation: {...initial.preparation, state: 'CLAIMED',
    intent: {...initial.preparation.intent, claimToken: token}}};
  const fixture = ticketFixture({upQuote: '88%', downQuote: '12¢', buySide: '跌'});
  const flow = preparationTransport({claim: () => claimed, read: () => claimed});
  const result = await prepareOnlyOnce(initial, fixture.doc, () => marketUrl,
    navigationFixture().storage, flow.transport, () => now);
  assert.equal(result?.status, 'READY');
  assert.equal(flow.reports[0].selectedSide, 'Up');
  assert.equal(fixture.directionClicks(), 1);
  assert.equal(fixture.buyClicks(), 0);
});

test('the worker accepts exact schema2 quote snapshots, keeps schema1 read-only compatibility and rejects extra quote data', async () => {
  let handler;
  const requests = [];
  class Clock extends Date { static now() { return now * 1000; } }
  vm.runInNewContext(readFileSync(new URL('./future-btc5m-extension/background.js', import.meta.url), 'utf8'), {
    URL, AbortSignal, Date: Clock, chrome: {runtime: {onMessage: {addListener(fn) { handler = fn; }}}},
    fetch: async (url, options) => { requests.push({url, options}); return {ok: true, json: async () => ({})}; },
  });
  const sender = {url: marketUrl, frameId: 0, tab: {id: 1, url: marketUrl}};
  const payload = {schemaVersion: 2, marketUrl, pagePeriodStart: start, checkedAt: now, navigation: 'CURRENT',
    ticketStatus: 'PASS', amountUsd: 1, selectedSide: 'Down', buyButtonEnabled: true, upQuoteCents: 12, downQuoteCents: 88};
  const {upQuoteCents, downQuoteCents, ...legacy} = payload;
  for (const report of [payload, {...legacy, schemaVersion: 1}, {...payload, upQuoteCents: null, downQuoteCents: null}]) {
    await new Promise((resolve) => {
      assert.equal(handler({type: 'FUTURE_BTC5M_PREFLIGHT', payload: report}, sender,
        (reply) => { assert.equal(reply.ok, true); resolve(); }), true);
    });
  }
  for (const change of [{schemaVersion: 3}, {upQuoteCents: '12'}, {upQuoteCents: -1}, {downQuoteCents: 100.01},
    {upQuoteCents: 12.123}, {downQuoteCents: Infinity}, {upQuoteCents: undefined},
    {quoteObservedAt: now}, {dom: 'private-page-data'}]) {
    assert.equal(handler({type: 'FUTURE_BTC5M_PREFLIGHT', payload: {...payload, ...change}}, sender, () => {}), undefined);
  }
  assert.equal(requests.length, 3);
  assert.deepEqual(JSON.parse(requests[0].options.body), payload);
  assert.equal(requests[0].options.credentials, 'omit');
  for (const reason of ['BUTTON_QUOTES_UNAVAILABLE', 'BUTTON_QUOTES_TIED', 'BUTTON_QUOTES_NOT_FRESH', 'HIGHER_BUTTON_SIDE_CHANGED']) {
    await new Promise((resolve) => {
      assert.equal(handler({type: 'FUTURE_BTC5M_PREPARATION_ACK', payload: {
        schemaVersion: 1, id: preparationIntent.id, claimToken: token, checkedAt: now, status: 'FAILED',
        marketUrl, amountUsd: 1, selectedSide: 'Down', reason, noSubmission: true,
      }}, sender, (reply) => { assert.equal(reply.ok, true); resolve(); }), true);
    });
  }
  assert.equal(requests.length, 7);
});
