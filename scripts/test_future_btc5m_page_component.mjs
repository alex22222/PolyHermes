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
    preparation: {mode: 'PREPARE_ONLY', noSubmission: true, operatorAuthorized: true,
      authorizationSource: 'USER_REQUEST', enabled: false, state: 'DISABLED', intent: null,
      lastAttempt: null, reasons: ['AUTO_PREPARATION_DISABLED']},
    signal: {slug: `btc-updown-5m-${start}`, side: 'Up', period_start: start, period_end: start + 300,
      price_observed_at: second - 1, open_price: 82000, current_price: 82001,
      price_source: 'chainlink', open_price_source: 'polymarket_crypto_price_fiveminute_twap60_openPrice',
      twap_lookback_seconds: 60},
    preflight: {mode: 'READ_ONLY', noSubmission: true, browserConnected: true,
      checkedAt: second, receivedAt: second, pagePeriodStart: start, navigation: 'CURRENT',
      ticketStatus: 'PASS', amountUsd: 1, selectedSide: 'Up', buyButtonEnabled: true,
      signalFresh: true, signalSide: 'Up', sideMatches: true, upQuoteCents: 54, downQuoteCents: 46,
      preferredSide: 'Up', selectionSource: 'HIGHER_BUTTON_PRICE', result: 'READ_ONLY_READY', reasons: []},
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

const preparationIntent = () => ({schemaVersion: 2, id: `future-btc5m-prepare:${start}`,
  slug: `btc-updown-5m-${start}`, periodStart: start, periodEnd: start + 300, side: 'Up', amountUsd: 1,
  createdAt: start + 65, expiresAt: start + 80, priceObservedAt: start + 65,
  openPrice: 82000, currentPrice: 82001, priceSource: 'chainlink',
  openPriceSource: 'polymarket_crypto_price_fiveminute_twap60_openPrice', twapLookbackSeconds: 60,
  mode: 'PREPARE_ONLY', noSubmission: true, operatorAuthorized: true,
  authorizationSource: 'USER_REQUEST', claimToken: null, upQuoteCents: 54, downQuoteCents: 46,
  quoteObservedAt: start + 65, selectionSource: 'HIGHER_BUTTON_PRICE'});

test('the switch controls ticket preparation and the extension buy with no running server executor', async () => {
  const page = mountPage(receipt);
  await page.reply('status', healthyStatus());
  assert.equal(page.elements((node) => node.type === 'Card' && node.props.title === '自动准备票据控制').length, 1);
  assert.equal(page.field('最终买入'), '浏览器扩展在票据准备好后自动点击（每轮最多一次）');
  assert.equal(page.field('实际下单'), '未运行');
  assert.equal(page.field('准备阶段'), '已关闭');
  assert.equal(page.elements((node) => node.type === 'Card' && node.props.title === '真实订单与历史跳过记录').length, 1);
  page.elements((node) => node.type === 'Switch')[0].props.onChange(true);
  const enabled = healthyStatus();
  enabled.requestedEnabled = true;
  enabled.mode = 'BLOCKED';
  enabled.preparation = {...enabled.preparation, enabled: true, state: 'WAITING_SIGNAL', reasons: ['WAITING_CURRENT_SIGNAL']};
  await page.reply('control', enabled);
  assert.equal(page.elements((node) => node.type === 'Switch')[0].props.checked, true);
  assert.equal(page.field('准备阶段'), '等待有效信号');
  assert.equal(page.field('实际下单'), '未运行');
});

test('pending ticket evidence expires at the entry boundary between polls', async () => {
  const page = mountPage(receipt);
  const value = healthyStatus();
  value.requestedEnabled = true;
  value.mode = 'BLOCKED';
  value.preparation = {...value.preparation, enabled: true, state: 'PENDING', intent: preparationIntent(), reasons: []};
  await page.reply('status', value);
  assert.equal(page.field('准备阶段'), '等待 Chrome 准备');
  assert.equal(page.field('待准备方向 / 金额'), 'Up / $1');
  page.tick(receipt + 5001);
  assert.equal(page.field('准备阶段'), '等待有效信号');
  assert.equal(page.field('待准备方向 / 金额'), '—');
  page.tick((start + 80) * 1000);
  assert.equal(page.field('准备阶段'), '已过期');
  assert.equal(page.field('待准备方向 / 金额'), '—');
});

test('a ready operation report stays separate from real orders and never claims a fill', async () => {
  const page = mountPage(receipt);
  const value = healthyStatus();
  value.requestedEnabled = true;
  value.mode = 'BLOCKED';
  value.preparation = {...value.preparation, enabled: true, state: 'READY', reasons: [],
    lastAttempt: {...preparationIntent(), state: 'READY', claimToken: 'a'.repeat(32),
      updatedAt: start + 65, claimedAt: start + 65, reason: null,
      receipt: {checkedAt: start + 65, marketUrl: `https://future.news/zh/event/btc-updown-5m-${start}`,
        amountUsd: 1, selectedSide: 'Up'}}};
  await page.reply('status', value);
  assert.equal(page.field('准备阶段'), '票据已准备，交由扩展自动买入');
  assert.equal(page.field('准备报告金额 / 方向'), '$1 / Up');
  assert.equal(page.field('实际下单'), '未运行');
  assert.equal(page.field('待准备方向 / 金额'), '—');
  assert.equal(page.elements((node) => node.type === 'Table')[0].props.dataSource.length, 0);
  page.tick(receipt + 5001);
  assert.equal(page.field('准备阶段'), '等待有效信号');
  assert.equal(page.field('最近准备结果'), '票据已准备，交由扩展自动买入');
  page.tick((start + 80) * 1000);
  assert.equal(page.field('准备阶段'), '已过期');
  assert.equal(page.field('最近准备结果'), '票据已准备，交由扩展自动买入');
});

