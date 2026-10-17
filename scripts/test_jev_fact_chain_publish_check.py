import hashlib
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent))

from jev_fact_chain_publish_check import validate_snapshot


def record(**changes):
    return {
        "schema_version": 1, "paper_only": True, "category": "finance",
        "market_slug": "fed-test", "status": "RULE_REVIEW_REQUIRED",
        "observed_at": "2026-09-26T03:00:00+00:00",
        "question": "Will the Fed raise rates?", "resolution_rules": "Resolves Yes after a rate hike.",
        "market_tags": ["economy", "fed"],
        "source": {
            "publisher": "federal_reserve_monetary",
            "source_url": "https://www.federalreserve.gov/example",
            "published_at": "2026-09-25T18:00:00+00:00",
            "retrieved_at": "2026-09-26T03:00:00+00:00",
            "content_sha256": "a" * 64, "text": "Official statement.",
        },
        **changes,
    }


class JevFactChainPublishCheckTest(unittest.TestCase):
    def test_valid_snapshot_reports_exact_file_hash_without_writing(self):
        raw = (json.dumps(record()) + "\n" + json.dumps(record(
            category="politics", market_slug="senate-test", question="Will the Senate confirm a nominee?",
            resolution_rules="Resolves Yes after Senate confirmation.", market_tags=["politics"],
            source=None,
        )) + "\n").encode()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.jsonl"
            path.write_bytes(raw)

            result = validate_snapshot(path)

            self.assertEqual({"records": 2, "finance": 1, "politics": 1,
                              "sha256": hashlib.sha256(raw).hexdigest()}, result)
            self.assertEqual(raw, path.read_bytes())

    def test_malformed_out_of_scope_and_sensitive_rows_stop_the_whole_publish(self):
        unsafe = (
            '{"schema_version":1,"paper_only":true,"category":"finance"\n',
            json.dumps(record(question="Will Bitcoin rise?")) + "\n",
            json.dumps(record(current_resolution_rules="Resolves on Bitcoin.")) + "\n",
            json.dumps(record(category="crypto")) + "\n",
            json.dumps(record(api_key="placeholder")) + "\n",
            json.dumps(record(paper_only=False)) + "\n",
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.jsonl"
            for row in unsafe:
                with self.subTest(row=row[:60]):
                    path.write_text(json.dumps(record()) + "\n" + row)
                    with self.assertRaises(ValueError):
                        validate_snapshot(path)

    def test_missing_timezone_and_partial_last_line_are_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.jsonl"
            undated = record()
            undated["source"]["published_at"] = "2026-09-25T18:00:00"
            path.write_text(json.dumps(undated) + "\n")
            with self.assertRaisesRegex(ValueError, "time zone"):
                validate_snapshot(path)

            path.write_text(json.dumps(record()))
            with self.assertRaisesRegex(ValueError, "newline"):
                validate_snapshot(path)

    def test_candidate_cannot_be_published_without_its_evidence_chain(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.jsonl"
            for candidate in (
                record(status="REVIEW_CANDIDATE", source=None),
                record(status="REVIEW_CANDIDATE", candidate_outcome="Yes",
                       source=None, jev={"model": "synthetic"}, quote={"shares": "20"}),
            ):
                with self.subTest(candidate=candidate):
                    path.write_text(json.dumps(candidate) + "\n")
                    with self.assertRaisesRegex(ValueError, "evidence chain"):
                        validate_snapshot(path)

    def test_incomplete_jev_scores_or_quote_cannot_be_published(self):
        candidate = record(
            status="REVIEW_CANDIDATE", candidate_outcome="Yes",
            rule_review={"complete": True, "evidence_verdict": "QUALIFIES",
                         "resolution_rules_sha256": hashlib.sha256(b"Resolves Yes after a rate hike.").hexdigest(),
                         "source_content_sha256": hashlib.sha256(b"Official statement.").hexdigest(),
                         "reviewed_by": "synthetic researcher", "reviewed_at": "2026-09-26T02:00:00+00:00",
                         "evidence_reason": "Synthetic fixture only."},
            rule_checks=[{"criterion": "A rate hike occurred", "rule_quote": "after a rate hike",
                          "evidence_quote": "Official statement.", "status": "CONFIRMED",
                          "reviewed_by": "synthetic researcher", "reviewed_at": "2026-09-26T02:00:00+00:00"}],
            jev_evidence=[{"text": "Official statement."}],
            jev={"scores": {"yes": 0.98, "no": 0.01, "ambiguous": 0.01}},
            quote={"shares": "20", "vwap": "0.6", "cost": "12", "fee": "0.01",
                   "gap_per_share": "0.39", "book_age_seconds": 1, "book_timestamp": "1",
                   "levels_used": [{"price": "0.6", "shares": "20"}]},
        )
        candidate["source"]["content_sha256"] = hashlib.sha256(candidate["source"]["text"].encode()).hexdigest()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.jsonl"
            path.write_text(json.dumps(candidate) + "\n")
            self.assertEqual(1, validate_snapshot(path)["records"])

            for field, missing in (("jev", "scores"), ("quote", "levels_used"), ("quote", "cost")):
                with self.subTest(field=field, missing=missing):
                    invalid = json.loads(json.dumps(candidate))
                    del invalid[field][missing]
                    path.write_text(json.dumps(invalid) + "\n")
                    with self.assertRaisesRegex(ValueError, "evidence chain"):
                        validate_snapshot(path)

            stale = json.loads(json.dumps(candidate))
            stale.update(status="RULE_REVIEW_REQUIRED", candidate_outcome=None,
                         current_resolution_rules="Resolves Yes after a rate hike. A later amendment applies.",
                         reason="Gamma question or resolution rules changed after Jev; review and rerun")
            del stale["quote"]
            path.write_text(json.dumps(stale) + "\n")
            self.assertEqual(1, validate_snapshot(path)["records"])

    def test_candidate_with_rejected_rule_or_broken_evidence_hash_is_rejected(self):
        candidate = record(
            status="REVIEW_CANDIDATE", candidate_outcome="Yes",
            rule_review={"complete": True, "evidence_verdict": "QUALIFIES",
                         "resolution_rules_sha256": hashlib.sha256(b"Resolves Yes after a rate hike.").hexdigest(),
                         "source_content_sha256": hashlib.sha256(b"Official statement.").hexdigest(),
                         "reviewed_by": "synthetic researcher", "reviewed_at": "2026-09-26T02:00:00+00:00",
                         "evidence_reason": "Synthetic fixture only."},
            rule_checks=[{"criterion": "A rate hike occurred", "rule_quote": "after a rate hike",
                          "evidence_quote": "Official statement.", "status": "CONFIRMED",
                          "reviewed_by": "synthetic researcher", "reviewed_at": "2026-09-26T02:00:00+00:00"}],
            jev_evidence=[{"text": "Official statement."}],
            jev={"scores": {"yes": 0.98, "no": 0.01, "ambiguous": 0.01}},
            quote={"shares": "20", "vwap": "0.6", "cost": "12", "fee": "0.01",
                   "gap_per_share": "0.39", "book_age_seconds": 1, "book_timestamp": "1",
                   "levels_used": [{"price": "0.6", "shares": "20"}]},
        )
        candidate["source"]["content_sha256"] = hashlib.sha256(candidate["source"]["text"].encode()).hexdigest()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.jsonl"
            path.write_text(json.dumps(candidate) + "\n")
            self.assertEqual(1, validate_snapshot(path)["records"])

            for field, value in (("rule_checks", [{**candidate["rule_checks"][0], "status": "REJECTED"}]),
                                 ("rule_checks", [{**candidate["rule_checks"][0], "rule_quote": "invented rule"}]),
                                 ("rule_review", {**candidate["rule_review"], "resolution_rules_sha256": "0" * 64}),
                                 ("source", {**candidate["source"], "content_sha256": "0" * 64})):
                with self.subTest(field=field, value=value):
                    invalid = {**candidate, field: value}
                    path.write_text(json.dumps(invalid) + "\n")
                    with self.assertRaisesRegex(ValueError, "evidence chain"):
                        validate_snapshot(path)


if __name__ == "__main__":
    unittest.main()
