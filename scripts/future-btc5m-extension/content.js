(() => {
  // Round series of the strategies (same table as future_btc5m_series.py). The bridge
  // reports which one is active; a page, ticket or record always carries its own series.
  const SERIES = {
    '5m': {period: 300, entry: [60, 80], slug: 'btc-updown-5m-', id: 'future-btc5m-prepare:',
      openSource: 'polymarket_crypto_price_fiveminute_twap60_openPrice', label: 'BTC 5 分钟'},
    '15m': {period: 900, entry: [150, 170], slug: 'btc-updown-15m-', id: 'future-btc15m-prepare:',
      openSource: 'polymarket_crypto_price_fifteen_twap60_openPrice', label: 'BTC 15 分钟（反 1 小时方向）'},
    // Runs alongside 15m; its entry is a 2-minute window at a decision checkpoint (entryWindow).
    '4h': {period: 14400, entry: null, slug: 'btc-updown-4h-', id: 'future-btc4h-prepare:',
      openSource: 'polymarket_crypto_price_fourhour_twap60_openPrice', label: 'BTC 4 小时（周末高把握）'},
  };
  // Absolute entry window of a round containing `at`. 4h decisions happen at minutes 5 and 10 of
  // each quarter hour, each with a 2-minute window (future_btc5m_series.checkpoint_window).
  function entryWindow(series, start, at) {
    if (series !== '4h') return [start + SERIES[series].entry[0], start + SERIES[series].entry[1]];
    const offset = at - start;
    const minute = Math.floor(offset / 300) * 5;
    if (!Number.isFinite(offset) || minute < 5 || minute > 235 || minute % 15 === 0 || offset - minute * 60 >= 120) return null;
    return [start + minute * 60, start + minute * 60 + 120];
  }
  // Seconds into the round; outside a 4h window this is an empty window at the round start.
  const relativeWindow = (series, start, at) => {
    const window = entryWindow(series, start, at);
    return window ? [window[0] - start, window[1] - start] : [0, 0];
  };
  const seriesOf = (value) => (typeof value === 'string' && Object.hasOwn(SERIES, value) ? value : null);
  const roundStart = (now, series) => Math.floor(now / SERIES[series].period) * SERIES[series].period;
  const roundUrl = (start, series) => `https://future.news/zh/event/${SERIES[series].slug}${start}`;
  // {series, start} of a Future BTC round path, else null.
  function pathRound(pathname) {
    const match = typeof pathname === 'string' && pathname.match(/^\/(?:zh\/)?event\/btc-updown-(5m|15m|4h)-(0|[1-9]\d*)\/?$/);
    const start = match && Number(match[2]);
    return match && Number.isSafeInteger(start) && start % SERIES[match[1]].period === 0 ? {series: match[1], start} : null;
  }
  function idRound(id) {
    for (const [series, value] of Object.entries(SERIES)) {
      const digits = typeof id === 'string' && id.startsWith(value.id) ? id.slice(value.id.length) : null;
      if (digits !== null && /^(0|[1-9]\d*)$/.test(digits) && Number(digits) % value.period === 0) {
        return {series, start: Number(digits)};
      }
    }
    return null;
  }

  // Presentation only: a disconnected service is not a switch back to BTC5m.
  // Page context can explain a market/round, but cannot prove the active strategy.
  function strategyPresentation(preparation, status, remembered, url, now) {
    const fresh = (stamp) => Number.isFinite(stamp) && Math.abs(now - stamp) <= 3;
    const prepared = preparation?.bridgeId === 'future-btc5m' && fresh(preparation.serverTime) &&
      preparation.preparation?.mode === 'PREPARE_ONLY' && preparation.preparation.noSubmission === true ?
      seriesOf(preparation.preparation.series) : null;
    const observed = status?.schema_version === 1 && status.mode === 'ASSIST_ONLY' &&
      status.live_enabled === false && fresh(status.server_time) ? seriesOf(status.series) : null;
    if (prepared && observed && prepared !== observed) {
      return {series: null, source: 'conflict', label: '策略状态冲突，待核实'};
    }
    const series = prepared ?? observed;
    // The combined strategy names the series whose page is current (4h only in its window).
    if (series) return {series, source: 'confirmed', combined: preparation?.preparation?.strategy === 'btc15m_plus_4h',
      label: preparation?.preparation?.strategy === 'btc15m_plus_4h' ? `15 分钟 + 4 小时 · 当前 ${SERIES[series].label}` :
        SERIES[series].label};
    if (seriesOf(remembered)) return {series: remembered, source: 'remembered',
      label: `${SERIES[remembered].label}（上次确认，当前未核实）`};
    try {
      const page = new URL(url);
      const context = page.origin === 'https://future.news' && !page.username && !page.password && pathRound(page.pathname);
      if (context) return {series: context.series, source: 'page',
        label: `策略未核实 · 页面市场：${SERIES[context.series].label}`};
    } catch {}
    return {series: null, source: 'unknown', label: '策略未核实'};
  }

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
    // The assistant polls the active strategy's series; its status names it.
    const series = seriesOf(status.series) ?? '5m';
    const start = roundStart(now, series);
    if (status.period_start !== start || (status.round_series ?? '5m') !== series) return null;
    try {
      const parsed = new URL(url);
      const page = pathRound(parsed.pathname);
      if (parsed.origin !== 'https://future.news' || parsed.username || parsed.password || !page ||
          page.series === series && page.start > start) return null;
      return roundUrl(start, series);
    } catch {
      return null;
    }
  }

  function endedMarketButtons(doc) {
    return [...doc.querySelectorAll('button')].filter((button) =>
      button.textContent.trim() === '前往实时市场' && button.getClientRects().length);
  }

  function followCurrentMarket(status, url, doc, storage, now = Date.now() / 1000, navigate = null) {
    const target = navigationTarget(status, url, now);
    if (!target) return '自动换轮：暂停（等待有效本地状态或当前 BTC5m 页面）';
    const slug = new URL(target).pathname.split('/').pop();
    // Full document navigation doesn't depend on Future's SPA rendering callbacks.
    // Recover before entry only; never reload a READY ticket or an uncertain Buy result.
    const series = pathRound(new URL(target).pathname).series;
    const start = roundStart(now, series);
    const report = readPreflight(doc, url, now);
    // Before entry only: up to 10 s ahead of the series' entry window. A 4h window is already open
    // when the bridge hands the page to it, so that page loads within the window's first 100 s.
    const window = entryWindow(series, start, now);
    const navigable = series === '4h' ? Boolean(window) && now < window[0] + 100 :
      now >= start + 5 && now < start + SERIES[series].entry[0] - 10;
    if (typeof navigate === 'function' && navigable &&
        (!matchesMarket(url, {slug}) || report?.navigation === 'MISMATCH')) {
      try {
        const key = 'polyhermes.future-btc5m.document-navigation';
        const previous = JSON.parse(storage.getItem(key) || 'null');
        const previousRound = previous && typeof previous.target === 'string' ? pathRound(new URL(previous.target).pathname) : null;
        if (previous !== null && (!previousRound || previous.periodStart !== previousRound.start ||
            previous.target !== roundUrl(previousRound.start, previousRound.series))) {
          return '自动换轮：页面恢复记录无效，本轮不重试';
        }
        if (previousRound?.series === series && previous.periodStart >= start) {
          return '自动换轮：已请求完整页面恢复，本轮不重复刷新';
        }
        storage.setItem(key, JSON.stringify({periodStart: start, target, attempted_at: now}));
        navigate(target);
        return `自动换轮：正在完整加载本轮 ${slug}`;
      } catch {
        return '自动换轮：完整页面恢复失败，本轮不重试';
      }
    }
    if (matchesMarket(url, {slug})) return `自动换轮：已进入本轮 ${slug}`;
    try {
      // This tab's own key survives a page reload; never read site auth or other storage keys.
      const key = 'polyhermes.future-btc5m.navigation';
      const attempt = JSON.parse(storage.getItem(key) || 'null');
      if (attempt?.target === target) return now - attempt.attempted_at < 10 ?
        `自动换轮：正在前往 ${slug}` : '自动换轮：跳转未完成，请点击“前往本轮市场”检查';
      // "前往实时市场" stays in the page's own series; another series waits for the full navigation.
      if (pathRound(new URL(url).pathname)?.series !== series) return `自动换轮：等待切换到 ${SERIES[series].label}`;
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
    const series = seriesOf(status.series) ?? '5m';
    const start = roundStart(now, series);
    if (status.period_start === start && (status.round_series ?? '5m') === series) view.marketUrl = roundUrl(start, series);
    if (!signal) return view;
    if (!seriesOf(signal.series) || !Number.isInteger(signal.period_start) || signal.series !== series ||
        signal.period_start % SERIES[series].period !== 0 ||
        signal.slug !== `${SERIES[series].slug}${signal.period_start}` ||
        signal.period_end !== signal.period_start + SERIES[series].period || signal.price_source !== 'chainlink' ||
        !['Up', 'Down', null].includes(signal.side)) {
      view.text += ' · 信号元数据无效';
      return view;
    }
    if (signal.period_start === start) view.marketUrl = `https://future.news/zh/event/${signal.slug}`;
    const verifiedOpening = signal.open_price_source === SERIES[series].openSource &&
      signal.twap_lookback_seconds === 60;
    let unavailable;
    if (signal.period_start !== start) unavailable = '信号轮次已结束';
    else if (!matchesMarket(url, signal)) unavailable = '页面轮次不匹配';
    else if (!verifiedOpening) unavailable = '开盘参考价未核实';
    else if (!Number.isFinite(signal.price_observed_at) || signal.price_observed_at > now) unavailable = '采样时间无效';
    else if (!entryWindow(series, start, now) || now >= entryWindow(series, start, now)[1]) unavailable = '入场窗口已过期';
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

  function findAmountTicket(doc, input, marketOnly = true) {
    let ticket = input.parentElement;
    for (let depth = 0; ticket && depth < 7; depth++, ticket = ticket.parentElement) {
      if (ticket === doc.body) break;
      const labels = [...ticket.querySelectorAll('button')]
        .filter((button) => button.getClientRects().length)
        .map((button) => button.textContent.trim());
      if (/金额\s*\(\$\)/.test(ticket.textContent) &&
          labels.includes('买入') && labels.includes('卖出') &&
          (marketOnly ? labels.includes('市价单') && !labels.includes('限价单') :
            labels.filter((label) => /^(市价单|限价单)$/.test(label)).length === 1) &&
          labels.some((label) => /^买入\s+(涨|跌)$/.test(label) ||
            !marketOnly && /^最低购买金额为\s*\$/.test(label)) &&
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

  function ticketMatchesPeriod(doc, ticket, start, period = 300) {
    const formatter = new Intl.DateTimeFormat('en-US', {timeZone: 'America/New_York', month: 'long',
      day: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true});
    const values = (timestamp) => Object.fromEntries(formatter.formatToParts(new Date(timestamp * 1000))
      .filter((part) => part.type !== 'literal').map((part) => [part.type, part.value]));
    const opening = values(start);
    const ending = values(start + period);
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

  function orderTypeTicket(doc, url, now, series = pathRound(new URL(url).pathname)?.series ?? '5m') {
    const start = roundStart(now, series);
    if (!matchesMarket(url, {slug: `${SERIES[series].slug}${start}`}) || endedMarketButtons(doc).length) {
      throw preparationError('MARKET_NOT_CURRENT');
    }
    const inputs = [...doc.querySelectorAll('input[placeholder="订单大小"]')]
      .filter((input) => !input.disabled && !input.readOnly && input.getClientRects().length);
    if (inputs.length !== 1 || !buttonIsEnabled(inputs[0])) throw preparationError('TICKET_CHECK_FAILED');
    const ticket = findAmountTicket(doc, inputs[0], false);
    if (!ticketMatchesPeriod(doc, ticket, start, SERIES[series].period)) throw preparationError('MARKET_NOT_CURRENT');
    const controls = [...ticket.querySelectorAll('button')].filter((button) => button.getClientRects().length);
    if (controls.filter((button) => /^买入\s+(涨|跌)$|^最低购买金额为\s*\$/.test(button.textContent.trim())).length !== 1) {
      throw preparationError('TICKET_CHECK_FAILED');
    }
    const modes = controls.filter((button) => /^(市价单|限价单)$/.test(button.textContent.trim()));
    if (modes.length !== 1) throw preparationError('ORDER_TYPE_CONTROL_UNSAFE');
    return {ticket, control: modes[0], mode: modes[0].textContent.trim(), controls};
  }

  // Normalize only the order type, ahead of the 60-second window. Each subsequent
  // menu/readback step requires another fresh, enabled, unclaimed preparation read.
  function restoreMarketOrder(wrapper, status, doc, url, attempt, now) {
    const value = wrapper?.preparation;
    const series = seriesOf(value?.series) ?? '5m';
    const start = roundStart(now, series);
    const lastRound = idRound(value?.lastAttempt?.id);
    if (wrapper?.bridgeId !== 'future-btc5m' || !Number.isFinite(wrapper.serverTime) ||
        Math.abs(now - wrapper.serverTime) > 3 || value?.mode !== 'PREPARE_ONLY' ||
        value.noSubmission !== true || value.operatorAuthorized !== true ||
        value.authorizationSource !== 'USER_REQUEST' || value.enabled !== true ||
        !['WAITING_SIGNAL', 'WAITING_BROWSER', 'BLOCKED'].includes(value.state) || value.intent ||
        lastRound?.series === series && lastRound.start >= start || !Array.isArray(value.reasons) ||
        value.reasons.some((reason) => !['WAITING_CURRENT_SIGNAL', 'BROWSER_NOT_CONNECTED', 'MARKET_NOT_CURRENT',
          'TICKET_CHECK_FAILED', 'BUTTON_QUOTES_UNAVAILABLE', 'BUTTON_QUOTES_TIED'].includes(reason)) ||
        status?.reason === 'NOT_ET_WEEKEND' || !navigationTarget(status, url, now) ||
        !(entryWindow(series, start, now)?.[1] > now)) return;
    if (attempt.phase === 'FAILED') return;
    try {
      const {control, mode} = orderTypeTicket(doc, url, now, series);
      if (mode === '市价单') {
        attempt.phase = 'READY';
        attempt.reason = null;
        return;
      }
      if (attempt.phase === 'SELECTED') throw preparationError('ORDER_TYPE_READBACK_FAILED');
      if (control.tagName !== 'BUTTON' || control.type !== 'button' || !buttonIsEnabled(control)) {
        throw preparationError('ORDER_TYPE_CONTROL_UNSAFE');
      }
      if (attempt.phase !== 'OPENED') {
        attempt.phase = 'OPENED';
        control.click();
        return;
      }
      // Future's visible portal contains these five choices. Scope to the linked
      // popup when available; otherwise require that exact, unique menu container.
      const popupId = control.getAttribute?.('aria-controls');
      const menus = popupId ? [doc.getElementById?.(popupId)].filter(Boolean) :
        [...doc.querySelectorAll('div')].filter((element) => element.getClientRects().length &&
          element.textContent.replace(/\s+/g, '') === '市价单限价单Stop拆分合并');
      const scopes = menus.filter((element) => !menus.some((other) => other !== element && element.contains(other)));
      if (scopes.length !== 1 || !scopes[0].getClientRects().length) throw preparationError('ORDER_TYPE_MENU_UNAVAILABLE');
      if (scopes[0].textContent.replace(/\s+/g, '') !== '市价单限价单Stop拆分合并') {
        throw preparationError('ORDER_TYPE_MENU_UNAVAILABLE');
      }
      const candidates = [...scopes[0].querySelectorAll('button,[role="menuitem"],[role="option"],div,span')]
        .filter((element) => element.getClientRects().length && element.textContent.trim() === '市价单');
      const options = candidates.filter((element) => !candidates.some((other) => other !== element && element.contains(other)));
      if (options.length !== 1 || !buttonIsEnabled(options[0]) ||
          options[0].tagName === 'BUTTON' && options[0].type !== 'button') {
        throw preparationError('ORDER_TYPE_MENU_UNAVAILABLE');
      }
      attempt.phase = 'SELECTED';
      options[0].click();
    } catch (error) {
      attempt.reason = error.code || 'TICKET_CHECK_FAILED';
      // A late-loading or mismatched ticket may become valid; an uncertain click
      // or menu selection never repeats in this round.
      if (attempt.phase === 'OPENED' || attempt.phase === 'SELECTED') attempt.phase = 'FAILED';
    }
  }

  function ticketBlockers(doc, url, now) {
    try {
      const {controls, mode} = orderTypeTicket(doc, url, now);
      const reasons = [];
      if (mode !== '市价单') reasons.push('ORDER_TYPE_LIMIT');
      if (controls.some((button) => /^最低购买金额为\s*\$/.test(button.textContent.trim()))) {
        reasons.push('PLATFORM_MINIMUM_UNAVAILABLE');
      }
      if (reasons.length) return reasons;
      const report = readPreflight(doc, url, now);
      if (report?.navigation !== 'CURRENT' || report.ticketStatus !== 'PASS') return ['TICKET_CHECK_FAILED'];
      if (!validButtonQuote(report.upQuoteCents) || !validButtonQuote(report.downQuoteCents)) return ['BUTTON_QUOTES_UNAVAILABLE'];
      if (report.upQuoteCents === report.downQuoteCents) return ['BUTTON_QUOTES_TIED'];
      return [];
    } catch (error) {
      return [error.code || 'TICKET_CHECK_FAILED'];
    }
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
    const page = pathRound(parsed.pathname);
    const pagePeriodStart = page && page.start;
    if (parsed.origin !== 'https://future.news' || parsed.username || parsed.password || !page ||
        !Number.isFinite(now)) return null;
    // Current, ended or mismatched relative to the page's own series.
    const start = roundStart(now, page.series);
    const navigation = pagePeriodStart < start ? 'ENDED' : pagePeriodStart !== start || endedMarketButtons(doc).length ? 'MISMATCH' : 'CURRENT';
    // Only origin/path leave the tab. Query parameters, DOM text and errors do not.
    const report = {schemaVersion: 2, marketUrl: parsed.origin + parsed.pathname, pagePeriodStart,
      checkedAt: now, navigation, ticketStatus: 'FAIL', amountUsd: null, selectedSide: null, buyButtonEnabled: false,
      upQuoteCents: null, downQuoteCents: null};
    if (navigation !== 'CURRENT') return report;
    try {
      const input = findAmountInput(doc);
      const ticket = findAmountTicket(doc, input);
      if (!ticketMatchesPeriod(doc, ticket, pagePeriodStart, SERIES[page.series].period)) {
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

  // The account badge has two dollar amounts: positions, then available cash.
  // Reading the badge never opens a wallet menu or touches an order control.
  function readWalletSnapshot(doc, url) {
    const unknown = {walletAddress: null, cashUsd: null};
    try {
      const page = new URL(url);
      if (page.origin !== 'https://future.news' || page.username || page.password) return unknown;
      const badges = [...doc.querySelectorAll('a[href]')].filter((element) => {
        if (!element.getClientRects().length || typeof element.textContent !== 'string') return false;
        const address = new URL(element.getAttribute('href'), page);
        return address.origin === page.origin && !address.username && !address.password &&
          /^\/(?:zh\/)?address\/0x[0-9a-fA-F]{40}\/?$/.test(address.pathname) &&
          /^\s*\$[^$]+\$[^$]+\s*$/.test(element.textContent);
      });
      if (badges.length !== 1) return unknown;
      const address = new URL(badges[0].getAttribute('href'), page).pathname.match(/0x[0-9a-fA-F]{40}/)[0].toLowerCase();
      const cashText = badges[0].textContent.split('$')[2].trim();
      const cash = /^(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$/.test(cashText) ? Number(cashText.replaceAll(',', '')) : null;
      return {walletAddress: address, cashUsd: Number.isFinite(cash) && cash >= 0 ? cash : null};
    } catch {
      return unknown;
    }
  }

  // This is the detailed position list, never the ticket's mark-to-market summary.
  // A missing list is unknown; only a distinct visible header and its row area can
  // establish an empty baseline. Inspection cannot open tabs or submit anything.
  function readPositionSnapshot(doc, url, periodStart, side, series = '5m') {
    try {
      const page = new URL(url);
      if (!seriesOf(series)) return null;
      const slug = `${SERIES[series].slug}${periodStart}`;
      if (!Number.isSafeInteger(periodStart) || periodStart < 0 || periodStart % SERIES[series].period ||
          !['Up', 'Down'].includes(side) || page.username || page.password || !matchesMarket(url, {slug})) return null;
      const headerPattern = /^市场结果份额均价\/现价投注额(?:预期获得)?(?:金额)?手续费(?:止盈\/止损)?(?:当前盈亏)?时间操作$/;
      const normalized = (element) => typeof element.textContent === 'string' ? element.textContent.replace(/\s+/g, '') : '';
      const candidates = [...doc.querySelectorAll('div,thead,[role="row"]')]
        .filter((element) => element.getClientRects().length && headerPattern.test(normalized(element)));
      const headers = candidates.filter((element) => !candidates.some((other) => other !== element && element.contains(other)));
      if (headers.length !== 1) return null;
      let rows = null;
      for (let boundary = headers[0], depth = 0; boundary && depth < 3; boundary = boundary.parentElement, depth++) {
        const scope = boundary.parentElement;
        if (!scope || scope === doc.body || scope.tagName === 'ASIDE') break;
        const children = [...scope.children];
        const index = children.indexOf(boundary);
        if (index < 0 || index + 1 >= children.length) continue;
        const area = children[index + 1];
        if (!area.getClientRects().length || area.getAttribute?.('aria-busy') === 'true') return null;
        if (area.tagName === 'A') {
          rows = children.slice(index + 1).filter((element, offset, siblings) => element.tagName === 'A' &&
            siblings.slice(0, offset).every((previous) => previous.tagName === 'A'));
        } else {
          const links = [...area.querySelectorAll('a[href]')];
          if (links.length) rows = links;
          else if (/^(暂无仓位|暂无持仓|暂无数据)$/.test(normalized(area))) rows = [];
        }
        if (rows !== null) break;
      }
      if (rows === null) return null;
      const positions = [];
      const number = '(?:0|[1-9]\\d*)(?:\\.\\d+)?';
      const rowPattern = new RegExp(`(?:^|\\s)(Up|Down|涨|跌)\\s+(${number})\\s+(${number})\\s*¢\\s+(${number})\\s*¢` +
        `\\s+\\$\\s*(${number})\\s+\\$\\s*(${number})\\s+\\$\\s*(${number})\\s+\\$\\s*(${number})(?=\\s|$)`, 'g');
      for (const row of rows) {
        const destination = row.getAttribute('href');
        if (typeof destination !== 'string' || !destination.trim()) return null;
        const href = new URL(destination, page);
        if (href.origin !== 'https://future.news' || href.username || href.password ||
            !/^\/(?:zh\/)?event\/[a-z0-9][a-z0-9_-]*\/?$/.test(href.pathname)) return null;
        if (!matchesMarket(href.href, {slug})) continue;
        // Hidden duplicates can conceal an older or second same-market position.
        if (!row.getClientRects().length) return null;
        // React's adjacent cells concatenate textContent ("Down1.5166¢").
        // Keep actual text-node boundaries; never split an ambiguous raw number.
        const parts = [];
        const collect = (element) => {
          if (element.nodeType === 3) parts.push(element.textContent);
          else if (!element.getClientRects || element.getClientRects().length) {
            const children = [...(element.childNodes || [])];
            if (children.length) children.forEach(collect);
            else if (typeof element.textContent === 'string') parts.push(element.textContent);
          }
        };
        collect(row);
        const text = parts.join(' ').replace(/\s+/g, ' ').trim();
        if (!/^Bitcoin Up or Down\s*[-–—]/.test(text) || !/\s卖出$/.test(text)) return null;
        const values = [...text.matchAll(rowPattern)];
        if (values.length !== 1) return null;
        const [, outcome, ...raw] = values[0];
        const [shares, avgPriceCents, currentPriceCents, costUsd, payoutUsd, valueUsd, feeUsd] = raw.map(Number);
        if (![shares, avgPriceCents, currentPriceCents, costUsd, payoutUsd, valueUsd, feeUsd].every(Number.isFinite) ||
            shares <= 0 || costUsd <= 0 || avgPriceCents <= 0 || avgPriceCents > 100 || currentPriceCents > 100) return null;
        const rowSide = ['Up', '涨'].includes(outcome) ? 'Up' : 'Down';
        if (rowSide === side) positions.push({shares, avgPriceCents, costUsd});
      }
      if (positions.length > 1) return null;
      // A filtered list can hide a pre-existing position even when it says no data.
      if (!positions.length && [...doc.querySelectorAll('input[placeholder="搜索"]')]
        .some((input) => input.getClientRects().length && typeof input.value === 'string' && input.value.trim())) return null;
      return {periodStart, side, positions};
    } catch {
      return null;
    }
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
    const round = idRound(intent.id);
    if (!round) return null;
    const {series} = round;
    const start = roundStart(now, series);
    // Absolute window; a 4h window is the checkpoint window the intent was created in.
    const window = Number.isFinite(intent.createdAt) ? entryWindow(series, start, intent.createdAt) : null;
    if (!window) return null;
    const [first, last] = window;
    if (!Number.isSafeInteger(intent.periodStart) || intent.periodStart !== start || round.start !== start ||
        intent.slug !== `${SERIES[series].slug}${start}` ||
        intent.periodEnd !== start + SERIES[series].period || intent.amountUsd !== 1 || !['Up', 'Down'].includes(intent.side) ||
        intent.priceSource !== 'chainlink' ||
        intent.openPriceSource !== SERIES[series].openSource ||
        intent.twapLookbackSeconds !== 60 || !Number.isFinite(intent.openPrice) || intent.openPrice <= 0 ||
        !Number.isFinite(intent.currentPrice) || intent.currentPrice <= 0 ||
        !Number.isFinite(intent.createdAt) || intent.createdAt < first || intent.createdAt >= last ||
        intent.expiresAt !== last || now < intent.createdAt || now >= intent.expiresAt ||
        !Number.isFinite(intent.priceObservedAt) || intent.priceObservedAt > intent.createdAt ||
        now - intent.priceObservedAt > 5 || now < first ||
        !(intent.claimToken === null || typeof intent.claimToken === 'string' && /^[a-f0-9]{32}$/.test(intent.claimToken))) return null;
    return intent;
  }

  function preparationError(code) {
    const error = new Error(code);
    error.code = code;
    return error;
  }

  function readPreparationTicket(doc, url, start, series = '5m') {
    // Freshness is checked against the bridge before every stage; this read binds the
    // DOM title and URL to that already checked round of that series.
    const report = readPreflight(doc, url, start + (SERIES[series].entry?.[0] ?? 1));
    let page = null;
    try { page = pathRound(new URL(url).pathname); } catch {}
    if (report?.navigation !== 'CURRENT' || report.pagePeriodStart !== start || page?.series !== series) {
      throw preparationError('MARKET_MISMATCH');
    }
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
    const {series} = idRound(intent.id);
    // One once-per-round key per series: a 15m start is also a 5m start.
    const key = series === '5m' ? 'polyhermes.future-btc5m.preparation' : `polyhermes.future-btc5m.preparation.${series}`;
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
      const ticket = readPreparationTicket(doc, readUrl(), intent.periodStart, series);
      if (ticket.preferredSide !== intent.side) throw preparationError('HIGHER_BUTTON_SIDE_CHANGED');
      return ticket;
    };
    try {
      const initial = readPreparationTicket(doc, readUrl(), intent.periodStart, series);
      if (initial.preferredSide !== intent.side) throw preparationError('HIGHER_BUTTON_SIDE_CHANGED');
      const previous = JSON.parse(storage.getItem(key) || 'null');
      if (previous !== null && (!Number.isSafeInteger(previous.periodStart) ||
          previous.id !== `${SERIES[series].id}${previous.periodStart}`)) throw preparationError('PREPARATION_FAILED');
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
      // The validated ticket is used immediately: no await between the guard and write.
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
  globalThis.FutureBtc5m = {SERIES, seriesOf, roundStart, pathRound, idRound, entryWindow, usableDraft, matchesMarket, observationView, findAmountInput, findAmountTicket, buttonIsEnabled, prepareAmount,
    navigationTarget, followCurrentMarket, readPreflight, usablePreparation, readPreparationTicket, prepareOnlyOnce, parseButtonQuote, readPositionSnapshot, readWalletSnapshot};
  if (typeof document === 'undefined') return;

  const panel = document.createElement('aside');
  panel.style.cssText = 'position:fixed;left:50%;top:16px;transform:translateX(-50%);z-index:2147483647;width:300px;max-width:calc(100vw - 32px);max-height:max(64px,calc(100dvh - 280px));overflow-y:auto;box-sizing:border-box;padding:14px;background:#171b22;color:#f4f4f4;border:1px solid #616976;border-radius:10px;font:13px/1.6 system-ui;box-shadow:0 4px 20px #0008';
  const header = document.createElement('div');
  header.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:8px;position:sticky;top:0;background:#171b22;z-index:1';
  const title = document.createElement('strong');
  title.textContent = 'PolyHermes · 策略未核实 · $1';
  const panelBody = document.createElement('div');
  panelBody.id = 'polyhermes-btc5m-body';
  panelBody.hidden = false;
  const collapse = document.createElement('button');
  collapse.type = 'button';
  collapse.textContent = '收起';
  collapse.ariaExpanded = 'true';
  collapse.setAttribute('aria-controls', panelBody.id);
  collapse.style.cssText = 'flex-shrink:0;padding:2px 6px;border:1px solid #616976;border-radius:4px;background:#232a35;color:#f4f4f4;cursor:pointer;font:12px/1.6 system-ui';
  collapse.addEventListener('click', () => {
    panelBody.hidden = !panelBody.hidden;
    collapse.textContent = panelBody.hidden ? '展开' : '收起';
    collapse.ariaExpanded = String(!panelBody.hidden);
  });
  header.append(title, collapse);
  const currentSummary = document.createElement('p');
  currentSummary.id = 'polyhermes-btc5m-current';
  currentSummary.style.cssText = 'white-space:pre-line;margin:10px 0;padding:10px;background:#232a35;border-left:3px solid #8ac5ff;border-radius:6px;font-size:14px';
  const recentSummary = document.createElement('p');
  recentSummary.id = 'polyhermes-btc5m-recent';
  recentSummary.style.cssText = 'white-space:pre-line;margin:10px 0;padding:10px;background:#20242c;border-radius:6px';
  const details = document.createElement('details');
  details.id = 'polyhermes-btc5m-details';
  details.open = false;
  const detailsTitle = document.createElement('summary');
  detailsTitle.textContent = '展开报价、检查记录与规则';
  detailsTitle.style.cssText = 'cursor:pointer;color:#8ac5ff';
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
  const preparationNoteFor = (series, heading = `当前策略：${SERIES[series].label}`) => {
    const [first, last] = SERIES[series].entry ?? [null, null];
    const rule = series === '4h' ?
      `${heading}。与 15 分钟策略同时运行：周末 4 小时盘在每刻钟第 5、10 分钟按 Binance 价格模型判断，模型把握 ≥95% 且比 Polymarket 卖价高 ≥3¢ 时，接下来 2 分钟切到 4 小时盘填入 $1，准备好后自动点击一次 Future 买入；每轮最多一次，其余时间回到 15 分钟盘。` :
      series === '15m' ?
      `${heading}。开启自动票据后，每轮第 ${first}–${last} 秒读取 15 分钟盘按钮数字较大的一方；只有它与同一时刻 1 小时盘的热门方向相反时才填入 $1，准备好后自动点击一次 Future 买入，方向相同则本轮跳过。` :
      `${heading}。开启自动票据后，仅在每轮第 ${first}–${last} 秒、行情有效时选择按钮数字较大的一方并填入 $1，准备好后自动点击一次 Future 买入。`;
    return rule + '每轮准备前自动切回市价单并核对。自动买入仅在热门方向 ≥60¢、页面与 Polymarket 盘口价差不超过 3¢，且两者均在准备价 ±5¢ 内、最高不超过 97¢ 时进行，否则本轮不点击。$1 为订单本金，费用以平台为准。';
  };
  note.style.whiteSpace = 'pre-line';
  note.textContent = '当前策略：未核实，等待本地助手报告。';
  const autoBuyReport = document.createElement('p');
  autoBuyReport.style.whiteSpace = 'pre-line';
  // Weekend-only is held by the local assistant and resets to on whenever it restarts.
  const scheduleRow = document.createElement('p');
  const weekendOnly = document.createElement('input');
  weekendOnly.type = 'checkbox';
  weekendOnly.disabled = true;
  const scheduleText = document.createElement('span');
  scheduleText.textContent = ' 仅周末运行：读取中';
  scheduleRow.append(weekendOnly, scheduleText);
  details.append(detailsTitle, text, link, prepare, inspect, inspection, navigation, note, preflightReport,
    preparationReport, autoBuyReport);
  panelBody.append(currentSummary, recentSummary, scheduleRow, details);
  panel.append(header, panelBody);
  document.body.append(panel);
  let latest = null;
  let polling = false;
  let inspectedUrl = null;
  let autoCheckedUrl = null;
  let reporting = false;
  let reportPromise = null;
  let autoBuyer = null;
  let runtimePort = null, lastRuntimeTick = null;
  let runtimeReconnectAllowed = true;
  let rendererState = 'UNAVAILABLE';
  let scheduleVersion = 0;
  let scheduleBusy = false;
  let orderTypeAttempt = {periodStart: null, phase: null, reason: null};
  let lastBlockers = [];
  let windowBlockerOutcomes = [];
  let preparationView = null;
  let lastConfirmedSeries = null;
  let extensionContextInvalidated = false;
  preparationReport.style.whiteSpace = 'pre-line';
  // The strategy series the bridge reports (preparation first, then the assistant status).
  const activeSeries = () => seriesOf(preparationView?.preparation?.series) ?? seriesOf(latest?.series) ?? '5m';
  const recordSeries = (last) => seriesOf(last?.series) ?? '5m';

  const displayStrategy = (now = Date.now() / 1000) => {
    const value = strategyPresentation(preparationView, latest, lastConfirmedSeries, location.href, now);
    if (value.source === 'confirmed') lastConfirmedSeries = value.series;
    return value;
  };

  async function reportPage() {
    if (reporting) return;
    const report = readPreflight(document, location.href);
    const payload = report && {...report, schemaVersion: 3, ...readWalletSnapshot(document, location.href)};
    if (!payload) {
      preflightReport.textContent = '只读预检：等待 BTC 5/15 分钟市场页面';
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

  const marketQuoteDetails = {HTTP_SOURCE_TIMEOUT: 'Polymarket 行情请求超时', HTTP_SOURCE_UNAVAILABLE: 'Polymarket 行情源不可用',
    HTTP_SOURCE_CONNECTION_RESET: 'Polymarket 行情连接被重置', HTTP_SOURCE_TLS_ERROR: 'Polymarket 行情证书验证失败',
    INVALID_MARKET_QUOTE: '盘口响应格式或时间无效', CLOB_BOOKS_MISMATCH: '盘口代币与本轮不一致',
    CLOB_BOOK_TIME_INVALID: '盘口源时间无效', ROUND_CHANGED_DURING_READ: '读取时已切换到下一轮',
    INVALID_BOOK: '盘口结构无效', INVALID_BOOK_LEVEL: '盘口价量无效',
    WRONG_MARKET_PRICE_CONFIG: '市场价格源或 TWAP 配置不一致', MARKET_NOT_UNIQUE: '本轮市场不唯一',
    WRONG_OR_INACTIVE_EVENT: '本轮事件无效或已停用', WRONG_OR_INACTIVE_MARKET: '本轮市场无效或已停用',
    WRONG_MARKET_PERIOD: '本轮市场时间不一致', INVALID_OUTCOME_TOKENS: '方向代币映射无效',
    LOCAL_QUOTE_TIMEOUT: '本地盘口请求超时', LOCAL_QUOTE_NOT_FOUND: '本地盘口接口不存在，请更新助手',
    MARKET_QUOTE_STALE: '盘口源采样超过 2 秒', MARKET_QUOTE_EMPTY: '盘口缺少可成交 $1 的报价'};

  const outcomeReasons = {
    PRICE_BELOW_MIN: ['价格风控', '价格低于 60¢ 或准备价 −5¢'],
    PRICE_ABOVE_MAX: ['价格风控', '价格高于 97¢ 或准备价 +5¢'],
    MARKET_QUOTE_MISMATCH: ['价格风控', '页面与盘口价差超过 3¢，或热门方向不一致'],
    MARKET_QUOTE_UNAVAILABLE: ['行情异常', '无法取得有效的 Polymarket 盘口'],
    WAITING_CURRENT_SIGNAL: ['行情异常', '本轮有效行情尚未就绪'],
    SOURCE_STATE_UNAVAILABLE: ['服务异常', '行情服务状态不可用'],
    SIGNAL_SOURCE_UNAVAILABLE: ['服务异常', '行情服务未连接'],
    SIGNAL_SOURCE_INVALID: ['服务异常', '行情服务响应无效'],
    BROWSER_NOT_CONNECTED: ['页面核对失败', '浏览器报告缺失或过期'],
    MARKET_NOT_CURRENT: ['页面核对失败', '页面或票据不是本轮市场'],
    MARKET_MISMATCH: ['页面核对失败', '页面轮次不匹配'],
    TICKET_CHECK_FAILED: ['页面核对失败', '美元市价买入栏未通过核对'],
    TICKET_CHANGED: ['页面核对失败', '金额、方向或票据已改变'],
    PREPARED_TICKET_CHANGED: ['页面核对失败', '准备后的票据已改变'],
    BUY_BUTTON_UNSAFE: ['页面核对失败', '买入按钮不唯一或不可用'],
    UNSAFE_DIRECTION_CONTROL: ['页面核对失败', '方向按钮无法安全核对'],
    BUTTON_QUOTES_UNAVAILABLE: ['行情异常', '涨跌按钮报价读取失败'],
    BUTTON_QUOTES_TIED: ['入场条件', '涨跌按钮同价，没有热门方向'],
    BUTTON_QUOTES_NOT_FRESH: ['行情异常', '按钮报价已过期'],
    HIGHER_BUTTON_SIDE_CHANGED: ['入场条件', '热门方向在准备期间改变'],
    ORDER_TYPE_LIMIT: ['页面核对失败', '当前为限价单，市价单尚未核对'],
    ORDER_TYPE_CONTROL_UNSAFE: ['页面核对失败', '市价单切换按钮不唯一或不可用'],
    ORDER_TYPE_MENU_UNAVAILABLE: ['页面核对失败', '市价单菜单缺失或无法安全选择'],
    ORDER_TYPE_READBACK_FAILED: ['页面核对失败', '切回市价单后回读失败'],
    PLATFORM_MINIMUM_UNAVAILABLE: ['平台金额限制', '平台提示最低购买金额，买入栏不可用'],
    DIRECTION_WRITE_FAILED: ['页面核对失败', '方向切换后回读失败'],
    AMOUNT_WRITE_FAILED: ['页面核对失败', '$1 金额回读失败'],
    POSTCHECK_FAILED: ['页面核对失败', '准备后的最终核对失败'],
    FINAL_CHECK_FAILED: ['最终保护', '点击前最后核对失败；本轮不再重试'],
    READY_CHANGED: ['准备失效', '准备许可已改变或过期'],
    PREPARATION_REVOKED: ['准备失效', '行情过期或准备许可已失效'],
    PREPARATION_REVOKED_BY_USER: ['已停止', '自动准备已被关闭'],
    PREPARATION_RECEIPT_UNKNOWN: ['回执未知', '票据准备回执未确认'],
    INTENT_EXPIRED: ['时间安排', '已过本轮入场截止时间'],
    SAME_AS_1H_FAVORITE: ['策略过滤', '15 分钟热门方向与 1 小时热门方向相同，本轮跳过'],
    HOUR_QUOTE_UNAVAILABLE: ['行情异常', '1 小时盘口不可用，无法判断方向'],
    HIGH_VOLATILITY: ['策略过滤', 'BTC 过去 60 分钟波动过大（高于 4.16 基点/分钟），本轮跳过'],
    BTC_VOLATILITY_UNAVAILABLE: ['行情异常', 'BTC 波动数据不可用，无法判断是否跳过'],
    FOUR_HOUR_SIDE_MISMATCH: ['策略过滤', '4 小时页面热门方向与模型方向不一致，本轮不买'],
    DECISION_LEDGER_INVALID: ['本地异常', '策略决策账本无法读取'],
    DECISION_LEDGER_WRITE_FAILED: ['本地异常', '策略决策账本写入失败'],
    ALREADY_CONSUMED: ['防重复保护', '本轮已记录买入尝试，不再点击'],
    STOP_FILE_PRESENT: ['已停止', '助手已停止'],
    AUTO_PREPARATION_DISABLED: ['自动功能关闭', '自动准备票据已关闭'],
    STORAGE_FAILED: ['本地异常', '本地买入尝试记录不可用'],
    WEB_LOCKS_REQUIRED: ['扩展异常', '浏览器缺少防重复所需的 Web Locks'],
    UPDATED_EXTENSION_CONTEXT_REQUIRED: ['扩展异常', '需要重新加载扩展并刷新页面'],
    PREPARATION_LEDGER_WRITE_FAILED: ['本地异常', '准备账本写入失败'],
    PREFLIGHT_LEDGER_WRITE_FAILED: ['本地异常', '预检账本写入失败'],
    ORDER_LEDGER_INVALID: ['本地异常', '订单账本无法读取'],
    PREFLIGHT_LEDGER_INVALID: ['本地异常', '预检账本无法读取'],
    PREPARATION_LEDGER_INVALID: ['本地异常', '准备账本无法读取'],
    CONTROL_STATE_WRITE_FAILED: ['本地异常', '自动开关状态保存失败'],
    PREPARATION_FAILED: ['准备异常', '票据准备未完成'],
  };

  function outcomeReason(code) {
    if (code === 'WAITING_CURRENT_SIGNAL' && latest?.reason === 'SOURCE_REQUEST_FAILED') {
      const sources = {GAMMA: 'Gamma 市场信息', OPENING_PRICE: 'TWAP 开盘价', GEOBLOCK: '地域检查'};
      const errors = {HTTP_SOURCE_CONNECTION_RESET: '连接被重置', HTTP_SOURCE_TIMEOUT: '请求超时',
        HTTP_SOURCE_TLS_ERROR: '证书验证失败', HTTP_SOURCE_UNAVAILABLE: '接口不可用'};
      const details = Object.entries(latest.source_errors ?? {}).filter(([name]) => Object.hasOwn(sources, name))
        .map(([name, error]) => `${sources[name]}：${errors[error] || '响应无效'}`);
      return ['行情异常', details.join('；') || '本轮行情请求失败'];
    }
    if (code === 'WAITING_CURRENT_SIGNAL' && latest?.reason === 'NOT_ET_WEEKEND') {
      return ['运行安排', '当前不是美东周末'];
    }
    if (code === 'WAITING_CURRENT_SIGNAL' && (latest?.reason === 'CHAINLINK_PRICE_STALE_OR_FUTURE' ||
        latest?.signal?.period_start === roundStart(Date.now() / 1000, activeSeries()) &&
        Number.isFinite(latest.signal.price_observed_at) && (latest.signal.price_observed_at > Date.now() / 1000 ||
          Date.now() / 1000 - latest.signal.price_observed_at > 5))) {
      return ['行情异常', '行情采样已过期或时间无效'];
    }
    return Object.hasOwn(outcomeReasons, code) ? outcomeReasons[code] : ['原因待核实', `未识别的状态代码：${code || '未提供'}`];
  }

  function roundLabel(start, series = activeSeries()) {
    const period = SERIES[series].period;
    if (!Number.isSafeInteger(start) || start < 0 || start % period !== 0) return '轮次未记录';
    const date = new Intl.DateTimeFormat('zh-CN', {timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit'});
    const time = new Intl.DateTimeFormat('zh-CN', {timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit', hourCycle: 'h23'});
    return `${date.format(start * 1000)} ${time.format(start * 1000)}–${time.format((start + period) * 1000)}（北京时间）`;
  }

  function confirmedPositionFill(last) {
    const fill = last.fill;
    return last.state === 'CLICK_ATTEMPTED' && last.reason === 'PLATFORM_RESULT_UNKNOWN' && last.amountUsd === 1 &&
      ['Up', 'Down'].includes(last.side) && Number.isSafeInteger(last.periodStart) && last.periodStart >= 0 &&
      last.periodStart % SERIES[recordSeries(last)].period === 0 &&
      fill?.source === 'FUTURE_POSITION_PAGE' && Number.isFinite(fill.shares) && fill.shares > 0 &&
      validButtonQuote(fill.avgPriceCents) && fill.avgPriceCents > 0 && Number.isFinite(fill.confirmedAt) &&
      fill.confirmedAt >= last.periodStart && fill.confirmedAt <= Date.now() / 1000 ? fill : null;
  }

  function buyOutcome(last) {
    const fill = confirmedPositionFill(last);
    if (fill) return ['已成交 · 页面持仓核实', `${last.side === 'Up' ? '涨' : '跌'} ${fill.shares} 份 · 均价 ${fill.avgPriceCents}¢`];
    if (last.state === 'CLICK_ATTEMPTED') return last.reason === 'CLICK_THROWN_RESULT_UNKNOWN' ?
      ['点击异常 · 结果未知', '买入点击发生异常；平台结果未知，本轮不重试'] :
      ['已点击 · 成交未确认', `已点击“买入${last.side === 'Up' ? '涨' : '跌'}” $1；下单及成交需以 Future 订单核实`];
    const [category, message] = outcomeReason(last.reason);
    let detail = message;
    if (last.reason === 'MARKET_QUOTE_UNAVAILABLE' && Object.hasOwn(marketQuoteDetails, last.detail)) {
      detail = marketQuoteDetails[last.detail];
    }
    const prices = last.priceCheck;
    const page = last.side === 'Up' ? prices?.upQuoteCents : prices?.downQuoteCents;
    const book = last.side === 'Up' ? prices?.marketUpAskCents : prices?.marketDownAskCents;
    if (last.reason === 'MARKET_QUOTE_MISMATCH' && ['Up', 'Down'].includes(last.side) &&
        validButtonQuote(page) && validButtonQuote(book)) {
      const gap = Math.abs(Math.round(page * 100) - Math.round(book * 100)) / 100;
      detail += `；${last.side === 'Up' ? '涨' : '跌'}页面 ${page}¢ / 盘口 ${book}¢，价差 ${gap}¢（上限 3¢）`;
    }
    return [`未点击 · ${category}`, detail];
  }

  function showOutcomeSummary(view) {
    const now = Date.now() / 1000;
    const strategy = displayStrategy(now);
    const series = strategy.series;
    const start = series ? roundStart(now, series) : null;
    const [first, last80] = series ? relativeWindow(series, start, now) : [null, null];
    const elapsed = now - start;
    const last = view?.last;
    const lastIsCurrent = last && last.periodStart === start && recordSeries(last) === series;
    recentSummary.textContent = last ? `最近买入检查\n${buyOutcome(last).join('\n')}\n${lastIsCurrent ? '本轮' : '历史轮次'} · ${roundLabel(last.periodStart, recordSeries(last))}` :
      '最近买入检查\n本页尚无买入检查记录\n刷新前的操作请查看本机账本或 Future 订单';
    if (!series) {
      currentSummary.textContent = `本轮状态 · 开关未核实 · ${strategy.label}\n状态未知 · 无法确认本轮操作\n轮次未核实`;
      return;
    }
    const value = preparationView?.preparation;
    const freshPreparation = value && Number.isFinite(preparationView.serverTime) && Math.abs(now - preparationView.serverTime) <= 3;
    let outcome;
    if (lastIsCurrent) outcome = buyOutcome(last);
    else if (view?.state === 'BLOCKED' && view.reason) {
      const [category, message] = outcomeReason(view.reason);
      outcome = [`未点击 · ${category}`, message];
    } else if (!freshPreparation) {
      outcome = ['状态未知 · 服务异常', extensionContextInvalidated ?
        '扩展上下文已失效，请刷新此页面恢复连接；无法确认本轮操作' :
        '本地准备服务未连接或状态已过期；无法确认本轮操作'];
    } else if (value.reasons?.includes('STOP_FILE_PRESENT')) outcome = ['未点击 · 已停止', '助手已停止'];
    else if (!value.enabled) outcome = ['未点击 · 自动功能关闭', '在 PolyHermes 开启“自动准备票据”后才会自动买入'];
    else if (value.reasons?.includes('SAME_AS_1H_FAVORITE') || value.reasons?.includes('HIGH_VOLATILITY')) {
      const reason = value.reasons.includes('SAME_AS_1H_FAVORITE') ? 'SAME_AS_1H_FAVORITE' : 'HIGH_VOLATILITY';
      outcome = ['未点击 · 策略过滤', outcomeReason(reason)[1]];
    } else if (elapsed >= last80) {
      // Only observations made inside this round's entry window can explain a missed entry.
      const observed = orderTypeAttempt.periodStart === start ? [...windowBlockerOutcomes] : [];
      const record = value.lastAttempt;
      if (!observed.length && idRound(record?.id)?.series === series && record.periodStart === start &&
          ['FAILED', 'REVOKED', 'EXPIRED'].includes(record.state) &&
          record.reason && record.reason !== 'INTENT_EXPIRED') observed.push(outcomeReason(record.reason));
      outcome = observed.length ? [`未点击 · ${observed[0][0]}`,
        `窗口内记录：${observed.map((item) => item[1]).join('；')}\n已过第 ${last80} 秒，等待下一轮`] :
        ['已过入场窗口 · 本轮无点击记录', '窗口内原因未记录，无法判断是否触发风控\n等待下一轮，不补买'];
    } else if (elapsed < first && !['BLOCKED', 'FAILED', 'REVOKED', 'RECEIPT_UNKNOWN'].includes(value.state)) {
      outcome = ['等待入场 · 时间安排', `距第 ${first} 秒还有 ${Math.ceil(first - elapsed)} 秒；入场窗口为第 ${first}–${last80} 秒`];
    } else if (value.state === 'READY') outcome = ['已准备 · 等待买入检查', '已准备 $1 票据；通过价格与页面检查后才会点击'];
    else if (['PENDING', 'CLAIMED'].includes(value.state)) outcome = ['准备中 · 尚未点击', '正在核对方向与 $1 金额'];
    else {
      const codes = [...new Set([...(value.reasons || []), ...ticketBlockers(document, location.href, now),
        ...(orderTypeAttempt.periodStart === start && orderTypeAttempt.reason ? [orderTypeAttempt.reason] : [])])];
      const [category] = outcomeReason(codes[0]);
      outcome = [`未点击 · ${category}`, codes.map((code) => outcomeReason(code)[1]).join('；') || '尚未取得有效准备许可'];
    }
    const enabled = freshPreparation ? value.enabled ? '自动买入已开启' : '自动买入已关闭' : '开关未核实';
    currentSummary.textContent = `本轮状态 · ${enabled} · ${strategy.label}\n${outcome.join('\n')}\n${roundLabel(start, series)}`;
  }

  async function preparationRequest(type, payload) {
    const reply = await chrome.runtime.sendMessage(payload ? {type, payload} : {type});
    if (!reply?.ok) {
      if (type === 'FUTURE_BTC5M_MARKET_QUOTE') throw Object.assign(preparationError('MARKET_QUOTE_UNAVAILABLE'), {
        detail: Object.hasOwn(marketQuoteDetails, reply?.errorCode) ? reply.errorCode : 'MARKET_QUOTE_UNAVAILABLE'});
      throw preparationError('PREPARATION_FAILED');
    }
    return reply.status;
  }

  // buy_once.js follows the same switch and re-reads READY itself; an omitted value only
  // redraws the current watcher state without arming or stopping it.
  function showAutoBuy(enabled) {
    let view;
    try {
      autoBuyer ??= globalThis.FutureBtc5mBuyOnce.createAutoBuyer({
        readPreparation: () => preparationRequest('FUTURE_BTC5M_PREPARATION'),
        // Independent Polymarket CLOB snapshot for the pre-click price gates.
        readMarketQuote: () => preparationRequest('FUTURE_BTC5M_MARKET_QUOTE'),
        reportAudit: (payload) => preparationRequest('FUTURE_BTC5M_BUY_AUDIT', payload)});
      view = enabled === undefined ? autoBuyer.status() : autoBuyer.sync(enabled);
    } catch {
      autoBuyReport.textContent = '自动买入：脚本未加载，不会点击';
      showOutcomeSummary({state: 'BLOCKED', reason: 'UPDATED_EXTENSION_CONTEXT_REQUIRED'});
      return;
    }
    const reasons = {TICKET_CHANGED: '票据已改变', BUY_BUTTON_UNSAFE: '买入按钮不唯一或不可用',
      READY_CHANGED: '准备记录已改变', STORAGE_FAILED: '本地点击记录不可用', FINAL_CHECK_FAILED: '最终核对失败',
      ALREADY_CONSUMED: '本轮已记录买入尝试，不再点击', WEB_LOCKS_REQUIRED: '浏览器缺少 Web Locks',
      UPDATED_EXTENSION_CONTEXT_REQUIRED: '请重新加载扩展',
      PRICE_BELOW_MIN: '价格低于 60¢ 或准备价 −5¢，本轮跳过', MARKET_QUOTE_UNAVAILABLE: '读不到 Polymarket 盘口，未点击',
      MARKET_QUOTE_MISMATCH: '页面按钮与 Polymarket 盘口不一致，未点击', PRICE_ABOVE_MAX: '价格高于准备价 +5¢ 或 97¢，未点击'};
    const states = {OFF: '跟随“自动准备票据”开关，当前关闭，不会点击',
      WATCHING: '已开启，新票据准备好后点击一次买入（每轮最多一次；热门价 ≥60¢ 且与 Polymarket 盘口一致才买）',
      PAUSED: '等待有效准备状态后重新监控，暂不点击',
      BLOCKED: `无法启动（${reasons[view.reason] || view.reason}），不会点击`};
    let report = `自动买入：${states[view.state]}`;
    if (view.last?.state === 'CLICK_ATTEMPTED') {
      const slug = `${SERIES[recordSeries(view.last)].slug}${view.last.periodStart}`;
      report += confirmedPositionFill(view.last) ? `\n最近：${buyOutcome(view.last).join('；')}（${slug}）` :
        view.last.reason === 'CLICK_THROWN_RESULT_UNKNOWN' ?
        `\n最近：点击异常，平台结果未知（${slug}），本轮不重试` :
        `\n最近：已点击“买入 ${view.last.side === 'Up' ? '涨' : '跌'}” $1（${slug}），成交以 Future 订单为准`;
    } else if (view.last) {
      report += `\n最近：未点击（${reasons[view.last.reason] || view.last.reason}）`;
      const lastSeries = recordSeries(view.last);
      if (Number.isSafeInteger(view.last.periodStart) && view.last.periodStart >= 0 &&
          view.last.periodStart % SERIES[lastSeries].period === 0) {
        report += `\n拒绝轮次：${SERIES[lastSeries].slug}${view.last.periodStart}（${view.last.periodStart ===
          roundStart(Date.now() / 1000, lastSeries) && lastSeries === activeSeries() ? '本轮' : '历史轮次'}）`;
      }
      const prices = view.last.priceCheck;
      if (validButtonQuote(prices?.upQuoteCents) && validButtonQuote(prices?.downQuoteCents)) {
        report += `\n拒绝时页面：涨 ${prices.upQuoteCents}¢ / 跌 ${prices.downQuoteCents}¢`;
      }
      if (validButtonQuote(prices?.marketUpAskCents) && validButtonQuote(prices?.marketDownAskCents)) {
        report += `\n拒绝时盘口：涨 ${prices.marketUpAskCents}¢ / 跌 ${prices.marketDownAskCents}¢`;
        if (view.last.reason === 'MARKET_QUOTE_MISMATCH') {
          const favorite = prices.marketUpAskCents === prices.marketDownAskCents ? null :
            prices.marketUpAskCents > prices.marketDownAskCents ? 'Up' : 'Down';
          if (!favorite) report += '\n盘口两边同价，无法核对较大方向。';
          else if (favorite !== view.last.side) report += '\n盘口较大方向与准备方向不一致。';
        }
        const up = view.last.side === 'Up';
        const pagePrice = up ? prices.upQuoteCents : prices.downQuoteCents;
        const marketPrice = up ? prices.marketUpAskCents : prices.marketDownAskCents;
        if (['Up', 'Down'].includes(view.last.side) && validButtonQuote(pagePrice)) {
          const gap = Math.abs(Math.round(marketPrice * 100) - Math.round(pagePrice * 100)) / 100;
          report += `\n${up ? '涨' : '跌'}价差：${gap}¢（上限 3¢）`;
        }
      }
      if (view.last.reason === 'MARKET_QUOTE_UNAVAILABLE' && Object.hasOwn(marketQuoteDetails, view.last.detail)) {
        report += `\n盘口原因：${marketQuoteDetails[view.last.detail]}`;
      }
    }
    report += view.auditError === 'AUDIT_STORAGE_FAILED' || view.last?.audit === 'FAILED' ? '\n审计：本地记录写入失败，请检查' :
      view.pendingAudits ? `\n审计：${view.pendingAudits} 条已保存在本页，等待写入本机账本` : '\n审计：全部已写入本机账本';
    autoBuyReport.textContent = report;
    showOutcomeSummary(view);
  }

  // Local observation must keep updating while any bridge request is pending.
  // It reads the current ticket only; it cannot change selection, amount or Buy state.
  function refreshTicketView() {
    const now = Date.now() / 1000;
    const strategy = displayStrategy(now);
    const report = readPreflight(document, location.href, now);
    const sideText = (side) => side === 'Up' ? '涨 Up' : side === 'Down' ? '跌 Down' : '未核对';
    title.textContent = `PolyHermes · ${strategy.label} · $1`;
    note.textContent = strategy.source === 'confirmed' ? (strategy.combined ?
      `${preparationNoteFor('15m', '当前策略：15 分钟 + 4 小时周末（15 分钟部分）')}\n${preparationNoteFor('4h', '4 小时部分')}` :
      preparationNoteFor(strategy.series)) :
      strategy.source === 'remembered' ? preparationNoteFor(strategy.series,
        `上次确认策略：${SERIES[strategy.series].label}（当前连接未核实，以下仅为规则说明）`) :
      `当前策略：未核实。${strategy.series ? `页面市场为${SERIES[strategy.series].label}，但页面周期不代表已选择或正在运行的策略。` :
        '等待本地助手返回一致的策略状态后再展示规则。'}`;
    if (strategy.source === 'page') note.textContent += '\n' + preparationNoteFor(strategy.series,
      '仅供对照的页面周期规则（不是运行确认）');
    if (report?.navigation === 'CURRENT' && report.ticketStatus === 'PASS' &&
        validButtonQuote(report.upQuoteCents) && validButtonQuote(report.downQuoteCents)) {
      const higherSide = report.upQuoteCents === report.downQuoteCents ? null :
        report.upQuoteCents > report.downQuoteCents ? 'Up' : 'Down';
      note.textContent += `\n报价观察：涨 ${report.upQuoteCents}¢ / 跌 ${report.downQuoteCents}¢；数字较大：${higherSide ? sideText(higherSide) : '同价，暂停准备'}；当前选中：${sideText(report.selectedSide)}。`;
      const pageSeries = pathRound(new URL(location.href).pathname)?.series ?? '5m';
      const pageWindow = entryWindow(pageSeries, report.pagePeriodStart, now);
      if (!pageWindow || now >= pageWindow[1]) {
        note.textContent += '\n入场窗口已过期，保留先前选边，本轮不再切换或买入。';
      }
    } else note.textContent += '\n报价观察不可用：当前票据未核对或报价缺失。';
    note.textContent += lastRuntimeTick !== null && now >= lastRuntimeTick && now - lastRuntimeTick <= 3 ?
      '\n锁屏心跳：已连接（不代表票据完成渲染）。' : '\n锁屏心跳：未连接，后台运行可能错过窗口。';
    const rendererText = {UNAVAILABLE: '未启用，锁屏仍可能漏单', ACTIVE: '浏览器渲染保持已开启，真实锁屏验收仍需核实',
      ERROR: '开启失败，锁屏仍可能漏单', STOPPED: '已停止，锁屏仍可能漏单'};
    note.textContent += `\n锁屏渲染：${rendererText[rendererState]}`;
  }

  function showSchedule(value) {
    if (typeof value !== 'boolean') {
      weekendOnly.disabled = true;
      scheduleText.textContent = ' 仅周末运行：本机助手未连接';
      return;
    }
    weekendOnly.checked = value;
    weekendOnly.disabled = false;
    scheduleText.textContent = value ? ' 仅周末运行（美东周六、周日）' : ' 仅周末运行：已关闭，工作日也会准备并自动买入';
  }

  async function scheduleRequest(payload) {
    const status = await preparationRequest(payload ? 'FUTURE_BTC5M_SCHEDULE_SET' : 'FUTURE_BTC5M_SCHEDULE', payload);
    if (!status || typeof status !== 'object' || Array.isArray(status) || Object.keys(status).length !== 1 ||
        typeof status.weekendOnly !== 'boolean') throw preparationError('PREPARATION_FAILED');
    return status.weekendOnly;
  }

  async function refreshSchedule() {
    if (scheduleBusy) return;
    const version = scheduleVersion;
    let value = null;
    try {
      value = await scheduleRequest();
    } catch {}
    // A read that started before a change must not overwrite the confirmed new value.
    if (!scheduleBusy && version === scheduleVersion) showSchedule(value);
  }

  weekendOnly.addEventListener('change', async () => {
    const wanted = weekendOnly.checked;
    if (!wanted && globalThis.confirm?.('关闭“仅周末运行”后，工作日也会自动准备票据并买入。回测里工作日比周末亏得更多。确定关闭吗？') !== true) {
      weekendOnly.checked = true;
      return;
    }
    scheduleVersion++;
    scheduleBusy = true;
    weekendOnly.disabled = true;
    try {
      showSchedule(await scheduleRequest({weekendOnly: wanted}));
    } catch {
      weekendOnly.checked = !wanted;
      weekendOnly.disabled = false;
      scheduleText.textContent = ' 仅周末运行：修改未被本机助手确认，请重试';
    } finally {
      scheduleBusy = false;
    }
  });

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
      preparationView = wrapper;
      // Arm before this poll can prepare a ticket, so the new READY is created after arming.
      showAutoBuy(value.enabled);
      text.textContent = text.textContent.replace('本轮采样方向：', 'BTC参考价差（不决定票据方向）：');
      const state = value.state;
      const now = Date.now() / 1000;
      const series = activeSeries();
      const start = roundStart(now, series);
      const [first, last] = relativeWindow(series, start, now);
      const elapsed = now - start;
      if (orderTypeAttempt.periodStart !== start || orderTypeAttempt.series !== series) {
        orderTypeAttempt = {periodStart: start, series, phase: null, reason: null};
        lastBlockers = [];
        windowBlockerOutcomes = [];
      }
      restoreMarketOrder(wrapper, latest, document, location.href, orderTypeAttempt, now);
      // Inspection describes the present DOM, not a passed check left over from
      // before an order-type change or a fill cleared the amount.
      const pagePassed = inspectPage();
      if (state === 'WAITING_SIGNAL') labels.WAITING_SIGNAL = elapsed < first ? `等待本轮第 ${first} 秒；本次检查未切换方向或填写金额` :
        elapsed >= last ? `本轮已超过第 ${last} 秒，等待下一轮；本次检查未切换方向或填写金额` :
        latest?.reason === 'CHAINLINK_PRICE_STALE_OR_FUTURE' ? '行情过期或采样时间无效，等待有效行情；本次检查未切换方向或填写金额' :
        labels.WAITING_SIGNAL;
      const reasons = {BROWSER_NOT_CONNECTED: '浏览器报告过期', MARKET_NOT_CURRENT: '页面不是本轮市场',
        TICKET_CHECK_FAILED: '买入栏未核对', BUTTON_QUOTES_UNAVAILABLE: '按钮数字读取失败',
        BUTTON_QUOTES_TIED: '两边按钮数字相同', BUTTON_QUOTES_NOT_FRESH: '按钮报价已过期',
        HIGHER_BUTTON_SIDE_CHANGED: '较大方向已改变', PREPARED_TICKET_CHANGED: '准备后的票据已改变',
        STOP_FILE_PRESENT: '助手已停止', PREPARATION_RECEIPT_UNKNOWN: '票据回执未知',
        PREPARATION_REVOKED: '行情过期或准备许可已失效', DIRECTION_WRITE_FAILED: '方向切换回读失败',
        AMOUNT_WRITE_FAILED: '$1 金额回读失败', POSTCHECK_FAILED: '准备后核对失败',
        ORDER_TYPE_LIMIT: '当前是限价单，市价单尚未核对',
        ORDER_TYPE_CONTROL_UNSAFE: '市价单切换按钮不唯一或不可用',
        ORDER_TYPE_MENU_UNAVAILABLE: '市价单菜单选项缺失、不唯一或不可用',
        ORDER_TYPE_READBACK_FAILED: '市价单切换回读失败，本轮不重复切换',
        PLATFORM_MINIMUM_UNAVAILABLE: '平台显示最低购买金额提示，买入栏不可用',
        WAITING_CURRENT_SIGNAL: latest?.reason === 'CHAINLINK_PRICE_STALE_OR_FUTURE' ||
          latest?.signal?.period_start === start && Number.isFinite(latest.signal.price_observed_at) &&
          (latest.signal.price_observed_at > now || now - latest.signal.price_observed_at > 5) ?
          '行情采样已过期或时间无效' : '本轮行情尚未满足准备条件',
        SOURCE_STATE_UNAVAILABLE: '行情服务状态不可用', AUTO_PREPARATION_DISABLED: '自动准备已关闭',
        PREPARATION_LEDGER_WRITE_FAILED: '准备账本写入失败（PREPARATION_LEDGER_WRITE_FAILED）',
        PREFLIGHT_LEDGER_WRITE_FAILED: '预检账本写入失败（PREFLIGHT_LEDGER_WRITE_FAILED）',
        SAME_AS_1H_FAVORITE: '15 分钟热门方向与 1 小时相同，本轮跳过', HOUR_QUOTE_UNAVAILABLE: '1 小时盘口不可用',
        HIGH_VOLATILITY: 'BTC 过去 60 分钟波动过大，本轮跳过', BTC_VOLATILITY_UNAVAILABLE: 'BTC 波动数据不可用',
        FOUR_HOUR_SIDE_MISMATCH: '4 小时页面热门方向与模型方向不一致'};
      const blockers = ticketBlockers(document, location.href, now);
      const codes = [...new Set([...(Array.isArray(value.reasons) ? value.reasons.filter((reason) => typeof reason === 'string') : []),
        ...blockers, ...(orderTypeAttempt.reason ? [orderTypeAttempt.reason] : [])])];
      const details = codes.map((reason) => reasons[reason] || reason).join('、');
      preparationReport.textContent = `自动票据：${labels[state]}${details ? ` · ${details}` : ''}（未提交订单）`;
      if (value.enabled && elapsed < last && (orderTypeAttempt.phase === 'OPENED' || orderTypeAttempt.phase === 'SELECTED')) {
        preparationReport.textContent += '\n订单类型：正在切回市价单，等待回读';
      } else if (orderTypeAttempt.phase === 'READY' && pagePassed) preparationReport.textContent += '\n订单类型：市价单已核对';
      if (value.enabled && ((elapsed >= first && elapsed < last &&
          ['WAITING_SIGNAL', 'WAITING_BROWSER', 'BLOCKED'].includes(state)) || orderTypeAttempt.phase === 'FAILED')) {
        if (codes.length) {
          lastBlockers = codes;
          if (elapsed >= first && elapsed < last) windowBlockerOutcomes = codes.filter((code) => code !== 'INTENT_EXPIRED').map(outcomeReason);
        }
      }
      if (state === 'READY') {
        lastBlockers = [];
        windowBlockerOutcomes = [];
      }
      if (lastBlockers.length && (elapsed >= last || orderTypeAttempt.phase === 'FAILED')) {
        preparationReport.textContent += `\n本轮阻断：${lastBlockers.map((reason) => reasons[reason] || reason).join('、')}`;
      }
      if (reportPromise) await reportPromise.catch(() => {});
      const result = await prepareOnlyOnce(wrapper, document, () => location.href, globalThis.sessionStorage, {
        readPreparation: () => preparationRequest('FUTURE_BTC5M_PREPARATION'),
        claimPreparation: (payload) => preparationRequest('FUTURE_BTC5M_PREPARATION_CLAIM', payload),
        reportPreflight: (payload) => chrome.runtime.sendMessage({type: 'FUTURE_BTC5M_PREFLIGHT', payload}),
        acknowledge: async (payload) => {
          const status = await preparationRequest('FUTURE_BTC5M_PREPARATION_ACK', payload);
          const ok = status?.bridgeId === 'future-btc5m' && status.preparation?.state === payload.status;
          if (ok && payload.status === 'READY') void autoBuyer?.notifyReady?.(status);
          return {ok};
        },
      });
      if (result) preparationReport.textContent = result.status === 'READY' ?
        `自动票据：已准备 $1，并按按钮较大数值选择${value.intent.side === 'Up' ? '涨 Up' : '跌 Down'}（准备本身未提交订单）` :
        `自动票据：${result.status} · ${reasons[result.reason] || result.reason}（未提交订单，不重试）`;
      refreshTicketView();
      showOutcomeSummary(autoBuyer?.status() ?? {state: 'BLOCKED', reason: 'UPDATED_EXTENSION_CONTEXT_REQUIRED'});
    } catch {
      preparationView = null;
      refreshTicketView();
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
      extensionContextInvalidated = false;
      const now = Date.now() / 1000;
      if (inspectedUrl !== location.href) {
        inspection.textContent = '';
        autoCheckedUrl = null;
        inspectedUrl = location.href;
      }
      const sourceUrl = location.href;
      navigation.textContent = followCurrentMarket(latest, sourceUrl, document, globalThis.sessionStorage, now,
        (target) => location.replace(target));
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
      text.textContent = `观察服务 / 手动草稿检查（自动买入结果见上方）：\n${text.textContent}`;
      if (view.marketUrl) {
        link.href = view.marketUrl;
        link.style.display = 'inline';
      }
      if (draft && matchesMarket(location.href, draft)) {
        text.textContent += `\n入场草稿剩余 ${Math.max(0, Math.floor(draft.expires_at - now))} 秒`;
        prepare.disabled = false;
      }
      await pollPreparation();
      await refreshSchedule();
    } catch (error) {
      if (/extension context invalidated/i.test(error.message)) extensionContextInvalidated = true;
      latest = null;
      preparationView = null;
      refreshTicketView();
      text.textContent = extensionContextInvalidated ?
        '扩展上下文已失效：扩展更新或重载后，此页面仍在使用旧脚本。请刷新此页面恢复连接；当前开关与执行状态未核实，不补买。' : error.message;
      inspection.textContent = '';
      autoCheckedUrl = null;
      navigation.textContent = '自动换轮：暂停（本地助手未连接）';
      preparationReport.textContent = '自动票据：暂停（本地助手未连接，未提交订单）';
      showAutoBuy();
      if (!scheduleBusy) showSchedule(null);
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
  function runTick() {
    refreshTicketView();
    showAutoBuy();
    poll();
    reportPage();
  }

  function connectRuntimeClock() {
    if (runtimePort || !chrome.runtime.connect) return;
    try {
      const port = chrome.runtime.connect({name: 'FUTURE_BTC5M_RUNTIME'});
      runtimePort = port;
      port.onMessage.addListener((tick) => {
        if (runtimePort !== port) return;
        if (tick && Object.keys(tick).length === 2 && tick.type === 'FUTURE_BTC5M_RENDERER_CHECK' &&
            Number.isFinite(tick.checkedAt) && Math.abs(Date.now() / 1000 - tick.checkedAt) <= 3) {
          const page = new URL(location.href);
          if (page.origin === 'https://future.news' &&
              pathRound(page.pathname)) {
            port.postMessage({type: 'FUTURE_BTC5M_RENDERER_PAGE', checkedAt: tick.checkedAt,
              marketUrl: page.origin + page.pathname});
          }
          return;
        }
        if (tick && Object.keys(tick).length === 2 && tick.type === 'FUTURE_BTC5M_RENDERER_STATUS' &&
            ['ACTIVE', 'ERROR', 'STOPPED'].includes(tick.state)) {
          rendererState = tick.state;
          refreshTicketView();
          return;
        }
        const now = Date.now() / 1000;
        if (!tick || Object.keys(tick).length !== 2 || tick.type !== 'FUTURE_BTC5M_TICK' ||
            !Number.isFinite(tick.serverTime) || Math.abs(now - tick.serverTime) > 3) return;
        lastRuntimeTick = now;
        runtimeReconnectAllowed = true;
        runTick();
      });
      port.onDisconnect.addListener(() => {
        if (runtimePort !== port) return;
        runtimePort = null;
        lastRuntimeTick = null;
        rendererState = 'UNAVAILABLE';
        refreshTicketView();
        // A transient port error must not wait for a hidden page timer. Read lastError
        // without exposing it, and bound recovery if the replacement is also rejected.
        void chrome.runtime.lastError;
        if (runtimeReconnectAllowed) {
          runtimeReconnectAllowed = false;
          connectRuntimeClock();
        }
      });
    } catch {
      runtimePort = null;
      lastRuntimeTick = null;
      rendererState = 'UNAVAILABLE';
    }
  }

  connectRuntimeClock();
  runTick();
  // Foreground/reconnect fallback only; the lock-screen critical path is the pushed clock.
  setInterval(() => { runtimeReconnectAllowed = true; connectRuntimeClock(); runTick(); }, 1000);
})();
