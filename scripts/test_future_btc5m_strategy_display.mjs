import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const content = readFileSync(new URL('./future-btc5m-extension/content.js', import.meta.url), 'utf8');
const start = 1792235700;

async function panelFixture({online = true, series = '15m', page = '15m', preparationSeries = null} = {}) {
  let time = start + 155;
  const messages = [];
  const document = {body: {append(panel) {this.panel = panel;}}, querySelectorAll: () => [],
    createElement: () => ({style: {}, children: [], attributes: {},
      append(...children) {this.children.push(...children);}, addEventListener() {},
      setAttribute(name, value) {this.attributes[name] = value;}})};
  let tick;
  const storage = new Map();
  vm.runInNewContext(content, {URL, Event, document,
    Date: class extends Date {static now() {return time * 1000;}},
    location: {href: `https://future.news/zh/event/btc-updown-${page}-${start}`},
    sessionStorage: {getItem: (key) => storage.get(key) || null, setItem: (key, value) => storage.set(key, value)},
    setInterval(callback) {tick = callback;},
    FutureBtc5mBuyOnce: {createAutoBuyer: () => ({status: () => ({state: 'PAUSED'}), sync: () => ({state: 'OFF'})})},
    chrome: {runtime: {async sendMessage(message) {
      messages.push(message);
      if (!online) throw new Error('Extension context invalidated.');
      if (message.type === 'FUTURE_BTC5M_STATUS') return {ok: true, status: {
        schema_version: 1, mode: 'ASSIST_ONLY', live_enabled: false, amount_usd: 1,
        series, round_series: series, status: 'OBSERVING', period_start: start, server_time: time,
      }};
      if (message.type === 'FUTURE_BTC5M_PREPARATION') return {ok: true, status: {
        bridgeId: 'future-btc5m', serverTime: time, preparation: {series: preparationSeries ?? series, mode: 'PREPARE_ONLY',
          noSubmission: true, operatorAuthorized: true, authorizationSource: 'USER_REQUEST',
          enabled: false, state: 'DISABLED', intent: null, reasons: ['AUTO_PREPARATION_DISABLED']},
      }};
      if (message.type === 'FUTURE_BTC5M_SCHEDULE') return {ok: true, status: {weekendOnly: true}};
      return {ok: true};
    }}},
  });
  const settle = () => new Promise((resolve) => setImmediate(resolve));
  await settle();
  const body = document.body.panel.children[1];
  const details = body.children.find((child) => child.id === 'polyhermes-btc5m-details');
  return {title: document.body.panel.children[0].children[0],
    current: body.children.find((child) => child.id === 'polyhermes-btc5m-current'),
    note: details.children[7], diagnostic: details.children[1], messages,
    async disconnect() {online = false; time += 5; tick(); await settle();},
    async changeSeries(value) {series = value; time++; tick(); await settle();},
  };
}

test('confirmed BTC15m presentation stays consistent after extension invalidation', async () => {
  const panel = await panelFixture();
  assert.match(panel.note.textContent, /当前策略：BTC 15 分钟/);
  await panel.disconnect();
  for (const element of [panel.title, panel.current, panel.note]) {
    assert.match(element.textContent, /15 分钟/);
    assert.doesNotMatch(element.textContent, /BTC 5 分钟|BTC 5m|60–80/);
  }
  assert.match(panel.note.textContent, /上次确认|未核实/);
  assert.match(panel.note.textContent, /150–170/);
  assert.match(panel.note.textContent, /4\.16 基点\/分钟（R1 高波动过滤）/, 'the 15m note must state the R1 skip');
  assert.match(panel.current.textContent, /19:15–19:30/);
  assert.match(panel.current.textContent, /开关未核实/);
  assert.match(panel.diagnostic.textContent, /扩展.*失效.*刷新/);
  assert.ok(panel.messages.every(({type}) => !/CLAIM|ACK|AUDIT|SET/.test(type)), 'display repair must not submit or change controls');
});

test('an offline first load identifies the 15m page but never invents a selected strategy', async () => {
  const panel = await panelFixture({online: false});
  assert.match(panel.title.textContent, /15 分钟|策略未核实/);
  assert.match(panel.note.textContent, /策略.*未核实/);
  assert.doesNotMatch(panel.note.textContent, /当前策略：BTC 5|60–80/);
  assert.match(panel.current.textContent, /19:15–19:30|轮次未核实/);
});

test('a fresh strategy change replaces the remembered label across all display sections', async () => {
  const panel = await panelFixture();
  await panel.changeSeries('5m');
  assert.match(panel.title.textContent, /BTC 5 分钟/);
  assert.match(panel.note.textContent, /当前策略：BTC 5 分钟/);
  assert.match(panel.current.textContent, /BTC 5 分钟/);
  assert.doesNotMatch(panel.note.textContent, /反 1 小时|150–170/);
});

test('conflicting fresh strategy reports are shown as unknown instead of preferring 5m', async () => {
  const panel = await panelFixture({series: '15m', preparationSeries: '5m'});
  assert.match(panel.title.textContent, /策略状态冲突/);
  assert.match(panel.current.textContent, /轮次未核实/);
  assert.doesNotMatch(panel.note.textContent, /当前策略：BTC 5|当前策略：BTC 15/);
});

test('an offline non-market page has no default 5m strategy or fabricated round', async () => {
  const panel = await panelFixture({online: false, page: 'unknown'});
  assert.match(panel.title.textContent, /策略未核实/);
  assert.match(panel.current.textContent, /轮次未核实/);
  assert.doesNotMatch(panel.note.textContent, /BTC 5 分钟|60–80|150–170/);
});
