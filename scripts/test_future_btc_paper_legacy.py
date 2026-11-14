import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from future_btc_paper_legacy import BtcLegacy


START = 1791705600
CONDITION = '0x' + '1' * 64


def source(start=START, win=False, price=65):
    return {'periodStart': start, 'side': 'Up', 'priceCents': price, 'trend60Bp': 20.,
            'volatilityBp': 2.8, 'state': 'RESOLVED', 'win': win, 'roi': -1. if win is False else .5,
            'g1Eligible': True, 'g2Eligible': True, 'createdAt': start + 150}


def market(start=START, winner='Up', fee=True):
    slug = f'btc-updown-15m-{start}'
    row = {'slug': slug, 'conditionId': CONDITION, 'outcomes': '["Up","Down"]',
           'clobTokenIds': '["11","22"]', 'closed': winner is not None,
           'umaResolutionStatus': 'resolved' if winner else 'pending',
           'outcomePrices': json.dumps(['1', '0'] if winner == 'Up' else ['0', '1'] if winner == 'Down' else ['.5', '.5']),
           'endDate': datetime.fromtimestamp(start + 900, timezone.utc).isoformat(),
           'feeSchedule': {'rate': .07, 'exponent': 1, 'takerOnly': True} if fee else None}
    return [{'slug': slug, 'markets': [row]}]


class LegacyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'legacy.db'
        self.rows = [source()]
        self.gamma = market()
        self.resolutions = [{'condition_id': CONDITION, 'status': 'resolved', 'payouts': [1000000, 0]}]
        self.paths = []
        self.now = START + 2000

    def bridge(self, path):
        self.paths.append(path)
        query = parse_qs(urlsplit(path).query)
        page = int(query['page'][0])
        return {'list': copy.deepcopy(self.rows[(page-1)*100:page*100]), 'total': len(self.rows), 'page': page, 'size': 100}

    def public(self, url):
        if urlsplit(url).path == '/events':
            return copy.deepcopy(self.gamma)
        self.assertEqual(urlsplit(url).path, '/v2/resolutions')
        return {'data': copy.deepcopy(self.resolutions)}

    def observer(self):
        return BtcLegacy(self.path, self.bridge, self.public)

    def tick(self, observer):
        with patch('future_btc_paper_legacy.time.time', return_value=self.now):
            observer.tick()
        return observer.status(self.now)

    def test_platform_corrects_binance_loss_without_rewriting_source(self):
        observer = self.observer()
        state = self.tick(observer)
        self.assertEqual((state['total'], state['verified'], state['mismatches']), (1, 1, 1))
        row = state['recent'][0]
        self.assertFalse(row['originalWin'])
        self.assertTrue(row['correctedWin'])
        self.assertAlmostEqual(row['netPnlUsd'], 1/.65 - 1 - .07*.35)
        self.assertTrue(state['historical'])
        self.assertEqual(state['source'], 'LEGACY_PREPARE')
        self.assertEqual(row['feesFetchedAt'], self.now)
        with observer.connect() as db:
            raw = json.loads(db.execute('SELECT original FROM legacy').fetchone()[0])
        self.assertEqual(raw, source())
        self.assertTrue(all(p.startswith('/bridge/paper?page=') for p in self.paths))

    def test_unresolved_and_missing_fee_never_appear_as_zero_or_gross_profit(self):
        for winner, fee in [(None, True), ('Up', False)]:
            with self.subTest(winner=winner, fee=fee):
                self.path = Path(self.temp.name) / f'{winner}-{fee}.db'
                self.gamma = market(winner=winner, fee=fee)
                if winner is None:
                    self.resolutions = [{'condition_id': CONDITION, 'status': 'pending', 'payouts': None}]
                else:
                    self.resolutions = [{'condition_id': CONDITION, 'status': 'resolved', 'payouts': [1000000, 0]}]
                state = self.tick(self.observer())
                self.assertIsNone(state['baseline']['netPnlUsd'])
                self.assertIsNone(state['recent'][0]['netPnlUsd'])
                self.assertEqual(state['baseline']['settled'], int(winner is not None))

    def test_payout_must_agree_with_gamma_and_condition(self):
        for wrong in [dict(condition_id='0x'+'2'*64, status='resolved', payouts=[1000000, 0]),
                      dict(condition_id=CONDITION, status='resolved', payouts=[0, 1000000]),
                      dict(condition_id=CONDITION, status='resolved', payouts=[1, 0])]:
            with self.subTest(wrong=wrong):
                self.path = Path(self.temp.name) / (str(len(list(Path(self.temp.name).iterdir()))) + '.db')
                self.resolutions = [wrong]
                state = self.tick(self.observer())
                self.assertEqual(state['verified'], 0)
                self.assertIsNone(state['recent'][0]['correctedWin'])
                self.assertIsNotNone(state['lastError'])

    def test_failed_pagination_never_partially_imports_or_replaces_previous_snapshot(self):
        observer = self.observer()
        self.tick(observer)
        self.now += 61
        count = 0
        original = self.bridge
        def changing(path):
            nonlocal count
            count += 1
            value = original(path)
            if count > 1:
                value['total'] += 1
            return value
        observer.read_bridge = changing
        self.rows = [source(START+900), source()]
        state = self.tick(observer)
        self.assertEqual(state['total'], 1)
        self.assertEqual(state['lastError'], 'LEGACY_LEDGER_CHANGED_DURING_READ')
        self.now += 2
        self.assertEqual(self.tick(observer)['lastError'], 'LEGACY_LEDGER_CHANGED_DURING_READ')
        observer.read_bridge = self.bridge
        self.rows = [source()]
        self.now += 61
        self.assertIsNone(self.tick(observer)['lastError'])

    def test_duplicate_rounds_rejected_and_existing_identity_never_changed(self):
        self.rows = [source(), source()]
        observer = self.observer()
        state = self.tick(observer)
        self.assertEqual(state['total'], 0)
        self.rows = [source()]
        self.now += 61
        self.tick(observer)
        self.rows[0]['priceCents'] = 80
        self.now += 61
        state = self.tick(observer)
        self.assertEqual(state['recent'][0]['priceCents'], 65)
        self.assertEqual(state['lastError'], 'LEGACY_ENTRY_CHANGED')

    def test_restart_preserves_first_seen_and_price_gate_is_only_a_subset(self):
        self.rows[0]['priceCents'] = 59
        observer = self.observer()
        self.tick(observer)
        with observer.connect() as db:
            first_seen = db.execute('SELECT first_seen FROM legacy').fetchone()[0]
        self.now += 1
        restored = self.observer()
        again = restored.status(self.now)
        self.assertEqual(again['total'], 1)
        with restored.connect() as db:
            self.assertEqual(db.execute('SELECT first_seen FROM legacy').fetchone()[0], first_seen)
        self.assertEqual(again['priceEligibleStats']['baseline']['trades'], 0)
        self.assertIsNone(again['priceEligibleStats']['baseline']['netPnlUsd'])

    def test_wrong_market_round_or_outcome_order_is_not_settled(self):
        self.gamma[0]['markets'][0]['outcomes'] = '["Down","Up"]'
        state = self.tick(self.observer())
        self.assertEqual(state['verified'], 0)
        self.assertIsNone(state['recent'][0]['correctedWin'])

    def test_multiple_pages_are_complete_before_atomic_import(self):
        self.rows = [source(START + i*900) for i in range(101)][::-1]
        observer = self.observer()
        observer._sync(self.now)
        state = observer.status(self.now)
        self.assertEqual(state['total'], 101)
        self.assertEqual(state['recent'][-1]['periodStart'], START)
        self.assertEqual(self.paths, ['/bridge/paper?page=1&size=100',
                                     '/bridge/paper?page=2&size=100', '/bridge/paper?page=1&size=100'])
        self.assertIsNone(state['baseline']['netPnlUsd'])

    def test_final_metadata_change_is_reported_and_confirmed_receipt_retained(self):
        observer = self.observer()
        self.tick(observer)
        self.gamma = market(winner='Down')
        self.now += 3601
        state = self.tick(observer)
        self.assertEqual(state['lastError'], 'LEGACY_FINAL_RESULT_CHANGED')
        self.assertTrue(state['recent'][0]['correctedWin'])

    def test_updated_source_estimate_cannot_overwrite_first_observed_original(self):
        self.rows[0].update(state='PENDING', win=None, roi=None)
        observer = self.observer()
        self.tick(observer)
        self.rows[0].update(state='RESOLVED', win=False, roi=-1)
        self.now += 61
        state = self.tick(observer)
        self.assertFalse(state['recent'][0]['originalWin'])
        with observer.connect() as db:
            original = json.loads(db.execute('SELECT original FROM legacy').fetchone()[0])
        self.assertIsNone(original['win'])

    def test_two_thousand_rows_fit_bounded_observer_response(self):
        self.rows = [source(START + i*900, price=64.99999999999999) for i in range(2000)][::-1]
        observer = self.observer()
        observer._sync(self.now)
        with observer.connect() as db:
            metadata = {'feeRate': .07, 'feesFetchedAt': 1794664835.123456}
            payout = {'winner': 'Up', 'fetchedAt': 1794664840.123456}
            db.execute('UPDATE legacy SET market=?,payout=?', (json.dumps(metadata), json.dumps(payout)))
        state = observer.status(self.now)
        self.assertEqual(state['total'], 2000)
        self.assertEqual(state['baseline']['settled'], 2000)
        self.assertEqual(len(state['recent']), 2000)
        self.assertLess(len(json.dumps(state, ensure_ascii=False, allow_nan=False).encode()), 700_000)

    def test_missing_first_ten_payouts_do_not_starve_later_round_across_restart(self):
        self.rows = [source(START + i*900) for i in range(11)][::-1]
        self.now = START + 12000
        observer = self.observer()
        observer._sync(self.now)
        with observer.connect() as db:
            for i in range(11):
                metadata = {'conditionId': CONDITION if i == 0 else '0x' + format(i+1, '064x'), 'gammaWinner': 'Up',
                            'feeRate': .07, 'feesFetchedAt': self.now}
                db.execute('UPDATE legacy SET market=?,market_retry=? WHERE start=?',
                           (json.dumps(metadata), self.now+3600, START+i*900))
        requests = []
        def missing_first_ten(url):
            self.assertEqual(urlsplit(url).path, '/v2/resolutions')
            conditions = parse_qs(urlsplit(url).query)['condition'][0].split(',')
            requests.append(conditions)
            return {'data': self.resolutions if CONDITION in conditions else []}
        observer.public_get = missing_first_ten
        self.assertEqual(self.tick(observer)['verified'], 0)
        self.assertEqual(len(requests[0]), 10)
        self.now += 5
        observer = BtcLegacy(self.path, self.bridge, missing_first_ten)
        self.assertEqual(self.tick(observer)['verified'], 1)
        self.assertEqual(requests[1], [CONDITION])
        self.now += 5
        self.tick(observer)
        self.assertEqual(len(requests), 2)

    def test_resolution_error_remains_visible_during_retry_delay(self):
        observer = self.observer()
        available = False
        def unavailable(url):
            if urlsplit(url).path == '/v2/resolutions' and not available:
                raise OSError('fixture offline')
            return self.public(url)
        observer.public_get = unavailable
        self.assertEqual(self.tick(observer)['lastError'], 'LEGACY_PAYOUT_UNAVAILABLE')
        self.now += 5
        self.assertEqual(self.tick(observer)['lastError'], 'LEGACY_PAYOUT_UNAVAILABLE')
        available = True
        self.now += 61
        self.assertIsNone(self.tick(observer)['lastError'])

    def test_initial_source_failure_retries_after_five_seconds_then_refreshes_every_minute(self):
        observer = self.observer()
        available = False
        calls = []
        def reconnecting(path):
            calls.append(path)
            if not available:
                raise OSError('fixture source starting')
            return self.bridge(path)
        observer.read_bridge = reconnecting
        initial = self.tick(observer)
        self.assertIsNone(initial['fetchedAt'])
        self.assertEqual(initial['lastError'], 'LEGACY_LEDGER_UNAVAILABLE')
        available = True
        self.now += 4
        waiting = self.tick(observer)
        self.assertIsNone(waiting['fetchedAt'])
        self.assertEqual(waiting['lastError'], 'LEGACY_LEDGER_UNAVAILABLE')
        self.assertEqual(len(calls), 1)
        self.now += 1
        recovered = self.tick(observer)
        self.assertEqual(recovered['fetchedAt'], self.now)
        self.assertIsNone(recovered['lastError'])
        self.assertEqual(len(calls), 3)
        self.now += 59
        self.tick(observer)
        self.assertEqual(len(calls), 3)
        self.now += 1
        self.tick(observer)
        self.assertEqual(len(calls), 5)


if __name__ == '__main__':
    unittest.main()
