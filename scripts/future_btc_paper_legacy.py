"""Read-only correction of legacy PREPARE estimates; never edits the assistant ledger.

Imported rows remain historical signals with unknown backfill provenance. Platform
payouts and current fee metadata are stored separately from the original estimate.
Neither a corrected label nor a 60--97 cent quote proves executable/live trading.
"""
from contextlib import contextmanager
from datetime import datetime
import json
import math
import re
import sqlite3
import time
import urllib.parse


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _stats(rows, rule):
    settled = [row for row in rows if row['correctedWin'] is not None]
    wins = sum(row['correctedWin'] for row in settled)
    costed = [row for row in settled if row['netPnlUsd'] is not None]
    net = sum(row['netPnlUsd'] for row in costed) if settled and len(costed) == len(settled) else None
    return {'rule': rule, 'trades': len(rows), 'pending': len(rows)-len(settled),
            'settled': len(settled), 'verified': len(settled), 'wins': wins, 'losses': len(settled)-wins,
            'winRate': wins/len(settled) if settled else None, 'feeVerifiedSettled': len(costed),
            'netPnlUsd': net, 'roiPerDollar': net/len(settled) if net is not None else None}


def _cohort(rows):
    baseline = _stats(rows, 'BASELINE')
    strategies = []
    for rule, field in [('G1', 'g1Eligible'), ('G2', 'g2Eligible')]:
        stats = _stats([row for row in rows if row[field]], rule)
        stats.update(filteredWins=baseline['wins']-stats['wins'], filteredLosses=baseline['losses']-stats['losses'])
        strategies.append(stats)
    return {'baseline': baseline, 'strategies': strategies}


