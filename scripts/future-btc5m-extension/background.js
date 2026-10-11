// Fixed local endpoints only. Preflight carries a whitelist of read-only ticket facts.
function marketPage(value) {
  try {
    const parsed = new URL(value);
    const match = parsed.pathname.match(/^\/(?:zh\/)?event\/btc-updown-5m-(0|[1-9]\d*)\/?$/);
    const start = match && Number(match[1]);
    return parsed.origin === 'https://future.news' && !parsed.username && !parsed.password && match &&
      Number.isSafeInteger(start) && start >= 0 && start % 300 === 0 ? parsed : null;
  } catch {
    return null;
  }
}

function validPreflight(message, sender) {
  if (!message || Object.keys(message).length !== 2 || !Object.hasOwn(message, 'payload')) return false;
  const payload = message.payload;
  const keys = ['schemaVersion', 'marketUrl', 'pagePeriodStart', 'checkedAt', 'navigation', 'ticketStatus',
    'amountUsd', 'selectedSide', 'buyButtonEnabled'];
  if (payload?.schemaVersion === 2) keys.push('upQuoteCents', 'downQuoteCents');
  if (!payload || typeof payload !== 'object' || Array.isArray(payload) ||
      Object.keys(payload).length !== keys.length || !keys.every((key) => Object.hasOwn(payload, key))) return false;
  const documentPage = marketPage(sender.url);
  // Chrome can retain the content script's original URL across an SPA navigation.
  // The trusted top-frame tab URL describes the currently displayed market.
  const page = marketPage(sender.tab.url ?? sender.url);
  const match = typeof payload.marketUrl === 'string' && payload.marketUrl.match(/^https:\/\/future\.news\/(?:zh\/)?event\/btc-updown-5m-(0|[1-9]\d*)\/?$/);
  const now = Date.now() / 1000;
  const start = Math.floor(now / 300) * 300;
  return Boolean(documentPage && page && match && payload.marketUrl === page.origin + page.pathname &&
    [1, 2].includes(payload.schemaVersion) && Number.isSafeInteger(payload.pagePeriodStart) && payload.pagePeriodStart >= 0 &&
    payload.pagePeriodStart % 300 === 0 && payload.pagePeriodStart === Number(match[1]) &&
    Number.isFinite(payload.checkedAt) && Math.abs(now - payload.checkedAt) <= 3 &&
    ['CURRENT', 'ENDED', 'MISMATCH'].includes(payload.navigation) &&
    (payload.navigation !== 'CURRENT' || payload.pagePeriodStart === start) &&
    (payload.navigation !== 'ENDED' || payload.pagePeriodStart < start) &&
    ['PASS', 'FAIL'].includes(payload.ticketStatus) &&
    (payload.amountUsd === null || Number.isFinite(payload.amountUsd) && payload.amountUsd >= 0) &&
    ['Up', 'Down', null].includes(payload.selectedSide) && typeof payload.buyButtonEnabled === 'boolean' &&
    (payload.schemaVersion === 1 || ['upQuoteCents', 'downQuoteCents'].every((key) => payload[key] === null ||
      Number.isFinite(payload[key]) && payload[key] >= 0 && payload[key] <= 100 && Number(payload[key].toFixed(2)) === payload[key])));
}

