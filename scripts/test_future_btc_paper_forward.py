import copy
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from future_btc_paper_forward import BtcForward, VERSION, verify_entry

S = 1791705600
C = '0x' + '1' * 64
H = '0x' + '2' * 64
TOKENS = ['11', '12', '21', '22']


def snapshot(at=S + 150, price=65, side='Up'):
    return {'bridgeId': 'future-btc5m', 'serverTime': at, 'series': '15m', 'periodStart': S,
            'requestedEnabled': False, 'feedStatus': 'CURRENT',
            'signal': {'id': f'15m:{S}', 'slug': f'btc-updown-15m-{S}', 'series': '15m',
                       'period_start': S, 'period_end': S+900, 'price_source': 'chainlink',
                       'open_price_source': 'polymarket_crypto_price_fifteen_twap60_openPrice',
                       'twap_lookback_seconds': 60, 'open_price': 80000., 'current_price': 80010.,
                       'price_observed_at': at, 'side': 'Up'},
            'preflight': {'mode': 'READ_ONLY', 'noSubmission': True, 'browserConnected': True,
                          'signalFresh': True, 'checkedAt': at, 'receivedAt': at,
                          'marketUrl': f'https://future.news/zh/event/btc-updown-15m-{S}',
                          'pagePeriodStart': S, 'navigation': 'CURRENT', 'ticketStatus': 'PASS',
                          'amountUsd': 1, 'selectedSide': side, 'buyButtonEnabled': True,
                          'upQuoteCents': price if side == 'Up' else 100-price,
                          'downQuoteCents': 100-price if side == 'Up' else price}}


def book(token, condition, price, at=S+151, size=100):
    return {'asset_id': token, 'market': condition, 'timestamp': str(at*1000),
            'asks': [{'price': str(price), 'size': str(size)}]}


def entry_inputs():
    return {'initial': snapshot(), 'final': snapshot(S+151), 'start': S, 'now': S+151,
            'first_observed_at': S+150, 'features': {'source': 'binance_btcusdt_1m',
                'periodStart': S, 'lastCandleOpen': S+60, 'observedAt': S+121,
                'trend60Bp': 20., 'volatilityBp': 3.},
            'condition': C, 'hour_condition': H, 'tokens': TOKENS,
            'books': [book('11', C, .65), book('12', C, .36), book('21', H, .40), book('22', H, .61)],
            'fee_schedule': {'rate': .07, 'exponent': 1, 'takerOnly': True}}


