import unittest

from future_btc5m_bankroll import Bankroll
from future_btc5m_late_hedge_backtest import replay


def candidate(start=0, winner="Down", hedge=True):
    buys = [[59, 1, 0.70, 100], [61, 1, 0.70, 100]]
    if hedge:
        buys += [[219, 0, 0.85, 200], [221, 0, 0.85, 200]]
    return replay({"start": start, "winner": winner, "feeSchedule": {"rate": 0.07}, "buys": buys})


class BankrollTests(unittest.TestCase):
    def test_cash_is_debited_for_both_legs_before_settlement_then_receives_one_winner(self):
        bank = Bankroll(100, hedge=True)
        row = bank.advance(0, candidate())
        self.assertAlmostEqual(row["minCashInRound"], 100 - 1.021 - 10.105)
        self.assertAlmostEqual(bank.cash, 100 + 10 / 0.85 - 11.126)
        self.assertAlmostEqual(row["pnl"], 10 / 0.85 - 11.126)
        self.assertTrue(row["hedged"])

    def test_insufficient_hedge_cash_keeps_original_position_and_never_borrows(self):
        bank = Bankroll(5, hedge=True)
        row = bank.advance(0, candidate())
        self.assertTrue(row["entered"])
        self.assertFalse(row["hedged"])
        self.assertEqual(row["cashBlock"], "INSUFFICIENT_HEDGE_FUNDS")
        self.assertAlmostEqual(bank.cash, 5 - 1.021)
        self.assertGreaterEqual(row["minCashInRound"], 0)

    def test_fees_can_block_a_one_dollar_entry_and_no_resizing_or_deposit_occurs(self):
        bank = Bankroll(1.01, hedge=True)
        row = bank.advance(0, candidate())
        self.assertFalse(row["entered"])
        self.assertEqual(row["cashBlock"], "INSUFFICIENT_ENTRY_FUNDS")
        self.assertEqual(bank.cash, 1.01)

    def test_delayed_winner_funds_cannot_pay_for_the_next_round_before_credit(self):
        bank = Bankroll(1.5, hedge=False, settlement_delay=600)
        first = bank.advance(0, candidate(winner="Up", hedge=False))
        self.assertAlmostEqual(first["equityEnd"], 1.5 + 1 / 0.70 - 1.021)
        self.assertLess(bank.cash, 1)
        middle = bank.advance(300, candidate(start=300, hedge=False))
        self.assertFalse(middle["entered"])
        bank.advance(600, candidate(start=600, hedge=False))
        later = bank.advance(900, candidate(start=900, hedge=False))
        self.assertTrue(later["entered"])

    def test_previous_payout_arriving_between_entry_and_hedge_is_available_at_hedge(self):
        bank = Bankroll(11.5, hedge=True, settlement_delay=200)
        bank.advance(0, candidate(winner="Up", hedge=False))
        row = bank.advance(300, candidate(start=300))
        self.assertTrue(row["hedged"])
        self.assertGreaterEqual(row["minCashInRound"], 0)

    def test_baseline_ignores_reverse_leg_but_preserves_exact_original_payout(self):
        bank = Bankroll(100, hedge=False)
        row = bank.advance(0, candidate())
        self.assertFalse(row["hedged"])
        self.assertAlmostEqual(row["pnl"], -1.021)
        self.assertAlmostEqual(bank.cash, 98.979)

    def test_extra_fee_is_charged_only_on_legs_actually_funded(self):
        bank = Bankroll(5, hedge=True, extra_fee=0.01)
        row = bank.advance(0, candidate())
        self.assertFalse(row["hedged"])
        self.assertAlmostEqual(row["fees"], 0.031)
        self.assertAlmostEqual(bank.cash, 5 - 1.031)

    def test_skipped_market_has_no_fee_and_receives_already_due_credit(self):
        bank = Bankroll(2, hedge=False, settlement_delay=60)
        bank.advance(0, candidate(winner="Up", hedge=False))
        row = bank.advance(300, {"skip": "ENTRY_PRICE_OUTSIDE_60_97"})
        self.assertFalse(row["entered"])
        self.assertEqual(row["fees"], 0)
        self.assertAlmostEqual(bank.cash, 2 + 1 / 0.70 - 1.021)


if __name__ == "__main__":
    unittest.main()
