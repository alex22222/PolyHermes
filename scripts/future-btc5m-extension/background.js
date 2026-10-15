// Fixed local endpoints only. Preflight carries a whitelist of read-only ticket facts.
const MARKET_QUOTE_ERROR_CODES = ['HTTP_SOURCE_TIMEOUT', 'HTTP_SOURCE_UNAVAILABLE', 'INVALID_MARKET_QUOTE',
  'CLOB_BOOKS_MISMATCH', 'CLOB_BOOK_TIME_INVALID', 'ROUND_CHANGED_DURING_READ', 'INVALID_BOOK', 'INVALID_BOOK_LEVEL',
  'WRONG_MARKET_PRICE_CONFIG', 'MARKET_NOT_UNIQUE', 'WRONG_OR_INACTIVE_EVENT', 'WRONG_OR_INACTIVE_MARKET',
  'WRONG_MARKET_PERIOD', 'INVALID_OUTCOME_TOKENS', 'LOCAL_QUOTE_TIMEOUT', 'LOCAL_QUOTE_NOT_FOUND'];

// Round series of the two strategies (same table as content.js and future_btc5m_series.py).
const SERIES = {'5m': {period: 300, id: 'future-btc5m-prepare:'}, '15m': {period: 900, id: 'future-btc15m-prepare:'}};
const PAGE_PATH = /^\/(?:zh\/)?event\/btc-updown-(5m|15m)-(0|[1-9]\d*)\/?$/;

// {series, start} of a canonical Future BTC round path, else null.
function roundOf(pathname) {
  const match = typeof pathname === 'string' && pathname.match(PAGE_PATH);
  const start = match && Number(match[2]);
  return match && Number.isSafeInteger(start) && start >= 0 && start % SERIES[match[1]].period === 0 ?
    {series: match[1], start} : null;
}

function marketPage(value) {
  try {
    const parsed = new URL(value);
    return parsed.origin === 'https://future.news' && !parsed.username && !parsed.password &&
      roundOf(parsed.pathname) ? parsed : null;
  } catch {
    return null;
  }
}

function validPreflight(message, sender) {
  if (!message || Object.keys(message).length !== 2 || !Object.hasOwn(message, 'payload')) return false;
  const payload = message.payload;
  const keys = ['schemaVersion', 'marketUrl', 'pagePeriodStart', 'checkedAt', 'navigation', 'ticketStatus',
    'amountUsd', 'selectedSide', 'buyButtonEnabled'];
  if ([2, 3].includes(payload?.schemaVersion)) keys.push('upQuoteCents', 'downQuoteCents');
  if (payload?.schemaVersion === 3) keys.push('walletAddress', 'cashUsd');
  if (!payload || typeof payload !== 'object' || Array.isArray(payload) ||
      Object.keys(payload).length !== keys.length || !keys.every((key) => Object.hasOwn(payload, key))) return false;
  const documentPage = marketPage(sender.url);
  // Chrome can retain the content script's original URL across an SPA navigation.
  // The trusted top-frame tab URL describes the currently displayed market.
  const page = marketPage(sender.tab.url ?? sender.url);
  const round = page && roundOf(page.pathname);
  const now = Date.now() / 1000;
  const period = round ? SERIES[round.series].period : 300;
  const start = Math.floor(now / period) * period;
  return Boolean(documentPage && page && round && payload.marketUrl === page.origin + page.pathname &&
    [1, 2, 3].includes(payload.schemaVersion) && Number.isSafeInteger(payload.pagePeriodStart) &&
    payload.pagePeriodStart === round.start &&
    Number.isFinite(payload.checkedAt) && Math.abs(now - payload.checkedAt) <= 3 &&
    ['CURRENT', 'ENDED', 'MISMATCH'].includes(payload.navigation) &&
    (payload.navigation !== 'CURRENT' || payload.pagePeriodStart === start) &&
    (payload.navigation !== 'ENDED' || payload.pagePeriodStart < start) &&
    ['PASS', 'FAIL'].includes(payload.ticketStatus) &&
    (payload.amountUsd === null || Number.isFinite(payload.amountUsd) && payload.amountUsd >= 0) &&
    ['Up', 'Down', null].includes(payload.selectedSide) && typeof payload.buyButtonEnabled === 'boolean' &&
    (payload.schemaVersion === 1 || ['upQuoteCents', 'downQuoteCents'].every((key) => payload[key] === null ||
      Number.isFinite(payload[key]) && payload[key] >= 0 && payload[key] <= 100 && Number(payload[key].toFixed(2)) === payload[key])) &&
    (payload.schemaVersion !== 3 || (payload.walletAddress === null ||
      typeof payload.walletAddress === 'string' && /^0x[0-9a-f]{40}$/.test(payload.walletAddress)) &&
      (payload.cashUsd === null || payload.walletAddress !== null && Number.isFinite(payload.cashUsd) && payload.cashUsd >= 0)));
}

