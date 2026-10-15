import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from future_btc5m_bridge import FutureBridge
import future_btc5m_bridge

# These suites cover the original 5m strategy; the 15m default is tested separately.
future_btc5m_bridge.DEFAULT_STRATEGY = "btc5m_favorite"
from test_future_btc5m_bridge import START, browser_report, source


class WalletReportTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.now = START + 65
        self.bridge = FutureBridge(Path(directory.name), lambda: source(self.now), lambda: self.now)
        self.wallet = '0x' + 'a' * 40

    def report(self, **changes):
        return browser_report(self.now, **{'schemaVersion': 3, 'walletAddress': self.wallet, 'cashUsd': 22.12, **changes})

    def test_wallet_report_is_independent_from_preparation_permission_and_does_not_create_orders(self):
        state = self.bridge.report_preflight(self.report())
        self.assertEqual(22.12, state['wallet']['cashUsd'])
        self.assertEqual(self.wallet, state['wallet']['walletAddress'])
        self.assertTrue(state['wallet']['fresh'])
        self.assertFalse(state['requestedEnabled'])
        self.assertEqual(0, state['orderCounts']['total'])

    def test_stale_cash_becomes_unknown_and_legacy_preparation_reports_do_not_refresh_it(self):
        self.bridge.report_preflight(self.report(cashUsd=0))
        self.assertEqual(0, self.bridge.status()['wallet']['cashUsd'])
        self.now += 16
        self.bridge.report_preflight(browser_report(self.now))
        state = self.bridge.status()['wallet']
        self.assertFalse(state['fresh'])
        self.assertIsNone(state['cashUsd'])

    def test_logout_clears_previous_wallet_and_cash(self):
        self.bridge.report_preflight(self.report())
        self.now += 1
        state = self.bridge.report_preflight(self.report(walletAddress=None, cashUsd=None))
        self.assertIsNone(state['wallet'])

    def test_malformed_cash_or_wallet_is_not_accepted(self):
        for changes in ({'cashUsd': -1}, {'cashUsd': float('nan')}, {'cashUsd': True},
                        {'walletAddress': '0xabc'}, {'walletAddress': None, 'cashUsd': 1}):
            with self.assertRaises(ValueError):
                self.bridge.report_preflight(self.report(**changes))

    def test_wallet_report_keeps_existing_higher_quote_preparation_contract(self):
        self.bridge.control(True)
        self.now += 1
        self.bridge.report_preflight(self.report(upQuoteCents=12, downQuoteCents=88))
        state = self.bridge.observe()['preparation']
        self.assertEqual('PENDING', state['state'])
        self.assertEqual('Down', state['intent']['side'])
        self.assertEqual(2, state['intent']['schemaVersion'])
        self.assertNotIn('walletAddress', state['intent'])
        claimed = self.bridge.claim_preparation({'schemaVersion': 1, 'id': state['intent']['id']})
        self.assertEqual('CLAIMED', claimed['preparation']['state'])


if __name__ == '__main__':
    unittest.main()
