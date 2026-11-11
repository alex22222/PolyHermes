"""Forward-only ETH G1/G2 and SOL G1 observer. Public GETs and a separate paper ledger only."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
import http.server
import json
import math
from pathlib import Path
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from future_btc5m_conditions import round_conditions

ASSETS = {'ETH': 'ethereum', 'SOL': 'solana'}
RULES = {'ETH': ['G1', 'G2'], 'SOL': ['G1']}
PUBLIC = {'gamma-api.polymarket.com': {'/events'}, 'clob.polymarket.com': {'/book'},
          'data-api.binance.vision': {'/api/v3/klines'}, 'data-api.polymarket.com': {'/v2/resolutions'}}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('PUBLIC_REDIRECT_REJECTED')


def public_get(url):
    parts = urllib.parse.urlsplit(url)
    if (parts.scheme != 'https' or parts.username or parts.password or parts.port is not None or parts.fragment
            or parts.hostname not in PUBLIC or parts.path not in PUBLIC[parts.hostname]):
        raise ValueError('PUBLIC_GET_NOT_ALLOWED')
    request = urllib.request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'PolyHermesPaper/1'}, method='GET')
    with urllib.request.build_opener(NoRedirect).open(request, timeout=4) as response:
        data = response.read(2_000_001)
    if len(data) > 2_000_000:
        raise ValueError('PUBLIC_RESPONSE_TOO_LARGE')
    return json.loads(data)


def selected_rules(asset, trend):
    if asset not in RULES or not math.isfinite(trend):
        raise ValueError('INVALID_PAPER_ASSET_OR_TREND')
    return [r for r in RULES[asset] if abs(trend) >= 15 or r == 'G2' and abs(trend) < 5]


def levels(book, token, now):
    if book.get('asset_id') != token:
        raise ValueError('BOOK_TOKEN_MISMATCH')
    at = float(book['timestamp']) / 1000
    if not 0 <= now - at <= 15:
        raise ValueError('BOOK_STALE')
    asks = book['asks']
    if not asks:
        raise ValueError('EMPTY_BOOK')
    for level in asks:
        p, size = float(level['price']), float(level['size'])
        if not math.isfinite(p) or not math.isfinite(size) or not 0 < p < 1 or size <= 0:
            raise ValueError('INVALID_BOOK')
    return sorted(asks, key=lambda level: float(level['price']))


def simulate_fill(asks, amount):
    remaining = amount
    shares = fee = cash = 0.
    for level in sorted(asks, key=lambda r: float(r['price'])):
        p, size = float(level['price']), float(level['size'])
        if p > .97:
            break
        take = min(size, remaining / p)
        shares += take
        cash += take * p
        fee += .07 * take * p * (1 - p)
        remaining -= take * p
        if remaining < 1e-9:
            break
    if remaining > 1e-8 or shares <= 0:
        raise ValueError('INSUFFICIENT_PAPER_DEPTH')
    return {'shares': shares, 'priceCents': cash / shares * 100, 'feeUsd': fee}


def evaluate(*, asset, start, now, trend, volatility, quotes, tokens, condition, fee):
    if not start % 900 == 0 or not start + 150 <= now < start + 170:
        raise ValueError('OUTSIDE_ENTRY_WINDOW')
    if not math.isfinite(volatility) or not 0 <= volatility <= 4.16:
        raise ValueError('R1_HIGH_VOLATILITY')
    rules = selected_rules(asset, trend)
    if fee != .07 or len(quotes) != 4 or len(tokens) != 4:
        raise ValueError('INVALID_MARKET_INPUTS')
    books = [levels(b, token, now) for b, token in zip(quotes, tokens)]
    prices = [float(b[0]['price']) for b in books]
    if prices[0] == prices[1] or prices[2] == prices[3]:
        raise ValueError('TIED_QUOTES')
    side = 'Up' if prices[0] > prices[1] else 'Down'
    hour = 'Up' if prices[2] > prices[3] else 'Down'
    if side == hour:
        raise ValueError('SAME_AS_1H')
    i = 0 if side == 'Up' else 1
    if not .6 <= prices[i] <= .97:
        raise ValueError('PRICE_GATE')
    fill = simulate_fill(books[i], 1.)
    if abs(fill['priceCents'] / 100 - prices[i]) > .05 + 1e-10:
        raise ValueError('PRICE_DRIFT_5C')
    return {'asset': asset, 'periodStart': start, 'createdAt': now, 'side': side, 'conditionId': condition,
            'amountUsd': 1, 'trend60Bp': trend, 'volatilityBp': volatility, 'rules': rules,
            'paperOnly': True, 'quoteSource': 'CLOB_PUBLIC_BOOK', 'futureQuoteVerified': False,
            'execution': 'SIMULATED_DEPTH', **fill}


class Store:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS trades(asset TEXT,start INTEGER,condition_id TEXT,payload TEXT,win INTEGER,pnl REAL,resolved_at REAL,PRIMARY KEY(asset,start))')
            db.execute('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT)')
            db.execute('INSERT OR IGNORE INTO meta VALUES(?,?)', ('startedAt', json.dumps(time.time())))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def meta(self, key, value):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', (key, json.dumps(value, allow_nan=False)))

    def record(self, row):
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO trades(asset,start,condition_id,payload) VALUES(?,?,?,?)',
                       (row['asset'], row['periodStart'], row['conditionId'], json.dumps(row, allow_nan=False)))

    def contains(self, asset, start):
        with self.connect() as db:
            return db.execute('SELECT 1 FROM trades WHERE asset=? AND start=?', (asset, start)).fetchone() is not None

    def pending(self, now):
        with self.connect() as db:
            return [r[0] for r in db.execute('SELECT condition_id FROM trades WHERE win IS NULL AND start+960<=? ORDER BY start LIMIT 100', (now,))]

    def settle(self, condition, payout, now):
        if payout not in ([1000000, 0], [0, 1000000]):
            raise ValueError('PAYOUT_UNVERIFIED')
        winner = 'Up' if payout[0] else 'Down'
        with self.connect() as db:
            for asset, start, payload in db.execute('SELECT asset,start,payload FROM trades WHERE condition_id=? AND win IS NULL', (condition,)).fetchall():
                if now < start + 900:
                    raise ValueError('EARLY_SETTLEMENT')
                row = json.loads(payload)
                win = row['side'] == winner
                pnl = (row['shares'] if win else 0) - 1 - row['feeUsd']
                db.execute('UPDATE trades SET win=?,pnl=?,resolved_at=? WHERE asset=? AND start=?', (int(win), pnl, now, asset, start))

    def status(self, now):
        with self.connect() as db:
            meta = {k: json.loads(v) for k, v in db.execute('SELECT key,value FROM meta')}
            rows = [{**json.loads(p), 'win': None if win is None else bool(win), 'netPnlUsd': pnl,
                     'resolvedAt': at} for p, win, pnl, at in db.execute('SELECT payload,win,pnl,resolved_at FROM trades ORDER BY start DESC')]
        def stats(items, name):
            settled = [r for r in items if r['win'] is not None]
            wins = sum(r['win'] for r in settled)
            losses = len(settled) - wins
            pnl = sum(r['netPnlUsd'] for r in settled) if settled else None
            return {'rule': name, 'trades': len(items), 'pending': len(items)-len(settled), 'settled': len(settled),
                    'wins': wins, 'losses': losses, 'winRate': wins/len(settled) if settled else None,
                    'netPnlUsd': pnl, 'roiPerDollar': pnl/len(settled) if settled else None,
                    'netPnlWith1PctCostUsd': pnl-.01*len(settled) if pnl is not None else None}
        assets = []
        for asset in ASSETS:
            sample = [r for r in rows if r['asset'] == asset]
            baseline = stats(sample, 'BASELINE')
            strategies = []
            for rule in RULES[asset]:
                st = stats([r for r in sample if rule in r['rules']], rule)
                st['filteredLosses'] = baseline['losses']-st['losses']
                st['filteredWins'] = baseline['wins']-st['wins']
                strategies.append(st)
            assets.append({'asset': asset, 'baseline': baseline, 'strategies': strategies,
                           'latest': meta.get(asset), 'recent': sample[:20]})
        heartbeat = meta.get('heartbeat')
        return {'schemaVersion': 1, 'paperOnly': True, 'serverTime': now, 'startedAt': meta['startedAt'],
                'heartbeat': heartbeat, 'fresh': heartbeat is not None and 0 <= now-heartbeat <= 30,
                'futureQuoteVerified': False, 'quoteSource': 'CLOB_PUBLIC_BOOK', 'resolutionSource': 'PLATFORM_PAYOUT',
                'assets': assets, 'lastResolveError': meta.get('resolveError')}


class Observer:
    def __init__(self, store):
        self.store = store
        self.cache = {}
        self.last_resolve = 0

    def market(self, slug, end):
        events = public_get('https://gamma-api.polymarket.com/events?' + urllib.parse.urlencode({'slug': slug}))
        events = [e for e in events if e.get('slug') == slug]
        if len(events) != 1 or len(events[0]['markets']) != 1:
            raise ValueError('MARKET_NOT_UNIQUE')
        m = events[0]['markets'][0]
        if (datetime.fromisoformat(m['endDate'].replace('Z', '+00:00')).timestamp() != end or m.get('closed')
                or m.get('acceptingOrders') is not True or json.loads(m['outcomes']) != ['Up', 'Down']):
            raise ValueError('MARKET_NOT_ACTIVE_OR_WRONG_ROUND')
        tokens = json.loads(m['clobTokenIds'])
        if len(tokens) != 2 or len(set(tokens)) != 2:
            raise ValueError('INVALID_TOKENS')
        return m, tokens

    def inputs(self, asset, start):
        key = (asset, start)
        if key in self.cache:
            return self.cache[key]
        hour = start//3600*3600
        date = datetime.fromtimestamp(hour, ZoneInfo('America/New_York'))
        slug = f"{ASSETS[asset]}-up-or-down-{date.strftime('%B').lower()}-{date.day}-{date.year}-{date.hour%12 or 12}{'am' if date.hour<12 else 'pm'}-et"
        m, tokens = self.market(f'{asset.lower()}-updown-15m-{start}', start+900)
        hm, htokens = self.market(slug, hour+3600)
        schedule = m.get('feeSchedule') or {}
        if schedule.get('rate') != .07 or schedule.get('exponent') != 1 or schedule.get('takerOnly') is not True:
            raise ValueError('FEE_UNVERIFIED')
        url = 'https://data-api.binance.vision/api/v3/klines?' + urllib.parse.urlencode(
            {'symbol':asset+'USDT','interval':'1m','startTime':(start-3600)*1000,'endTime':(start+60)*1000,'limit':62})
        features = round_conditions(start, public_get(url), time.time())
        self.cache = {k:v for k,v in self.cache.items() if k[1] == start}
        self.cache[key] = (m, tokens+htokens, features, hm['conditionId'])
        return self.cache[key]

    def tick(self):
        now = time.time()
        start = int(now)//900*900
        for asset in ASSETS:
            if self.store.contains(asset, start):
                continue
            reason = 'WAITING_ENTRY_WINDOW'
            try:
                if 121 <= now-start < 170:
                    market, tokens, features, hour_condition = self.inputs(asset, start)
                    if features['volatilityBp'] > 4.16:
                        raise ValueError('R1_HIGH_VOLATILITY')
                    if now-start >= 150:
                        def fetch(token):
                            return public_get('https://clob.polymarket.com/book?' + urllib.parse.urlencode({'token_id':token}))
                        with ThreadPoolExecutor(max_workers=4) as pool:
                            books = list(pool.map(fetch, tokens))
                        # Every book must belong to the expected condition, not merely the token list.
                        if (any(b.get('market') != market['conditionId'] for b in books[:2])
                                or any(b.get('market') != hour_condition for b in books[2:])):
                            raise ValueError('BOOK_CONDITION_MISMATCH')
                        row = evaluate(asset=asset,start=start,now=time.time(),trend=features['trend60Bp'],
                            volatility=features['volatilityBp'],quotes=books,tokens=tokens,condition=market['conditionId'],fee=.07)
                        self.store.record(row)
                        reason = 'PAPER_RECORDED' if row['rules'] else 'FILTERED_BY_REQUESTED_RULES'
                elif now-start >= 170:
                    reason = 'ENTRY_WINDOW_CLOSED'
            except ValueError as error:
                reason = str(error)
            except Exception as error:
                reason = 'PUBLIC_DATA_UNAVAILABLE:' + type(error).__name__
            self.store.meta(asset, {'periodStart': start, 'checkedAt': time.time(), 'reason': reason})
        if now-self.last_resolve >= 30:
            self.last_resolve = now
            try:
                pending = self.store.pending(now)
                for i in range(0,len(pending),20):
                    cohort = pending[i:i+20]
                    data = public_get('https://data-api.polymarket.com/v2/resolutions?' + urllib.parse.urlencode({'condition':','.join(cohort)}))
                    for row in data['data']:
                        if row.get('condition_id') not in cohort:
                            raise ValueError('RESOLUTION_CONDITION_MISMATCH')
                        if row.get('status') == 'resolved':
                            self.store.settle(row['condition_id'], row.get('payouts'), now)
                self.store.meta('resolveError', None)
            except Exception as error:
                self.store.meta('resolveError', type(error).__name__)
        self.store.meta('heartbeat', time.time())


def serve(store, port):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in ('/status','/health'):
                self.send_error(404); return
            body = json.dumps(store.status(time.time()), allow_nan=False).encode()
            self.send_response(200); self.send_header('Content-Type','application/json')
            self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body)))
            self.end_headers(); self.wfile.write(body)
        def log_message(self, *args):
            pass
    server = http.server.ThreadingHTTPServer(('0.0.0.0',port),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir',type=Path,required=True)
    parser.add_argument('--port',type=int,default=8777)
    args = parser.parse_args()
    args.state_dir.mkdir(parents=True,exist_ok=True)
    store = Store(args.state_dir/'paper.db')
    serve(store,args.port)
    observer = Observer(store)
    while True:
        observer.tick()
        time.sleep(2 if 120 <= time.time()%900 < 175 else 5)


if __name__ == '__main__':
    main()