// An attempt audit may be flushed after the tab moved to a later round, so it is bound
// to its READY record by the bridge rather than to the current page.
function validBuyAudit(message) {
  if (Object.keys(message).length !== 2 || !Object.hasOwn(message, 'payload')) return false;
  const value = message.payload;
  const keys = ['schemaVersion', 'auditId', 'id', 'claimToken', 'periodStart', 'side', 'amountUsd', 'state', 'reason',
    'armedAt', 'attemptedAt', 'marketUrl', 'upQuoteCents', 'downQuoteCents', 'selectedSide', 'ticketAmountUsd',
    'extensionVersion'];
  // Schema 2 adds the independent Polymarket CLOB asks the price gates compared, or nulls when none was read.
  if (value?.schemaVersion === 2) keys.push('marketUpAskCents', 'marketDownAskCents', 'marketQuoteObservedAt');
  const reasons = {CLICK_ATTEMPTED: ['PLATFORM_RESULT_UNKNOWN', 'CLICK_THROWN_RESULT_UNKNOWN'],
    BLOCKED: ['TICKET_CHANGED', 'BUY_BUTTON_UNSAFE', 'READY_CHANGED', 'STORAGE_FAILED', 'FINAL_CHECK_FAILED',
      'ALREADY_CONSUMED', 'PRICE_BELOW_MIN', 'MARKET_QUOTE_UNAVAILABLE', 'MARKET_QUOTE_MISMATCH', 'PRICE_ABOVE_MAX']};
  const quote = (cents) => cents === null ||
    Number.isFinite(cents) && cents >= 0 && cents <= 100 && Number(cents.toFixed(2)) === cents;
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).length !== keys.length ||
      !keys.every((key) => Object.hasOwn(value, key))) return false;
  const page = marketPage(value.marketUrl);
  const round = page && roundOf(page.pathname);
  return [1, 2].includes(value.schemaVersion) && Number.isSafeInteger(value.periodStart) && value.periodStart >= 0 &&
    Boolean(round) && round.start === value.periodStart && value.id === `${SERIES[round.series].id}${value.periodStart}` &&
    Number.isFinite(value.armedAt) && Number.isFinite(value.attemptedAt) && value.armedAt <= value.attemptedAt &&
    value.auditId === `${value.id}:${Math.floor(value.attemptedAt * 1000)}` &&
    typeof value.claimToken === 'string' && /^[a-f0-9]{32}$/.test(value.claimToken) &&
    ['Up', 'Down'].includes(value.side) && value.amountUsd === 1 &&
    Object.hasOwn(reasons, value.state) && reasons[value.state].includes(value.reason) &&
    Boolean(page) && value.marketUrl === page.origin + page.pathname &&
    quote(value.upQuoteCents) && quote(value.downQuoteCents) && ['Up', 'Down', null].includes(value.selectedSide) &&
    (value.ticketAmountUsd === null || Number.isFinite(value.ticketAmountUsd) && value.ticketAmountUsd >= 0) &&
    typeof value.extensionVersion === 'string' && /^\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(value.extensionVersion) &&
    (value.schemaVersion === 1 || quote(value.marketUpAskCents) && quote(value.marketDownAskCents) &&
      (value.marketQuoteObservedAt === null || Number.isFinite(value.marketQuoteObservedAt)));
}

