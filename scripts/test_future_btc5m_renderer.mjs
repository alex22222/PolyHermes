import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const background = readFileSync(new URL('./future-btc5m-extension/background.js', import.meta.url), 'utf8');
const renderer = readFileSync(new URL('./future-btc5m-extension/renderer.js', import.meta.url), 'utf8');
const url = 'https://future.news/zh/event/btc-updown-5m-1791650700';
const flush = () => new Promise((resolve) => setImmediate(resolve));

function worker({granted = true, attach, command} = {}) {
  const connected = [], calls = [], power = [];
  let updated, removed, detached;
  let context;
  const chrome = {
    runtime: {getManifest: () => ({permissions: granted ? ['power', 'debugger'] : ['power']}),
      onConnect: {addListener(fn) { connected.push(fn); }}, onMessage: {addListener() {}}},
    power: {requestKeepAwake(level) {power.push(level);}, releaseKeepAwake() {}},
    tabs: {onUpdated: {addListener(fn) {updated = fn;}}, onRemoved: {addListener(fn) {removed = fn;}}},
    debugger: {onDetach: {addListener(fn) {detached = fn;}},
      async attach(target, version) {calls.push(['attach', {...target}, version]); await attach?.();},
      async sendCommand(target, method, params) {
        assert.equal(method, 'Emulation.setFocusEmulationEnabled');
        assert.deepEqual(Object.keys(params), ['enabled']);
        assert.equal(typeof params.enabled, 'boolean');
        calls.push(['command', {...target}, method, {...params}]);
        await command?.(params.enabled);
      },
      async detach(target) {calls.push(['detach', {...target}]);}},
  };
  context = vm.createContext({chrome, URL, AbortSignal, Date, setTimeout() { return 1; }, clearTimeout() {},
    WebSocket: class {close() {}}, fetch() {assert.fail('renderer must never fetch a control or order');},
    importScripts(path) {
      assert.equal(path, 'renderer.js');
      vm.runInContext(renderer, context);
    }});
  vm.runInContext(background, context);
  const port = (changes = {}) => {
    const disconnect = [], receive = [], messages = [];
    const value = {name: 'FUTURE_BTC5M_RUNTIME', sender: {url, frameId: 0, tab: {id: 7, url}},
      onDisconnect: {addListener(fn) {disconnect.push(fn);}},
      onMessage: {addListener(fn) {receive.push(fn);}},
      postMessage(message) {messages.push(JSON.parse(JSON.stringify(message)));},
      disconnect() {this.closed = true; disconnect.forEach(fn => fn());}, ...changes};
    connected.forEach(fn => fn(value));
    return {value, messages, reply: message => receive.forEach(fn => fn(message))};
  };
  return {port, calls, power, update: (...args) => updated?.(...args), remove: (...args) => removed?.(...args),
    detach: (...args) => detached?.(...args)};
}

test('rendering capability never loads or attaches without the separately approved debugger permission', async () => {
  const w = worker({granted: false});
  w.port();
  await flush();
  assert.deepEqual(w.calls, []);
});

test('only a trusted BTC5m top frame gets the fixed focus command; no screenshots, input or arbitrary scripts', async () => {
  const w = worker();
  const p = w.port();
  await flush();
  assert.deepEqual(w.calls, [['attach', {tabId: 7}, '1.3'],
    ['command', {tabId: 7}, 'Emulation.setFocusEmulationEnabled', {enabled: true}]]);
  assert.deepEqual(p.messages.at(-1), {type: 'FUTURE_BTC5M_RENDERER_STATUS', state: 'ACTIVE'});
  p.value.disconnect();
  await flush();
  assert.deepEqual(w.calls.slice(-2), [['command', {tabId: 7}, 'Emulation.setFocusEmulationEnabled', {enabled: false}],
    ['detach', {tabId: 7}]]);
});

test('foreign origins, stale trusted tab URLs, subframes and malformed tab IDs never attach', async () => {
  const w = worker();
  for (const sender of [{url: 'https://example.com', frameId: 0, tab: {id: 7, url}},
    {url, frameId: 1, tab: {id: 7, url}}, {url, frameId: 0, tab: {id: 7, url: 'https://future.news/zh/settings'}},
    {url, frameId: 0, tab: {id: -1, url}}, {url, frameId: 0, tab: {id: '7', url}}]) {
    w.port({sender});
  }
  await flush();
  assert.deepEqual(w.calls, []);
});

test('multiple ports share ownership and only the last disconnect releases it', async () => {
  const w = worker();
  const first = w.port(), second = w.port();
  await flush();
  first.value.disconnect();
  await flush();
  assert.equal(w.calls.length, 2);
  second.value.disconnect();
  await flush();
  assert.equal(w.calls.filter(c => c[0] === 'attach').length, 1);
  assert.equal(w.calls.filter(c => c[0] === 'detach').length, 1);
});

test('a disconnect while attach is pending cannot enable focus and cleans up only its own attachment', async () => {
  let resolve;
  const w = worker({attach: () => new Promise(r => {resolve = r;})});
  const p = w.port();
  await flush();
  p.value.disconnect();
  resolve();
  await flush();
  assert.deepEqual(w.calls, [['attach', {tabId: 7}, '1.3'], ['detach', {tabId: 7}]]);
});

