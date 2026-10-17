import copy
import json
import unittest

from future_btc5m_path_audit import features, policy_candidate
from future_btc5m_path_fetch import boundaries, candles
from future_btc5m_late_hedge_backtest import replay


def seconds():
    return [[at, 100, 100, 100, 100, 1, 1] for at in range(-120, 300)]


def market(winner="Down"):
    return {"start": 0, "winner": winner, "feeSchedule": {"rate": 0.07},
            "buys": [[59, 1, .7, 100], [61, 1, .7, 100],
                     [219, 0, .85, 200], [221, 0, .95, 200], [222, 0, .85, 200]]}


class PathAuditTests(unittest.TestCase):
    def test_trigger_features_ignore_same_second_and_future_candles(self):
        data = seconds()
        for row in data:
            if 160 <= row[0] < 220:
                row[1:5] = [80] * 4
        before = features(data, 220, -1)
        changed = copy.deepcopy(data)
        for row in changed:
            if row[0] >= 220:
                row[1:5] = [10000] * 4
        self.assertEqual(before, features(changed, 220, -1))
        self.assertEqual(before["observedSecond"], 219)
        self.assertEqual(before["spotGapUsd"], 20)

    def test_trailing_twap_can_reject_spot_only_crossing(self):
        data = seconds()
        for row in data:
            if 160 <= row[0] < 219:
                row[1:5] = [110] * 4
            elif row[0] == 219:
                row[1:5] = [90] * 4
        value = features(data, 220, -1)
        self.assertGreater(value["spotGapUsd"], 0)
        self.assertLess(value["twapGapUsd"], 0)
        r = market()
        actual, reason = policy_candidate(r, replay(r), {"BTCUSDT": data}, "agreement")
        self.assertFalse(actual["hedged"])
        self.assertEqual(reason, "BTC_DIRECTION_OR_TWAP_MISMATCH")

    def test_sustained_agreement_rejects_a_single_second_confirmation(self):
        data = seconds()
        for row in data:
            if 160 <= row[0] < 220:
                row[1:5] = [90] * 4
            if row[0] == 218:
                row[1:5] = [110] * 4
        self.assertFalse(features(data, 220, -1)["sustainedAgreement10s"])

    def test_price_cap_never_uses_an_above_cap_print_even_if_average_would_pass(self):
        r = market()
        actual, reason = policy_candidate(r, replay(r), None, "cap90")
        self.assertTrue(actual["hedged"])
        self.assertAlmostEqual(actual["hedgePrice"], .85)
        self.assertIsNone(reason)

    def test_capped_fill_requires_a_full_ten_dollars_without_retry(self):
        r = market()
        r["buys"][-1][3] = 1
        r["buys"] += [[240, 0, .85, 10000]]
        actual, reason = policy_candidate(r, replay(r), None, "cap90")
        self.assertFalse(actual["hedged"])
        self.assertEqual(reason, "CAPPED_PROXY_FILL_UNAVAILABLE")
        self.assertEqual(actual["triggerAt"], 220)

    def test_settlement_winner_changes_payout_but_not_filter_or_fill(self):
        left, right = market("Down"), market("Up")
        a, ar = policy_candidate(left, replay(left), None, "cap90")
        b, br = policy_candidate(right, replay(right), None, "cap90")
        self.assertEqual(ar, br)
        self.assertEqual(a["hedged"], b["hedged"])
        self.assertEqual(a["hedgePrice"], b["hedgePrice"])
        self.assertNotEqual(a["pnl"], b["pnl"])

    def test_volatility_filter_uses_past_range_and_is_separate_from_direction_agreement(self):
        r, data = market(), seconds()
        accepted, reason = policy_candidate(r, replay(r), {"BTCUSDT": data}, "volatility10bp")
        self.assertTrue(accepted["hedged"])
        self.assertIsNone(reason)
        data[300][2] = 101  # Second 180 is inside the pre-trigger 60s window.
        rejected, reason = policy_candidate(r, replay(r), {"BTCUSDT": data}, "volatility10bp")
        self.assertFalse(rejected["hedged"])
        self.assertEqual(reason, "PRE60_VOLATILITY_ABOVE_10BP")

    def test_distance_filter_does_not_accept_a_gap_below_the_fixed_floor(self):
        r, data = market(), seconds()
        for row in data:
            if 159 <= row[0] < 220:
                row[1:5] = [80.01] * 4
        rejected, reason = policy_candidate(r, replay(r), {"BTCUSDT": data}, "distance")
        self.assertFalse(rejected["hedged"])
        self.assertEqual(reason, "BTC_MARGIN_TOO_SMALL_FOR_RECENT_NOISE")

    def test_missing_second_is_rejected_instead_of_interpolated(self):
        raw = [[at * 1000, 100, 100, 100, 100, 1, at * 1000 + 999, 0, 1]
               for at in range(-120, 300)]
        self.assertEqual(len(candles(raw, 0)), 420)
        del raw[100]
        with self.assertRaises(ValueError):
            candles(raw, 0)

    def test_public_prices_must_match_resolved_winner(self):
        event = {"slug": "btc-updown-5m-0", "closed": True,
                 "eventMetadata": {"priceToBeat": 100, "finalPrice": 99},
                 "markets": [{"outcomes": json.dumps(["Up", "Down"]),
                              "outcomePrices": json.dumps(["0", "1"])}]}
        self.assertEqual(boundaries(event, 0)["winner"], "Down")
        event["eventMetadata"]["finalPrice"] = 101
        with self.assertRaises(ValueError):
            boundaries(event, 0)


if __name__ == "__main__":
    unittest.main()
