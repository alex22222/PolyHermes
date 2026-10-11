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
    payload.schemaVersion === 1 && Number.isSafeInteger(payload.pagePeriodStart) && payload.pagePeriodStart >= 0 &&
    payload.pagePeriodStart % 300 === 0 && payload.pagePeriodStart === Number(match[1]) &&
    Number.isFinite(payload.checkedAt) && Math.abs(now - payload.checkedAt) <= 3 &&
    ['CURRENT', 'ENDED', 'MISMATCH'].includes(payload.navigation) &&
    (payload.navigation !== 'CURRENT' || payload.pagePeriodStart === start) &&
    (payload.navigation !== 'ENDED' || payload.pagePeriodStart < start) &&
    ['PASS', 'FAIL'].includes(payload.ticketStatus) &&
    (payload.amountUsd === null || Number.isFinite(payload.amountUsd) && payload.amountUsd >= 0) &&
    ['Up', 'Down', null].includes(payload.selectedSide) && typeof payload.buyButtonEnabled === 'boolean');
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!['FUTURE_BTC5M_STATUS', 'FUTURE_BTC5M_PREFLIGHT'].includes(message?.type) || !sender.tab || sender.frameId !== 0) return;
  let origin;
  try {
    origin = new URL(sender.url).origin;
  } catch {
    return;
  }
  if (origin !== 'https://future.news') return;
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
