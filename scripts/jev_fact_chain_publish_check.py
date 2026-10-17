#!/usr/bin/env python3
"""Validate a Jev fact-chain JSONL file before any manual read-only publication."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any

from jev_fact_chain import check_rule_review, check_rules
from jev_shadow_monitor import CRYPTO_TERMS


SOURCE_HOSTS = {
    "federal_reserve_monetary": "www.federalreserve.gov",
    "white_house_presidential": "www.whitehouse.gov",
    "white_house_briefings": "www.whitehouse.gov",
    "senate_roll_call": "www.senate.gov",
}
SENSITIVE_FIELDS = re.compile(
    r"^(?:api_?key|typesafe_api_key|jev_key|secret|password|private_?key|authorization|access_?token|refresh_?token)$",
    re.IGNORECASE,
)
SENSITIVE_VALUES = re.compile(r"(?i)(?:bearer\s+[a-z0-9._-]{8,}|apikey_[a-z0-9_]{20,}|-----BEGIN PRIVATE KEY-----)")
SHA256 = re.compile(r"[0-9a-f]{64}")


def _timestamp(value: Any, line_number: int, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        raise ValueError(f"line {line_number}: {field} is not a valid timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"line {line_number}: {field} has no time zone")
    return parsed


def _has_sensitive_data(value: Any) -> bool:
    if isinstance(value, dict):
        return any(SENSITIVE_FIELDS.fullmatch(key) or _has_sensitive_data(item)
                   for key, item in value.items())
    if isinstance(value, list):
        return any(_has_sensitive_data(item) for item in value)
    return isinstance(value, str) and bool(SENSITIVE_VALUES.search(value))


def _complete_quote(quote: Any) -> bool:
    if not isinstance(quote, dict):
        return False
    fields = ("shares", "vwap", "cost", "fee", "gap_per_share", "book_timestamp")
    levels = quote.get("levels_used")
    return (all(isinstance(quote.get(field), str) and quote[field] for field in fields)
            and type(quote.get("book_age_seconds")) in (int, float)
            and isinstance(levels, list) and bool(levels)
            and all(isinstance(level, dict) and all(isinstance(level.get(field), str) and level[field]
                                                    for field in ("price", "shares")) for level in levels))


def validate_snapshot(path: Path) -> dict[str, str | int]:
    raw = path.read_bytes()
    if not raw or len(raw) > 20_000_000:
        raise ValueError("snapshot is empty or exceeds the 20 MB review limit")
    if not raw.endswith(b"\n"):
        raise ValueError("snapshot must end with a newline")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        raise ValueError("snapshot is not UTF-8") from None

    counts = {"finance": 0, "politics": 0}
    for line_number, line in enumerate(lines, 1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            raise ValueError(f"line {line_number}: malformed JSON") from None
        if not isinstance(record, dict):
            raise ValueError(f"line {line_number}: snapshot is not an object")
        if _has_sensitive_data(record):
            raise ValueError(f"line {line_number}: sensitive field or value present")
        if (type(record.get("schema_version")) is not int or record["schema_version"] != 1
                or record.get("paper_only") is not True):
            raise ValueError(f"line {line_number}: not a schema v1 read-only snapshot")
        category = record.get("category")
        if category not in counts:
            raise ValueError(f"line {line_number}: market is not politics or finance")
        slug = record.get("market_slug")
        if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
            raise ValueError(f"line {line_number}: market slug is invalid")
        observed = _timestamp(record.get("observed_at"), line_number, "observed_at")
        tags = record.get("market_tags", [])
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
            raise ValueError(f"line {line_number}: market tags are invalid")
        rule_document = record.get("rule_document")
        if rule_document is not None and not isinstance(rule_document, dict):
            raise ValueError(f"line {line_number}: rule document is invalid")
        market_text = " ".join(str(record.get(key) or "") for key in
                               ("market_slug", "question", "resolution_rules", "gamma_resolution_rules",
                                "current_question", "current_resolution_rules"))
        market_text += " " + " ".join(tags)
        if rule_document:
            market_text += " " + str(rule_document.get("text") or "")
        if CRYPTO_TERMS.search(market_text):
            raise ValueError(f"line {line_number}: crypto market content is out of scope")

        source = record.get("source")
        if source is not None:
            if not isinstance(source, dict) or source.get("publisher") not in SOURCE_HOSTS:
                raise ValueError(f"line {line_number}: source publisher is not approved")
            parsed_url = urllib.parse.urlparse(str(source.get("source_url") or ""))
            if parsed_url.scheme != "https" or parsed_url.hostname != SOURCE_HOSTS[source["publisher"]]:
                raise ValueError(f"line {line_number}: source URL is not official")
            published = _timestamp(source.get("published_at"), line_number, "source.published_at")
            retrieved = _timestamp(source.get("retrieved_at"), line_number, "source.retrieved_at")
            if published > retrieved or retrieved > observed:
                raise ValueError(f"line {line_number}: source chronology is inconsistent")
            if (not isinstance(source.get("text"), str) or not source["text"]
                    or not isinstance(source.get("content_sha256"), str)
                    or not SHA256.fullmatch(source["content_sha256"])):
                raise ValueError(f"line {line_number}: source evidence is incomplete")
        if (record.get("status") == "REVIEW_CANDIDATE" or record.get("jev") is not None or record.get("quote") is not None
                or record.get("candidate_outcome")):
            review = record.get("rule_review")
            checks = record.get("rule_checks")
            jev = record.get("jev")
            quote = record.get("quote")
            scores = jev.get("scores") if isinstance(jev, dict) else None
            rules = record.get("resolution_rules")
            if (source is None or not isinstance(review, dict) or review.get("complete") is not True
                    or review.get("evidence_verdict") != "QUALIFIES"
                    or not isinstance(rules, str) or not rules
                    or source["content_sha256"] != hashlib.sha256(source["text"].encode("utf-8")).hexdigest()
                    or (rule_document is not None and (not SHA256.fullmatch(str(rule_document.get("raw_sha256") or ""))
                        or rule_document.get("text_sha256") != hashlib.sha256(
                            str(rule_document.get("text") or "").encode("utf-8")).hexdigest()))
                    or not check_rule_review(review, rules, source, observed, rule_document)
                    or not check_rules(checks, rules, source, observed)
                    or any(check["status"] != "CONFIRMED" for check in checks)
                    or not isinstance(record.get("jev_evidence"), list) or not record["jev_evidence"]
                    or (jev is not None and (not isinstance(scores, dict)
                        or any(type(scores.get(field)) not in (int, float) for field in ("yes", "no", "ambiguous"))))
                    or (quote is not None and (jev is None or not _complete_quote(quote)))
                    or (record.get("status") == "REVIEW_CANDIDATE"
                        and (record.get("candidate_outcome") not in ("Yes", "No")
                             or jev is None or quote is None))):
                raise ValueError(f"line {line_number}: Jev or quote lacks its evidence chain")
        counts[category] += 1

    return {"records": len(lines), **counts, "sha256": hashlib.sha256(raw).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/jev-fact-chain.jsonl"))
    args = parser.parse_args()
    try:
        print(json.dumps(validate_snapshot(args.input), sort_keys=True))
    except (OSError, ValueError) as error:
        print(f"Jev snapshot is not publishable: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