function preparationMessage(message, sender) {
  const page = marketPage(sender.tab.url ?? sender.url);
  if (!marketPage(sender.url) || !page) return null;
  const type = message.type;
  if (type === 'FUTURE_BTC5M_PREPARATION') return Object.keys(message).length === 1 ? '' : null;
  if (type === 'FUTURE_BTC5M_MARKET_QUOTE') return Object.keys(message).length === 1 ? '/market-quote' : null;
  if (type === 'FUTURE_BTC5M_BUY_AUDIT') return validBuyAudit(message) ? '/buy-audit' : null;
  if (type === 'FUTURE_BTC5M_SCHEDULE') return Object.keys(message).length === 1 ? '/schedule' : null;
  if (type === 'FUTURE_BTC5M_SCHEDULE_SET') {
    const payload = message.payload;
    return Object.keys(message).length === 2 && payload && typeof payload === 'object' && !Array.isArray(payload) &&
      Object.keys(payload).length === 1 && typeof payload.weekendOnly === 'boolean' ? '/schedule' : null;
  }
  if (Object.keys(message).length !== 2 || !Object.hasOwn(message, 'payload')) return null;
  const payload = message.payload;
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return null;
  // Claims and receipts name the round of the page that prepares it, in that page's series.
  const {series, start} = roundOf(page.pathname);
  const id = `${SERIES[series].id}${start}`;
  if (payload.schemaVersion !== 1 || payload.id !== id) return null;
  if (type === 'FUTURE_BTC5M_PREPARATION_CLAIM') {
    const period = SERIES[series].period;
    return Object.keys(payload).length === 2 && start === Math.floor(Date.now() / 1000 / period) * period ? '/claim' : null;
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

// WebSocket messages wake the page even when Chrome suspends its hidden-page timers.
// The clock is read-only; the existing preparation, STOP and Buy checks still decide actions.
const runtimePorts = new Set();
let runtimeSocket = null, runtimeRetry = null;
// A locked or dark screen stops Future rendering the next round's ticket even while this
// clock keeps the page awake, so the display also stays on while the automatic-ticket
// switch is on. Off or unknown, only the system stays awake.
let displayAwake = false;
const rendererPermitted = Boolean(chrome.runtime.getManifest?.()?.permissions?.includes('debugger'));
const keepAwakeLevel = () => displayAwake && !rendererPermitted ? 'display' : 'system';

function followAutoSwitch(status) {
  const enabled = status?.bridgeId === 'future-btc5m' ? status.preparation?.enabled : undefined;
  if (typeof enabled !== 'boolean' || enabled === displayAwake) return;
  displayAwake = enabled;
  // A newer request from this extension replaces the previous one.
  if (runtimePorts.size) chrome.power.requestKeepAwake(keepAwakeLevel());
}

function connectRuntimeClock() {
  if (!runtimePorts.size || runtimeSocket) return;
  const socket = new WebSocket('ws://127.0.0.1:8767/runtime');
  runtimeSocket = socket;
  socket.onmessage = ({data}) => {
    let tick;
    try { tick = JSON.parse(data); } catch { return; }
    if (!tick || Object.keys(tick).length !== 2 || tick.type !== 'FUTURE_BTC5M_TICK' ||
        !Number.isFinite(tick.serverTime) || Math.abs(Date.now() / 1000 - tick.serverTime) > 3) return;
    for (const port of runtimePorts) {
      try { port.postMessage(tick); } catch { /* onDisconnect removes the closed port. */ }
    }
  };
  socket.onclose = () => {
    if (runtimeSocket !== socket) return;
    runtimeSocket = null;
    if (runtimePorts.size) runtimeRetry = setTimeout(() => {
      runtimeRetry = null;
      connectRuntimeClock();
    }, 1000);
  };
  socket.onerror = () => socket.close();
}

chrome.runtime.onConnect?.addListener((port) => {
  const sender = port.sender;
  if (port.name !== 'FUTURE_BTC5M_RUNTIME' || !sender?.tab || sender.frameId !== 0 ||
      !marketPage(sender.url) || !marketPage(sender.tab.url ?? sender.url)) {
    port.disconnect();
    return;
  }
  runtimePorts.add(port);
  chrome.power.requestKeepAwake(keepAwakeLevel());
  port.onDisconnect.addListener(() => {
    runtimePorts.delete(port);
    if (runtimePorts.size) return;
    if (runtimeRetry !== null) clearTimeout(runtimeRetry);
    runtimeRetry = null;
    const socket = runtimeSocket;
    runtimeSocket = null;
    socket?.close();
    chrome.power.releaseKeepAwake();
  });
  connectRuntimeClock();
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const preparationTypes = ['FUTURE_BTC5M_PREPARATION', 'FUTURE_BTC5M_PREPARATION_CLAIM', 'FUTURE_BTC5M_PREPARATION_ACK',
    'FUTURE_BTC5M_BUY_AUDIT', 'FUTURE_BTC5M_MARKET_QUOTE', 'FUTURE_BTC5M_SCHEDULE', 'FUTURE_BTC5M_SCHEDULE_SET'];
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
    // Reads (preparation state, CLOB quote, schedule) carry no payload; only payload messages POST.
    const read = !Object.hasOwn(message, 'payload');
    const marketQuote = message.type === 'FUTURE_BTC5M_MARKET_QUOTE';
    const error = marketQuote ? '本地盘口服务未确认' : '本地准备服务未确认';
    const options = {method: read ? 'GET' : 'POST', credentials: 'omit', cache: 'no-store',
      redirect: 'error', headers: {'X-PolyHermes-Future-Preparation': '1'}, signal: AbortSignal.timeout(marketQuote ? 4500 : 2000)};
    if (!read) {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(message.payload);
    }
    fetch(`http://127.0.0.1:8766/bridge/preparation${suffix}`, options).then(async (response) => {
      if (!marketQuote) {
        if (!response.ok) throw new Error(error);
        return response.json();
      }
      if (response.status === 404) throw Object.assign(new Error(error), {errorCode: 'LOCAL_QUOTE_NOT_FOUND'});
      let status;
      try {
        status = await response.json();
      } catch (failure) {
        if (['TimeoutError', 'AbortError'].includes(failure?.name)) throw failure;
        throw Object.assign(new Error(error), {errorCode: 'INVALID_MARKET_QUOTE'});
      }
      if (!response.ok) throw Object.assign(new Error(error), {errorCode:
        MARKET_QUOTE_ERROR_CODES.includes(status?.errorCode) ? status.errorCode : 'MARKET_QUOTE_UNAVAILABLE'});
      return status;
    }).then((status) => {
      if (!marketQuote) followAutoSwitch(status);
      sendResponse({ok: true, status});
    }).catch((failure) => {
      const reply = {ok: false, error};
      if (marketQuote) reply.errorCode = ['TimeoutError', 'AbortError'].includes(failure?.name) ? 'LOCAL_QUOTE_TIMEOUT' :
        MARKET_QUOTE_ERROR_CODES.includes(failure?.errorCode) ? failure.errorCode : 'MARKET_QUOTE_UNAVAILABLE';
      sendResponse(reply);
    });
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

// The current installed manifest does not grant this permission. The reviewed
// rendering candidate is activated only after the operator approves that upgrade.
if (rendererPermitted) importScripts('renderer.js');
