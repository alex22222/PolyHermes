import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('./future-btc5m-extension/background.js', import.meta.url), 'utf8');
const profileUrl = 'https://future.news/zh/address/0x' + '1'.repeat(40) + '?tab=activity';
const marketUrl = 'https://future.news/zh/event/btc-updown-15m-1792123200';
const profileSender = {url: profileUrl, frameId: 0, tab: {id: 1, url: profileUrl}};

function worker(respond = null) {
  let handler;
  const requests = [];
  vm.runInNewContext(source, {URL, AbortSignal,
    chrome: {runtime: {onMessage: {addListener(fn) { handler = fn; }}}},
    fetch: async (url, options) => {
      requests.push({url, options});
      return {ok: true, json: async () => respond ? respond(url, options) :
        url.endsWith('/schedule') ? {weekendOnly: true} :
          {bridgeId: 'future-btc5m', preparation: {enabled: true, state: 'WAITING_SIGNAL'}}};
    }});
  return {requests, rejected(message, sender) {
    assert.equal(handler(message, sender, () => assert.fail('rejected message replied')), undefined);
  }, async send(message, sender = profileSender) {
    let reply;
    assert.equal(handler(message, sender, (value) => { reply = value; }), true);
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(reply?.ok, true);
    return reply.status;
  }};
}

test('the account activity page reads the actual preparation and weekend states', async () => {
  const value = worker();
  assert.equal((await value.send({type: 'FUTURE_BTC5M_PREPARATION'})).preparation.enabled, true);
  assert.equal((await value.send({type: 'FUTURE_BTC5M_SCHEDULE'})).weekendOnly, true);
  assert.deepEqual(value.requests.map(({url}) => url), [
    'http://127.0.0.1:8766/bridge/preparation', 'http://127.0.0.1:8766/bridge/preparation/schedule']);
  for (const {options} of value.requests) {
    assert.equal(options.method, 'GET');
    assert.equal(options.body, undefined);
    assert.equal(options.credentials, 'omit');
    assert.equal(options.headers['X-PolyHermes-Future-Preparation'], '1');
  }
});

test('profile schedule writes preserve the exact existing boolean-only contract', async () => {
  const value = worker();
  await value.send({type: 'FUTURE_BTC5M_SCHEDULE_SET', payload: {weekendOnly: true}});
  assert.equal(value.requests[0].url, 'http://127.0.0.1:8766/bridge/preparation/schedule');
  assert.equal(value.requests[0].options.method, 'POST');
  assert.equal(value.requests[0].options.body, '{"weekendOnly":true}');
  for (const message of [{type: 'FUTURE_BTC5M_SCHEDULE', payload: {}},
    {type: 'FUTURE_BTC5M_PREPARATION', payload: {}},
    {type: 'FUTURE_BTC5M_SCHEDULE_SET', payload: {weekendOnly: 'true'}},
    {type: 'FUTURE_BTC5M_SCHEDULE_SET', payload: {weekendOnly: true, enabled: true}}]) {
    value.rejected(message, profileSender);
  }
  assert.equal(value.requests.length, 1);
});

test('profile reads tolerate a trusted SPA transition without granting market mutations', async () => {
  const value = worker();
  for (const sender of [{...profileSender, tab: {id: 1, url: marketUrl}},
    {...profileSender, url: marketUrl}]) {
    await value.send({type: 'FUTURE_BTC5M_PREPARATION'}, sender);
    await value.send({type: 'FUTURE_BTC5M_SCHEDULE'}, sender);
    for (const message of [{type: 'FUTURE_BTC5M_MARKET_QUOTE'},
      {type: 'FUTURE_BTC5M_PREPARATION_CLAIM', payload: {schemaVersion: 1, id: 'future-btc15m-prepare:1792123200'}},
      {type: 'FUTURE_BTC5M_PREPARATION_ACK', payload: {}},
      {type: 'FUTURE_BTC5M_BUY_AUDIT', payload: {}}]) value.rejected(message, sender);
  }
  assert.equal(value.requests.length, 4);
});

