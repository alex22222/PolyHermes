#!/usr/bin/env python3
"""Read-only Jev/Polymarket evidence-price disagreement probe."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable


GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"
JEV_URL = "https://api.typesafe.ai/v1/systemone"
USER_AGENT = "PolyHermes-Jev-Shadow/0.1"
KEYCHAIN_SERVICE = "polyhermes-jev-shadow"
KEYCHAIN_ACCOUNT = "typesafe"
MAX_BOOK_AGE_SECONDS = 30
MIN_MARKET_BUY_NOTIONAL = Decimal("1")
MIN_DECISIVE_SCORE = 0.95
MAX_OPPOSITE_SCORE = 0.05


def load_api_key() -> str | None:
    api_key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if api_key:
        return api_key
    if sys.platform != "darwin":
        return None
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-a", KEYCHAIN_ACCOUNT, "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def http_json(url: str, body: dict[str, Any] | None = None, api_key: str | None = None) -> Any:
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    if api_key is not None:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        try:
            import certifi
        except ImportError:
            context = ssl.create_default_context()
        else:
            context = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(request, timeout=15, context=context) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        service = "Jev" if api_key is not None else "Polymarket"
        raise RuntimeError(f"{service} HTTP {error.code}") from None


def parse_binary_market(market: dict[str, Any]) -> dict[str, Any]:
    if market.get("active") is not True or market.get("closed") is not False or market.get("acceptingOrders") is not True:
        raise ValueError("market is not open for orders")
    if not market.get("question") or not market.get("description") or not market.get("conditionId"):
        raise ValueError("market question, rules, or condition ID missing")
    outcomes = market.get("outcomes")
    tokens = market.get("clobTokenIds")
    try:
        outcomes = json.loads(outcomes) if isinstance(outcomes, str) else outcomes
        tokens = json.loads(tokens) if isinstance(tokens, str) else tokens
    except (TypeError, json.JSONDecodeError):
        raise ValueError("invalid binary outcome/token mapping") from None
    if outcomes != ["Yes", "No"] or not isinstance(tokens, list) or len(tokens) != 2 or not all(tokens):
        raise ValueError("only binary Yes/No markets are supported")

    fees_enabled = market.get("feesEnabled")
    if fees_enabled is False:
        fee_rate = Decimal("0")
    elif fees_enabled is True:
        schedule = market.get("feeSchedule")
        if not isinstance(schedule, dict) or schedule.get("exponent") != 1 or schedule.get("rate") is None:
            raise ValueError("market fee schedule is missing or unsupported")
        try:
            fee_rate = Decimal(str(schedule["rate"]))
        except InvalidOperation:
            raise ValueError("market fee rate is invalid") from None
        if not fee_rate.is_finite() or not Decimal("0") <= fee_rate <= Decimal("1"):
            raise ValueError("market fee rate is invalid")
    else:
        raise ValueError("market fee status is unknown")

    return {"tokens": dict(zip(outcomes, tokens)), "fee_rate": fee_rate}


def simulate_buy(book: dict[str, Any], shares: Decimal, fee_rate: Decimal, now: datetime) -> dict[str, Decimal | int]:
    if not shares.is_finite() or shares <= 0:
        raise ValueError("shares must be positive")
    try:
        book_time = datetime.fromtimestamp(int(book["timestamp"]) / 1000, timezone.utc)
        min_order_size = Decimal(str(book["min_order_size"]))
    except (KeyError, ValueError, TypeError, OverflowError, InvalidOperation):
        raise ValueError("book timestamp or minimum order size missing") from None
    if not min_order_size.is_finite() or min_order_size <= 0:
        raise ValueError("invalid minimum order size")
    age_seconds = (now - book_time).total_seconds()
    if age_seconds > MAX_BOOK_AGE_SECONDS or age_seconds < -5:
        raise ValueError("stale or future order book")

    levels = []
    for level in book.get("asks", []):
        try:
            price = Decimal(str(level["price"]))
            size = Decimal(str(level["size"]))
        except (KeyError, TypeError, InvalidOperation):
            raise ValueError("invalid ask level") from None
        if not price.is_finite() or not size.is_finite() or not Decimal("0") < price < Decimal("1") or size <= 0:
            raise ValueError("invalid ask level")
        levels.append((price, size))

    remaining = shares
    cost = Decimal("0")
    fee = Decimal("0")
    levels_used = []
    for price, size in sorted(levels):
        taken = min(remaining, size)
        cost += taken * price
        fee += taken * fee_rate * price * (Decimal("1") - price)
        levels_used.append({"price": str(price), "shares": str(taken)})
        remaining -= taken
        if remaining == 0:
            break
    if remaining > 0:
        raise ValueError("insufficient ask depth")
    if shares < min_order_size:
        raise ValueError("order below market minimum shares")
    if cost < MIN_MARKET_BUY_NOTIONAL:
        raise ValueError("order below market minimum notional")

    return {
        "shares": shares,
        "vwap": cost / shares,
        "cost": cost,
        "fee": fee,
        "gap_per_share": (shares - cost - fee) / shares,
        "book_age_seconds": int(age_seconds),
        "book_timestamp": book["timestamp"],
        "book_hash": book.get("hash"),
        "levels_used": levels_used,
    }


def evaluate_jev(
    question: str,
    rules: str,
    evidence: list[dict[str, str]],
    api_key: str,
    http_fn: Callable[..., Any] = http_json,
) -> dict[str, Any]:
    body = {
        "model": "jev-latest",
        "state": {"market_question": question, "resolution_rules": rules, "evidence": evidence},
        "questions": {
            "yes": {"type": "noul", "instructions": "Does the supplied evidence already establish that the market's Yes outcome occurred under its resolution rules? Answer no for a forecast, rumor, or missing fact."},
            "no": {"type": "noul", "instructions": "Does the supplied evidence already establish that the market's No outcome is unavoidable under its resolution rules? Answer no if Yes could still occur."},
            "ambiguous": {"type": "noul", "instructions": "Is the settlement outcome ambiguous or unsupported by the supplied evidence and resolution rules?"},
        },
    }
    response = http_fn(JEV_URL, body=body, api_key=api_key)
    if not isinstance(response, dict) or not isinstance(response.get("answers"), dict):
        raise ValueError("invalid Jev response")
    answers = response["answers"]
    scores = {}
    for name in ("yes", "no", "ambiguous"):
        answer = answers.get(name, {})
        if not isinstance(answer, dict):
            raise ValueError(f"invalid Jev {name} answer")
        value = answer.get("noul") if answer.get("type") == "noul" else None
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise ValueError(f"invalid Jev {name} answer")
        scores[name] = value
    return {"model": response.get("model"), "scores": scores, "usage": response.get("usage")}


def check_jev(api_key: str, http_fn: Callable[..., Any] = http_json) -> dict[str, Any]:
    response = http_fn(
        JEV_URL,
        body={
            "model": "jev-latest",
            "state": "Fixed string used to verify the Jev API connection.",
            "questions": {
                "connected": {
                    "type": "noul",
                    "instructions": "Is this a Jev API connectivity check?",
                },
            },
        },
        api_key=api_key,
    )
    answers = response.get("answers") if isinstance(response, dict) else None
    answer = answers.get("connected") if isinstance(answers, dict) else None
    if (not isinstance(answer, dict) or answer.get("type") != "noul"
            or not isinstance(answer.get("noul"), (int, float))
            or not 0 <= answer["noul"] <= 1):
        raise ValueError("invalid Jev connectivity response")
    return {"model": response.get("model"), "usage": response.get("usage")}


def evaluate_candidate(scores: dict[str, float], quotes: dict[str, dict[str, Any]], min_gap: Decimal) -> str | None:
    if scores["ambiguous"] > MAX_OPPOSITE_SCORE:
        return None
    for side, other in (("Yes", "No"), ("No", "Yes")):
        if (scores[side.lower()] >= MIN_DECISIVE_SCORE
                and scores[other.lower()] <= MAX_OPPOSITE_SCORE
                and side in quotes
                and quotes[side]["gap_per_share"] >= min_gap):
            return side
    return None


def validate_evidence(evidence: Any, now: datetime) -> list[dict[str, str]]:
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("at least one dated evidence item is required")
    for item in evidence:
        if not isinstance(item, dict) or not str(item.get("source_url", "")).startswith("https://") or not str(item.get("text", "")).strip():
            raise ValueError("evidence needs source_url (https) and text")
        try:
            observed = datetime.fromisoformat(item["observed_at"].replace("Z", "+00:00"))
        except (AttributeError, KeyError, ValueError, TypeError):
            raise ValueError("evidence observed_at must be ISO-8601") from None
        if observed.tzinfo is None or observed > now:
            raise ValueError("evidence timestamp is naive or in the future")
    return evidence


def run_case(
    case: dict[str, Any],
    api_key: str,
    shares: Decimal,
    min_gap: Decimal,
    now: datetime,
    http_fn: Callable[..., Any] = http_json,
) -> dict[str, Any]:
    slug = case.get("market_slug", "")
    if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
        raise ValueError("market_slug must be a market slug, not an event slug or URL")
    evidence = validate_evidence(case.get("evidence"), now)
    market = http_fn(f"{GAMMA_BASE}/markets/slug/{urllib.parse.quote(slug, safe='')}")
    parsed = parse_binary_market(market)
    quotes = {}
    quote_errors = {}
    for side, token in parsed["tokens"].items():
        try:
            book = http_fn(f"{CLOB_BASE}/book?{urllib.parse.urlencode({'token_id': token})}")
            quotes[side] = simulate_buy(book, shares, parsed["fee_rate"], now)
        except (ValueError, RuntimeError, urllib.error.URLError) as error:
            quote_errors[side] = str(error)
    result = {
        "observed_at": now.isoformat(),
        "market_slug": slug,
        "condition_id": market["conditionId"],
        "question": market["question"],
        "resolution_rules": market["description"],
        "evidence": evidence,
        "requested_shares": shares,
        "fee_rate": parsed["fee_rate"],
        "min_gap": min_gap,
        "quotes": quotes,
        "quote_errors": quote_errors,
        "candidate_outcome": None,
        "status": "NO_ACTIONABLE_QUOTE",
        "paper_only": True,
        "evidence_source_verified": False,
    }
    if quotes:
        jev = evaluate_jev(market["question"], market["description"], evidence, api_key, http_fn)
        result["jev"] = jev
        result["candidate_outcome"] = evaluate_candidate(jev["scores"], quotes, min_gap)
        result["status"] = "REVIEW_CANDIDATE" if result["candidate_outcome"] else "NO_CANDIDATE"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="JSON list of market slugs and dated evidence")
    parser.add_argument("--output", type=Path, default=Path("data/jev-shadow.jsonl"))
    parser.add_argument("--shares", type=Decimal, default=Decimal("20"))
    parser.add_argument("--min-gap", type=Decimal, default=Decimal("0.15"), help="minimum payout gap per share if the selected side wins")
    parser.add_argument("--check-jev", action="store_true", help="make one harmless read-only Jev API request and exit")
    args = parser.parse_args()
    if not args.check_jev and args.input is None:
        parser.error("--input is required unless --check-jev is used")
    api_key = load_api_key()
    if not api_key:
        parser.error("configure TYPESAFE_API_KEY or the polyhermes-jev-shadow macOS Keychain item; no request was sent")
    if args.check_jev:
        try:
            result = check_jev(api_key)
        except (ValueError, RuntimeError, urllib.error.URLError) as error:
            print(f"Jev connectivity check failed: {error}", file=sys.stderr)
            return 1
        print(f"Jev reachable: model={result['model']}, usage={result.get('usage')}")
        return 0
    if not args.shares.is_finite() or args.shares <= 0 or not args.min_gap.is_finite() or not Decimal("0") <= args.min_gap <= Decimal("1"):
        parser.error("shares and min-gap must be valid positive values")

    with args.input.open(encoding="utf-8") as input_file:
        cases = json.load(input_file)
    if not isinstance(cases, list) or not cases:
        parser.error("input must be a non-empty JSON list")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    completed = 0
    with args.output.open("a", encoding="utf-8") as output_file:
        for case in cases:
            now = datetime.now(timezone.utc)
            try:
                if not isinstance(case, dict):
                    raise ValueError("each case must be an object")
                result = run_case(case, api_key, args.shares, args.min_gap, now)
            except (ValueError, RuntimeError, urllib.error.URLError) as error:
                result = {"observed_at": now.isoformat(), "market_slug": case.get("market_slug") if isinstance(case, dict) else None, "status": "SKIPPED", "reason": str(error), "paper_only": True}
            if result["status"] in ("REVIEW_CANDIDATE", "NO_CANDIDATE"):
                completed += 1
            output_file.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
            print(f"{result['market_slug']}: {result['status']}")
    return 0 if completed else 1


if __name__ == "__main__":
    sys.exit(main())