class EntryGatesTest(unittest.TestCase):
    def test_disabled_live_switch_still_paper_and_full_evidence(self):
        r = verify_entry(**entry_inputs())
        self.assertEqual(r['rules'], ['G1', 'G2', 'A', 'B'])
        self.assertTrue(r['paperOnly'])
        self.assertTrue(r['futureQuoteVerified'])
        self.assertIsNone(r['actualFill'])
        self.assertFalse(r['backfilled'])
        self.assertAlmostEqual(r['feeUsd'], .07 * .35)
        self.assertEqual(r['version'], VERSION)

    def test_strict_ticket_and_chainlink_evidence(self):
        for group, field, value in [('preflight', 'amountUsd', 2), ('preflight', 'selectedSide', 'Down'),
                ('preflight', 'buyButtonEnabled', False), ('preflight', 'ticketStatus', 'FAIL'),
                ('preflight', 'navigation', 'OLD'), ('preflight', 'checkedAt', S+140),
                ('signal', 'price_source', 'binance'), ('signal', 'twap_lookback_seconds', 0),
                ('signal', 'open_price_source', 'inferred'), ('signal', 'price_observed_at', S+140),
                ('signal', 'period_start', S-900)]:
            x = entry_inputs(); x['final'][group][field] = value
            with self.assertRaises(ValueError, msg=f'{group}.{field}'): verify_entry(**x)

    def test_baseline_cannot_change_between_preparation_and_verification(self):
        x = entry_inputs(); x['final']['signal']['open_price'] = 79999
        with self.assertRaisesRegex(ValueError, 'CHAINLINK_BASELINE_CHANGED'): verify_entry(**x)

    def test_window_freshness_and_identity(self):
        for change in ['late', 'early', 'stale_book', 'wrong_token', 'wrong_condition', 'hour_same', 'volatility']:
            x = entry_inputs()
            if change == 'late': x['now'] = S+170
            if change == 'early': x['now'] = S+149
            if change == 'stale_book': x['books'][0]['timestamp'] = str((S+148)*1000)
            if change == 'wrong_token': x['books'][0]['asset_id'] = 'wrong'
            if change == 'wrong_condition': x['books'][0]['market'] = H
            if change == 'hour_same': x['books'][2]['asks'][0]['price'] = '.8'
            if change == 'volatility': x['features']['volatilityBp'] = 4.161
            with self.assertRaises(ValueError, msg=change): verify_entry(**x)

    def test_price_gap_and_preparation_drift_are_independent(self):
        for prepared, final_price, book_price in [(59, 60, .60), (98, 97, .97), (65, 59, .60),
                                                   (65, 71, .71), (65, 65, .69), (65, 60, .59)]:
            x = entry_inputs(); x['initial'] = snapshot(price=prepared); x['final'] = snapshot(S+151, final_price)
            x['books'][0] = book('11', C, book_price)
            with self.assertRaises(ValueError, msg=str((prepared, final_price, book_price))): verify_entry(**x)
        x = entry_inputs(); x['final'] = snapshot(S+151, 70); x['books'][0] = book('11', C, .70)
        self.assertEqual(verify_entry(**x)['worstAskCents'], 70)

    def test_dust_uses_one_dollar_worst_level_not_best_or_average(self):
        x = entry_inputs()
        x['books'][2]['asks'] = [{'price': '.10', 'size': '.01'}, {'price': '.80', 'size': '100'}]
        with self.assertRaisesRegex(ValueError, 'SAME_AS_1H'): verify_entry(**x)
        x = entry_inputs()
        x['books'][0]['asks'] = [{'price': '.65', 'size': '1'}, {'price': '.75', 'size': '100'}]
        with self.assertRaises(ValueError): verify_entry(**x)

    def test_candidates_use_only_entry_features_and_chainlink_baseline(self):
        x = entry_inputs(); x['features']['trend60Bp'] = 10
        self.assertEqual(verify_entry(**x)['rules'], [])
        x['features']['trend60Bp'] = 3; x['features']['volatilityBp'] = 3.001
        x['final']['signal']['current_price'] = 79990; x['final']['signal']['side'] = 'Down'
        self.assertEqual(verify_entry(**x)['rules'], ['G2'])
        x['features']['volatilityBp'] = 3
        self.assertEqual(verify_entry(**x)['rules'], ['G2', 'A'])

    def test_boolean_fee_exponent_is_not_a_verified_numeric_fee(self):
        x = entry_inputs(); x['fee_schedule']['exponent'] = True
        with self.assertRaises(ValueError): verify_entry(**x)

    def test_unknown_stress_depth_is_not_zero(self):
        x = entry_inputs(); x['initial'] = snapshot(price=97); x['final'] = snapshot(S+151, 97)
        x['books'][0] = book('11', C, .97)
        r = verify_entry(**x)
        self.assertIsNone(r['adverseCentFill'])
        self.assertEqual(r['adverseCentReason'], 'INSUFFICIENT_PAPER_DEPTH')


class LifecycleTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.path = Path(self.temp.name)/'forward.db'
        self.clock = S+140; self.calls = []; self.snapshots = [snapshot(), snapshot(S+151)]
        self.observer = BtcForward(self.path, self.read_bridge, self.public_get, now_fn=lambda: self.clock)
        self.observer.cache = {S: (C, H, TOKENS, entry_inputs()['features'], entry_inputs()['fee_schedule'])}

    def tearDown(self): self.temp.cleanup()

    def read_bridge(self, path):
        self.assertEqual(path, '/bridge/status'); self.calls.append(path)
        value = self.snapshots.pop(0) if len(self.snapshots) > 1 else self.snapshots[0]
        self.clock = value['serverTime']
        return copy.deepcopy(value)

    def public_get(self, url):
        self.calls.append(url)
        parsed = urlsplit(url); args = parse_qs(parsed.query)
        if parsed.path == '/book':
            token = args['token_id'][0]
            return copy.deepcopy(entry_inputs()['books'][TOKENS.index(token)])
        if parsed.path == '/v2/resolutions':
            return {'data': [{'condition_id': C, 'status': 'resolved', 'payouts': [1000000, 0]}]}
        raise AssertionError(url)

    def test_forward_only_two_phases_idempotence_restart_and_actual_unknown(self):
        self.clock = S+150; self.observer.tick()
        self.clock = S+152; self.observer.tick()
        view = self.observer.status(self.clock)
        self.assertEqual(view['signalCount'], 1); self.assertEqual(view['baseline']['trades'], 1)
        self.assertIsNone(view['baseline']['netPnlUsd']); self.assertIsNone(view['recent'][0]['win'])
        frozen = view['rulesFrozenAt']
        again = BtcForward(self.path, self.read_bridge, self.public_get, now_fn=lambda: self.clock)
        self.assertEqual(again.status(self.clock)['rulesFrozenAt'], frozen)
        self.clock = S+1000; again.tick()
        settled = again.status(self.clock)
        self.assertEqual(settled['baseline']['settled'], 1)
        self.assertAlmostEqual(settled['baseline']['netPnlUsd'], 1/.65-1-.07*.35)
        self.assertAlmostEqual(settled['baseline']['netPnlWithExtraCentUsd'], 1/.65-1-.07*.35-.01)
        self.assertIsNone(settled['recent'][0]['actualFill'])
        self.assertEqual(settled['recent'][0]['firstObservedAt'], S+150)
        self.assertFalse(settled['recent'][0]['backfilled'])
        self.assertEqual(settled['recent'][0]['settlement']['payouts'], [1000000, 0])
        self.assertEqual(settled['recent'][0]['settlement']['conditionId'], C)
        before = len(self.calls); again.status(self.clock)
        self.assertEqual(len(self.calls), before)

    def test_old_round_cannot_backfill_or_enroll_after_entry(self):
        self.clock = S+175; self.observer.tick()
        self.assertEqual(self.observer.status(self.clock)['signalCount'], 0)
        with tempfile.TemporaryDirectory() as d:
            late = BtcForward(Path(d)/'new.db', self.read_bridge, self.public_get, now_fn=lambda: S+155)
            late.tick()
            self.assertEqual(late.status(S+155)['baseline']['trades'], 0)
            self.assertEqual(late.status(S+155)['latest']['reason'], 'ENTRY_BEFORE_ENROLLMENT')

    def test_changed_or_missing_payout_stays_unknown(self):
        self.clock = S+150; self.observer.tick(); self.clock = S+1000
        for payout in [[1, 0], [.5, .5], None]:
            self.observer.last_resolve = 0
            self.observer.public_get = lambda url, payout=payout: {'data': [{'condition_id': C, 'status': 'resolved', 'payouts': payout}]}
            self.observer.tick()
            self.assertIsNone(self.observer.status(self.clock)['baseline']['netPnlUsd'])

    def test_refused_execution_retains_signal_but_never_records_a_trade(self):
        self.snapshots[1]['preflight']['amountUsd'] = 2
        self.clock = S+150; self.observer.tick()
        view = self.observer.status(self.clock)
        self.assertEqual(view['signalCount'], 1)
        self.assertEqual(view['baseline']['trades'], 0)
        self.assertEqual(view['latest']['reason'], 'FUTURE_TICKET_UNVERIFIED')

    def test_foreign_resolution_never_settles_and_version_is_frozen(self):
        self.clock = S+150; self.observer.tick(); self.clock = S+1000
        self.observer.public_get = lambda url: {'data': [{'condition_id': H, 'status': 'resolved', 'payouts': [1000000, 0]}]}
        self.observer.tick()
        self.assertEqual(self.observer.status(self.clock)['baseline']['settled'], 0)
        self.assertEqual(self.observer.status(self.clock)['lastResolveError'], 'RESOLUTION_IDENTITY_MISMATCH')
        self.observer._meta('version', 'changed')
        with self.assertRaisesRegex(ValueError, 'FORWARD_RULE_VERSION_MISMATCH'):
            BtcForward(self.path, self.read_bridge, self.public_get, now_fn=lambda: self.clock)

    def test_resolutions_never_compete_with_entry_capture(self):
        self.clock = S+150; self.observer.tick()
        self.clock = S+900+145; self.observer.last_resolve = 0
        self.observer.cache = {S+900: (C, H, TOKENS, entry_inputs()['features'], entry_inputs()['fee_schedule'])}
        before = len(self.calls); self.observer.tick()
        self.assertFalse(any('/v2/resolutions' in call for call in self.calls[before:]))
        self.assertEqual(self.observer.status(self.clock)['baseline']['settled'], 0)

    def test_market_must_match_active_chainlink_twap_configuration(self):
        from datetime import datetime, timezone
        slug = f'btc-updown-15m-{S}'
        end = datetime.fromtimestamp(S+900, timezone.utc).isoformat()
        base = {'slug': slug, 'active': True, 'closed': False, 'endDate': end, 'markets': [{
            'slug': slug, 'active': True, 'closed': False, 'acceptingOrders': True, 'endDate': end,
            'eventStartTime': datetime.fromtimestamp(S, timezone.utc).isoformat(), 'conditionId': C,
            'outcomes': '["Up","Down"]', 'clobTokenIds': '["11","12"]',
            'cryptoMarketConfig': {'asset': 'btc', 'duration': '15m', 'twapEnabled': True, 'twapLookbackSeconds': 60}}]}
        self.observer.public_get = lambda url: [copy.deepcopy(base)]
        self.assertEqual(self.observer._market(slug, S+900)[1], ['11', '12'])
        for kind in ['asset', 'twap', 'duration', 'inactive_event', 'inactive_market', 'event_end', 'start']:
            bad = copy.deepcopy(base)
            if kind == 'asset': bad['markets'][0]['cryptoMarketConfig']['asset'] = 'eth'
            if kind == 'twap': bad['markets'][0]['cryptoMarketConfig']['twapEnabled'] = False
            if kind == 'duration': bad['markets'][0]['cryptoMarketConfig']['duration'] = '5m'
            if kind == 'inactive_event': bad['active'] = False
            if kind == 'inactive_market': bad['markets'][0]['active'] = False
            if kind == 'event_end': bad['endDate'] = '2020-01-01T00:00:00Z'
            if kind == 'start': bad['markets'][0]['eventStartTime'] = end
            self.observer.public_get = lambda url, bad=bad: [bad]
            with self.assertRaises(ValueError, msg=kind): self.observer._market(slug, S+900)

    def test_hour_market_uses_exact_hour_without_requiring_twap(self):
        from datetime import datetime, timezone
        from future_btc5m_series import hourly_slug
        hour = S//3600*3600; slug = hourly_slug(hour)
        end = datetime.fromtimestamp(hour+3600, timezone.utc).isoformat()
        market = {'slug': slug, 'active': True, 'closed': False, 'acceptingOrders': True,
                  'endDate': end, 'eventStartTime': datetime.fromtimestamp(hour, timezone.utc).isoformat(),
                  'conditionId': H, 'outcomes': ['Up', 'Down'], 'clobTokenIds': ['21', '22']}
        self.observer.public_get = lambda url: [{'slug': slug, 'active': True, 'closed': False, 'markets': [market]}]
        self.assertEqual(self.observer._market(slug, hour+3600, hourly=True)[1], ['21', '22'])
        del market['eventStartTime']
        with self.assertRaises(ValueError): self.observer._market(slug, hour+3600, hourly=True)

    def test_invalid_resolution_batch_cannot_partially_commit_a_winner(self):
        self.clock = S+150; self.observer.tick(); self.clock = S+1000
        valid = {'condition_id': C, 'status': 'resolved', 'payouts': [1000000, 0]}
        for invalid in [{'condition_id': C, 'status': 'resolved', 'payouts': [0, 1000000]},
                        {'condition_id': H, 'status': 'resolved', 'payouts': [1000000, 0]}]:
            self.observer.public_get = lambda url, invalid=invalid: {'data': [valid, invalid]}
            with self.assertRaisesRegex(ValueError, 'RESOLUTION_IDENTITY_MISMATCH'):
                self.observer._resolve(self.clock)
            self.assertEqual(self.observer.status(self.clock)['baseline']['settled'], 0)
            self.assertIsNone(self.observer.status(self.clock)['baseline']['netPnlUsd'])

    def test_pending_resolution_checks_rotate_persistently_without_starving_newer_rounds(self):
        with self.observer.connect() as db:
            for index in range(21):
                row = verify_entry(**entry_inputs())
                start = S+index*900
                row.update(periodStart=start, periodEnd=start+900, conditionId='0x'+f'{index+1:064x}')
                db.execute('INSERT INTO trades(start,condition_id,payload) VALUES(?,?,?)',
                           (start, row['conditionId'], json.dumps(row)))
        last_condition = '0x'+f'{21:064x}'
        cohorts = []
        def resolve(url):
            cohort = parse_qs(urlsplit(url).query)['condition'][0].split(',')
            cohorts.append(cohort)
            # The first twenty have no resolution receipt; omission is also an attempted check.
            return {'data': [{'condition_id': last_condition, 'status': 'resolved', 'payouts': [1000000, 0]}]
                    if last_condition in cohort else []}
        self.observer.public_get = resolve
        self.clock = S+21*900+200
        self.observer.tick()
        self.assertEqual(len(cohorts[0]), 20)
        self.assertNotIn(last_condition, cohorts[0])
        self.assertEqual(self.observer.status(self.clock)['baseline']['settled'], 0)
        self.clock += 31
        restarted = BtcForward(self.path, self.read_bridge, resolve, now_fn=lambda: self.clock)
        restarted.tick()
        self.assertIn(last_condition, cohorts[1])
        self.assertLessEqual(len(cohorts[1]), 20)
        stats = restarted.status(self.clock)['baseline']
        self.assertEqual(stats['settled'], 1)
        self.assertEqual(stats['pending'], 20)
        with restarted.connect() as db:
            self.assertEqual(db.execute('SELECT start FROM trades WHERE win IS NOT NULL').fetchall(), [(S+20*900,)])

    def test_public_recent_omits_large_depth_evidence_but_database_retains_it(self):
        self.clock = S+150; self.observer.tick()
        with self.observer.connect() as db:
            row = json.loads(db.execute('SELECT payload FROM trades WHERE start=?', (S,)).fetchone()[0])
            row['evidence']['fillLevels'] = row['evidence']['fillLevels']*30000
            row['adverseCentFill']['levels'] = row['adverseCentFill']['levels']*30000
            payload = json.dumps(row)
            self.assertGreater(len(payload), 1_000_000)
            db.execute('UPDATE trades SET payload=? WHERE start=?', (payload, S))
        view = self.observer.status(self.clock)
        recent = view['recent'][0]
        self.assertNotIn('evidence', list(recent))
        self.assertNotIn('adverseCentFill', list(recent))
        self.assertEqual(recent['version'], VERSION)
        self.assertIsNone(recent['actualFill'])
        self.assertEqual(recent['feeSource'], 'MARKET_FEE_MODEL_AT_OBSERVATION')
        self.assertLess(len(json.dumps(view)), 10_000)
        with self.observer.connect() as db:
            retained = json.loads(db.execute('SELECT payload FROM trades WHERE start=?', (S,)).fetchone()[0])
        self.assertEqual(len(retained['evidence']['fillLevels']), 30000)

    def test_no_sensitive_bridge_fields_in_saved_evidence(self):
        self.snapshots[0]['wallet'] = {'walletAddress': 'PRIVATE_WALLET'}
        self.snapshots[0]['preparation'] = {'lastAttempt': {'claimToken': 'SECRET_TOKEN'}}
        self.clock = S+150; self.observer.tick()
        with self.observer.connect() as db:
            text = '\n'.join(str(r) for r in db.iterdump())
        self.assertNotIn('SECRET_TOKEN', text); self.assertNotIn('PRIVATE_WALLET', text)


if __name__ == '__main__': unittest.main()
