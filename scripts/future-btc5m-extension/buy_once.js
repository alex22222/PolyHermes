// Loaded by the extension manifest after content.js. Loading defines the watcher only.
// content.js drives createAutoBuyer() from the project's automatic-ticket switch; a bare
// start() still defaults to a non-clicking dry run.
(() => {
  'use strict';
  const KEY = 'polyhermes.future-btc5m.buy-once';
  const INTENT_FIELDS = ['schemaVersion', 'id', 'slug', 'periodStart', 'periodEnd', 'side', 'amountUsd',
    'createdAt', 'expiresAt', 'priceObservedAt', 'openPrice', 'currentPrice', 'priceSource', 'openPriceSource',
    'twapLookbackSeconds', 'mode', 'noSubmission', 'operatorAuthorized', 'authorizationSource', 'claimToken',
    'upQuoteCents', 'downQuoteCents', 'quoteObservedAt', 'selectionSource'];
  const RECORD_FIELDS = [...INTENT_FIELDS, 'state', 'updatedAt', 'claimedAt', 'reason', 'receipt'];
  const exact = (value, keys) => value && typeof value === 'object' && !Array.isArray(value) &&
    Object.keys(value).length === keys.length && keys.every((key) => Object.hasOwn(value, key));
  const quote = (value) => Number.isFinite(value) && value >= 0 && value <= 100 && Number(value.toFixed(2)) === value;
  const fresh = (at, now) => Number.isFinite(at) && now >= at && now - at <= 5;

  function readyRecord(wrapper, now, armedAt) {
    const preparation = wrapper?.preparation;
    const record = preparation?.lastAttempt;
    const start = Math.floor(now / 300) * 300;
    if (!Number.isFinite(now) || wrapper?.bridgeId !== 'future-btc5m' || !Number.isFinite(wrapper.serverTime) ||
        Math.abs(now - wrapper.serverTime) > 3 || preparation?.mode !== 'PREPARE_ONLY' ||
        preparation.enabled !== true || preparation.noSubmission !== true || preparation.operatorAuthorized !== true ||
        preparation.authorizationSource !== 'USER_REQUEST' || preparation.state !== 'READY' || preparation.intent !== null ||
        !Array.isArray(preparation.reasons) || preparation.reasons.length || !exact(record, RECORD_FIELDS) ||
        record.schemaVersion !== 2 || record.state !== 'READY' || record.reason !== null ||
        record.mode !== 'PREPARE_ONLY' || record.noSubmission !== true || record.operatorAuthorized !== true ||
        record.authorizationSource !== 'USER_REQUEST' || record.selectionSource !== 'HIGHER_BUTTON_PRICE' ||
        record.periodStart !== start || record.periodEnd !== start + 300 || record.expiresAt !== start + 80 ||
        record.id !== `future-btc5m-prepare:${start}` || record.slug !== `btc-updown-5m-${start}` || record.amountUsd !== 1 ||
        !quote(record.upQuoteCents) || !quote(record.downQuoteCents) || record.upQuoteCents === record.downQuoteCents ||
        record.side !== (record.upQuoteCents > record.downQuoteCents ? 'Up' : 'Down') ||
        record.priceSource !== 'chainlink' || record.openPriceSource !== 'polymarket_crypto_price_fiveminute_twap60_openPrice' ||
        record.twapLookbackSeconds !== 60 || !Number.isFinite(record.openPrice) || record.openPrice <= 0 ||
        !Number.isFinite(record.currentPrice) || record.currentPrice <= 0 ||
        !Number.isFinite(record.createdAt) || record.createdAt < armedAt || record.createdAt < start + 60 ||
        record.createdAt > now || record.createdAt >= start + 80 || now < start + 60 || now >= record.expiresAt ||
        !fresh(record.priceObservedAt, now) || record.priceObservedAt > record.createdAt ||
        !fresh(record.quoteObservedAt, now) || record.quoteObservedAt > record.createdAt ||
        !Number.isFinite(record.claimedAt) || record.claimedAt < record.createdAt || record.claimedAt > record.updatedAt ||
        !Number.isFinite(record.updatedAt) || record.updatedAt >= record.expiresAt || record.updatedAt > wrapper.serverTime ||
        !fresh(record.priceObservedAt, record.claimedAt) || !fresh(record.quoteObservedAt, record.claimedAt) ||
        !fresh(record.priceObservedAt, record.updatedAt) || !fresh(record.quoteObservedAt, record.updatedAt) ||
        typeof record.claimToken !== 'string' || !/^[a-f0-9]{32}$/.test(record.claimToken) ||
        !exact(record.receipt, ['checkedAt', 'marketUrl', 'amountUsd', 'selectedSide']) ||
        ![`https://future.news/zh/event/${record.slug}`, `https://future.news/zh/event/${record.slug}/`,
          `https://future.news/event/${record.slug}`, `https://future.news/event/${record.slug}/`].includes(record.receipt.marketUrl) ||
        record.receipt.amountUsd !== 1 || record.receipt.selectedSide !== record.side ||
        !Number.isFinite(record.receipt.checkedAt) || record.receipt.checkedAt < start + 60 ||
        record.receipt.checkedAt >= record.expiresAt || Math.abs(now - record.receipt.checkedAt) > 5 ||
        record.receipt.checkedAt < record.claimedAt - 3 || Math.abs(record.receipt.checkedAt - record.updatedAt) > 3) return null;
    return record;
  }

  function buyButton(core, document, url, record, now) {
    const report = core.readPreflight(document, url, now);
    const ticket = core.readPreparationTicket(document, url, record.periodStart);
    if (report?.navigation !== 'CURRENT' || report.ticketStatus !== 'PASS' || report.pagePeriodStart !== record.periodStart ||
        report.amountUsd !== 1 || report.selectedSide !== record.side || !report.buyButtonEnabled ||
        ticket.input.value !== '1' || ticket.selectedSide !== record.side || ticket.preferredSide !== record.side) {
      throw new Error('TICKET_CHANGED');
    }
    const scope = core.findAmountTicket(document, ticket.input);
    const matches = [...scope.querySelectorAll('button')].filter((button) => button.getClientRects().length &&
      /^买入\s+(涨|跌)$/.test(button.textContent.trim()));
    if (matches.length !== 1 || matches[0].tagName !== 'BUTTON' || matches[0].type !== 'button' ||
        !core.buttonIsEnabled(matches[0]) ||
        matches[0].textContent.trim().replace(/\s+/g, ' ') !== `买入 ${record.side === 'Up' ? '涨' : '跌'}`) {
      throw new Error('BUY_BUTTON_UNSAFE');
    }
    return matches[0];
  }

  function browserReadPreparation() {
    return new Promise((resolve, reject) => {
      if (!globalThis.chrome?.runtime?.sendMessage) return reject(new Error('EXTENSION_CONTEXT_REQUIRED'));
      chrome.runtime.sendMessage({type: 'FUTURE_BTC5M_PREPARATION'}, (reply) => {
        if (chrome.runtime.lastError || !reply?.ok || !reply.status) reject(new Error('READ_FAILED'));
        else resolve(reply.status);
      });
    });
  }

  function createWatcher(env = {}) {
    const core = env.core ?? globalThis.FutureBtc5m;
    const document = env.document ?? globalThis.document;
    const readUrl = env.readUrl ?? (() => globalThis.location.href);
    const readPreparation = env.readPreparation ?? browserReadPreparation;
    const nowFn = env.nowFn ?? (() => Date.now() / 1000);
    const schedule = env.setIntervalFn ?? globalThis.setInterval;
    const unschedule = env.clearIntervalFn ?? globalThis.clearInterval;
    const withLock = env.withLock ?? (globalThis.navigator?.locks &&
      ((callback) => navigator.locks.request(KEY, {mode: 'exclusive'}, callback)));
    let storage = env.storage;
    let active = false, busy = false, generation = 0, timer = null, armedAt = null, live = false, consumed = false;
    let result = {state: 'IDLE', reason: null, periodStart: null, side: null, amountUsd: null};
    const current = (run) => active && generation === run;
    const finish = (state, reason, record) => {
      active = false;
      if (timer !== null) unschedule(timer);
      timer = null;
      result = {state, reason, periodStart: record?.periodStart ?? null, side: record?.side ?? null,
        amountUsd: record ? 1 : null};
    };

    async function poll() {
      if (!active || busy) return;
      busy = true;
      const run = generation;
      try {
        const first = await readPreparation();
        if (!current(run)) return;
        const record = readyRecord(first, nowFn(), armedAt);
        if (!record) return;
        buyButton(core, document, readUrl(), record, nowFn());
        const attempt = async () => {
          if (!current(run)) return;
          const second = await readPreparation();
          if (!current(run)) return;
          const freshRecord = readyRecord(second, nowFn(), armedAt);
          if (!freshRecord || !RECORD_FIELDS.every((key) =>
            JSON.stringify(freshRecord[key]) === JSON.stringify(record[key]))) throw new Error('READY_CHANGED');
          const button = buyButton(core, document, readUrl(), freshRecord, nowFn());
          if (!current(run)) return;
          if (!live) return finish('DRY_RUN_READY', null, freshRecord);
          try {
            storage ??= globalThis.localStorage;
            const raw = storage.getItem(KEY);
            if (raw !== null) {
              const previous = JSON.parse(raw);
              if (!exact(previous, ['schemaVersion', 'periodStart', 'id', 'side', 'amountUsd', 'state']) ||
                  previous.schemaVersion !== 1 || !Number.isSafeInteger(previous.periodStart) || previous.periodStart < 0 ||
                  previous.periodStart % 300 || previous.id !== `future-btc5m-prepare:${previous.periodStart}` ||
                  !['Up', 'Down'].includes(previous.side) || previous.amountUsd !== 1 || previous.state !== 'CLICK_ATTEMPTED') {
                throw new Error('STORAGE_FAILED');
              }
              if (previous.periodStart >= freshRecord.periodStart) return finish('BLOCKED', 'ALREADY_CONSUMED', freshRecord);
            }
            storage.setItem(KEY, JSON.stringify({schemaVersion: 1, periodStart: freshRecord.periodStart,
              id: freshRecord.id, side: freshRecord.side, amountUsd: 1, state: 'CLICK_ATTEMPTED'}));
          } catch {
            throw new Error('STORAGE_FAILED');
          }
          // No await after the persistent marker. A thrown click remains consumed.
          consumed = true;
          if (!current(run)) return;
          try {
            if (!readyRecord(second, nowFn(), armedAt)) throw new Error('FINAL_CHECK_FAILED');
            const finalButton = buyButton(core, document, readUrl(), freshRecord, nowFn());
            if (finalButton !== button || finalButton.isConnected !== true ||
                !readyRecord(second, nowFn(), armedAt)) throw new Error('FINAL_CHECK_FAILED');
          } catch {
            if (current(run)) finish('BLOCKED', 'FINAL_CHECK_FAILED', freshRecord);
            return;
          }
          if (!current(run)) return;
          finish('CLICK_ATTEMPTED', 'PLATFORM_RESULT_UNKNOWN', freshRecord);
          try { button.click(); } catch { result.reason = 'CLICK_THROWN_RESULT_UNKNOWN'; }
        };
        if (live) await withLock(attempt);
        else await attempt();
      } catch (error) {
        if (current(run)) finish('BLOCKED', ['TICKET_CHANGED', 'BUY_BUTTON_UNSAFE', 'READY_CHANGED', 'STORAGE_FAILED'].includes(error.message)
          ? error.message : 'READ_FAILED');
      } finally { busy = false; }
    }

    return {
      start(options = {}) {
        if (active || consumed) throw new Error('ALREADY_STARTED_OR_CONSUMED');
        if (!exact(options, options.live === undefined ? [] : ['live']) ||
            options.live !== undefined && typeof options.live !== 'boolean') throw new Error('INVALID_START_OPTIONS');
        if (!core?.readPreflight || !core.readPreparationTicket || !core.findAmountTicket || !core.buttonIsEnabled || !document) {
          throw new Error('UPDATED_EXTENSION_CONTEXT_REQUIRED');
        }
        live = options.live === true;
        if (live && typeof withLock !== 'function') throw new Error('WEB_LOCKS_REQUIRED');
        armedAt = nowFn();
        if (!Number.isFinite(armedAt)) throw new Error('INVALID_CLOCK');
        generation++;
        active = true;
        result = {state: 'WATCHING', reason: null, periodStart: null, side: null, amountUsd: null};
        timer = schedule(() => { void poll(); }, 500);
        return {...result};
      },
      stop() { generation++; if (active || !consumed) finish('STOPPED', null); return {...result}; },
      status() { return {...result}; },
      poll,
    };
  }

  // Follows the project's automatic-ticket switch: while it is on, one live watcher stays
  // armed and a finished one is replaced. createdAt >= armedAt and the persistent
  // per-round mark keep every round to at most one click; a READY that existed before
  // re-arming is never caught up.
  function createAutoBuyer(env = {}) {
    let enabled = false, watcher = null, failure = null, last = null;
    const noteworthy = (value) => value?.state === 'CLICK_ATTEMPTED' ||
      value?.state === 'BLOCKED' && value.reason !== 'READ_FAILED';
    const view = () => {
      const current = watcher?.status() ?? null;
      const finished = current && current.state !== 'WATCHING' ? current : null;
      const recent = noteworthy(finished) ? finished : last;
      return {state: !enabled ? 'OFF' : failure ? 'BLOCKED' : finished || !current ? 'PAUSED' : 'WATCHING',
        reason: enabled ? failure : null, last: recent && {...recent}};
    };
    return {
      sync(value) {
        const current = watcher?.status();
        if (current && current.state !== 'WATCHING') {
          if (noteworthy(current)) last = current;
          watcher = null;
        }
        enabled = value === true;
        failure = null;
        if (!enabled) {
          watcher?.stop();
          watcher = null;
        } else if (!watcher) {
          const next = createWatcher(env);
          try {
            next.start({live: true});
            watcher = next;
          } catch (error) {
            failure = error.message;
          }
        }
        return view();
      },
      status: view,
    };
  }

  if (globalThis.FutureBtc5mBuyOnce) throw new Error('WATCHER_ALREADY_LOADED');
  globalThis.FutureBtc5mBuyOnce = {...createWatcher(), createWatcher, createAutoBuyer};
})();
