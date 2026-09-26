import sys
import json
import ssl
import unittest
from contextlib import redirect_stderr
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

from jev_shadow_probe import (
    check_jev,
    evaluate_candidate,
    load_api_key,
    parse_binary_market,
    run_case,
    simulate_buy,
)


NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


class JevShadowProbeTest(unittest.TestCase):
    def test_load_api_key_prefers_environment(self):
        with patch.dict("os.environ", {"TYPESAFE_API_KEY": " env-secret "}), patch("jev_shadow_probe.subprocess.run") as run:
            self.assertEqual("env-secret", load_api_key())
        run.assert_not_called()

    def test_load_api_key_reads_macos_keychain_without_printing_it(self):
        with patch.dict("os.environ", {}, clear=True), patch("jev_shadow_probe.sys.platform", "darwin"), patch(
            "jev_shadow_probe.subprocess.run", return_value=type("Result", (), {"returncode": 0, "stdout": "keychain-secret\n"})(),
        ) as run:
            self.assertEqual("keychain-secret", load_api_key())
        self.assertEqual(
            ["security", "find-generic-password", "-a", "typesafe", "-s", "polyhermes-jev-shadow", "-w"],
            run.call_args.args[0],
        )
        self.assertTrue(run.call_args.kwargs["capture_output"])

    def test_check_jev_makes_single_read_only_noul_request(self):
        captured = {}

        def fake_http(url, body=None, api_key=None):
            captured.update(url=url, body=body, api_key=api_key)
            return {"model": "jev-1.13.0", "answers": {"connected": {"type": "noul", "noul": 0.99}}, "usage": {"input_tokens": 10, "output_tokens": 2}}

        result = check_jev("secret", fake_http)

        self.assertEqual("jev-1.13.0", result["model"])
        self.assertEqual("https://api.typesafe.ai/v1/systemone", captured["url"])
        self.assertEqual("secret", captured["api_key"])
        self.assertEqual({"connected"}, set(captured["body"]["questions"]))
        self.assertNotIn("secret", str(result))

    def test_simulate_buy_uses_ask_depth_not_first_or_midpoint(self):
        book = {
            "timestamp": str(int(NOW.timestamp() * 1000)),
            "min_order_size": "1",
            "asks": [
                {"price": "0.60", "size": "8"},
                {"price": "0.40", "size": "4"},
            ],
        }

        quote = simulate_buy(book, Decimal("10"), Decimal("0.04"), NOW)

        self.assertEqual(Decimal("0.52"), quote["vwap"])
        self.assertEqual(Decimal("5.20"), quote["cost"])
        self.assertEqual(Decimal("0.0960"), quote["fee"])
        self.assertEqual(Decimal("0.4704"), quote["gap_per_share"])
        self.assertEqual([{"price": "0.40", "shares": "4"}, {"price": "0.60", "shares": "6"}], quote["levels_used"])

    def test_simulate_buy_rejects_stale_or_insufficient_book(self):
        stale = {"timestamp": str(int(NOW.timestamp() * 1000) - 60000), "min_order_size": "1", "asks": [{"price": "0.4", "size": "10"}]}
        thin = {"timestamp": str(int(NOW.timestamp() * 1000)), "min_order_size": "1", "asks": [{"price": "0.4", "size": "2"}]}

        with self.assertRaisesRegex(ValueError, "stale"):
            simulate_buy(stale, Decimal("10"), Decimal("0"), NOW)
        with self.assertRaisesRegex(ValueError, "depth"):
            simulate_buy(thin, Decimal("10"), Decimal("0"), NOW)

    def test_minimum_shares_and_dollar_notional_are_separate(self):
        book = {
            "timestamp": str(int(NOW.timestamp() * 1000)),
            "min_order_size": "5",
            "asks": [{"price": "0.10", "size": "20"}],
        }

        self.assertEqual(Decimal("2.00"), simulate_buy(book, Decimal("20"), Decimal("0"), NOW)["cost"])
        with self.assertRaisesRegex(ValueError, "notional"):
            simulate_buy({**book, "asks": [{"price": "0.01", "size": "20"}]}, Decimal("20"), Decimal("0"), NOW)

    def test_market_requires_open_binary_yes_no_and_known_fee(self):
        market = {
            "slug": "example-event",
            "conditionId": "0xabc",
            "question": "Will X happen?",
            "description": "Resolves Yes if X happens by the deadline.",
            "active": True,
            "closed": False,
            "acceptingOrders": True,
            "outcomes": '["Yes", "No"]',
            "clobTokenIds": '["yes-token", "no-token"]',
            "feesEnabled": True,
            "feeSchedule": {"rate": 0.04, "exponent": 1},
        }

        parsed = parse_binary_market(market)
        self.assertEqual("yes-token", parsed["tokens"]["Yes"])
        self.assertEqual(Decimal("0.04"), parsed["fee_rate"])
        with self.assertRaisesRegex(ValueError, "fee"):
            parse_binary_market({**market, "feeSchedule": None})
        with self.assertRaisesRegex(ValueError, "fee"):
            parse_binary_market({**market, "feeSchedule": {"rate": "not-a-number", "exponent": 1}})
        with self.assertRaisesRegex(ValueError, "binary"):
            parse_binary_market({**market, "outcomes": '["Up", "Down"]'})

    def test_candidate_needs_one_decisive_side_and_no_ambiguity(self):
        quote = {"gap_per_share": Decimal("0.25")}
        self.assertEqual("Yes", evaluate_candidate({"yes": 0.98, "no": 0.01, "ambiguous": 0.02}, {"Yes": quote}, Decimal("0.15")))
        self.assertIsNone(evaluate_candidate({"yes": 0.98, "no": 0.92, "ambiguous": 0.02}, {"Yes": quote}, Decimal("0.15")))
        self.assertIsNone(evaluate_candidate({"yes": 0.98, "no": 0.01, "ambiguous": 0.3}, {"Yes": quote}, Decimal("0.15")))
        self.assertIsNone(evaluate_candidate({"yes": 0.98, "no": 0.01, "ambiguous": 0.02}, {"Yes": {"gap_per_share": Decimal("0.1")}}, Decimal("0.15")))

    def test_http_request_uses_bearer_key_without_returning_it(self):
        from jev_shadow_probe import evaluate_jev

        captured = {}

        def fake_http(url, body=None, api_key=None):
            captured.update(url=url, body=body, api_key=api_key)
            return {
                "model": "jev-1.13.0",
                "answers": {
                    "yes": {"type": "noul", "noul": 0.97},
                    "no": {"type": "noul", "noul": 0.01},
                    "ambiguous": {"type": "noul", "noul": 0.02},
                },
            }

        result = evaluate_jev("Question", "Rules", [{"source_url": "https://example.org", "observed_at": "2026-09-23T11:00:00Z", "text": "Official result"}], "secret", fake_http)

        self.assertEqual({"yes": 0.97, "no": 0.01, "ambiguous": 0.02}, result["scores"])
        self.assertEqual("https://api.typesafe.ai/v1/systemone", captured["url"])
        self.assertEqual("secret", captured["api_key"])
        self.assertNotIn("secret", str(result))
        self.assertEqual("jev-latest", captured["body"]["model"])

    def test_http_client_sends_post_with_bearer_header(self):
        from jev_shadow_probe import http_json

        with patch("jev_shadow_probe.urllib.request.urlopen") as open_url:
            open_url.return_value.__enter__.return_value = BytesIO(b'{"answers":{}}')
            self.assertEqual({"answers": {}}, http_json("https://api.typesafe.ai/v1/systemone", {"model": "jev-latest"}, "secret"))
            request = open_url.call_args.args[0]
            context = open_url.call_args.kwargs["context"]

        self.assertEqual("POST", request.get_method())
        self.assertEqual("Bearer secret", request.get_header("Authorization"))
        self.assertEqual({"model": "jev-latest"}, json.loads(request.data))
        self.assertTrue(context.check_hostname)
        self.assertEqual(ssl.CERT_REQUIRED, context.verify_mode)

    def test_run_case_is_read_only_review_candidate(self):
        market = {
            "slug": "example-event",
            "conditionId": "0xabc",
            "question": "Will X happen?",
            "description": "Resolves Yes if X happens.",
            "active": True,
            "closed": False,
            "acceptingOrders": True,
            "outcomes": '["Yes", "No"]',
            "clobTokenIds": '["yes-token", "no-token"]',
            "feesEnabled": False,
        }
        book_time = str(int(NOW.timestamp() * 1000))
        calls = []

        def fake_http(url, body=None, api_key=None):
            calls.append((url, body, api_key))
            if "/markets/slug/" in url:
                return market
            if "yes-token" in url:
                return {"timestamp": book_time, "min_order_size": "1", "asks": [{"price": "0.60", "size": "20"}]}
            if "no-token" in url:
                return {"timestamp": book_time, "min_order_size": "1", "asks": [{"price": "0.99", "size": "20"}]}
            return {"model": "jev-1.13.0", "answers": {"yes": {"type": "noul", "noul": 0.98}, "no": {"type": "noul", "noul": 0.01}, "ambiguous": {"type": "noul", "noul": 0.01}}}

        result = run_case(
            {"market_slug": "example-event", "evidence": [{"source_url": "https://example.org", "observed_at": "2026-09-23T11:00:00Z", "text": "Official result"}]},
            "secret", Decimal("10"), Decimal("0.15"), NOW, fake_http,
        )

        self.assertEqual("REVIEW_CANDIDATE", result["status"])
        self.assertEqual("Yes", result["candidate_outcome"])
        self.assertFalse(result["evidence_source_verified"])
        self.assertTrue(result["paper_only"])
        self.assertNotIn("secret", str(result))
        self.assertEqual(4, len(calls))

    def test_run_case_does_not_call_jev_without_a_quote(self):
        market = {
            "conditionId": "0xabc", "question": "Will X happen?", "description": "Rules",
            "active": True, "closed": False, "acceptingOrders": True,
            "outcomes": '["Yes", "No"]', "clobTokenIds": '["yes-token", "no-token"]',
            "feesEnabled": False,
        }
        calls = []

        def fake_http(url, body=None, api_key=None):
            calls.append(url)
            if "/markets/slug/" in url:
                return market
            return {"timestamp": str(int(NOW.timestamp() * 1000) - 60000), "min_order_size": "1", "asks": [{"price": "0.5", "size": "20"}]}

        result = run_case(
            {"market_slug": "example-event", "evidence": [{"source_url": "https://example.org", "observed_at": "2026-09-23T11:00:00Z", "text": "Official result"}]},
            "secret", Decimal("10"), Decimal("0.15"), NOW, fake_http,
        )

        self.assertEqual("NO_ACTIONABLE_QUOTE", result["status"])
        self.assertEqual(3, len(calls))

    def test_missing_key_stops_before_network(self):
        from jev_shadow_probe import main

        with patch.dict("os.environ", {}, clear=True), patch.object(sys, "argv", ["jev_shadow_probe.py", "--input", "missing.json"]), redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as result:
                main()
        self.assertEqual(2, result.exception.code)

    def test_cli_appends_snapshot_without_key(self):
        from jev_shadow_probe import main

        with TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.json"
            output_path = Path(directory) / "snapshots.jsonl"
            input_path.write_text('[{"market_slug":"example-event","evidence":[]}]', encoding="utf-8")
            argv = ["jev_shadow_probe.py", "--input", str(input_path), "--output", str(output_path)]
            with patch.dict("os.environ", {"TYPESAFE_API_KEY": "secret"}), patch.object(sys, "argv", argv), patch("jev_shadow_probe.run_case") as run:
                run.return_value = {"market_slug": "example-event", "status": "NO_CANDIDATE", "paper_only": True}
                self.assertEqual(0, main())
            saved = output_path.read_text(encoding="utf-8")

        self.assertEqual("NO_CANDIDATE", json.loads(saved)["status"])
        self.assertNotIn("secret", saved)

    def test_cli_fails_when_every_market_is_skipped(self):
        from jev_shadow_probe import main

        with TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.json"
            output_path = Path(directory) / "snapshots.jsonl"
            input_path.write_text('[{"market_slug":"example-event","evidence":[]}]', encoding="utf-8")
            argv = ["jev_shadow_probe.py", "--input", str(input_path), "--output", str(output_path)]
            with patch.dict("os.environ", {"TYPESAFE_API_KEY": "secret"}), patch.object(sys, "argv", argv), patch("jev_shadow_probe.run_case") as run:
                run.side_effect = RuntimeError("Polymarket HTTP 503")
                self.assertEqual(1, main())
            saved = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual("SKIPPED", saved["status"])
        self.assertNotIn("secret", str(saved))


if __name__ == "__main__":
    unittest.main()