class BtcLegacy:
    def __init__(self, path, read_bridge, public_get):
        self.path = str(path)
        self.read_bridge = read_bridge
        self.public_get = public_get
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS legacy(start INTEGER PRIMARY KEY,original TEXT NOT NULL,payload TEXT NOT NULL,first_seen REAL NOT NULL,market TEXT,market_at REAL,market_retry REAL,payout TEXT,payout_at REAL,error TEXT)')
            if 'payout_retry' not in {row[1] for row in db.execute('PRAGMA table_info(legacy)')}:
                db.execute('ALTER TABLE legacy ADD COLUMN payout_retry REAL')
            db.execute('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT)')
        self.next_refresh = 0

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
            db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', (key, _json(value)))

    def _fetch_ledger(self):
        def page(number):
            result = self.read_bridge(f'/bridge/paper?page={number}&size=100')
            if (not isinstance(result, dict) or type(result.get('total')) is not int
                    or not 0 <= result['total'] <= 2000 or result.get('page') != number
                    or result.get('size') != 100 or not isinstance(result.get('list'), list)
                    or len(result['list']) > 100):
                raise ValueError('LEGACY_LEDGER_INVALID')
            return result
        first = page(1)
        rows = list(first['list'])
        for number in range(2, (first['total']+99)//100+1):
            result = page(number)
            if result['total'] != first['total']:
                raise ValueError('LEGACY_LEDGER_CHANGED_DURING_READ')
            rows.extend(result['list'])
        if page(1) != first:
            raise ValueError('LEGACY_LEDGER_CHANGED_DURING_READ')
        if len(rows) != first['total']:
            raise ValueError('LEGACY_LEDGER_INCOMPLETE')
        for row in rows:
            if (not isinstance(row, dict) or type(row.get('periodStart')) is not int
                    or row['periodStart'] < 0 or row['periodStart'] % 900 or row.get('side') not in ('Up', 'Down')
                    or not _finite(row.get('priceCents')) or not 0 < row['priceCents'] < 100
                    or not _finite(row.get('trend60Bp')) or not _finite(row.get('volatilityBp'))
                    or row.get('win') is not None and type(row['win']) is not bool
                    or row.get('roi') is not None and not _finite(row['roi'])):
                raise ValueError('LEGACY_LEDGER_INVALID')
        if any(a['periodStart'] <= b['periodStart'] for a, b in zip(rows, rows[1:])):
            raise ValueError('LEGACY_LEDGER_ORDER_INVALID')
        return rows

    def _sync(self, now):
        rows = self._fetch_ledger()
        with self.connect() as db:
            saved = {start: json.loads(raw) for start, raw in db.execute('SELECT start,payload FROM legacy')}
            if not set(saved).issubset({row['periodStart'] for row in rows}):
                raise ValueError('LEGACY_LEDGER_SHRANK')
            identity = ('periodStart', 'side', 'priceCents', 'trend60Bp', 'volatilityBp', 'createdAt')
            for row in rows:
                previous = saved.get(row['periodStart'])
                if previous and any(previous.get(key) != row.get(key) for key in identity):
                    raise ValueError('LEGACY_ENTRY_CHANGED')
            for row in rows:
                encoded = _json(row)
                db.execute('INSERT OR IGNORE INTO legacy(start,original,payload,first_seen) VALUES(?,?,?,?)',
                           (row['periodStart'], encoded, encoded, now))
                db.execute('UPDATE legacy SET payload=? WHERE start=?', (encoded, row['periodStart']))
            db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', ('fetchedAt', _json(now)))

    def _fetch_market(self, start, now):
        slug = f'btc-updown-15m-{start}'
        url = 'https://gamma-api.polymarket.com/events?' + urllib.parse.urlencode({'slug': slug})
        events = self.public_get(url)
        if not isinstance(events, list):
            raise ValueError('LEGACY_MARKET_INVALID')
        matched = [event for event in events if isinstance(event, dict) and event.get('slug') == slug]
        if len(matched) != 1 or len(matched[0].get('markets', [])) != 1:
            raise ValueError('LEGACY_MARKET_NOT_UNIQUE')
        market = matched[0]['markets'][0]
        condition = market.get('conditionId')
        if (market.get('slug') != slug or not isinstance(condition, str)
                or re.fullmatch(r'0x[0-9a-fA-F]{64}', condition) is None
                or json.loads(market['outcomes']) != ['Up', 'Down']
                or datetime.fromisoformat(market['endDate'].replace('Z', '+00:00')).timestamp() != start+900):
            raise ValueError('LEGACY_MARKET_IDENTITY_INVALID')
        tokens = json.loads(market['clobTokenIds'])
        if (not isinstance(tokens, list) or len(tokens) != 2 or len(set(tokens)) != 2
                or any(not isinstance(token, str) or not token.isdigit() for token in tokens)):
            raise ValueError('LEGACY_MARKET_TOKENS_INVALID')
        prices = json.loads(market['outcomePrices'])
        gamma_winner = None
        if market.get('closed') is True and market.get('umaResolutionStatus') == 'resolved':
            if prices not in (['1', '0'], ['0', '1']):
                raise ValueError('LEGACY_GAMMA_PAYOUT_INVALID')
            gamma_winner = 'Up' if prices[0] == '1' else 'Down'
        schedule = market.get('feeSchedule') or {}
        fee_valid = (_finite(schedule.get('rate')) and schedule['rate'] == .07
                     and type(schedule.get('exponent')) is int and schedule['exponent'] == 1
                     and schedule.get('takerOnly') is True)
        return {'conditionId': condition, 'slug': slug, 'tokenIds': tokens, 'gammaWinner': gamma_winner,
                'feeRate': .07 if fee_valid else None, 'feesFetchedAt': now if fee_valid else None,
                'feeEvidence': 'CURRENT_METADATA_NOT_EXECUTION_RECEIPT', 'source': url, 'fetchedAt': now}

    def _markets(self, now):
        with self.connect() as db:
            pending = db.execute('SELECT start,market FROM legacy WHERE market_retry IS NULL OR market_retry<=? ORDER BY market_retry,start DESC LIMIT 5', (now,)).fetchall()
        errors = []
        for start, previous_raw in pending:
            try:
                market = self._fetch_market(start, now)
                previous = json.loads(previous_raw) if previous_raw else None
                if previous and (previous['conditionId'] != market['conditionId'] or previous['tokenIds'] != market['tokenIds']):
                    raise ValueError('LEGACY_MARKET_CHANGED')
                if previous and previous['gammaWinner'] and previous['gammaWinner'] != market['gammaWinner']:
                    raise ValueError('LEGACY_FINAL_RESULT_CHANGED')
                retry = now+3600 if market['gammaWinner'] and market['feeRate'] is not None else now+60
                with self.connect() as db:
                    db.execute('UPDATE legacy SET market=?,market_at=?,market_retry=?,error=NULL WHERE start=?',
                               (_json(market), now, retry, start))
            except Exception as error:
                code = str(error) if isinstance(error, ValueError) and str(error).startswith('LEGACY_') else 'LEGACY_MARKET_UNAVAILABLE'
                errors.append(code)
                with self.connect() as db:
                    db.execute('UPDATE legacy SET market_retry=?,error=? WHERE start=?', (now+60, code, start))
        return errors

    def _resolve(self, now):
        with self.connect() as db:
            candidates = [(start, json.loads(raw)) for start, raw in db.execute(
                'SELECT start,market FROM legacy WHERE market IS NOT NULL AND payout IS NULL AND start+960<=? '
                'AND (payout_retry IS NULL OR payout_retry<=?) ORDER BY payout_retry,start DESC', (now, now))]
        candidates = [(start, market) for start, market in candidates if market['gammaWinner'] is not None][:10]
        if not candidates:
            return False
        by_condition = {market['conditionId']: (start, market) for start, market in candidates}
        if len(by_condition) != len(candidates):
            raise ValueError('LEGACY_CONDITION_REUSED')
        # Persist before the request, including failures and missing receipts. Each
        # batch yields to never-checked rounds and cannot hammer the same ten rows.
        with self.connect() as db:
            for start, _ in candidates:
                db.execute('UPDATE legacy SET payout_retry=? WHERE start=?', (now+60, start))
        url = 'https://data-api.polymarket.com/v2/resolutions?' + urllib.parse.urlencode({'condition': ','.join(by_condition)})
        result = self.public_get(url)
        rows = result.get('data') if isinstance(result, dict) else None
        if not isinstance(rows, list):
            raise ValueError('LEGACY_PAYOUT_INVALID')
        updates, seen = [], set()
        for row in rows:
            condition = row.get('condition_id') if isinstance(row, dict) else None
            if condition not in by_condition or condition in seen:
                raise ValueError('LEGACY_PAYOUT_CONDITION_MISMATCH')
            seen.add(condition)
            if row.get('status') != 'resolved':
                continue
            payouts = row.get('payouts')
            if payouts not in ([1000000, 0], [0, 1000000]) or any(type(value) is not int for value in payouts):
                raise ValueError('LEGACY_PAYOUT_INVALID')
            winner = 'Up' if payouts[0] else 'Down'
            start, market = by_condition[condition]
            if winner != market['gammaWinner']:
                raise ValueError('LEGACY_PAYOUT_DISAGREES_WITH_GAMMA')
            updates.append((start, {'winner': winner, 'payouts': payouts, 'conditionId': condition,
                                   'source': url, 'fetchedAt': now, 'resolution': row}))
        with self.connect() as db:
            for start, payload in updates:
                db.execute('UPDATE legacy SET payout=?,payout_at=?,error=NULL WHERE start=? AND payout IS NULL',
                           (_json(payload), now, start))
        return True

    def tick(self):
        now = time.time()
        if now >= self.next_refresh:
            try:
                self._sync(now)
                self.next_refresh = now+60
                self._meta('ledgerError', None)
            except Exception as error:
                self.next_refresh = now+5
                self._meta('ledgerError', str(error) if isinstance(error, ValueError) and str(error).startswith('LEGACY_') else 'LEGACY_LEDGER_UNAVAILABLE')
        self._markets(now)
        try:
            if self._resolve(now):
                self._meta('resolveError', None)
        except Exception as error:
            self._meta('resolveError', str(error) if isinstance(error, ValueError) and str(error).startswith('LEGACY_') else 'LEGACY_PAYOUT_UNAVAILABLE')
        self._meta('heartbeat', time.time())

    def status(self, now):
        with self.connect() as db:
            meta = {key: json.loads(value) for key, value in db.execute('SELECT key,value FROM meta')}
            stored = db.execute('SELECT payload,first_seen,market,payout,error FROM legacy ORDER BY start DESC').fetchall()
        rows = []
        for raw, first_seen, market_raw, payout_raw, error in stored:
            source = json.loads(raw)
            market = json.loads(market_raw) if market_raw else None
            payout = json.loads(payout_raw) if payout_raw else None
            win = payout['winner'] == source['side'] if payout else None
            p = source['priceCents']/100
            fee = market['feeRate']*(1-p) if market and market['feeRate'] is not None else None
            net = (1/p if win else 0)-1-fee if win is not None and fee is not None else None
            trend = abs(source['trend60Bp'])
            rows.append({'periodStart': source['periodStart'], 'side': source['side'], 'priceCents': source['priceCents'],
                         'trend60Bp': source['trend60Bp'], 'volatilityBp': source['volatilityBp'],
                         'g1Eligible': trend >= 15, 'g2Eligible': trend < 5 or trend >= 15,
                         'originalWin': source.get('win'), 'originalRoi': source.get('roi'), 'correctedWin': win,
                         'win': win, 'netPnlUsd': net, 'feeUsd': fee, 'mismatch': win != source['win'] if win is not None and source.get('win') is not None else None,
                         'feesFetchedAt': market['feesFetchedAt'] if market else None,
                         'platformFetchedAt': payout['fetchedAt'] if payout else None,
                         'historical': True, 'backfilled': None, 'firstObservedAt': first_seen,
                         'source': 'LEGACY_PREPARE', 'executionVerified': False, 'error': error})
        result = _cohort(rows)
        at = meta.get('fetchedAt')
        # The UI polls the whole observer response. Keep per-row transport bounded;
        # complete source, metadata and payout evidence remain in SQLite.
        visible_fields = ('periodStart', 'side', 'priceCents', 'originalWin', 'originalRoi',
                          'correctedWin', 'netPnlUsd', 'mismatch', 'feesFetchedAt')
        return {'schemaVersion': 1, 'paperOnly': True, 'source': 'LEGACY_PREPARE', 'historical': True,
                'resolutionSource': 'PLATFORM_PAYOUT', 'feeEvidence': 'CURRENT_METADATA_NOT_EXECUTION_RECEIPT',
                'serverTime': now, 'fetchedAt': at, 'heartbeat': meta.get('heartbeat'),
                'fresh': at is not None and 0 <= now-at <= 120,
                'lastError': meta.get('ledgerError') or meta.get('resolveError') or next((row['error'] for row in rows if row['error']), None),
                'total': len(rows), 'verified': result['baseline']['settled'],
                'mismatches': sum(row['mismatch'] is True for row in rows), **result,
                'priceEligibleStats': _cohort([row for row in rows if 60 <= row['priceCents'] <= 97]),
                'recent': [{key: row[key] for key in visible_fields} for row in rows]}
