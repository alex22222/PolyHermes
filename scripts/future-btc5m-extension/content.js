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

  function parseButtonQuote(text, side) {
    if (typeof text !== 'string' || !['Up', 'Down'].includes(side)) return null;
    const match = text.trim().match(/^(涨|跌)\s*((?:0|[1-9]\d{0,2})(?:\.\d{1,2})?)\s*(¢|%)$/);
    if (!match || match[1] !== (side === 'Up' ? '涨' : '跌')) return null;
    const quote = Number(match[2]);
    return quote >= 0 && quote <= 100 ? quote : null;
  }

  function validButtonQuote(value) {
    return Number.isFinite(value) && value >= 0 && value <= 100 && Number(value.toFixed(2)) === value;
  }

  function readButtonQuotes(ticket) {
    const buttons = [...ticket.querySelectorAll('button')].filter((button) => button.getClientRects().length);
    const quote = (side, pattern) => {
      const matches = buttons.filter((button) => pattern.test(button.textContent.trim()));
      return matches.length === 1 && buttonIsEnabled(matches[0]) && matches[0].tagName === 'BUTTON' &&
        matches[0].type === 'button' ? parseButtonQuote(matches[0].textContent, side) : null;
    };
    const upQuoteCents = quote('Up', /^涨(?:\s|\d|--)/);
    const downQuoteCents = quote('Down', /^跌(?:\s|\d|--)/);
    const preferredSide = upQuoteCents === null || downQuoteCents === null || upQuoteCents === downQuoteCents ? null :
      upQuoteCents > downQuoteCents ? 'Up' : 'Down';
    return {upQuoteCents, downQuoteCents, preferredSide};
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
    const report = {schemaVersion: 2, marketUrl: parsed.origin + parsed.pathname, pagePeriodStart,
      checkedAt: now, navigation, ticketStatus: 'FAIL', amountUsd: null, selectedSide: null, buyButtonEnabled: false,
      upQuoteCents: null, downQuoteCents: null};
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
      const quotes = readButtonQuotes(ticket);
      report.upQuoteCents = quotes.upQuoteCents;
      report.downQuoteCents = quotes.downQuoteCents;
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

  // User-authorized ticket preparation has no order-submission capability and does not
  // change the legacy official-eligibility guard above.
  function usablePreparation(wrapper, now = Date.now() / 1000) {
    const preparation = wrapper?.preparation;
    const intent = preparation?.intent;
    if (wrapper?.bridgeId !== 'future-btc5m' || !Number.isFinite(wrapper.serverTime) ||
        !Number.isFinite(now) || Math.abs(now - wrapper.serverTime) > 3 ||
        preparation?.mode !== 'PREPARE_ONLY' || preparation.noSubmission !== true ||
        preparation.operatorAuthorized !== true || preparation.authorizationSource !== 'USER_REQUEST' ||
        preparation.enabled !== true || !['PENDING', 'CLAIMED'].includes(preparation.state) || !intent ||
        intent.schemaVersion !== 2 || intent.mode !== 'PREPARE_ONLY' || intent.noSubmission !== true ||
        intent.operatorAuthorized !== true || intent.authorizationSource !== 'USER_REQUEST') return null;
    const keys = ['schemaVersion', 'id', 'slug', 'periodStart', 'periodEnd', 'side', 'amountUsd', 'createdAt',
      'expiresAt', 'priceObservedAt', 'openPrice', 'currentPrice', 'priceSource', 'openPriceSource',
      'twapLookbackSeconds', 'mode', 'noSubmission', 'operatorAuthorized', 'authorizationSource', 'claimToken',
      'upQuoteCents', 'downQuoteCents', 'quoteObservedAt', 'selectionSource'];
    if (Object.keys(intent).length !== keys.length || !keys.every((key) => Object.hasOwn(intent, key)) ||
        intent.selectionSource !== 'HIGHER_BUTTON_PRICE' || !validButtonQuote(intent.upQuoteCents) ||
        !validButtonQuote(intent.downQuoteCents) || intent.upQuoteCents === intent.downQuoteCents ||
        intent.side !== (intent.upQuoteCents > intent.downQuoteCents ? 'Up' : 'Down') ||
        !Number.isFinite(intent.quoteObservedAt) || intent.quoteObservedAt > now || now - intent.quoteObservedAt > 5) return null;
    const start = Math.floor(now / 300) * 300;
    if (!Number.isSafeInteger(intent.periodStart) || intent.periodStart !== start ||
        intent.id !== `future-btc5m-prepare:${start}` || intent.slug !== `btc-updown-5m-${start}` ||
        intent.periodEnd !== start + 300 || intent.amountUsd !== 1 || !['Up', 'Down'].includes(intent.side) ||
        intent.priceSource !== 'chainlink' ||
        intent.openPriceSource !== 'polymarket_crypto_price_fiveminute_twap60_openPrice' ||
        intent.twapLookbackSeconds !== 60 || !Number.isFinite(intent.openPrice) || intent.openPrice <= 0 ||
        !Number.isFinite(intent.currentPrice) || intent.currentPrice <= 0 ||
        !Number.isFinite(intent.createdAt) || intent.createdAt < start + 60 || intent.createdAt >= start + 80 ||
        intent.expiresAt !== start + 80 || now < intent.createdAt || now >= intent.expiresAt ||
        !Number.isFinite(intent.priceObservedAt) || intent.priceObservedAt > intent.createdAt ||
        now - intent.priceObservedAt > 5 || now < start + 60 ||
        !(intent.claimToken === null || typeof intent.claimToken === 'string' && /^[a-f0-9]{32}$/.test(intent.claimToken))) return null;
    return intent;
  }

  function preparationError(code) {
    const error = new Error(code);
    error.code = code;
    return error;
  }

  function readPreparationTicket(doc, url, start) {
    // Freshness is checked against the bridge before every stage; this read binds the
    // DOM title and URL to that already checked round.
    const report = readPreflight(doc, url, start + 60);
    if (report?.navigation !== 'CURRENT' || report.pagePeriodStart !== start) throw preparationError('MARKET_MISMATCH');
    if (report.ticketStatus !== 'PASS') throw preparationError('TICKET_CHANGED');
    const input = findAmountInput(doc);
    if (!buttonIsEnabled(input)) throw preparationError('TICKET_CHANGED');
    const ticket = findAmountTicket(doc, input);
    const buttons = [...ticket.querySelectorAll('button')].filter((button) => button.getClientRects().length);
    const directions = {};
    const states = {};
    for (const [side, pattern] of [['Up', /^涨(?:\s|\d|--)/], ['Down', /^跌(?:\s|\d|--)/]]) {
      const matches = buttons.filter((button) => pattern.test(button.textContent.trim()));
      if (matches.length !== 1 || !buttonIsEnabled(matches[0]) || matches[0].tagName !== 'BUTTON' ||
          matches[0].type !== 'button') throw preparationError('UNSAFE_DIRECTION_CONTROL');
      const button = matches[0];
      const evidence = ['aria-pressed', 'aria-selected'].map((name) => button.getAttribute?.(name))
        .filter((value) => value !== null && value !== undefined);
      directions[side] = button;
      if (evidence.length) {
        if (evidence.some((value) => !['true', 'false'].includes(value)) ||
            evidence.some((value) => value !== evidence[0])) throw preparationError('UNSAFE_DIRECTION_CONTROL');
        states[side] = evidence[0] === 'true';
      } else {
        // Observed in the real Future ticket: this exact misspelled token marks the
        // selected button. The other button has both panel/text tokens. No color is guessed.
        const classes = new Set((typeof button.className === 'string' ? button.className : '').split(/\s+/));
        if (classes.has('text-text-hightlightbtn') && !classes.has('bg-panel-100') && !classes.has('text-text-400')) {
          states[side] = true;
        } else if (!classes.has('text-text-hightlightbtn') && classes.has('bg-panel-100') && classes.has('text-text-400')) {
          states[side] = false;
        } else throw preparationError('UNSAFE_DIRECTION_CONTROL');
      }
    }
    if (states.Up === states.Down) throw preparationError('UNSAFE_DIRECTION_CONTROL');
    const selectedSide = states.Up ? 'Up' : 'Down';
    if (selectedSide !== report.selectedSide) throw preparationError('UNSAFE_DIRECTION_CONTROL');
    const quotes = readButtonQuotes(ticket);
    if (quotes.upQuoteCents === null || quotes.downQuoteCents === null) throw preparationError('BUTTON_QUOTES_UNAVAILABLE');
    if (!quotes.preferredSide) throw preparationError('BUTTON_QUOTES_TIED');
    return {input, directions, selectedSide, ...quotes};
  }

  async function prepareOnlyOnce(wrapper, doc, readUrl, storage, transport, nowFn = () => Date.now() / 1000) {
    const intent = usablePreparation(wrapper, nowFn());
    if (!intent || wrapper.preparation.state !== 'PENDING' || intent.claimToken !== null) return null;
    let claimed = null;
    let result = null;
    const key = 'polyhermes.future-btc5m.preparation';
    const check = async () => {
      const current = await transport.readPreparation();
      const now = nowFn();
      if (now >= intent.expiresAt) throw preparationError('INTENT_EXPIRED');
      if (now - intent.priceObservedAt > 5) throw preparationError('PREPARATION_REVOKED');
      if (now - intent.quoteObservedAt > 5) throw preparationError('BUTTON_QUOTES_NOT_FRESH');
      const value = usablePreparation(current, now);
      if (!value || current.preparation.state !== 'CLAIMED' || value.id !== intent.id ||
          value.claimToken !== claimed.claimToken || now - intent.priceObservedAt > 5 ||
          !Object.keys(intent).every((field) => field === 'claimToken' || value[field] === intent[field])) {
        throw preparationError('PREPARATION_REVOKED');
      }
      const ticket = readPreparationTicket(doc, readUrl(), intent.periodStart);
      if (ticket.preferredSide !== intent.side) throw preparationError('HIGHER_BUTTON_SIDE_CHANGED');
      return ticket;
    };
    try {
      const initial = readPreparationTicket(doc, readUrl(), intent.periodStart);
      if (initial.preferredSide !== intent.side) throw preparationError('HIGHER_BUTTON_SIDE_CHANGED');
      const previous = JSON.parse(storage.getItem(key) || 'null');
      if (previous !== null && (!Number.isSafeInteger(previous.periodStart) ||
          previous.id !== `future-btc5m-prepare:${previous.periodStart}`)) throw preparationError('PREPARATION_FAILED');
      if (previous?.periodStart >= intent.periodStart) return null;
      // Persist before claiming. An uncertain claim response, reload or failure never retries this round.
      storage.setItem(key, JSON.stringify({periodStart: intent.periodStart, id: intent.id}));
      const response = await transport.claimPreparation({schemaVersion: 1, id: intent.id});
      claimed = usablePreparation(response, nowFn());
      if (!claimed || response.preparation.state !== 'CLAIMED' || claimed.id !== intent.id ||
          typeof claimed.claimToken !== 'string' ||
          !Object.keys(intent).every((field) => field === 'claimToken' || claimed[field] === intent[field])) {
        claimed = null;
        throw preparationError('PREPARATION_FAILED');
      }
      let ticket = await check();
      if (ticket.selectedSide !== intent.side) {
        // This is the outcome toggle, never the final Buy control or a form submission.
        ticket.directions[intent.side].click();
        ticket = await check();
        if (ticket.selectedSide !== intent.side) throw preparationError('DIRECTION_WRITE_FAILED');
      }
      ticket = await check();
      try {
        const setter = Object.getOwnPropertyDescriptor(ticket.input.ownerDocument.defaultView.HTMLInputElement.prototype, 'value').set;
        setter.call(ticket.input, '1');
        ticket.input.dispatchEvent(new Event('input', {bubbles: true}));
        ticket.input.dispatchEvent(new Event('change', {bubbles: true}));
      } catch {
        throw preparationError('AMOUNT_WRITE_FAILED');
      }
      ticket = await check();
      if (ticket.input.value !== '1') throw preparationError('AMOUNT_WRITE_FAILED');
      if (ticket.selectedSide !== intent.side) throw preparationError('DIRECTION_WRITE_FAILED');
      const report = readPreflight(doc, readUrl(), nowFn());
      if (report?.navigation !== 'CURRENT' || report.ticketStatus !== 'PASS' || report.amountUsd !== 1 ||
          report.selectedSide !== intent.side || !report.buyButtonEnabled ||
          !(await transport.reportPreflight(report))?.ok) throw preparationError('POSTCHECK_FAILED');
      ticket = await check();
      if (ticket.input.value !== '1' || ticket.selectedSide !== intent.side) throw preparationError('POSTCHECK_FAILED');
      result = {status: 'READY', reason: null};
    } catch (error) {
      const codes = ['PREPARATION_FAILED', 'MARKET_MISMATCH', 'TICKET_CHANGED', 'UNSAFE_DIRECTION_CONTROL',
        'AMOUNT_WRITE_FAILED', 'DIRECTION_WRITE_FAILED', 'POSTCHECK_FAILED', 'INTENT_EXPIRED', 'PREPARATION_REVOKED',
        'BUTTON_QUOTES_UNAVAILABLE', 'BUTTON_QUOTES_TIED', 'BUTTON_QUOTES_NOT_FRESH', 'HIGHER_BUTTON_SIDE_CHANGED'];
      const reason = codes.includes(error.code) ? error.code : 'PREPARATION_FAILED';
      result = {status: reason === 'INTENT_EXPIRED' ? 'EXPIRED' : 'FAILED', reason};
    }
    if (claimed) {
      const report = readPreflight(doc, readUrl(), nowFn());
      const payload = {schemaVersion: 1, id: intent.id, claimToken: claimed.claimToken, checkedAt: nowFn(),
        status: result.status, marketUrl: report?.marketUrl || `https://future.news/zh/event/${intent.slug}`,
        amountUsd: report?.amountUsd ?? null, selectedSide: report?.selectedSide ?? null,
        reason: result.reason, noSubmission: true};
      try {
        if (!(await transport.acknowledge(payload))?.ok) return {status: 'FAILED', reason: 'POSTCHECK_FAILED'};
      } catch {
        return {status: 'FAILED', reason: 'POSTCHECK_FAILED'};
      }
    }
    return result;
  }

  // Export pure guards for the local fixture tests; this is an isolated extension world.
  globalThis.FutureBtc5m = {usableDraft, matchesMarket, observationView, findAmountInput, findAmountTicket, buttonIsEnabled, prepareAmount,
    navigationTarget, followCurrentMarket, readPreflight, usablePreparation, readPreparationTicket, prepareOnlyOnce, parseButtonQuote};
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
  const preparationReport = document.createElement('p');
  const note = document.createElement('p');
  const preparationNote = '开启自动票据后，仅在每轮第 60–80 秒、行情有效时选择按钮数字较大的一方并填入 $1，准备好后自动点击一次 Future 买入。$1 为订单本金，费用以平台为准。';
  note.style.whiteSpace = 'pre-line';
  note.textContent = preparationNote;
  const autoBuyReport = document.createElement('p');
  autoBuyReport.style.whiteSpace = 'pre-line';
  panel.append(title, text, link, prepare, inspect, inspection, navigation, note, preflightReport, preparationReport,
    autoBuyReport);
  document.body.append(panel);
  let latest = null;
  let polling = false;
  let inspectedUrl = null;
  let autoCheckedUrl = null;
  let reporting = false;
  let reportPromise = null;
  let autoBuyer = null;

  async function reportPage() {
    if (reporting) return;
    const payload = readPreflight(document, location.href);
    if (!payload) {
      preflightReport.textContent = '只读预检：等待 BTC 5 分钟市场页面';
      return;
    }
    reporting = true;
    try {
      reportPromise = chrome.runtime.sendMessage({type: 'FUTURE_BTC5M_PREFLIGHT', payload});
      const reply = await reportPromise;
      preflightReport.textContent = reply?.ok ? '只读预检：已上报现有票据，未提交订单' : '只读预检：本地服务未确认';
    } catch {
      preflightReport.textContent = '只读预检：本地服务未连接';
    } finally {
      reporting = false;
      reportPromise = null;
    }
  }

  async function readStatus() {
    const reply = await chrome.runtime.sendMessage({type: 'FUTURE_BTC5M_STATUS'});
    if (!reply?.ok) throw new Error(reply?.error || '本地助手未连接');
    return reply.status;
  }

  async function preparationRequest(type, payload) {
    const reply = await chrome.runtime.sendMessage(payload ? {type, payload} : {type});
    if (!reply?.ok) throw preparationError('PREPARATION_FAILED');
    return reply.status;
  }

  // buy_once.js follows the same switch and re-reads READY itself; an omitted value only
  // redraws the current watcher state without arming or stopping it.
  function showAutoBuy(enabled) {
    let view;
    try {
      autoBuyer ??= globalThis.FutureBtc5mBuyOnce.createAutoBuyer({
        readPreparation: () => preparationRequest('FUTURE_BTC5M_PREPARATION'),
        reportAudit: (payload) => preparationRequest('FUTURE_BTC5M_BUY_AUDIT', payload)});
      view = enabled === undefined ? autoBuyer.status() : autoBuyer.sync(enabled);
    } catch {
      autoBuyReport.textContent = '自动买入：脚本未加载，不会点击';
      return;
    }
    const reasons = {TICKET_CHANGED: '票据已改变', BUY_BUTTON_UNSAFE: '买入按钮不唯一或不可用',
      READY_CHANGED: '准备记录已改变', STORAGE_FAILED: '本地点击记录不可用', FINAL_CHECK_FAILED: '最终核对失败',
      ALREADY_CONSUMED: '本轮已点击过', WEB_LOCKS_REQUIRED: '浏览器缺少 Web Locks',
      UPDATED_EXTENSION_CONTEXT_REQUIRED: '请重新加载扩展'};
    const states = {OFF: '跟随“自动准备票据”开关，当前关闭，不会点击',
      WATCHING: '已开启，新票据准备好后点击一次买入（每轮最多一次）',
      PAUSED: '等待有效准备状态后重新监控，暂不点击',
      BLOCKED: `无法启动（${reasons[view.reason] || view.reason}），不会点击`};
    let report = `自动买入：${states[view.state]}`;
    if (view.last?.state === 'CLICK_ATTEMPTED') {
      report += `\n最近：已点击“买入 ${view.last.side === 'Up' ? '涨' : '跌'}” $1（btc-updown-5m-${view.last.periodStart}），成交以 Future 订单为准`;
    } else if (view.last) report += `\n最近：未点击（${reasons[view.last.reason] || view.last.reason}）`;
    report += view.auditError === 'AUDIT_STORAGE_FAILED' || view.last?.audit === 'FAILED' ? '\n审计：本地记录写入失败，请检查' :
      view.pendingAudits ? `\n审计：${view.pendingAudits} 条已保存在本页，等待写入本机账本` : '\n审计：全部已写入本机账本';
    autoBuyReport.textContent = report;
  }

  async function pollPreparation() {
    try {
      const wrapper = await preparationRequest('FUTURE_BTC5M_PREPARATION');
      const labels = {DISABLED: '已关闭；本次检查未切换方向或填写金额，请在 PolyHermes 开启“自动准备票据”',
        WAITING_SIGNAL: '等待本轮有效行情；本次检查未切换方向或填写金额', WAITING_BROWSER: '等待浏览器报告；本次检查未切换方向或填写金额', PENDING: '等待准备',
        CLAIMED: '本轮已认领，不重复准备', READY: '已准备 $1 与按钮数字较大的一方',
        FAILED: '本轮准备失败，不重试', EXPIRED: '本轮准备窗口已过期', REVOKED: '本轮准备已停止',
        RECEIPT_UNKNOWN: '票据回执未知，请检查页面', BLOCKED: '准备受阻'};
      const value = wrapper?.preparation;
      if (wrapper?.bridgeId !== 'future-btc5m' || !Number.isFinite(wrapper.serverTime) ||
          Math.abs(Date.now() / 1000 - wrapper.serverTime) > 3 || value?.mode !== 'PREPARE_ONLY' ||
          value.noSubmission !== true || value.operatorAuthorized !== true ||
          value.authorizationSource !== 'USER_REQUEST' || typeof value.enabled !== 'boolean' ||
          !Object.hasOwn(labels, value.state)) throw preparationError('PREPARATION_FAILED');
      // Arm before this poll can prepare a ticket, so the new READY is created after arming.
      showAutoBuy(value.enabled);
      text.textContent = text.textContent.replace('本轮采样方向：', 'BTC参考价差（不决定票据方向）：');
      const state = value.state;
      const now = Date.now() / 1000;
      const elapsed = now - Math.floor(now / 300) * 300;
      if (state === 'WAITING_SIGNAL') labels.WAITING_SIGNAL = elapsed < 60 ? '等待本轮第 60 秒；本次检查未切换方向或填写金额' :
        elapsed >= 80 ? '本轮已超过第 80 秒，等待下一轮；本次检查未切换方向或填写金额' :
        latest?.reason === 'CHAINLINK_PRICE_STALE_OR_FUTURE' ? '行情过期或采样时间无效，等待有效行情；本次检查未切换方向或填写金额' :
        labels.WAITING_SIGNAL;
      const reasons = {BROWSER_NOT_CONNECTED: '浏览器报告过期', MARKET_NOT_CURRENT: '页面不是本轮市场',
        TICKET_CHECK_FAILED: '买入栏未核对', BUTTON_QUOTES_UNAVAILABLE: '按钮数字读取失败',
        BUTTON_QUOTES_TIED: '两边按钮数字相同', BUTTON_QUOTES_NOT_FRESH: '按钮报价已过期',
        HIGHER_BUTTON_SIDE_CHANGED: '较大方向已改变', PREPARED_TICKET_CHANGED: '准备后的票据已改变',
        STOP_FILE_PRESENT: '助手已停止', PREPARATION_RECEIPT_UNKNOWN: '票据回执未知',
        PREPARATION_REVOKED: '行情过期或准备许可已失效', DIRECTION_WRITE_FAILED: '方向切换回读失败',
        AMOUNT_WRITE_FAILED: '$1 金额回读失败', POSTCHECK_FAILED: '准备后核对失败'};
      const details = Array.isArray(value.reasons) ? value.reasons.filter((reason) => Object.hasOwn(reasons, reason))
        .map((reason) => reasons[reason]).join('、') : '';
      preparationReport.textContent = `自动票据：${labels[state]}${details ? ` · ${details}` : ''}（未提交订单）`;
      if (reportPromise) await reportPromise.catch(() => {});
      const result = await prepareOnlyOnce(wrapper, document, () => location.href, globalThis.sessionStorage, {
        readPreparation: () => preparationRequest('FUTURE_BTC5M_PREPARATION'),
        claimPreparation: (payload) => preparationRequest('FUTURE_BTC5M_PREPARATION_CLAIM', payload),
        reportPreflight: (payload) => chrome.runtime.sendMessage({type: 'FUTURE_BTC5M_PREFLIGHT', payload}),
        acknowledge: async (payload) => {
          const status = await preparationRequest('FUTURE_BTC5M_PREPARATION_ACK', payload);
          return {ok: status?.bridgeId === 'future-btc5m' && status.preparation?.state === payload.status};
        },
      });
      if (result) preparationReport.textContent = result.status === 'READY' ?
        `自动票据：已准备 $1，并按按钮较大数值选择${value.intent.side === 'Up' ? '涨 Up' : '跌 Down'}（准备本身未提交订单）` :
        `自动票据：${result.status} · ${reasons[result.reason] || result.reason}（未提交订单，不重试）`;
      const report = readPreflight(document, location.href);
      const sideText = (side) => side === 'Up' ? '涨 Up' : side === 'Down' ? '跌 Down' : '未核对';
      note.textContent = preparationNote;
      if (report?.navigation === 'CURRENT' && report.ticketStatus === 'PASS' &&
          validButtonQuote(report.upQuoteCents) && validButtonQuote(report.downQuoteCents)) {
        const higherSide = report.upQuoteCents === report.downQuoteCents ? null :
          report.upQuoteCents > report.downQuoteCents ? 'Up' : 'Down';
        note.textContent += `\n报价观察：涨 ${report.upQuoteCents}¢ / 跌 ${report.downQuoteCents}¢；数字较大：${higherSide ? sideText(higherSide) : '同价，暂停准备'}；当前选中：${sideText(report.selectedSide)}。`;
      }
    } catch {
      note.textContent = preparationNote;
      preparationReport.textContent = '自动票据：本地准备服务未连接（未提交订单）';
      showAutoBuy();
    }
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
      await pollPreparation();
    } catch (error) {
      latest = null;
      note.textContent = preparationNote;
      text.textContent = error.message;
      inspection.textContent = '';
      autoCheckedUrl = null;
      navigation.textContent = '自动换轮：暂停（本地助手未连接）';
      preparationReport.textContent = '自动票据：暂停（本地助手未连接，未提交订单）';
      showAutoBuy();
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
