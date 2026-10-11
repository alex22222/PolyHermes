import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import ts from '../frontend/node_modules/typescript/lib/typescript.js';

const transpile = (path, jsx = ts.JsxEmit.ReactJSX) => ts.transpileModule(
  readFileSync(new URL(path, import.meta.url), 'utf8'),
  {compilerOptions: {module: ts.ModuleKind.CommonJS, jsx}},
).outputText;
const guards = {exports: {}};
vm.runInNewContext(transpile('../frontend/src/utils/futureBtc5mPreflight.ts'), guards);
const componentSource = transpile('../frontend/src/pages/FutureBtc5mBridge.tsx');
const start = 1791706200;
const receipt = (start + 65) * 1000;

const healthyStatus = (at = receipt) => {
  const second = at / 1000;
  return {bridgeId: 'future-btc5m', online: true, requestedEnabled: false, effectiveEnabled: false,
    amountUsd: 1, series: '5m', mode: 'DISABLED', serverTime: second,
    periodStart: start, feedStatus: 'CURRENT', executorReady: false, blockReasons: [],
    orderCounts: {total: 0, pending: 0, submitted: 0, filled: 0, failed: 0, skipped: 0},
    signal: {slug: `btc-updown-5m-${start}`, side: 'Up', period_start: start, period_end: start + 300,
      price_observed_at: second - 1, open_price: 82000, current_price: 82001,
      price_source: 'chainlink', open_price_source: 'polymarket_crypto_price_fiveminute_twap60_openPrice',
      twap_lookback_seconds: 60},
    preflight: {mode: 'READ_ONLY', noSubmission: true, browserConnected: true,
      checkedAt: second, receivedAt: second, pagePeriodStart: start, navigation: 'CURRENT',
      ticketStatus: 'PASS', amountUsd: 1, selectedSide: 'Up', buyButtonEnabled: true,
      signalFresh: true, signalSide: 'Up', sideMatches: true, result: 'READ_ONLY_READY', reasons: []},
  };
};

// Execute the real component callbacks with state/effect slots; no DOM or network is involved.
const mountPage = (initialTime) => {
  let now = initialTime;
  let cursor = 0;
  let tree;
  const slots = [];
  const effects = [];
  const intervals = new Map();
  const requests = {status: [], control: []};
  const sameDeps = (left, right) => left && right && left.length === right.length &&
    left.every((value, index) => Object.is(value, right[index]));
  const react = {
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = {value: typeof initial === 'function' ? initial() : initial};
      return [slots[index].value, (value) => {
        slots[index].value = typeof value === 'function' ? value(slots[index].value) : value;
      }];
    },
    useRef(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = {value: {current: initial}};
      return slots[index].value;
    },
    useCallback(callback, deps) {
      const index = cursor++;
      if (!(index in slots) || !sameDeps(slots[index].deps, deps)) slots[index] = {value: callback, deps};
      return slots[index].value;
    },
    useEffect(callback, deps) {
      const index = cursor++;
      if (!(index in slots) || !sameDeps(slots[index].deps, deps)) {
        slots[index] = {deps};
        effects.push(callback);
      }
    },
  };
  const pending = (kind) => () => new Promise((resolve) => requests[kind].push(resolve));
  const antd = Object.fromEntries(['Alert', 'Button', 'Card', 'Drawer', 'Empty', 'Select', 'Space',
    'Spin', 'Switch', 'Table', 'Tag'].map((name) => [name, name]));
  antd.Descriptions = Object.assign('Descriptions', {Item: 'Descriptions.Item'});
  antd.Typography = {Title: 'Typography.Title', Text: 'Typography.Text', Link: 'Typography.Link'};
  antd.message = {success() {}, error() {}};
  const modules = {
    react,
    'react/jsx-runtime': {jsx: (type, props) => ({type, props}), jsxs: (type, props) => ({type, props})},
    antd,
    '@ant-design/icons': {ReloadOutlined: 'ReloadOutlined'},
    'react-responsive': {useMediaQuery: () => false},
    '../services/api': {apiService: {futureBtc5mBridge: {
      status: pending('status'), control: pending('control'),
      list: async () => ({data: {code: 0, data: {list: [], total: 0}}}),
    }}},
    '../utils/futureBtc5mPreflight': guards.exports,
  };
  const sandbox = {exports: {}, Date: class extends Date {static now() {return now;}},
    window: {setInterval(callback, delay) {
      const id = intervals.size + 1;
      intervals.set(id, {callback, delay});
      return id;
    }, clearInterval(id) {intervals.delete(id);}},
    require: (name) => {
      assert.ok(name in modules, `unexpected component import: ${name}`);
      return modules[name];
    },
  };
  vm.runInNewContext(componentSource, sandbox);
  const render = () => {
    cursor = 0;
    tree = sandbox.exports.default();
    for (const effect of effects.splice(0)) effect();
    return tree;
  };
  const elements = (predicate) => {
    const matches = [];
    const visit = (value) => {
      if (Array.isArray(value)) return value.forEach(visit);
      if (!value || typeof value !== 'object' || !value.props) return;
      if (predicate(value)) matches.push(value);
      visit(value.props.children);
    };
    visit(tree);
    return matches;
  };
  const text = (value) => Array.isArray(value) ? value.map(text).join('') :
    value && typeof value === 'object' ? text(value.props?.children) : value == null ? '' : String(value);
  render();
  return {render, elements,
    field: (label) => text(elements((node) => node.type === 'Descriptions.Item' && node.props.label === label)[0]),
    expiredAlert: () => elements((node) => node.type === 'Alert' && node.props.message === '运行状态已过期，请刷新核对'),
    setTime(at) {now = at;},
    tick(at) {
      now = at;
      for (const interval of intervals.values()) if (interval.delay === 1000) interval.callback();
      render();
    },
    poll(at) {
      now = at;
      for (const interval of intervals.values()) if (interval.delay === 5000) interval.callback();
    },
    async reply(kind, value) {
      assert.ok(requests[kind].length, `${kind} request must already be pending`);
      requests[kind].shift()({data: {code: 0, data: value}});
      await new Promise((resolve) => setImmediate(resolve));
      render();
    },
  };
};

