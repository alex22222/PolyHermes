// Loaded by the extension manifest after content.js. Loading defines the watcher only.
// content.js drives createAutoBuyer() from the project's automatic-ticket switch; a bare
// start() still defaults to a non-clicking dry run.
(() => {
  'use strict';
  const KEY = 'polyhermes.future-btc5m.buy-once';
  // Durable outbox of attempt/refusal audits; entries leave only after the bridge stores them.
  const AUDIT_KEY = 'polyhermes.future-btc5m.buy-audit';
  const INTENT_FIELDS = ['schemaVersion', 'id', 'slug', 'periodStart', 'periodEnd', 'side', 'amountUsd',
    'createdAt', 'expiresAt', 'priceObservedAt', 'openPrice', 'currentPrice', 'priceSource', 'openPriceSource',
    'twapLookbackSeconds', 'mode', 'noSubmission', 'operatorAuthorized', 'authorizationSource', 'claimToken',
    'upQuoteCents', 'downQuoteCents', 'quoteObservedAt', 'selectionSource'];
  const RECORD_FIELDS = [...INTENT_FIELDS, 'state', 'updatedAt', 'claimedAt', 'reason', 'receipt'];
  const exact = (value, keys) => value && typeof value === 'object' && !Array.isArray(value) &&
    Object.keys(value).length === keys.length && keys.every((key) => Object.hasOwn(value, key));
  const quote = (value) => Number.isFinite(value) && value >= 0 && value <= 100 && Number(value.toFixed(2)) === value;
  const fresh = (at, now) => Number.isFinite(at) && now >= at && now - at <= 5;
  // Price gates before the automatic Buy: the favorite must be worth at least 60¢, the page
  // button must agree with an independent Polymarket CLOB book, and both must stay within
  // 5¢ above or below the price the READY round was prepared at.
  const MIN_FAVORITE_CENTS = 60;
  const MAX_READY_CHANGE_CENTS = 5;
  // Absolute ceiling: near 100¢ the payout cannot cover the price plus fees.
  const MAX_PRICE_CENTS = 97;
  const MAX_MARKET_GAP_CENTS = 3;
  const MARKET_QUOTE_MAX_AGE_SECONDS = 2;
  const MARKET_FIELDS = ['schemaVersion', 'source', 'periodStart', 'slug', 'upAskCents', 'downAskCents',
    'upBidCents', 'downBidCents', 'observedAt', 'serverTime'];
  const GATE_REASONS = ['PRICE_BELOW_MIN', 'MARKET_QUOTE_UNAVAILABLE', 'MARKET_QUOTE_MISMATCH', 'PRICE_ABOVE_MAX'];
  const MARKET_QUOTE_DETAILS = ['HTTP_SOURCE_TIMEOUT', 'HTTP_SOURCE_UNAVAILABLE', 'INVALID_MARKET_QUOTE',
    'CLOB_BOOKS_MISMATCH', 'CLOB_BOOK_TIME_INVALID', 'ROUND_CHANGED_DURING_READ', 'INVALID_BOOK', 'INVALID_BOOK_LEVEL',
    'WRONG_MARKET_PRICE_CONFIG', 'MARKET_NOT_UNIQUE', 'WRONG_OR_INACTIVE_EVENT', 'WRONG_OR_INACTIVE_MARKET',
    'WRONG_MARKET_PERIOD', 'INVALID_OUTCOME_TOKENS', 'LOCAL_QUOTE_TIMEOUT', 'LOCAL_QUOTE_NOT_FOUND',
    'MARKET_QUOTE_STALE', 'MARKET_QUOTE_EMPTY'];
  // Quotes have at most two decimals; boundaries compare whole hundredths, never float sums.
  const hundredths = (value) => Math.round(value * 100);
  const sideCents = (record) => record.side === 'Up' ? record.upQuoteCents : record.downQuoteCents;

  function marketQuoteError(detail) {
    return Object.assign(new Error('MARKET_QUOTE_UNAVAILABLE'), {
      detail: MARKET_QUOTE_DETAILS.includes(detail) ? detail : 'MARKET_QUOTE_UNAVAILABLE'});
  }

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
    return {button: matches[0], report};
  }

  // The local assistant's CLOB snapshot of the READY round. A copy is judged so a later change
  // to the reply object cannot alter what the gates compare.
  function validMarketQuote(value, record, now) {
    const market = value && typeof value === 'object' && !Array.isArray(value) ? {...value} : null;
    if (!exact(market, MARKET_FIELDS) || market.schemaVersion !== 1 || market.source !== 'polymarket_clob_book' ||
        market.periodStart !== record.periodStart || market.slug !== record.slug ||
        !['upAskCents', 'downAskCents', 'upBidCents', 'downBidCents'].every((key) => market[key] === null || quote(market[key])) ||
        !Number.isFinite(now) || !Number.isFinite(market.observedAt) || !Number.isFinite(market.serverTime) ||
        Math.abs(now - market.serverTime) > 3 || now - market.observedAt < -0.5) throw marketQuoteError('INVALID_MARKET_QUOTE');
    if (now - market.observedAt > MARKET_QUOTE_MAX_AGE_SECONDS) throw marketQuoteError('MARKET_QUOTE_STALE');
    return market;
  }

  // Throws the first failed gate. The final synchronous check runs it again on the final DOM.
  function priceGate(record, report, market, now) {
    validMarketQuote(market, record, now);
    const up = record.side === 'Up';
    const sideAsk = up ? market.upAskCents : market.downAskCents;
    const otherAsk = up ? market.downAskCents : market.upAskCents;
    if (sideAsk === null || otherAsk === null) throw marketQuoteError('MARKET_QUOTE_EMPTY');
    if (!(sideAsk > otherAsk)) throw new Error('MARKET_QUOTE_MISMATCH');
    const domCents = up ? report?.upQuoteCents : report?.downQuoteCents;
    if (!quote(domCents) || Math.abs(hundredths(sideAsk) - hundredths(domCents)) > MAX_MARKET_GAP_CENTS * 100) {
      throw new Error('MARKET_QUOTE_MISMATCH');
    }
    const readyCents = sideCents(record);
    if (Math.min(readyCents, domCents, sideAsk) < MIN_FAVORITE_CENTS ||
        hundredths(Math.min(domCents, sideAsk)) < hundredths(readyCents) - MAX_READY_CHANGE_CENTS * 100) {
      throw new Error('PRICE_BELOW_MIN');
    }
    if (hundredths(Math.max(domCents, sideAsk)) > hundredths(readyCents) + MAX_READY_CHANGE_CENTS * 100 ||
        Math.max(readyCents, domCents, sideAsk) > MAX_PRICE_CENTS) {
      throw new Error('PRICE_ABOVE_MAX');
    }
  }

  function readAudits(storage) {
    const raw = storage.getItem(AUDIT_KEY);
    const list = raw === null ? [] : JSON.parse(raw);
    if (!Array.isArray(list)) throw new Error('AUDIT_STORAGE_FAILED');
    return list;
  }

  function browserReportAudit(payload) {
    return new Promise((resolve, reject) => {
      if (!globalThis.chrome?.runtime?.sendMessage) return reject(new Error('EXTENSION_CONTEXT_REQUIRED'));
      chrome.runtime.sendMessage({type: 'FUTURE_BTC5M_BUY_AUDIT', payload}, (reply) => {
        if (chrome.runtime.lastError || !reply?.ok || !reply.status) reject(new Error('AUDIT_REPORT_FAILED'));
        else resolve(reply.status);
      });
    });
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

  function browserReadMarketQuote() {
    return new Promise((resolve, reject) => {
      if (!globalThis.chrome?.runtime?.sendMessage) return reject(new Error('EXTENSION_CONTEXT_REQUIRED'));
      chrome.runtime.sendMessage({type: 'FUTURE_BTC5M_MARKET_QUOTE'}, (reply) => {
        if (chrome.runtime.lastError || !reply?.ok || !reply.status) {
          reject(marketQuoteError(chrome.runtime.lastError ? undefined : reply?.errorCode));
        }
        else resolve(reply.status);
      });
    });
  }

  function createWatcher(env = {}) {
    const core = env.core ?? globalThis.FutureBtc5m;
    const document = env.document ?? globalThis.document;
    const readUrl = env.readUrl ?? (() => globalThis.location.href);
    const readPreparation = env.readPreparation ?? browserReadPreparation;
    const readMarketQuote = env.readMarketQuote ?? browserReadMarketQuote;
    const nowFn = env.nowFn ?? (() => Date.now() / 1000);
    const schedule = env.setIntervalFn ?? globalThis.setInterval;
    const unschedule = env.clearIntervalFn ?? globalThis.clearInterval;
    const withLock = env.withLock ?? (globalThis.navigator?.locks &&
      ((callback) => navigator.locks.request(KEY, {mode: 'exclusive'}, callback)));
    const extensionVersion = env.extensionVersion ?? globalThis.chrome?.runtime?.getManifest?.()?.version ?? '0.0.0';
    let storage = env.storage;
    let auditStorage = env.auditStorage;
    let active = false, busy = false, generation = 0, timer = null, armedAt = null, live = false, consumed = false;
    let queuedReady = null;
    let result = {state: 'IDLE', reason: null, detail: null, periodStart: null, side: null, amountUsd: null, audit: null};
    const current = (run) => active && generation === run;
    const finish = (state, reason, record, detail = null) => {
      active = false;
      if (timer !== null) unschedule(timer);
      timer = null;
      result = {state, reason, detail: reason === 'MARKET_QUOTE_UNAVAILABLE' ? marketQuoteError(detail).detail : null,
        periodStart: record?.periodStart ?? null, side: record?.side ?? null,
        amountUsd: record ? 1 : null, audit: null};
    };
    // Live outcomes for a READY round only. The page facts come from the final DOM check, or
    // for a price-gate refusal from the DOM check it judged; without one, the canonical market
    // URL of the READY round is recorded. The CLOB asks come from the validated order-book
    // snapshot, or are null when none was read.
    const audit = (record, state, reason, report, market, attemptedAt) => {
      if (!live) return;
      try {
        auditStorage ??= globalThis.localStorage;
        const list = readAudits(auditStorage);
        list.push({schemaVersion: 2, auditId: `${record.id}:${Math.floor(attemptedAt * 1000)}`, id: record.id,
          claimToken: record.claimToken, periodStart: record.periodStart, side: record.side, amountUsd: 1, state, reason,
          armedAt, attemptedAt, marketUrl: report?.marketUrl ?? `https://future.news/zh/event/${record.slug}`,
          upQuoteCents: report?.upQuoteCents ?? null, downQuoteCents: report?.downQuoteCents ?? null,
          selectedSide: report?.selectedSide ?? null, ticketAmountUsd: report?.amountUsd ?? null, extensionVersion,
          marketUpAskCents: market?.upAskCents ?? null, marketDownAskCents: market?.downAskCents ?? null,
          marketQuoteObservedAt: market?.observedAt ?? null});
        auditStorage.setItem(AUDIT_KEY, JSON.stringify(list.slice(-500)));
        result.audit = 'QUEUED';
      } catch {
        result.audit = 'FAILED';
      }
    };

    async function poll(confirmedReady) {
      if (!active) return;
      if (busy) {
        if (confirmedReady) queuedReady = {wrapper: confirmedReady, run: generation};
        return;
      }
      busy = true;
      const run = generation;
      let audited = null, latestReport = null, market = null;
      try {
        // An acknowledged READY can wake the watcher without a timer/discovery GET.
        // The locked and post-book reads below still validate the current permission.
        const first = confirmedReady ?? await readPreparation();
        if (!current(run)) return;
        const record = readyRecord(first, nowFn(), armedAt);
        if (!record) return;
        audited = record;
        latestReport = buyButton(core, document, readUrl(), record, nowFn()).report;
        const attempt = async () => {
          if (!current(run)) return;
          const secondRead = readPreparation();
          // Independent reads overlap. Handle book failures now so an earlier READY
          // refusal cannot leave an unhandled rejection in the background.
          const marketRead = sideCents(record) >= MIN_FAVORITE_CENTS && sideCents(record) <= MAX_PRICE_CENTS ?
            Promise.resolve().then(() => readMarketQuote()).then((value) => ({value}), (error) => ({error})) : null;
          const second = await secondRead;
          if (!current(run)) return;
          const freshRecord = readyRecord(second, nowFn(), armedAt);
          if (!freshRecord || !RECORD_FIELDS.every((key) =>
            JSON.stringify(freshRecord[key]) === JSON.stringify(record[key]))) throw new Error('READY_CHANGED');
          audited = freshRecord;
          // A favorite prepared below the minimum skips the round without asking the order book.
          if (sideCents(freshRecord) < MIN_FAVORITE_CENTS) throw new Error('PRICE_BELOW_MIN');
          if (sideCents(freshRecord) > MAX_PRICE_CENTS) throw new Error('PRICE_ABOVE_MAX');
          latestReport = buyButton(core, document, readUrl(), freshRecord, nowFn()).report;
          try {
            const reply = await marketRead;
            if (reply && Object.hasOwn(reply, 'error')) throw marketQuoteError(reply.error?.detail ?? reply.error?.errorCode);
            market = validMarketQuote(reply?.value, freshRecord, nowFn());
          } catch (error) {
            throw marketQuoteError(error?.detail ?? error?.errorCode);
          }
          if (!current(run)) return;
          // The page may have changed while the order book was read.
          latestReport = buyButton(core, document, readUrl(), freshRecord, nowFn()).report;
          priceGate(freshRecord, latestReport, market, nowFn());
          // READY is read again after the order book: a STOP or switch-off during that read, or a
          // READY that aged out of its 5 s sample window, refuses here before the round is marked.
          const third = await readPreparation();
          if (!current(run)) return;
          const latestRecord = readyRecord(third, nowFn(), armedAt);
          if (!latestRecord || !RECORD_FIELDS.every((key) =>
            JSON.stringify(latestRecord[key]) === JSON.stringify(record[key]))) throw new Error('READY_CHANGED');
          const {button, report} = buyButton(core, document, readUrl(), freshRecord, nowFn());
          latestReport = report;
          priceGate(freshRecord, report, market, nowFn());
          // A dry run reports READY only when the price gates pass as well.
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
              if (previous.periodStart >= freshRecord.periodStart) {
                finish('BLOCKED', 'ALREADY_CONSUMED', freshRecord);
                return audit(freshRecord, 'BLOCKED', 'ALREADY_CONSUMED', null, market, nowFn());
              }
            }
            storage.setItem(KEY, JSON.stringify({schemaVersion: 1, periodStart: freshRecord.periodStart,
              id: freshRecord.id, side: freshRecord.side, amountUsd: 1, state: 'CLICK_ATTEMPTED'}));
          } catch {
            throw new Error('STORAGE_FAILED');
          }
          // No await after the persistent marker. A thrown click remains consumed.
          consumed = true;
          if (!current(run)) return;
          let finalReport;
          try {
            if (!readyRecord(third, nowFn(), armedAt)) throw new Error('FINAL_CHECK_FAILED');
            const final = buyButton(core, document, readUrl(), freshRecord, nowFn());
            finalReport = final.report;
            // The same price gates on the final DOM, still against a fresh enough order book.
            priceGate(freshRecord, final.report, market, nowFn());
            if (final.button !== button || final.button.isConnected !== true ||
                !readyRecord(third, nowFn(), armedAt)) throw new Error('FINAL_CHECK_FAILED');
          } catch {
            if (current(run)) {
              finish('BLOCKED', 'FINAL_CHECK_FAILED', freshRecord);
              audit(freshRecord, 'BLOCKED', 'FINAL_CHECK_FAILED', finalReport, market, nowFn());
            }
            return;
          }
          if (!current(run)) return;
          finish('CLICK_ATTEMPTED', 'PLATFORM_RESULT_UNKNOWN', freshRecord);
          const clickedAt = nowFn();
          try { button.click(); } catch { result.reason = 'CLICK_THROWN_RESULT_UNKNOWN'; }
          // Queued after the click so the audit write never delays it.
          audit(freshRecord, 'CLICK_ATTEMPTED', result.reason, finalReport, market, clickedAt);
        };
        if (live) await withLock(attempt);
        else await attempt();
      } catch (error) {
        if (current(run)) {
          const reason = ['TICKET_CHANGED', 'BUY_BUTTON_UNSAFE', 'READY_CHANGED', 'STORAGE_FAILED', ...GATE_REASONS]
            .includes(error?.message) ? error.message : 'READ_FAILED';
          finish('BLOCKED', reason, audited, error?.detail);
          // A price-gate refusal keeps the latest page facts it was judged on.
          if (audited && GATE_REASONS.includes(reason)) {
            result.priceCheck = {upQuoteCents: latestReport?.upQuoteCents ?? null,
              downQuoteCents: latestReport?.downQuoteCents ?? null,
              marketUpAskCents: market?.upAskCents ?? null, marketDownAskCents: market?.downAskCents ?? null};
          }
          if (audited && reason !== 'READ_FAILED') {
            audit(audited, 'BLOCKED', reason, GATE_REASONS.includes(reason) ? latestReport : null, market, nowFn());
          }
        }
      } finally {
        busy = false;
        const pending = queuedReady;
        queuedReady = null;
        if (pending && current(pending.run)) void poll(pending.wrapper);
      }
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
        result = {state: 'WATCHING', reason: null, detail: null, periodStart: null, side: null, amountUsd: null, audit: null};
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
    const reportAudit = env.reportAudit ?? browserReportAudit;
    let enabled = false, watcher = null, failure = null, last = null;
    let flushing = false, pendingAudits = 0, auditError = null;
    // Every entry is retried until the bridge confirms storing it; one rejected entry
    // never hides the others.
    async function flushAudits() {
      if (flushing) return;
      flushing = true;
      let failed = 0;
      try {
        const storage = env.auditStorage ?? globalThis.localStorage;
        for (const entry of readAudits(storage)) {
          try {
            const reply = await reportAudit(entry);
            if (reply?.auditId !== entry.auditId || reply.stored !== true) throw new Error('AUDIT_NOT_ACKNOWLEDGED');
            storage.setItem(AUDIT_KEY, JSON.stringify(readAudits(storage).filter((item) => item?.auditId !== entry.auditId)));
          } catch {
            failed++;
          }
        }
        pendingAudits = readAudits(storage).length;
        auditError = failed ? 'AUDIT_REPORT_PENDING' : null;
      } catch {
        auditError = 'AUDIT_STORAGE_FAILED';
      } finally {
        flushing = false;
      }
    }
    const noteworthy = (value) => value?.state === 'CLICK_ATTEMPTED' ||
      value?.state === 'BLOCKED' && value.reason !== 'READ_FAILED';
    const view = () => {
      const current = watcher?.status() ?? null;
      const finished = current && current.state !== 'WATCHING' ? current : null;
      const recent = noteworthy(finished) ? finished : last;
      return {state: !enabled ? 'OFF' : failure ? 'BLOCKED' : finished || !current ? 'PAUSED' : 'WATCHING',
        reason: enabled ? failure : null, last: recent && {...recent}, pendingAudits, auditError};
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
        void flushAudits();
        return view();
      },
      async notifyReady(wrapper) {
        // A notification never arms, re-arms or bypasses the watcher's generation/lock.
        if (enabled && watcher) await watcher.poll(wrapper);
      },
      status: view,
      flushAudits,
    };
  }

  if (globalThis.FutureBtc5mBuyOnce) throw new Error('WATCHER_ALREADY_LOADED');
  globalThis.FutureBtc5mBuyOnce = {...createWatcher(), createWatcher, createAutoBuyer};
})();