test('disabled preparation retains its historical report without current permission', async () => {
  const page = mountPage(receipt);
  const value = healthyStatus();
  value.preparation.lastAttempt = {...preparationIntent(), schemaVersion: 1, upQuoteCents: null, downQuoteCents: null,
    quoteObservedAt: null, selectionSource: null, state: 'REVOKED',
    updatedAt: start + 65, claimedAt: null, reason: 'PREPARATION_REVOKED', receipt: null};
  await page.reply('status', value);
  assert.equal(page.field('准备阶段'), '已关闭');
  assert.equal(page.field('最近准备结果'), '已撤销');
  assert.equal(page.field('待准备方向 / 金额'), '—');
  assert.equal(page.field('实际下单'), '未运行');
});


const higherButtonStatus = (flat = false) => {
  const value = healthyStatus();
  const intent = {...preparationIntent(), schemaVersion: 2, side: 'Down', upQuoteCents: 12,
    downQuoteCents: 88, quoteObservedAt: start + 65, selectionSource: 'HIGHER_BUTTON_PRICE',
    currentPrice: flat ? 82000 : 82001};
  if (flat) value.signal = {...value.signal, side: null, current_price: 82000};
  value.preflight = {...value.preflight, selectedSide: 'Down', signalSide: flat ? null : 'Up',
    upQuoteCents: 12, downQuoteCents: 88, preferredSide: 'Down', selectionSource: 'HIGHER_BUTTON_PRICE'};
  value.requestedEnabled = true;
  value.mode = 'BLOCKED';
  value.preparation = {...value.preparation, enabled: true, state: 'READY', reasons: [],
    lastAttempt: {...intent, state: 'READY', claimToken: 'a'.repeat(32),
      updatedAt: start + 65, claimedAt: start + 65, reason: null,
      receipt: {checkedAt: start + 65, marketUrl: `https://future.news/zh/event/btc-updown-5m-${start}`,
        amountUsd: 1, selectedSide: 'Down'}}};
  return value;
};

test('higher Down button quote remains READY when Chainlink points Up or is flat', async () => {
  for (const flat of [false, true]) {
    const page = mountPage(receipt);
    await page.reply('status', higherButtonStatus(flat));
    assert.equal(page.field('准备阶段'), '票据已准备，交由扩展自动买入');
    assert.equal(page.field('按钮报价方向'), 'Down');
    assert.equal(page.field('观察方向'), flat ? '平价' : 'Up');
    assert.equal(page.field('Up / Down 按钮报价'), '12¢ / 88¢');
    assert.equal(page.field('准备报告金额 / 方向'), '$1 / Down');
    assert.equal(page.field('实际下单'), '未运行');
  }
});

test('frozen original quotes and changed current button winner revoke current READY between polls', async () => {
  for (const change of [{quoteObservedAt: start + 59}, {schemaVersion: 1}]) {
    const page = mountPage(receipt);
    const value = higherButtonStatus();
    value.preparation.lastAttempt = {...value.preparation.lastAttempt, ...change};
    await page.reply('status', value);
    assert.equal(page.field('准备阶段'), '等待有效信号');
    assert.equal(page.field('最近准备结果'), '票据已准备，交由扩展自动买入');
  }
  const page = mountPage(receipt);
  const value = higherButtonStatus();
  value.preflight = {...value.preflight, upQuoteCents: 90, downQuoteCents: 10, preferredSide: 'Up',
    sideMatches: false, result: 'BLOCKED', reasons: ['SIDE_MISMATCH']};
  await page.reply('status', value);
  assert.equal(page.field('准备阶段'), '等待有效信号');
});


test('a button quote tie or missing quote cannot display an active preparation or ready result', async () => {
  for (const change of [{upQuoteCents: 88, preferredSide: null}, {downQuoteCents: null, preferredSide: null}]) {
    const page = mountPage(receipt);
    const value = higherButtonStatus();
    value.preflight = {...value.preflight, ...change, result: 'BLOCKED', sideMatches: false, reasons: ['BUTTON_QUOTES_TIED']};
    await page.reply('status', value);
    assert.equal(page.field('准备阶段'), '等待有效信号');
    assert.equal(page.field('按钮报价方向'), '等待不同且有效的按钮报价');
    assert.equal(page.field('待准备方向 / 金额'), '—');
    assert.equal(page.field('实际下单'), '未运行');
  }
});


test('READY requires the current read-only preflight result to have passed', async () => {
  const page = mountPage(receipt);
  const value = higherButtonStatus();
  value.preflight = {...value.preflight, result: 'BLOCKED', reasons: ['BROWSER_CHECK_OUTSIDE_ENTRY']};
  await page.reply('status', value);
  assert.equal(page.field('准备阶段'), '等待有效信号');
  assert.equal(page.field('最近准备结果'), '票据已准备，交由扩展自动买入');
});