const assertHealthy = (page) => {
  assert.equal(page.expiredAlert().length, 0, 'a successful current response must not flash an expired-status alert');
  assert.equal(page.field('观察方向'), 'Up', 'a fresh response must retain its valid direction');
  assert.equal(page.field('Chrome 预检报告'), '新鲜', 'a fresh response must retain its browser evidence');
  assert.equal(page.elements((node) => node.type === 'Switch')[0].props.disabled, false);
};

test('first healthy response between clock ticks never renders an expired status', async () => {
  const page = mountPage(receipt - 700);
  page.setTime(receipt);
  await page.reply('status', healthyStatus());
  assertHealthy(page);
});

test('healthy five-second polling responses do not flash expired status before the next tick', async () => {
  const page = mountPage(receipt);
  await page.reply('status', healthyStatus());
  assertHealthy(page);
  page.tick(receipt + 4000);
  page.poll(receipt + 4500);
  page.setTime(receipt + 4800);
  await page.reply('status', healthyStatus(receipt + 4800));
  assertHealthy(page);
});

test('successful close-control response between ticks retains current status and evidence', async () => {
  const page = mountPage(receipt);
  await page.reply('status', healthyStatus());
  page.setTime(receipt + 900);
  page.elements((node) => node.type === 'Button' && node.props.danger)[0].props.onClick();
  await page.reply('control', healthyStatus(receipt + 900));
  assertHealthy(page);
});

test('a real fifteen-second status lapse still displays the expired alert', async () => {
  const page = mountPage(receipt);
  await page.reply('status', healthyStatus());
  page.tick(receipt + 15001);
  assert.equal(page.expiredAlert().length, 1);
  assert.equal(page.elements((node) => node.type === 'Switch')[0].props.disabled, true);
});

test('a received server timestamp outside the three-second tolerance remains invalid', async () => {
  const page = mountPage(receipt);
  await page.reply('status', healthyStatus(receipt - 4000));
  assert.equal(page.expiredAlert().length, 1);
  assert.equal(page.field('观察方向'), '采样已过期');
});

test('a wall-clock rollback after receipt remains invalid', async () => {
  const page = mountPage(receipt);
  await page.reply('status', healthyStatus());
  page.tick(receipt - 1);
  assert.equal(page.expiredAlert().length, 1);
  assert.equal(page.field('Chrome 预检报告'), '未连接或已过期');
});