function preparationMessage(message, sender) {
  const page = marketPage(sender.tab.url ?? sender.url);
  if (!marketPage(sender.url) || !page) return null;
  const type = message.type;
  if (type === 'FUTURE_BTC5M_PREPARATION') return Object.keys(message).length === 1 ? '' : null;
  if (Object.keys(message).length !== 2 || !Object.hasOwn(message, 'payload')) return null;
  const payload = message.payload;
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return null;
  const start = Number(page.pathname.match(/btc-updown-5m-(\d+)/)[1]);
  const id = `future-btc5m-prepare:${start}`;
  if (payload.schemaVersion !== 1 || payload.id !== id) return null;
  if (type === 'FUTURE_BTC5M_PREPARATION_CLAIM') {
    return Object.keys(payload).length === 2 && start === Math.floor(Date.now() / 300000) * 300 ? '/claim' : null;
  }
  const keys = ['schemaVersion', 'id', 'claimToken', 'checkedAt', 'status', 'marketUrl',
    'amountUsd', 'selectedSide', 'reason', 'noSubmission'];
  const reasons = ['PREPARATION_FAILED', 'MARKET_MISMATCH', 'TICKET_CHANGED', 'UNSAFE_DIRECTION_CONTROL',
    'AMOUNT_WRITE_FAILED', 'DIRECTION_WRITE_FAILED', 'POSTCHECK_FAILED', 'PREPARATION_REVOKED',
    'BUTTON_QUOTES_UNAVAILABLE', 'BUTTON_QUOTES_TIED', 'BUTTON_QUOTES_NOT_FRESH', 'HIGHER_BUTTON_SIDE_CHANGED'];
  if (type !== 'FUTURE_BTC5M_PREPARATION_ACK' || Object.keys(payload).length !== keys.length ||
      !keys.every((key) => Object.hasOwn(payload, key)) || payload.noSubmission !== true ||
      typeof payload.claimToken !== 'string' || !/^[a-f0-9]{32}$/.test(payload.claimToken) ||
      !Number.isFinite(payload.checkedAt) || Math.abs(Date.now() / 1000 - payload.checkedAt) > 3 ||
      payload.marketUrl !== page.origin + page.pathname ||
      !(payload.amountUsd === null || Number.isFinite(payload.amountUsd) && payload.amountUsd >= 0) ||
      !['Up', 'Down', null].includes(payload.selectedSide) ||
      !(payload.status === 'READY' && payload.reason === null && payload.amountUsd === 1 && payload.selectedSide !== null ||
        payload.status === 'FAILED' && reasons.includes(payload.reason) ||
        payload.status === 'EXPIRED' && payload.reason === 'INTENT_EXPIRED')) return null;
  return '/ack';
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const preparationTypes = ['FUTURE_BTC5M_PREPARATION', 'FUTURE_BTC5M_PREPARATION_CLAIM', 'FUTURE_BTC5M_PREPARATION_ACK'];
  if (!['FUTURE_BTC5M_STATUS', 'FUTURE_BTC5M_PREFLIGHT', ...preparationTypes].includes(message?.type) ||
      !sender.tab || sender.frameId !== 0) return;
  let origin;
  try {
    origin = new URL(sender.url).origin;
  } catch {
    return;
  }
  if (origin !== 'https://future.news') return;
  if (preparationTypes.includes(message.type)) {
    const suffix = preparationMessage(message, sender);
    if (suffix === null) return;
    const options = {method: suffix ? 'POST' : 'GET', credentials: 'omit', cache: 'no-store',
      redirect: 'error', headers: {'X-PolyHermes-Future-Preparation': '1'}, signal: AbortSignal.timeout(2000)};
    if (suffix) {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(message.payload);
    }
    fetch(`http://127.0.0.1:8766/bridge/preparation${suffix}`, options).then((response) => {
      if (!response.ok) throw new Error('本地准备服务未确认');
      return response.json();
    }).then((status) => sendResponse({ok: true, status}))
      .catch(() => sendResponse({ok: false, error: '本地准备服务未确认'}));
    return true;
  }
  if (message.type === 'FUTURE_BTC5M_PREFLIGHT') {
    if (!validPreflight(message, sender)) return;
    fetch('http://127.0.0.1:8766/bridge/preflight', {
      method: 'POST', credentials: 'omit', cache: 'no-store', redirect: 'error',
      headers: {'Content-Type': 'application/json', 'X-PolyHermes-Future-Preflight': '1'},
      body: JSON.stringify(message.payload), signal: AbortSignal.timeout(2000),
    }).then((response) => {
      if (!response.ok) throw new Error('本地预检服务未就绪');
      sendResponse({ok: true});
    }).catch(() => sendResponse({ok: false, error: '本地预检服务未连接'}));
    return true;
  }
  fetch('http://127.0.0.1:8766/status', {
    method: 'GET', credentials: 'omit', cache: 'no-store', redirect: 'error',
    signal: AbortSignal.timeout(2000),
  }).then((response) => {
    if (!response.ok) throw new Error('本地助手未就绪');
    return response.json();
  }).then((status) => sendResponse({ok: true, status}))
    .catch(() => sendResponse({ok: false, error: '本地信号服务未连接'}));
  return true;
});
