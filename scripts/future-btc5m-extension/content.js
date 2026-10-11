(() => {
  function verifiedEligibility(status) {
    const eligibility = status?.future_eligibility;
    if (eligibility?.status !== 'VERIFIED' || eligibility.venue !== 'future.news' ||
        eligibility.operation !== 'PREPARE_USD_BUY_AMOUNT' || typeof eligibility.source_url !== 'string') return false;
    try {
      const source = new URL(eligibility.source_url);
      return source.origin === 'https://future.news' && source.pathname !== '/' &&
        !source.username && !source.password;
    } catch {
      return false;
    }
  }

  function usableDraft(status, now = Date.now() / 1000) {
    const draft = status?.draft;
    if (status?.schema_version !== 1 || status.mode !== 'ASSIST_ONLY' ||
        status.live_enabled !== false || status.amount_usd !== 1 ||
        status.status !== 'READY' || status.feed_status !== 'CURRENT' ||
        status.geoblock?.blocked !== false ||
        status.geoblock.source_url !== 'https://polymarket.com/api/geoblock' ||
        !verifiedEligibility(status) || !draft) return null;
    if (!Number.isFinite(status.server_time) || Math.abs(now - status.server_time) > 3) return null;
    if (!Number.isInteger(draft.period_start) || draft.period_start % 300 !== 0 ||
        draft.slug !== `btc-updown-5m-${draft.period_start}` || draft.series !== '5m' ||
        draft.period_end !== draft.period_start + 300 || draft.amount_usd !== 1 ||
        !['Up', 'Down'].includes(draft.side) || draft.trade_ready !== true ||
        draft.manual_submit_required !== true || draft.platform_amount_validation_required !== true ||
        draft.price_source !== 'chainlink' ||
        draft.open_price_source !== 'polymarket_crypto_price_fiveminute_twap60_openPrice' ||
        draft.twap_lookback_seconds !== 60 || !draft.token_id || !draft.condition_id) return null;
    if (!Number.isFinite(draft.created_at) || !Number.isFinite(draft.price_observed_at) ||
        draft.created_at < draft.period_start + 60 || draft.created_at > draft.period_start + 80 ||
        draft.expires_at !== draft.period_start + 80 || now < draft.created_at || now >= draft.expires_at ||
        draft.price_observed_at > draft.created_at || now - draft.price_observed_at > 5) return null;
    return draft;
  }

  function matchesMarket(url, draft) {
    const parsed = new URL(url);
    return parsed.origin === 'https://future.news' &&
      [`/event/${draft.slug}`, `/zh/event/${draft.slug}`].includes(parsed.pathname.replace(/\/$/, ''));
  }

  function navigationTarget(status, url, now = Date.now() / 1000) {
    if (status?.schema_version !== 1 || status.mode !== 'ASSIST_ONLY' ||
        status.live_enabled !== false || status.amount_usd !== 1 ||
        !['WAITING', 'OBSERVING', 'READY', 'EXPIRED', 'SKIPPED'].includes(status.status) ||
        !Number.isFinite(status.server_time) || Math.abs(now - status.server_time) > 3) return null;
    const start = Math.floor(now / 300) * 300;
    if (status.period_start !== start) return null;
    try {
      const parsed = new URL(url);
      const match = parsed.pathname.match(/^\/(?:zh\/)?event\/btc-updown-5m-(\d+)\/?$/);
      const pageStart = match && Number(match[1]);
      if (parsed.origin !== 'https://future.news' || parsed.username || parsed.password || !match ||
          !Number.isSafeInteger(pageStart) || pageStart % 300 !== 0 || pageStart > start) return null;
      return `https://future.news/zh/event/btc-updown-5m-${start}`;
    } catch {
      return null;
    }
  }

  function endedMarketButtons(doc) {
    return [...doc.querySelectorAll('button')].filter((button) =>
      button.textContent.trim() === '前往实时市场' && button.getClientRects().length);
  }

  function followCurrentMarket(status, url, doc, storage, now = Date.now() / 1000) {
    const target = navigationTarget(status, url, now);
    if (!target) return '自动换轮：暂停（等待有效本地状态或当前 BTC5m 页面）';
    const slug = new URL(target).pathname.split('/').pop();
    if (matchesMarket(url, {slug})) return `自动换轮：已进入本轮 ${slug}`;
    try {
      // This tab's own key survives a page reload; never read site auth or other storage keys.
      const key = 'polyhermes.future-btc5m.navigation';
      const attempt = JSON.parse(storage.getItem(key) || 'null');
      if (attempt?.target === target) return now - attempt.attempted_at < 10 ?
        `自动换轮：正在前往 ${slug}` : '自动换轮：跳转未完成，请点击“前往本轮市场”检查';
      const buttons = endedMarketButtons(doc).filter((button) => !button.disabled);
      if (buttons.length !== 1) return '自动换轮：等待唯一可用的“前往实时市场”按钮';
      storage.setItem(key, JSON.stringify({target, source: url, attempted_at: now}));
      buttons[0].click();
      return `自动换轮：正在前往 ${slug}`;
    } catch (error) {
      return `自动换轮失败：${error.message}`;
    }
  }

  function observationView(status, url, now = Date.now() / 1000) {
    const view = {text: `${status?.status || '未就绪'}：${status?.reason || '没有可用草稿'}`, marketUrl: null};
    if (!Number.isFinite(status?.server_time) || Math.abs(now - status.server_time) > 3) {
      view.text += ' · 本地状态已陈旧';
      return view;
    }
    view.text += `\nFuture 金额准备依据：${verifiedEligibility(status) ? '已核实（仅金额准备）' :
      status.future_eligibility?.status === 'RESTRICTED' ? '受限' : '未核实'}`;
    const signal = status.signal || status.draft;
    const start = Math.floor(now / 300) * 300;
    if (status.period_start === start) view.marketUrl = `https://future.news/zh/event/btc-updown-5m-${start}`;
    if (!signal) return view;
    if (!Number.isInteger(signal.period_start) || signal.period_start % 300 !== 0 ||
        signal.slug !== `btc-updown-5m-${signal.period_start}` || signal.series !== '5m' ||
        signal.period_end !== signal.period_start + 300 || signal.price_source !== 'chainlink' ||
        !['Up', 'Down', null].includes(signal.side)) {
      view.text += ' · 信号元数据无效';
      return view;
    }
    if (signal.period_start === start) view.marketUrl = `https://future.news/zh/event/${signal.slug}`;
    const verifiedOpening = signal.open_price_source === 'polymarket_crypto_price_fiveminute_twap60_openPrice' &&
      signal.twap_lookback_seconds === 60;
    let unavailable;
    if (signal.period_start !== start) unavailable = '信号轮次已结束';
    else if (!matchesMarket(url, signal)) unavailable = '页面轮次不匹配';
    else if (!verifiedOpening) unavailable = '开盘参考价未核实';
    else if (!Number.isFinite(signal.price_observed_at) || signal.price_observed_at > now) unavailable = '采样时间无效';
    else if (now >= start + 80) unavailable = '入场窗口已过期';
    else if (now - signal.price_observed_at > 5) unavailable = '采样已陈旧';
    else if (status.feed_status !== 'CURRENT') unavailable = '实时行情不可用';
    else if (status.status === 'STOPPED') unavailable = '助手已停止';
    view.text += unavailable ? ` · ${unavailable}，方向不用于入场` :
      signal.side ? ` · 本轮采样方向：${signal.side === 'Up' ? '涨 Up' : '跌 Down'}` : ' · 本轮采样价格持平';
    view.text += `\n采样轮次：${signal.slug}`;
    if (Number.isFinite(signal.price_observed_at)) view.text += `\n采样时间：${new Date(signal.price_observed_at * 1000).toISOString()}`;
    if (Number.isFinite(signal.current_price) && signal.current_price > 0) view.text += `\nChainlink 采样价 $${signal.current_price}`;
    if (Number.isFinite(signal.open_price) && signal.open_price > 0) {
      view.text += `\n${verifiedOpening ? 'Polymarket 60秒 TWAP 开盘参考价' : '开盘参考价未核实'} $${signal.open_price}`;
    }
    return view;
  }

  function findAmountTicket(doc, input) {
    let ticket = input.parentElement;
    for (let depth = 0; ticket && depth < 7; depth++, ticket = ticket.parentElement) {
      if (ticket === doc.body) break;
      const labels = [...ticket.querySelectorAll('button')]
        .filter((button) => button.getClientRects().length)
        .map((button) => button.textContent.trim());
      if (/金额\s*\(\$\)/.test(ticket.textContent) &&
          labels.includes('买入') && labels.includes('卖出') && labels.includes('市价单') &&
          !labels.includes('限价单') &&
          labels.some((label) => /^买入\s+(涨|跌)$/.test(label)) &&
          !labels.some((label) => /^卖出\s+(涨|跌)$/.test(label)) &&
          labels.some((label) => /^涨(?:\s|\d|--)/.test(label)) &&
          labels.some((label) => /^跌(?:\s|\d|--)/.test(label))) return ticket;
    }
    throw new Error('当前不是已核对的中文美元市价买入栏');
  }

  // Scope to the order ticket, never an order-book row or the quick-trade control.
  function findAmountInput(doc) {
    const inputs = [...doc.querySelectorAll('input[placeholder="订单大小"]')]
      .filter((input) => !input.disabled && !input.readOnly && input.getClientRects().length);
    if (inputs.length !== 1) throw new Error('找不到唯一的可见订单金额框');
    findAmountTicket(doc, inputs[0]);
    return inputs[0];
  }

  function ticketMatchesPeriod(doc, ticket, start) {
    const formatter = new Intl.DateTimeFormat('en-US', {timeZone: 'America/New_York', month: 'long',
      day: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true});
    const values = (timestamp) => Object.fromEntries(formatter.formatToParts(new Date(timestamp * 1000))
      .filter((part) => part.type !== 'literal').map((part) => [part.type, part.value]));
    const opening = values(start);
    const ending = values(start + 300);
    const timeText = (parts) => `${parts.hour}:${parts.minute}${parts.dayPeriod}`;
    const expected = `Bitcoin Up or Down - ${opening.month} ${opening.day}, ${timeText(opening)}-${timeText(ending)} ET`;
    const normalize = (value) => value.replace(/\s+/g, '').replace(/[–—]/g, '-');
    const accepted = new Set([normalize(expected)]);
    if (opening.month !== ending.month || opening.day !== ending.day) accepted.add(normalize(
      `Bitcoin Up or Down - ${opening.month} ${opening.day}, ${timeText(opening)}-${ending.month} ${ending.day}, ${timeText(ending)} ET`));
    const pattern = /^Bitcoin\s+Up\s+or\s+Down\s*[-–—]\s*[A-Za-z]+\s+\d{1,2},\s*\d{1,2}:\d{2}\s*(?:AM|PM)\s*[-–—]\s*(?:[A-Za-z]+\s+\d{1,2},\s*)?\d{1,2}:\d{2}\s*(?:AM|PM)\s*ET$/;
    // Stay in the ticket and its immediate title container; never search a watchlist.
    for (let scope = ticket, depth = 0; scope && scope !== doc.body && depth < 2; scope = scope.parentElement, depth++) {
      if (typeof scope.querySelectorAll !== 'function') return false;
      const titles = new Set([...scope.querySelectorAll('h1,h2,h3,span,p,div,[role="heading"]')]
        .filter((element) => element.getClientRects().length && pattern.test(element.textContent.trim()))
        .map((element) => normalize(element.textContent.trim())));
      if (titles.size) return titles.size === 1 && accepted.has([...titles][0]);
    }
    return false;
  }

  function buttonIsEnabled(button) {
    for (let ancestor = button; ancestor; ancestor = ancestor.parentElement) {
      if ((ancestor === button || ancestor.tagName === 'FIELDSET') && ancestor.disabled || ancestor.inert ||
          ancestor.hasAttribute?.('inert') || ancestor.getAttribute?.('aria-disabled') === 'true') return false;
    }
    return true;
  }

  function readPreflight(doc, url, now = Date.now() / 1000) {
    let parsed;
    try {
      parsed = new URL(url);
    } catch {
      return null;
    }
    const match = parsed.pathname.match(/^\/(?:zh\/)?event\/btc-updown-5m-(0|[1-9]\d*)\/?$/);
    const pagePeriodStart = match && Number(match[1]);
    if (parsed.origin !== 'https://future.news' || parsed.username || parsed.password || !match ||
        !Number.isSafeInteger(pagePeriodStart) || pagePeriodStart < 0 || pagePeriodStart % 300 !== 0 ||
        !Number.isFinite(now)) return null;
    const start = Math.floor(now / 300) * 300;
    const navigation = pagePeriodStart < start ? 'ENDED' : pagePeriodStart !== start || endedMarketButtons(doc).length ? 'MISMATCH' : 'CURRENT';
    // Only origin/path leave the tab. Query parameters, DOM text and errors do not.
    const report = {schemaVersion: 1, marketUrl: parsed.origin + parsed.pathname, pagePeriodStart,
      checkedAt: now, navigation, ticketStatus: 'FAIL', amountUsd: null, selectedSide: null, buyButtonEnabled: false};
    if (navigation !== 'CURRENT') return report;
    try {
      const input = findAmountInput(doc);
      const ticket = findAmountTicket(doc, input);
      if (!ticketMatchesPeriod(doc, ticket, pagePeriodStart)) {
        report.navigation = 'MISMATCH';
        return report;
      }
      const buttons = [...ticket.querySelectorAll('button')].filter((button) =>
        button.getClientRects().length && /^买入\s+(涨|跌)$/.test(button.textContent.trim()));
      if (buttons.length !== 1) return report;
      const amount = input.value.trim();
      const numeric = /^(?:\d+(?:\.\d*)?|\.\d+)$/.test(amount) ? Number(amount) : null;
      report.amountUsd = Number.isFinite(numeric) && numeric >= 0 ? numeric : null;
      report.selectedSide = /涨$/.test(buttons[0].textContent.trim()) ? 'Up' : 'Down';
      report.buyButtonEnabled = buttonIsEnabled(buttons[0]);
      report.ticketStatus = 'PASS';
    } catch {
      // Inspection failures report fixed stages, never raw page data.
      report.navigation = 'MISMATCH';
    }
    return report;
  }

  function prepareAmount(status, url, doc, now = Date.now() / 1000) {
    const draft = usableDraft(status, now);
    if (!draft || !matchesMarket(url, draft)) throw new Error('草稿过期、受限或页面轮次不匹配');
    const input = findAmountInput(doc);
    const report = readPreflight(doc, url, now);
    if (report?.navigation !== 'CURRENT' || report.ticketStatus !== 'PASS') throw new Error('当前票据标题或页面轮次未核对');
    const setter = Object.getOwnPropertyDescriptor(input.ownerDocument.defaultView.HTMLInputElement.prototype, 'value').set;
    setter.call(input, '1');
    input.dispatchEvent(new Event('input', {bubbles: true}));
    input.dispatchEvent(new Event('change', {bubbles: true}));
    if (input.value !== '1') throw new Error('金额未保持为 1，请手动检查');
    return draft.side;
  }

  // Export pure guards for the local fixture tests; this is an isolated extension world.
  globalThis.FutureBtc5m = {usableDraft, matchesMarket, observationView, findAmountInput, prepareAmount,
    navigationTarget, followCurrentMarket, readPreflight};
  if (typeof document === 'undefined') return;

  const panel = document.createElement('aside');
  panel.style.cssText = 'position:fixed;left:16px;bottom:48px;z-index:2147483647;width:300px;padding:14px;background:#171b22;color:#f4f4f4;border:1px solid #616976;border-radius:10px;font:13px/1.6 system-ui;box-shadow:0 4px 20px #0008';
  const title = document.createElement('strong');
  title.textContent = 'PolyHermes · BTC 5m · $1';
  const text = document.createElement('p');
  text.style.whiteSpace = 'pre-line';
  const link = document.createElement('a');
  link.textContent = '前往本轮市场';
  link.style.cssText = 'display:none;color:#8ac5ff;margin-right:12px';
  const prepare = document.createElement('button');
  prepare.textContent = '填入 $1 草稿';
  prepare.disabled = true;
  const inspect = document.createElement('button');
  inspect.textContent = '检查页面';
  inspect.style.marginLeft = '8px';
  const inspection = document.createElement('p');
  const navigation = document.createElement('p');
  const preflightReport = document.createElement('p');
  const note = document.createElement('p');
  note.textContent = '选择提示方向后，由你检查并点击 Future 买入。$1 为订单本金，费用以平台为准。';
  panel.append(title, text, link, prepare, inspect, inspection, navigation, note, preflightReport);
  document.body.append(panel);
  let latest = null;
  let polling = false;
  let inspectedUrl = null;
  let autoCheckedUrl = null;
  let reporting = false;

  async function reportPage() {
    if (reporting) return;
    const payload = readPreflight(document, location.href);
    if (!payload) {
      preflightReport.textContent = '只读预检：等待 BTC 5 分钟市场页面';
      return;
    }
    reporting = true;
    try {
      const reply = await chrome.runtime.sendMessage({type: 'FUTURE_BTC5M_PREFLIGHT', payload});
      preflightReport.textContent = reply?.ok ? '只读预检：已上报现有票据，未提交订单' : '只读预检：本地服务未确认';
    } catch {
      preflightReport.textContent = '只读预检：本地服务未连接';
    } finally {
      reporting = false;
    }
  }

  async function readStatus() {
    const reply = await chrome.runtime.sendMessage({type: 'FUTURE_BTC5M_STATUS'});
    if (!reply?.ok) throw new Error(reply?.error || '本地助手未连接');
    return reply.status;
  }

  async function poll() {
    if (polling) return;
    polling = true;
    prepare.disabled = true;
    link.style.display = 'none';
    try {
      latest = await readStatus();
      const now = Date.now() / 1000;
      if (inspectedUrl !== location.href) {
        inspection.textContent = '';
        autoCheckedUrl = null;
        inspectedUrl = location.href;
      }
      const sourceUrl = location.href;
      navigation.textContent = followCurrentMarket(latest, sourceUrl, document, globalThis.sessionStorage, now);
      const target = navigationTarget(latest, location.href, now);
      if (sourceUrl === location.href && target &&
          matchesMarket(location.href, {slug: new URL(target).pathname.split('/').pop()}) &&
          typeof document.querySelectorAll === 'function' && !endedMarketButtons(document).length) {
        if (autoCheckedUrl !== location.href && inspectPage()) autoCheckedUrl = location.href;
      } else {
        inspection.textContent = '';
        autoCheckedUrl = null;
      }
      const draft = usableDraft(latest, now);
      const view = observationView(latest, location.href, now);
      text.textContent = view.text;
      if (view.marketUrl) {
        link.href = view.marketUrl;
        link.style.display = 'inline';
      }
      if (draft && matchesMarket(location.href, draft)) {
        text.textContent += `\n入场草稿剩余 ${Math.max(0, Math.floor(draft.expires_at - now))} 秒`;
        prepare.disabled = false;
      }
    } catch (error) {
      latest = null;
      text.textContent = error.message;
      inspection.textContent = '';
      autoCheckedUrl = null;
      navigation.textContent = '自动换轮：暂停（本地助手未连接）';
    } finally {
      polling = false;
    }
  }

  function inspectPage() {
    try {
      const value = findAmountInput(document).value;
      const report = readPreflight(document, location.href);
      if (report?.navigation !== 'CURRENT' || report.ticketStatus !== 'PASS') throw new Error('当前票据标题或页面轮次未核对');
      inspection.textContent = `页面检查通过：已找到中文美元市价买入栏；${Number(value) === 1 ?
        '检查时金额为 $1' : `检查时金额为 ${value || '空'}，尚未设为 $1`}。仅检查，未修改金额。`;
      return true;
    } catch (error) {
      inspection.textContent = `页面检查失败：${error.message}`;
      return false;
    }
  }

  inspect.addEventListener('click', inspectPage);

  prepare.addEventListener('click', async () => {
    prepare.disabled = true;
    try {
      // Re-read STOP and expiry immediately before changing the amount.
      latest = await readStatus();
      const side = prepareAmount(latest, location.href, document);
      text.textContent = `已填入 $1。请手动选择${side === 'Up' ? '涨 Up' : '跌 Down'}，核对市场和费用后买入。`;
    } catch (error) {
      text.textContent = error.message;
    }
  });
  poll();
  reportPage();
  setInterval(() => { poll(); reportPage(); }, 1000);
})();