test('foreign documents, subframes and malformed profile paths cannot access controls', () => {
  const value = worker();
  for (const sender of [{...profileSender, frameId: 1}, {...profileSender, frameId: undefined},
    {...profileSender, tab: undefined},
    ...['https://evil.test/', 'https://future.news.evil.test/zh/address/0x' + '1'.repeat(40),
      profileUrl.replace('https:', 'http:'), profileUrl.replace('future.news', 'user:pass@future.news'),
      'https://future.news/zh/address/0x1234', 'https://future.news/zh/address/' + 'g'.repeat(40)]
      .flatMap((url) => [{...profileSender, url}, {...profileSender, tab: {id: 1, url}}])]) {
    for (const type of ['FUTURE_BTC5M_PREPARATION', 'FUTURE_BTC5M_SCHEDULE']) value.rejected({type}, sender);
    value.rejected({type: 'FUTURE_BTC5M_SCHEDULE_SET', payload: {weekendOnly: true}}, sender);
  }
  assert.equal(value.requests.length, 0);
});

test('the real account-page panel shows confirmed controls without preparing or buying', async () => {
  const now = 1792123265;
  let weekendOnly = false;
  const value = worker((url, options) => {
    if (url.endsWith('/schedule')) {
      if (options.method === 'POST') weekendOnly = JSON.parse(options.body).weekendOnly;
      return {weekendOnly};
    }
    if (url.endsWith('/status')) return {schema_version: 1, mode: 'ASSIST_ONLY', live_enabled: false,
      amount_usd: 1, status: 'OBSERVING', reason: 'GEOBLOCK_BLOCKED', server_time: now,
      series: '15m', round_series: '15m', period_start: 1792123200, draft: null, signal: null};
    return {bridgeId: 'future-btc5m', serverTime: now, preparation: {enabled: true, mode: 'PREPARE_ONLY',
      noSubmission: true, operatorAuthorized: true, authorizationSource: 'USER_REQUEST',
      state: 'WAITING_SIGNAL', series: '15m', reasons: ['WAITING_CURRENT_SIGNAL'], intent: null, lastAttempt: null}};
  });
  const messages = [];
  let clicks = 0;
  const elements = [];
  const body = {append(panel) { this.panel = panel; }};
  const document = {body, querySelectorAll: () => [], createElement: () => {
    const element = {style: {}, children: [], listeners: {}, attributes: {},
      append(...children) { this.children.push(...children); },
      setAttribute(name, value) { this.attributes[name] = value; },
      getAttribute(name) { return this.attributes[name] ?? null; },
      addEventListener(type, fn) { this.listeners[type] = fn; }, click() { clicks++; }};
    elements.push(element);
    return element;
  }};
  const values = new Map();
  const storage = {getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, value)};
  class Clock extends Date { static now() { return now * 1000; } }
  const sandbox = vm.createContext({URL, Event, Date: Clock, document, location: {href: profileUrl},
    sessionStorage: storage, localStorage: storage, setInterval: () => 1, clearInterval() {},
    navigator: {locks: {request: (_name, _options, run) => run()}},
    chrome: {runtime: {sendMessage: async (message) => {
      messages.push(message);
      return {ok: true, status: await value.send(message)};
    }}}});
  vm.runInContext(readFileSync(new URL('./future-btc5m-extension/content.js', import.meta.url), 'utf8'), sandbox);
  vm.runInContext(readFileSync(new URL('./future-btc5m-extension/buy_once.js', import.meta.url), 'utf8'), sandbox);
  const checkbox = elements.find((element) => element.type === 'checkbox');
  for (let turn = 0; turn < 8 && checkbox.disabled; turn++) {
    await new Promise((resolve) => setImmediate(resolve));
  }
  assert.equal(checkbox.disabled, false, JSON.stringify({messages: messages.map(({type}) => type),
    text: elements.map(({textContent}) => textContent).filter(Boolean)}));
  assert.equal(checkbox.checked, false);
  assert.match(elements.find((element) => element.id === 'polyhermes-btc5m-current').textContent, /自动买入已开启/);
  checkbox.checked = true;
  await checkbox.listeners.change();
  assert.equal(checkbox.checked, true);
  assert.equal(checkbox.disabled, false);
  assert.equal(weekendOnly, true);
  assert.equal(clicks, 0);
  assert.equal(messages.some(({type}) => /CLAIM|ACK|QUOTE|AUDIT|PREFLIGHT/.test(type)), false);
});
