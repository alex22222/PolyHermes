import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../frontend/public/sw.js', import.meta.url), 'utf8');
const origin = 'https://polyhermes.test';
const response = (body, status = 200) => ({body, status, type: 'basic', clone() { return response(body, status); }});
const request = (path, mode = 'navigate', method = 'GET') => ({url: origin + path, mode, method});

function fixture({offline = false, writeError = false} = {}) {
  const handlers = {};
  const stores = new Map();
  const network = [];
  const cacheReads = [];
  const deleted = [];
  const key = (value) => new URL(typeof value === 'string' ? value : value.url, origin).href;
  const cache = (name) => {
    if (!stores.has(name)) stores.set(name, new Map());
    return {
      async match(value) { cacheReads.push({name, key: key(value)}); return stores.get(name).get(key(value)); },
      async put(value, result) {
        if (writeError) throw new Error('cache quota');
        stores.get(name).set(key(value), result);
      },
      async addAll() {},
    };
  };
  const caches = {
    async open(name) { return cache(name); },
    async keys() { return [...stores.keys()]; },
    async delete(name) { deleted.push(name); return stores.delete(name); },
    async match(value) {
      for (const name of stores.keys()) {
        const found = await cache(name).match(value);
        if (found) return found;
      }
    },
  };
  const context = vm.createContext({URL, caches, fetch: async (value) => {
    network.push(value.url);
    if (offline) throw new Error('offline');
    return response('new release');
  }, self: {addEventListener(name, handler) { handlers[name] = handler; },
    skipWaiting() {}, clients: {claim() {}}}});
  vm.runInContext(source, context);
  const currentName = vm.runInContext('CACHE_NAME', context);
  cache(currentName);
  return {
    currentName, stores, network, cacheReads, deleted,
    seed(name, path, body) { cache(name); stores.get(name).set(key(path), response(body)); },
    read(name, path) { return stores.get(name)?.get(key(path)); },
    async fetch(value) {
      let result;
      let intercepted = false;
      handlers.fetch({request: value, respondWith(promise) { intercepted = true; result = promise; }});
      const returned = await result;
      await new Promise((resolve) => setImmediate(resolve));
      return {intercepted, response: returned};
    },
    async activate() {
      let pending;
      handlers.activate({waitUntil(promise) { pending = promise; }});
      await pending;
    },
  };
}

test('online navigation replaces cached old HTML with the current release', async () => {
  const worker = fixture();
  worker.seed(worker.currentName, '/future-btc5m-bridge', 'old release without Future route');
  const result = await worker.fetch(request('/future-btc5m-bridge'));
  assert.equal(result.intercepted, true);
  assert.equal(result.response.body, 'new release');
  assert.equal(worker.network.length, 1);
  assert.equal(worker.read(worker.currentName, '/future-btc5m-bridge').body, 'new release');
});

test('offline navigation attempts the network then keeps its current cached page', async () => {
  const worker = fixture({offline: true});
  worker.seed(worker.currentName, '/future-btc5m-bridge', 'current offline page');
  const result = await worker.fetch(request('/future-btc5m-bridge'));
  assert.equal(result.response.body, 'current offline page');
  assert.equal(worker.network.length, 1);
});

test('offline navigation falls back only to the current own index cache', async () => {
  const worker = fixture({offline: true});
  worker.seed('other-app-cache', '/index.html', 'unrelated stale HTML');
  worker.seed(worker.currentName, '/index.html', 'current index');
  const current = worker.stores.get(worker.currentName);
  worker.stores.delete(worker.currentName);
  worker.stores.set(worker.currentName, current);
  const result = await worker.fetch(request('/new-route'));
  assert.equal(result.response.body, 'current index');
  assert.equal(worker.network.length, 1);
});

test('API websocket and non-GET requests remain outside the service worker cache', async () => {
  const worker = fixture();
  for (const value of [request('/api/future-btc5m/status', 'cors'), request('/api/auth/login', 'cors', 'POST'),
    request('/ws/connect', 'cors'), request('/something', 'cors', 'POST')]) {
    assert.equal((await worker.fetch(value)).intercepted, false);
  }
  assert.equal(worker.network.length, 0);
  assert.equal(worker.cacheReads.length, 0);
});

test('hashed static assets retain cache-first behavior and cache successful misses', async () => {
  const worker = fixture();
  worker.seed(worker.currentName, '/assets/index-oldhash.js', 'immutable cached JavaScript');
  assert.equal((await worker.fetch(request('/assets/index-oldhash.js', 'same-origin'))).response.body,
    'immutable cached JavaScript');
  assert.equal(worker.network.length, 0);
  assert.equal((await worker.fetch(request('/assets/index-newhash.js', 'same-origin'))).response.body, 'new release');
  assert.equal(worker.network.length, 1);
  assert.equal(worker.read(worker.currentName, '/assets/index-newhash.js').body, 'new release');
});

test('a navigation cache write failure cannot substitute old HTML for a successful network response', async () => {
  const worker = fixture({writeError: true});
  worker.seed(worker.currentName, '/', 'old release');
  assert.equal((await worker.fetch(request('/'))).response.body, 'new release');
});

test('cache version upgrade retires only old PolyHermes caches', async () => {
  const worker = fixture();
  assert.notEqual(worker.currentName, 'polyhermes-cache-v1');
  worker.seed('polyhermes-cache-v1', '/', 'old release');
  worker.seed('other-app-cache', '/', 'unrelated data');
  await worker.activate();
  assert.equal(worker.stores.has('polyhermes-cache-v1'), false);
  assert.equal(worker.stores.has(worker.currentName), true);
  assert.equal(worker.stores.has('other-app-cache'), true);
  assert.deepEqual(worker.deleted, ['polyhermes-cache-v1']);
});
