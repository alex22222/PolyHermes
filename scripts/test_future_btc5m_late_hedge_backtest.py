import unittest

from future_btc5m_late_hedge_backtest import fill, quote, replay, summarize


def market(winner="Down", reverse_price=0.85, hedge_size=200):
    return {"start": 1790614200, "winner": winner, "feeSchedule": {"rate": 0.07}, "buys": [
        [59, 1, 0.70, 100], [61, 1, 0.70, 100],
        [219, 0, reverse_price, 200], [221, 0, reverse_price, hedge_size]]}


class LateHedgeTests(unittest.TestCase):
    def test_decision_cannot_use_same_second_or_future_prices(self):
        buys = [[59, 1, 0.70, 100], [60, 0, 0.99, 100]]
        self.assertAlmostEqual(quote(buys, 60), 0.70)
        self.assertIsNone(quote(buys, 66))

    def test_first_trigger_and_latency_are_causal_and_winner_does_not_change_action(self):
        loss = replay(market("Down"))
        recovery = replay(market("Up"))
        self.assertTrue(loss["hedged"])
        self.assertEqual(loss["triggerAt"], 220)
        self.assertEqual(loss["triggerAt"], recovery["triggerAt"])
        self.assertEqual(loss["hedgePrice"], recovery["hedgePrice"])
        self.assertAlmostEqual(loss["pnl"], 10 / 0.85 - 11 - 0.021 - 0.105)
        self.assertAlmostEqual(recovery["pnl"], 1 / 0.70 - 11 - 0.021 - 0.105)

    def test_above_90_91_cent_buy_can_lose_even_when_reverse_wins(self):
        row = replay(market(reverse_price=0.95))
        self.assertTrue(row["hedgeWon"])
        self.assertLess(row["pnl"], 0)

    def test_exact_80_cents_is_not_a_trigger(self):
        row = replay(market(reverse_price=0.80))
        self.assertIsNone(row["triggerAt"])
        self.assertFalse(row["hedged"])

    def test_incomplete_proxy_fill_is_not_invented_as_a_full_10_dollar_fill(self):
        row = replay(market(hedge_size=1))
        self.assertFalse(row["hedged"])
        self.assertEqual(row["hedgeBlocked"], "HEDGE_PROXY_LIQUIDITY_UNAVAILABLE")
        self.assertEqual(row["pnl"], row["baselinePnl"])

    def test_window_does_not_include_a_post_close_print(self):
        self.assertIsNone(fill([[300, 0, 0.85, 10000]], 0, 299, 10))

    def test_first_trigger_refusal_never_retries_on_later_lower_prices(self):
        round_data = market(reverse_price=0.95)
        round_data["buys"] += [[230, 0, 0.85, 10000], [231, 0, 0.85, 10000]]
        row = replay(round_data, max_reverse_price=0.90)
        self.assertEqual(row["triggerAt"], 220)
        self.assertEqual(row["hedgeBlocked"], "PRICE_CAP_AT_FIRST_TRIGGER")
        self.assertFalse(row["hedged"])

    def test_added_fees_decrease_both_legs_profit_and_nonloss_is_not_reverse_winrate(self):
        ordinary = replay(market())
        higher_fee = replay(market(), extra_fee=0.01)
        self.assertAlmostEqual(ordinary["pnl"] - higher_fee["pnl"], 0.11)
        rows = [replay(market(reverse_price=0.95)), replay(market(reverse_price=0.85))]
        self.assertTrue(all(row["hedgeWon"] for row in rows))
        result = summarize(rows)
        self.assertEqual(result["nonLossRate"], 0.5)
        self.assertEqual(result["deployedPrincipalUsd"], 22)


if __name__ == "__main__":
    unittest.main()
