import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent))

from future_btc5m_backtest_export import build_rows, main, summary

START = 1791732600


def preparation(start, state, side="Down", up=46, down=55, **changes):
    return {"id": f"future-btc5m-prepare:{start}", "slug": f"btc-updown-5m-{start}", "periodStart": start,
            "state": state, "side": side, "upQuoteCents": up, "downQuoteCents": down,
            "quoteObservedAt": start + 61, "openPrice": 82000.0, "currentPrice": 82010.0,
            "createdAt": start + 61, "updatedAt": start + 62, "reason": None, **changes}


def audit(start, state="CLICK_ATTEMPTED", reason="PLATFORM_RESULT_UNKNOWN", at=None):
    at = at or start + 62.5
    return {"periodStart": start, "state": state, "reason": reason, "attemptedAt": at,
            "upQuoteCents": 45, "downQuoteCents": 56, "selectedSide": "Down", "extensionVersion": "0.4.1"}


class BacktestExportTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name)

    def write(self, name, rows):
        (self.path / name).write_text("".join(json.dumps(row) + "\n" for row in rows))

    def test_rounds_join_preparation_audit_resolution_and_fills_without_inventing_fills(self):
        self.write("preparations.jsonl", [
            preparation(START, "PENDING"), preparation(START, "CLAIMED"), preparation(START, "READY", updatedAt=START + 63),
            preparation(START + 300, "PENDING", side="Up", up=76, down=25),
            preparation(START + 300, "CLAIMED", side="Up", up=76, down=25),
            preparation(START + 300, "READY", side="Up", up=76, down=25),
            preparation(START + 600, "PENDING"), preparation(START + 600, "CLAIMED"),
            preparation(START + 600, "FAILED", reason="BUTTON_QUOTES_TIED"),
            preparation(START + 900, "PENDING"), preparation(START + 900, "CLAIMED"), preparation(START + 900, "READY"),
        ])
        self.write("buy_attempts.jsonl", [audit(START), audit(START + 300, "BLOCKED", "FINAL_CHECK_FAILED")])
        self.write("fills.jsonl", [{"periodStart": START, "platformOrderId": "order-1", "filledShares": 1.8,
                                    "avgFillPrice": 0.55, "feeUsd": 0.01, "source": "manual"}])
        outcomes = {f"btc-updown-5m-{START}": "Up", f"btc-updown-5m-{START + 300}": "Up",
                    f"btc-updown-5m-{START + 600}": "Down", f"btc-updown-5m-{START + 900}": None}
        rows = build_rows(self.path, lambda slug: outcomes[slug])
        by_start = {row["periodStart"]: row for row in rows}
        clicked = by_start[START]
        self.assertEqual(("READY", "CLICK_ATTEMPTED", 1, "Up", False), (clicked["preparationState"], clicked["buyState"],
                         clicked["buyAttempts"], clicked["resolvedOutcome"], clicked["won"]))
        self.assertEqual(START + 63, clicked["readyAt"])
        self.assertEqual((55, 56), (clicked["sideQuoteCents"], clicked["clickDownQuoteCents"]))
        self.assertEqual(-1, clicked["estPnlUsdAtQuote"])
        self.assertEqual(round(0 - (1.8 * 0.55 + 0.01), 6), clicked["realizedPnlUsd"])
        self.assertEqual("Up", clicked["chainlinkSide"])
        blocked = by_start[START + 300]
        self.assertEqual(("BLOCKED", "FINAL_CHECK_FAILED", 0, True), (blocked["buyState"], blocked["buyReason"],
                         blocked["buyAttempts"], blocked["won"]))
        self.assertAlmostEqual(100 / 76 - 1, blocked["estPnlUsdAtQuote"], places=6)
        self.assertIsNone(blocked["realizedPnlUsd"], "no fill row means no fill fact")
        self.assertEqual(("FAILED", "NOT_READY"), (by_start[START + 600]["preparationState"], by_start[START + 600]["buyState"]))
        self.assertEqual(("NO_AUDIT", None), (by_start[START + 900]["buyState"], by_start[START + 900]["won"]))
        totals = summary(rows)
        self.assertEqual({"rounds": 4, "ready": 3, "clickAttempts": 1, "blocked": 1, "readyWithoutAudit": 1,
                          "resolvedReady": 2, "readyWins": 1, "filledRounds": 1}, {key: totals[key] for key in (
                              "rounds", "ready", "clickAttempts", "blocked", "readyWithoutAudit",
                              "resolvedReady", "readyWins", "filledRounds")})
        cached = json.loads((self.path / "resolutions.json").read_text())
        self.assertNotIn(f"btc-updown-5m-{START + 900}", cached, "unresolved rounds are looked up again later")
        again = build_rows(self.path, lambda slug: self.fail("resolved rounds come from the cache") if slug in cached else None)
        self.assertEqual("Up", {row["periodStart"]: row for row in again}[START]["resolvedOutcome"])

    def test_cli_writes_csv_and_jsonl_and_can_skip_network(self):
        self.write("preparations.jsonl", [preparation(START, "PENDING"), preparation(START, "CLAIMED"),
                                          preparation(START, "READY")])
        out = self.path / "rounds.csv"
        self.assertEqual(0, main(["--state-dir", str(self.path), "--out", str(out), "--no-resolve"]))
        self.assertEqual("periodStart", out.read_text().split(",", 1)[0])
        self.assertEqual("NO_AUDIT", json.loads(out.with_suffix(".jsonl").read_text())["buyState"])
        self.assertFalse((self.path / "resolutions.json").exists())


if __name__ == "__main__":
    unittest.main()