test('an attachment failure never detaches another debugger or claims rendering is active', async () => {
  const w = worker({attach: async () => {throw new Error('another debugger owns the target');}});
  const p = w.port();
  await flush();
  p.value.disconnect();
  await flush();
  assert.equal(w.calls.length, 1);
  assert.deepEqual(p.messages.at(-1), {type: 'FUTURE_BTC5M_RENDERER_STATUS', state: 'ERROR'});
});

test('manual cancellation is respected and fresh page ports cannot automatically reattach', async () => {
  const w = worker();
  const p = w.port();
  await flush();
  w.detach({tabId: 7}, 'canceled_by_user');
  const later = w.port();
  await flush();
  assert.equal(w.calls.length, 2);
  assert.deepEqual(later.messages.at(-1), {type: 'FUTURE_BTC5M_RENDERER_STATUS', state: 'STOPPED'});
  p.value.disconnect();
  later.value.disconnect();
});

test('loading or leaving the BTC5m page releases emulation before the new page gets access', async () => {
  for (const change of [{status: 'loading'}, {url: 'https://example.com'}, {url: 'https://future.news/zh/settings'}]) {
    const w = worker();
    w.port();
    await flush();
    w.update(7, change);
    await flush();
    assert.equal(w.calls.at(-1)[0], 'detach');
  }
});

test('a completed trusted navigation restores rendering for a surviving port after releasing the old document', async () => {
  const w = worker();
  const p = w.port();
  await flush();
  w.update(7, {status: 'loading'}, {url});
  await flush();
  w.update(7, {status: 'complete'}, {url});
  await flush();
  assert.equal(w.calls.filter(c => c[0] === 'attach').length, 2);
  assert.deepEqual(p.messages.at(-1), {type: 'FUTURE_BTC5M_RENDERER_STATUS', state: 'ACTIVE'});
  p.value.disconnect();
  await flush();
  assert.equal(w.calls.filter(c => c[0] === 'detach').length, 2);
});

test('completion cannot reacquire rendering with a missing or foreign current URL, or after manual cancellation', async () => {
  for (const tab of [undefined, {url: 'https://example.com'}, {url: 'https://future.news/zh/settings'}]) {
    const w = worker();
    const p = w.port();
    await flush();
    w.update(7, {status: 'loading'}, {url});
    await flush();
    w.update(7, {status: 'complete'}, tab);
    await flush();
    assert.equal(w.calls.filter(c => c[0] === 'attach').length, 1);
    p.value.disconnect();
  }
  const w = worker();
  w.port();
  await flush();
  w.detach({tabId: 7}, 'canceled_by_user');
  w.update(7, {status: 'complete'}, {url});
  await flush();
  assert.equal(w.calls.filter(c => c[0] === 'attach').length, 1);
});

test('when Chrome omits the completed tab URL, only a fresh reply from its trusted live port can restore rendering', async () => {
  const w = worker();
  const p = w.port();
  await flush();
  w.update(7, {status: 'loading'});
  await flush();
  w.update(7, {status: 'complete'});
  const check = p.messages.at(-1);
  assert.equal(check.type, 'FUTURE_BTC5M_RENDERER_CHECK');
  assert.equal(w.calls.filter(c => c[0] === 'attach').length, 1);
  p.reply({type: 'FUTURE_BTC5M_RENDERER_PAGE', checkedAt: check.checkedAt, marketUrl: url});
  await flush();
  assert.equal(w.calls.filter(c => c[0] === 'attach').length, 2);
});

test('foreign, extra-field and invalidated port replies cannot widen rendering access', async () => {
  for (const change of [{marketUrl:'https://example.com'}, {extra:true}, {checkedAt:0}]) {
    const w = worker();
    const p = w.port();
    await flush();
    w.update(7, {status:'loading'});
    await flush();
    w.update(7, {status:'complete'});
    const check = p.messages.at(-1);
    p.reply({type:'FUTURE_BTC5M_RENDERER_PAGE',checkedAt:check.checkedAt,marketUrl:url,...change});
    await flush();
    assert.equal(w.calls.filter(c=>c[0]==='attach').length,1);
  }
  const w=worker();
  const p=w.port();
  await flush();
  w.update(7,{status:'loading'});
  await flush();
  w.update(7,{status:'complete'});
  const check=p.messages.at(-1);
  w.update(7,{status:'loading'});
  p.reply({type:'FUTURE_BTC5M_RENDERER_PAGE',checkedAt:check.checkedAt,marketUrl:url});
  await flush();
  assert.equal(w.calls.filter(c=>c[0]==='attach').length,1);
});

test('a new document waits for old cleanup instead of racing for debugger ownership', async () => {
  let resolve;
  const w = worker({command: enabled => enabled ? undefined : new Promise(r => {resolve = r;})});
  const p = w.port();
  await flush();
  p.value.disconnect();
  w.port();
  await flush();
  assert.equal(w.calls.filter(c => c[0] === 'attach').length, 1);
  resolve();
  await flush();
  assert.equal(w.calls.filter(c => c[0] === 'attach').length, 2);
});
