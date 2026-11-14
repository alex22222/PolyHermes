"""BTC forward-only, evidence-gated paper comparison. No trading or browser writes.

Two independent reads of the Future ticket surround fresh public books. A separate
paper preparation snapshot is retained when live trading is disabled; it is never
called a READY receipt or a fill. Historical PREPARE records are not imported.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
import json
import math
import re
import sqlite3
import time
import urllib.parse

from future_btc5m_conditions import round_conditions
from future_btc5m_series import hourly_slug, market_url_round

VERSION = 'btc-forward-v1-20261114'
RULES = ['G1', 'G2', 'A', 'B']
OPEN_SOURCE = 'polymarket_crypto_price_fifteen_twap60_openPrice'


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _fee_verified(value):
    return (isinstance(value, dict) and number(value.get('rate')) and value['rate'] == .07
            and number(value.get('exponent')) and value['exponent'] == 1
            and value.get('takerOnly') is True)


def _time(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('MARKET_TIMEZONE_MISSING')
    return parsed.timestamp()


def quote(value):
    return number(value) and 0 <= value <= 100 and value == round(value, 2)


def _window(start, now):
    if type(start) is not int or start % 900 or not number(now) or not start+150 <= now < start+170:
        raise ValueError('OUTSIDE_ENTRY_WINDOW')


def _snapshot(value, start, now):
    _window(start, now)
    if (not isinstance(value, dict) or value.get('bridgeId') != 'future-btc5m'
            or value.get('series') != '15m' or value.get('periodStart') != start
            or value.get('feedStatus') != 'CURRENT' or not number(value.get('serverTime'))
            or abs(now-value['serverTime']) > 3):
        raise ValueError('BRIDGE_NOT_CURRENT')
    signal, ticket = value.get('signal'), value.get('preflight')
    if not isinstance(signal, dict) or not isinstance(ticket, dict):
        raise ValueError('MISSING_ENTRY_EVIDENCE')
    if (signal.get('id') != f'15m:{start}' or signal.get('slug') != f'btc-updown-15m-{start}'
            or signal.get('series') != '15m' or signal.get('period_start') != start
            or signal.get('period_end') != start+900 or signal.get('price_source') != 'chainlink'
            or signal.get('open_price_source') != OPEN_SOURCE or signal.get('twap_lookback_seconds') != 60
            or any(not number(signal.get(k)) or signal[k] <= 0 for k in ('open_price', 'current_price'))
            or not number(signal.get('price_observed_at')) or not 0 <= now-signal['price_observed_at'] <= 5):
        raise ValueError('CHAINLINK_BASELINE_UNVERIFIED')
    actual_side = ('Up' if signal['current_price'] > signal['open_price'] else
                   'Down' if signal['current_price'] < signal['open_price'] else None)
    if signal.get('side') != actual_side:
        raise ValueError('CHAINLINK_DIRECTION_INVALID')
    if (ticket.get('mode') != 'READ_ONLY' or ticket.get('noSubmission') is not True
            or ticket.get('browserConnected') is not True or ticket.get('signalFresh') is not True
            or ticket.get('navigation') != 'CURRENT' or ticket.get('ticketStatus') != 'PASS'
            or type(ticket.get('amountUsd')) not in (int, float) or ticket['amountUsd'] != 1
            or ticket.get('buyButtonEnabled') is not True or ticket.get('pagePeriodStart') != start
            or market_url_round(ticket.get('marketUrl')) != ('15m', start)
            or any(not number(ticket.get(k)) or not 0 <= now-ticket[k] <= 5 for k in ('checkedAt', 'receivedAt'))
            or not start+150 <= ticket['checkedAt'] < start+170):
        raise ValueError('FUTURE_TICKET_UNVERIFIED')
    up, down = ticket.get('upQuoteCents'), ticket.get('downQuoteCents')
    if not quote(up) or not quote(down) or up == down:
        raise ValueError('FUTURE_QUOTES_UNVERIFIED')
    side = 'Up' if up > down else 'Down'
    if ticket.get('selectedSide') != side:
        raise ValueError('FUTURE_SELECTED_SIDE_MISMATCH')
    # Explicit whitelist: claim tokens, account/wallet data and authorizations are never persisted.
    return {'bridgeId': 'future-btc5m', 'serverTime': value['serverTime'], 'series': '15m',
            'periodStart': start, 'feedStatus': 'CURRENT',
            'signal': {k: signal[k] for k in ('id', 'slug', 'series', 'period_start', 'period_end',
                'price_source', 'open_price_source', 'twap_lookback_seconds', 'open_price',
                'current_price', 'price_observed_at', 'side')},
            'preflight': {k: ticket[k] for k in ('mode', 'noSubmission', 'browserConnected', 'signalFresh',
                'checkedAt', 'receivedAt', 'marketUrl', 'pagePeriodStart', 'navigation', 'ticketStatus',
                'amountUsd', 'selectedSide', 'buyButtonEnabled', 'upQuoteCents', 'downQuoteCents')}}


def _features(value, start, now):
    if (not isinstance(value, dict) or value.get('source') != 'binance_btcusdt_1m'
            or value.get('periodStart') != start or value.get('lastCandleOpen') != start+60
            or not number(value.get('observedAt')) or not start+120 <= value['observedAt'] <= now
            or not number(value.get('trend60Bp')) or not number(value.get('volatilityBp'))
            or not 0 <= value['volatilityBp'] <= 4.16):
        raise ValueError('R1_OR_FEATURES_UNVERIFIED')


def _book(value, token, condition, now):
    if not isinstance(value, dict) or value.get('asset_id') != token or value.get('market') != condition:
        raise ValueError('BOOK_IDENTITY_MISMATCH')
    try:
        at = float(value['timestamp'])/1000
    except (KeyError, ValueError, TypeError):
        raise ValueError('BOOK_TIME_INVALID') from None
    if not math.isfinite(at) or not -.5 <= now-at <= 2:
        raise ValueError('BOOK_STALE')
    asks = value.get('asks')
    if not isinstance(asks, list):
        raise ValueError('INVALID_BOOK')
    levels = []
    for level in asks:
        if not isinstance(level, dict) or any(type(level.get(k)) not in (int, float, str) for k in ('price', 'size')):
            raise ValueError('INVALID_BOOK_LEVEL')
        try:
            price, size = float(level['price']), float(level['size'])
        except (ValueError, OverflowError):
            raise ValueError('INVALID_BOOK_LEVEL') from None
        if not math.isfinite(price) or not math.isfinite(size) or not 0 < price < 1 or size < 0:
            raise ValueError('INVALID_BOOK_LEVEL')
        if size:
            levels.append((price, size))
    return sorted(levels), at


def _fill(levels, shift=0., ceiling=1.):
    remaining, shares, fee, spent, used = 1., 0., 0., 0., []
    for price, size in levels:
        price += shift
        if price > ceiling or price >= 1:
            break
        take = min(size, remaining/price)
        shares += take
        cash = take*price
        spent += cash
        fee += .07*cash*(1-price)
        remaining -= cash
        used.append({'price': price, 'shares': take})
        if remaining < 1e-9:
            return {'shares': shares, 'priceCents': spent/shares*100, 'feeUsd': fee,
                    'worstAskCents': round(price*100, 2), 'levels': used}
    raise ValueError('INSUFFICIENT_PAPER_DEPTH')


def verify_entry(*, initial, final, start, now, first_observed_at, features, condition,
                 hour_condition, tokens, books, fee_schedule):
    """Pure final check. Input evidence, including book timestamps, must predate this decision."""
    _window(start, now)
    if not number(first_observed_at) or not start+150 <= first_observed_at <= now or now-first_observed_at > 5:
        raise ValueError('PAPER_PREPARATION_EXPIRED')
    initial = _snapshot(initial, start, first_observed_at)
    final = _snapshot(final, start, now)
    # The original sample remains subject to the same five-second lifetime as the real READY.
    if any(now-initial[group][key] > 5 for group, key in (
            ('preflight', 'checkedAt'), ('preflight', 'receivedAt'), ('signal', 'price_observed_at'))):
        raise ValueError('PAPER_PREPARATION_EXPIRED')
    if (final['preflight']['checkedAt'] < initial['preflight']['checkedAt']
            or final['signal']['price_observed_at'] < initial['signal']['price_observed_at']):
        raise ValueError('FUTURE_SNAPSHOT_REGRESSED')
    if final['signal']['open_price'] != initial['signal']['open_price']:
        raise ValueError('CHAINLINK_BASELINE_CHANGED')
    _features(features, start, now)
    if (not _fee_verified(fee_schedule)
            or not isinstance(tokens, list) or len(tokens) != 4 or len(set(tokens)) != 4
            or any(not isinstance(t, str) or not t.isdigit() for t in tokens)
            or not isinstance(books, list) or len(books) != 4
            or not isinstance(condition, str) or not re.fullmatch(r'0x[0-9a-f]{64}', condition)
            or not isinstance(hour_condition, str) or not re.fullmatch(r'0x[0-9a-f]{64}', hour_condition)
            or condition == hour_condition):
        raise ValueError('MARKET_INPUTS_UNVERIFIED')
    parsed = [_book(book, token, condition if i < 2 else hour_condition, now)
              for i, (book, token) in enumerate(zip(books, tokens))]
    fills = [_fill(levels) for levels, at in parsed]
    asks = [fill['worstAskCents'] for fill in fills]
    if asks[0] == asks[1] or asks[2] == asks[3]:
        raise ValueError('TIED_QUOTES')
    side = initial['preflight']['selectedSide']
    if final['preflight']['selectedSide'] != side or side != ('Up' if asks[0] > asks[1] else 'Down'):
        raise ValueError('FAVORITE_CHANGED')
    if side == ('Up' if asks[2] > asks[3] else 'Down'):
        raise ValueError('SAME_AS_1H')
    key = 'upQuoteCents' if side == 'Up' else 'downQuoteCents'
    prepared, page = initial['preflight'][key], final['preflight'][key]
    i = 0 if side == 'Up' else 1
    clob = asks[i]
    if any(not 60 <= p <= 97 for p in (prepared, page, clob)):
        raise ValueError('PRICE_GATE')
    if abs(round(page*100)-round(clob*100)) > 300:
        raise ValueError('FUTURE_CLOB_GAP_3C')
    if max(abs(round(p*100)-round(prepared*100)) for p in (page, clob)) > 500:
        raise ValueError('PRICE_DRIFT_5C')
    fill = fills[i]
    try:
        stress, stress_reason = _fill(parsed[i][0], shift=.01, ceiling=.97), None
    except ValueError as error:
        stress, stress_reason = None, str(error)
    trend, vol = features['trend60Bp'], features['volatilityBp']
    signed = (1 if side == 'Up' else -1)*math.log(final['signal']['current_price']/final['signal']['open_price'])*1e4
    g1, g2 = abs(trend) >= 15, abs(trend) < 5 or abs(trend) >= 15
    rules = [rule for rule, eligible in [('G1', g1), ('G2', g2), ('A', g2 and vol <= 3), ('B', g2 and signed > 0)] if eligible]
    return {'schemaVersion': 1, 'version': VERSION, 'paperOnly': True, 'backfilled': False,
            'periodStart': start, 'periodEnd': start+900, 'side': side, 'conditionId': condition,
            'amountUsd': 1, 'firstObservedAt': first_observed_at, 'verifiedAt': now,
            'preparedPriceCents': prepared, 'pagePriceCents': page, 'priceCents': fill['priceCents'],
            'worstAskCents': clob, 'shares': fill['shares'], 'feeUsd': fill['feeUsd'],
            'feeSource': 'MARKET_FEE_MODEL_AT_OBSERVATION', 'feeSchedule': fee_schedule,
            'actualFill': None, 'actualFeeUsd': None, 'quoteSource': 'FUTURE_PAGE_AND_CLOB_DEPTH',
            'futureQuoteVerified': True, 'execution': 'SIMULATED_DEPTH',
            'trend60Bp': trend, 'volatilityBp': vol, 'signedDistanceBp': signed, 'rules': rules,
            'adverseCentFill': stress, 'adverseCentReason': stress_reason,
            'evidence': {'preparationSource': 'PAPER_OBSERVATION', 'initial': initial, 'final': final,
                'featureObservedAt': features['observedAt'], 'lastCandleOpen': features['lastCandleOpen'],
                'tokens': tokens, 'hourConditionId': hour_condition, 'bookObservedAt': [at for _, at in parsed],
                'oneDollarWorstAskCents': asks, 'fillLevels': fill['levels']}}


class BtcForward:
    def __init__(self, storepath, read_bridge, public_get, now_fn=time.time):
        self.path, self.read_bridge, self.public_get, self.now_fn = str(storepath), read_bridge, public_get, now_fn
        self.cache, self.last_resolve = {}, 0.
        now = now_fn()
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS signals(start INTEGER PRIMARY KEY,payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS resolution_checks(start INTEGER PRIMARY KEY,checked_at REAL NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS trades(start INTEGER PRIMARY KEY,condition_id TEXT NOT NULL,payload TEXT NOT NULL,win INTEGER,pnl REAL,stress_pnl REAL,resolved_at REAL)')
            for key, value in [('version', VERSION), ('startedAt', now), ('rulesFrozenAt', now)]:
                db.execute('INSERT OR IGNORE INTO meta VALUES(?,?)', (key, json.dumps(value)))
            meta = {k: json.loads(v) for k, v in db.execute('SELECT key,value FROM meta')}
        if meta['version'] != VERSION:
            raise ValueError('FORWARD_RULE_VERSION_MISMATCH')
        self.started_at, self.rules_frozen_at = meta['startedAt'], meta['rulesFrozenAt']

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def _meta(self, key, value):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', (key, json.dumps(value, allow_nan=False)))

    def _market(self, slug, end, hourly=False):
        events = self.public_get('https://gamma-api.polymarket.com/events?' + urllib.parse.urlencode({'slug': slug}))
        if not isinstance(events, list):
            raise ValueError('MARKET_NOT_UNIQUE')
        matched = [e for e in events if isinstance(e, dict) and e.get('slug') == slug]
        if len(events) != 1 or len(matched) != 1 or not isinstance(matched[0].get('markets'), list) or len(matched[0]['markets']) != 1:
            raise ValueError('MARKET_NOT_UNIQUE')
        event = matched[0]
        if event.get('active') is not True or event.get('closed') is not False:
            raise ValueError('MARKET_NOT_ACTIVE_OR_WRONG_ROUND')
        market = event['markets'][0]
        start = end-(3600 if hourly else 900)
        if (not isinstance(market, dict) or market.get('closed') is not False or market.get('active') is not True
                or market.get('acceptingOrders') is not True or market.get('slug') != slug
                or _time(market['endDate']) != end
                or not hourly and _time(event['endDate']) != end
                or hourly and not market.get('eventStartTime')
                or market.get('eventStartTime') and _time(market['eventStartTime']) != start
                or not re.fullmatch(r'0x[0-9a-f]{64}', market.get('conditionId', ''))):
            raise ValueError('MARKET_NOT_ACTIVE_OR_WRONG_ROUND')
        if not hourly:
            config = market.get('cryptoMarketConfig')
            if (not isinstance(config, dict) or config.get('asset') != 'btc' or config.get('duration') != '15m'
                    or config.get('twapEnabled') is not True or config.get('twapLookbackSeconds') != 60):
                raise ValueError('WRONG_MARKET_PRICE_CONFIG')
        outcomes = json.loads(market['outcomes']) if isinstance(market['outcomes'], str) else market['outcomes']
        if outcomes != ['Up', 'Down']:
            raise ValueError('INVALID_TOKENS')
        tokens = json.loads(market['clobTokenIds']) if isinstance(market['clobTokenIds'], str) else market['clobTokenIds']
        if not isinstance(tokens, list) or len(tokens) != 2 or len(set(tokens)) != 2 or any(not isinstance(t, str) or not t.isdigit() for t in tokens):
            raise ValueError('INVALID_TOKENS')
        return market, tokens

    def _inputs(self, start):
        if start not in self.cache:
            hour = start//3600*3600
            market, tokens = self._market(f'btc-updown-15m-{start}', start+900)
            hour_market, hour_tokens = self._market(hourly_slug(hour), hour+3600, hourly=True)
            schedule = market.get('feeSchedule') or {}
            fee = {k: schedule.get(k) for k in ('rate', 'exponent', 'takerOnly')}
            if not _fee_verified(fee):
                raise ValueError('FEE_UNVERIFIED')
            url = 'https://data-api.binance.vision/api/v3/klines?' + urllib.parse.urlencode(
                {'symbol': 'BTCUSDT', 'interval': '1m', 'startTime': (start-3600)*1000,
                 'endTime': (start+60)*1000, 'limit': 62})
            candles = self.public_get(url)
            features = round_conditions(start, candles, self.now_fn())
            self.cache = {start: (market['conditionId'], hour_market['conditionId'], tokens+hour_tokens, features, fee)}
        return self.cache[start]

    def _observe(self, start):
        now = self.now_fn()
        if start+150 < self.started_at:
            return 'ENTRY_BEFORE_ENROLLMENT'
        if now < start+121:
            return 'WAITING_ENTRY_WINDOW'
        if now >= start+170:
            return 'ENTRY_WINDOW_CLOSED'
        condition, hour_condition, tokens, features, fee = self._inputs(start)
        now = self.now_fn()
        if now < start+150:
            return 'WAITING_ENTRY_WINDOW'
        _window(start, now)
        _features(features, start, now)
        with self.connect() as db:
            if db.execute('SELECT 1 FROM trades WHERE start=?', (start,)).fetchone():
                return 'PAPER_RECORDED'
            saved = db.execute('SELECT payload FROM signals WHERE start=?', (start,)).fetchone()
        if saved:
            preparation = json.loads(saved[0])
        else:
            raw = self.read_bridge('/bridge/status')
            observed = self.now_fn()
            initial = _snapshot(raw, start, observed)
            preparation = {'version': VERSION, 'periodStart': start, 'firstObservedAt': observed,
                           'rulesFrozenAt': self.rules_frozen_at, 'backfilled': False,
                           'preparationSource': 'PAPER_OBSERVATION', 'snapshot': initial}
            with self.connect() as db:
                db.execute('INSERT INTO signals VALUES(?,?)', (start, json.dumps(preparation, allow_nan=False)))
        if self.now_fn()-preparation['firstObservedAt'] > 5:
            raise ValueError('PAPER_PREPARATION_EXPIRED')
        def fetch(token):
            return self.public_get('https://clob.polymarket.com/book?' + urllib.parse.urlencode({'token_id': token}))
        with ThreadPoolExecutor(max_workers=4) as pool:
            books = list(pool.map(fetch, tokens))
        final = self.read_bridge('/bridge/status')
        row = verify_entry(initial=preparation['snapshot'], final=final, start=start,
                           now=self.now_fn(), first_observed_at=preparation['firstObservedAt'],
                           features=features, condition=condition, hour_condition=hour_condition,
                           tokens=tokens, books=books, fee_schedule=fee)
        row['rulesFrozenAt'] = self.rules_frozen_at
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO trades(start,condition_id,payload) VALUES(?,?,?)',
                       (start, condition, json.dumps(row, allow_nan=False)))
        return 'PAPER_RECORDED'

    def _resolve(self, now):
        with self.connect() as db:
            due = db.execute('''SELECT t.start,t.condition_id,t.payload FROM trades t
                LEFT JOIN resolution_checks c ON c.start=t.start
                WHERE t.win IS NULL AND t.start+960<=?
                ORDER BY COALESCE(c.checked_at,-1),t.start LIMIT 20''', (now,)).fetchall()
            # Mark the attempt before the request, including missing/failed responses.
            # Otherwise old unresolved markets can permanently starve newer settlements.
            db.executemany('INSERT OR REPLACE INTO resolution_checks VALUES(?,?)',
                           [(start, now) for start, _, _ in due])
        for i in range(0, len(due), 20):
            batch = due[i:i+20]
            by_condition = {condition: (start, json.loads(payload)) for start, condition, payload in batch}
            result = self.public_get('https://data-api.polymarket.com/v2/resolutions?' + urllib.parse.urlencode({'condition': ','.join(by_condition)}))
            if not isinstance(result, dict) or not isinstance(result.get('data'), list):
                raise ValueError('RESOLUTION_UNVERIFIED')
            seen, updates = set(), []
            for resolution in result['data']:
                if (not isinstance(resolution, dict) or resolution.get('condition_id') not in by_condition
                        or resolution['condition_id'] in seen):
                    raise ValueError('RESOLUTION_IDENTITY_MISMATCH')
                seen.add(resolution['condition_id'])
                if resolution.get('status') != 'resolved':
                    continue
                payout = resolution.get('payouts')
                if payout not in ([1000000, 0], [0, 1000000]) or any(type(p) is not int for p in payout):
                    raise ValueError('PAYOUT_UNVERIFIED')
                start, row = by_condition[resolution['condition_id']]
                win = row['side'] == ('Up' if payout[0] else 'Down')
                pnl = (row['shares'] if win else 0)-1-row['feeUsd']
                stress = row['adverseCentFill']
                stress_pnl = (stress['shares'] if win else 0)-1-stress['feeUsd'] if stress else None
                row['settlement'] = {'source': 'POLYMARKET_V2_RESOLUTIONS', 'conditionId': resolution['condition_id'],
                                     'status': 'resolved', 'payouts': payout, 'observedAt': now}
                updates.append((json.dumps(row, allow_nan=False), int(win), pnl, stress_pnl, now, start))
            # Validate every response identity/payout before committing any result.
            # A duplicate or foreign condition must not leave an earlier winner finalized.
            with self.connect() as db:
                db.executemany('UPDATE trades SET payload=?,win=?,pnl=?,stress_pnl=?,resolved_at=? WHERE start=? AND win IS NULL', updates)

    def tick(self):
        now = self.now_fn()
        start = int(now)//900*900
        try:
            reason = self._observe(start)
        except ValueError as error:
            reason = str(error)
        except Exception as error:
            reason = 'ENTRY_DATA_UNAVAILABLE:' + type(error).__name__
        self._meta('latest', {'periodStart': start, 'checkedAt': self.now_fn(), 'reason': reason})
        now = self.now_fn()
        # Settlement never competes with the short-lived Future/Chainlink entry evidence.
        # One bounded resolution batch outside this interval can catch up later.
        if not 120 <= now % 900 < 175 and now-self.last_resolve >= 30:
            self.last_resolve = now
            try:
                self._resolve(now)
                self._meta('resolveError', None)
            except Exception as error:
                self._meta('resolveError', str(error) if isinstance(error, ValueError) else type(error).__name__)
        self._meta('heartbeat', self.now_fn())

    def status(self, now):
        with self.connect() as db:
            meta = {k: json.loads(v) for k, v in db.execute('SELECT key,value FROM meta')}
            signal_count = db.execute('SELECT count(*) FROM signals').fetchone()[0]
            rows = [{**json.loads(payload), 'win': None if win is None else bool(win),
                     'netPnlUsd': pnl, 'netPnlWithExtraCentUsd': pnl-.01 if pnl is not None else None,
                     'netPnlWithAdverseCentUsd': stress, 'resolvedAt': at}
                    for payload, win, pnl, stress, at in db.execute('SELECT payload,win,pnl,stress_pnl,resolved_at FROM trades ORDER BY start DESC')]
        def stats(items, rule):
            settled = [r for r in items if r['win'] is not None]
            wins = sum(r['win'] for r in settled)
            pnl = sum(r['netPnlUsd'] for r in settled) if settled else None
            stressed = [r for r in settled if r['netPnlWithAdverseCentUsd'] is not None]
            return {'rule': rule, 'trades': len(items), 'pending': len(items)-len(settled),
                    'settled': len(settled), 'wins': wins, 'losses': len(settled)-wins,
                    'winRate': wins/len(settled) if settled else None, 'netPnlUsd': pnl,
                    'roiPerDollar': pnl/len(settled) if settled else None,
                    'netPnlWithExtraCentUsd': pnl-.01*len(settled) if pnl is not None else None,
                    'netPnlWithAdverseCentUsd': sum(r['netPnlWithAdverseCentUsd'] for r in stressed) if settled and len(stressed) == len(settled) else None,
                    'adverseCentVerifiedTrades': len(stressed)}
        baseline = stats(rows, 'BASELINE')
        strategies = []
        for rule in RULES:
            values = stats([r for r in rows if rule in r['rules']], rule)
            values.update(filteredWins=baseline['wins']-values['wins'], filteredLosses=baseline['losses']-values['losses'])
            strategies.append(values)
        heartbeat = meta.get('heartbeat')
        # The full two-snapshot and depth evidence stays in SQLite. Public rows are
        # deliberately bounded even when a simulated fill traverses many dust levels.
        public_fields = ('schemaVersion', 'version', 'paperOnly', 'backfilled', 'periodStart',
            'periodEnd', 'side', 'conditionId', 'amountUsd', 'firstObservedAt', 'verifiedAt',
            'rulesFrozenAt', 'preparedPriceCents', 'pagePriceCents', 'priceCents', 'worstAskCents',
            'shares', 'feeUsd', 'feeSource', 'feeSchedule', 'actualFill', 'actualFeeUsd',
            'quoteSource', 'futureQuoteVerified', 'execution', 'trend60Bp', 'volatilityBp',
            'signedDistanceBp', 'rules', 'adverseCentReason', 'win', 'netPnlUsd',
            'netPnlWithExtraCentUsd', 'netPnlWithAdverseCentUsd', 'resolvedAt', 'settlement')
        recent = [{key: row.get(key) for key in public_fields} for row in rows[:20]]
        return {'schemaVersion': 1, 'paperOnly': True, 'version': VERSION, 'startedAt': self.started_at,
                'rulesFrozenAt': self.rules_frozen_at, 'heartbeat': heartbeat,
                'fresh': number(heartbeat) and 0 <= now-heartbeat <= 30, 'latest': meta.get('latest'),
                'signalCount': signal_count, 'baseline': baseline, 'strategies': strategies,
                'recent': recent, 'resolutionSource': 'PLATFORM_PAYOUT', 'lastResolveError': meta.get('resolveError')}
