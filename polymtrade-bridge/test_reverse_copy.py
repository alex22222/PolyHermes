import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

import main


class ReverseCopySignalTest(unittest.TestCase):
    def signal(self, outcome="Yes", price=0.30):
        return main.LeaderTradeSignal(
            timestamp=1,
            leaderAddress="0xleader",
            transactionHash="0xtx",
            conditionId="condition-1",
            marketSlug="btc-updown-15m-1784274000",
            side="BUY",
            outcome=outcome,
            outcomeIndex=0,
            price=price,
            size=2,
        )

    def test_reverse_copy_changes_yes_to_no_and_complements_price(self):
        signal, reason = main._signal_for_config(self.signal(), SimpleNamespace(reverse_copy=True))

        self.assertIsNone(reason)
        self.assertEqual("No", signal.outcome)
        self.assertEqual(1, signal.outcome_index)
        self.assertAlmostEqual(0.70, signal.price)

    def test_reverse_copy_changes_up_to_down(self):
        signal, reason = main._signal_for_config(
            self.signal(outcome="Up", price=0.62), SimpleNamespace(reverse_copy=True)
        )

        self.assertIsNone(reason)
        self.assertEqual("Down", signal.outcome)
        self.assertEqual(1, signal.outcome_index)
        self.assertAlmostEqual(0.38, signal.price)

    def test_reverse_copy_rejects_unknown_outcome(self):
        signal, reason = main._signal_for_config(
            self.signal(outcome="France"), SimpleNamespace(reverse_copy=True)
        )

        self.assertIsNone(signal)
        self.assertEqual("reverse copy unsupported outcome: France", reason)
