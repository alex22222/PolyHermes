#!/usr/bin/env python3
"""Collect and evaluate Kalshi XRP 15m as a shadow signal for XRP 5m."""

from __future__ import annotations

import argparse
import json
import math
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"
GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"
KALSHI_SERIES = "KXXRP15M"
POLYMARKET_5M_SERIES_ID = "10685"
USER_AGENT = "PolyHermes-Kalshi-Shadow/1.0"


def ssl_context() -> ssl.SSLContext:
    configured = os.environ.get("SSL_CERT_FILE")
    if configured:
        return ssl.create_default_context(cafile=configured)
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


@dataclass(frozen=True)
class FiveMinuteSample:
    window_start: int
    observed_ts: int
    quote_ts: int
    segment: int
    outcome: int
    polymarket_probability: float
    kalshi_probability: float
    kalshi_delta: float
    kalshi_ticker: str
    polymarket_slug: str


def http_json(url: str, retries: int = 3) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    context = ssl_context()
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=20, context=context) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt + 1 == retries:
                raise
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError("unreachable")


def parse_timestamp(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())


def _close_value(node: Any) -> float | None:
    if not isinstance(node, dict):
        return None
    value = node.get("close_dollars", node.get("close"))
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def candle_probability(candle: dict[str, Any]) -> float | None:
    bid = _close_value(candle.get("yes_bid"))
    ask = _close_value(candle.get("yes_ask"))
    if bid is not None and ask is not None and 0 <= bid <= ask <= 1:
        return (bid + ask) / 2
    trade = _close_value(candle.get("price"))
    if trade is not None and 0 <= trade <= 1:
        return trade
    return None


def align_five_minute_samples(
    markets: list[dict[str, Any]],
    candles_by_ticker: dict[str, list[dict[str, Any]]],
    polymarket_by_start: dict[int, dict[str, Any]],
    max_quote_age_seconds: int = 120,
) -> list[FiveMinuteSample]:
    samples: list[FiveMinuteSample] = []
    for market in markets:
        ticker = str(market["ticker"])
        close_ts = int(market["close_ts"])
        candles = sorted(
            candles_by_ticker.get(ticker, []),
            key=lambda candle: int(candle["end_period_ts"]),
        )
        for segment, window_start in ((2, close_ts - 600), (3, close_ts - 300)):
            polymarket = polymarket_by_start.get(window_start)
            if not polymarket:
                continue
            observed_ts = int(polymarket["observed_ts"])
            visible = [
                candle
                for candle in candles
                if int(candle["end_period_ts"]) <= observed_ts
                and observed_ts - int(candle["end_period_ts"]) <= max_quote_age_seconds
                and candle_probability(candle) is not None
            ]
            if not visible:
                continue
            candle = visible[-1]
            probability = candle_probability(candle)
            if probability is None:
                continue
            previous_probability = (
                candle_probability(visible[-2]) if len(visible) > 1 else probability
            )
            if previous_probability is None:
                previous_probability = probability
            samples.append(
                FiveMinuteSample(
                    window_start=window_start,
                    observed_ts=observed_ts,
                    quote_ts=int(candle["end_period_ts"]),
                    segment=segment,
                    outcome=int(polymarket["outcome"]),
                    polymarket_probability=float(polymarket["probability"]),
                    kalshi_probability=probability,
                    kalshi_delta=probability - previous_probability,
                    kalshi_ticker=ticker,
                    polymarket_slug=str(
                        polymarket.get("slug", f"xrp-updown-5m-{window_start}")
                    ),
                )
            )
    return sorted(samples, key=lambda sample: sample.observed_ts)


def evaluate_probabilities(
    probabilities: Iterable[float], outcomes: Iterable[int]
) -> dict[str, float]:
    pairs = [(min(0.999999, max(0.000001, p)), int(y)) for p, y in zip(probabilities, outcomes)]
    if not pairs:
        raise ValueError("at least one prediction is required")
    accuracy = sum((p >= 0.5) == bool(y) for p, y in pairs) / len(pairs)
    brier = sum((p - y) ** 2 for p, y in pairs) / len(pairs)
    log_loss = -sum(y * math.log(p) + (1 - y) * math.log(1 - p) for p, y in pairs) / len(pairs)
    return {"count": len(pairs), "accuracy": accuracy, "brier": brier, "log_loss": log_loss}


def _logit(probability: float) -> float:
    p = min(0.999, max(0.001, probability))
    return math.log(p / (1 - p))


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1 / (1 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1 + exp_value)


def fit_logistic(
    features: list[list[float]], outcomes: list[int], iterations: int = 1600
) -> list[float]:
    if not features or len(features) != len(outcomes):
        raise ValueError("features and outcomes must be non-empty and aligned")
    weights = [0.0] * (len(features[0]) + 1)
    learning_rate = 0.08
    l2 = 0.01
    for _ in range(iterations):
        gradients = [0.0] * len(weights)
        for row, outcome in zip(features, outcomes):
            values = [1.0, *row]
            error = _sigmoid(sum(w * x for w, x in zip(weights, values))) - outcome
            for index, value in enumerate(values):
                gradients[index] += error * value
        for index in range(len(weights)):
            penalty = 0.0 if index == 0 else l2 * weights[index]
            weights[index] -= learning_rate * (gradients[index] / len(features) + penalty)
    return weights


def logistic_predictions(weights: list[float], features: list[list[float]]) -> list[float]:
    return [
        _sigmoid(weights[0] + sum(w * x for w, x in zip(weights[1:], row)))
        for row in features
    ]


def paired_improvement(
    baseline: list[float], augmented: list[float], outcomes: list[int], loss: str
) -> dict[str, float]:
    differences = []
    for base, extra, outcome in zip(baseline, augmented, outcomes):
        base = min(0.999999, max(0.000001, base))
        extra = min(0.999999, max(0.000001, extra))
        if loss == "brier":
            base_loss = (base - outcome) ** 2
            extra_loss = (extra - outcome) ** 2
        elif loss == "log_loss":
            base_loss = -(outcome * math.log(base) + (1 - outcome) * math.log(1 - base))
            extra_loss = -(outcome * math.log(extra) + (1 - outcome) * math.log(1 - extra))
        else:
            raise ValueError(f"unsupported loss: {loss}")
        differences.append(base_loss - extra_loss)
    mean = sum(differences) / len(differences)
    variance = sum((value - mean) ** 2 for value in differences) / max(1, len(differences) - 1)
    margin = 1.96 * math.sqrt(variance / len(differences))
    return {"mean": mean, "ci95_low": mean - margin, "ci95_high": mean + margin}


def validate_chronologically(samples: list[FiveMinuteSample], train_fraction: float = 0.7) -> dict[str, Any]:
    if len(samples) < 40:
        raise ValueError("at least 40 aligned samples are required")
    split = max(20, min(len(samples) - 20, int(len(samples) * train_fraction)))
    train = samples[:split]
    test = samples[split:]
    outcomes_train = [sample.outcome for sample in train]
    outcomes_test = [sample.outcome for sample in test]

    baseline_train = [
        [_logit(sample.polymarket_probability), float(sample.segment == 3)]
        for sample in train
    ]
    baseline_test = [
        [_logit(sample.polymarket_probability), float(sample.segment == 3)]
        for sample in test
    ]
    augmented_train = [
        [
            _logit(sample.polymarket_probability),
            float(sample.segment == 3),
            _logit(sample.kalshi_probability),
            _logit(sample.kalshi_probability) * float(sample.segment == 3),
            sample.kalshi_delta,
        ]
        for sample in train
    ]
    augmented_test = [
        [
            _logit(sample.polymarket_probability),
            float(sample.segment == 3),
            _logit(sample.kalshi_probability),
            _logit(sample.kalshi_probability) * float(sample.segment == 3),
            sample.kalshi_delta,
        ]
        for sample in test
    ]

    baseline_weights = fit_logistic(baseline_train, outcomes_train)
    augmented_weights = fit_logistic(augmented_train, outcomes_train)
    baseline_predictions = logistic_predictions(baseline_weights, baseline_test)
    augmented_predictions = logistic_predictions(augmented_weights, augmented_test)
    baseline = evaluate_probabilities(baseline_predictions, outcomes_test)
    augmented = evaluate_probabilities(augmented_predictions, outcomes_test)
    raw_kalshi = evaluate_probabilities(
        [sample.kalshi_probability for sample in test], outcomes_test
    )
    majority_probability = sum(outcomes_train) / len(outcomes_train)
    no_signal = evaluate_probabilities([majority_probability] * len(test), outcomes_test)
    return {
        "train_count": len(train),
        "test_count": len(test),
        "train_start": train[0].observed_ts,
        "test_start": test[0].observed_ts,
        "test_end": test[-1].observed_ts,
        "no_signal": no_signal,
        "raw_kalshi": raw_kalshi,
        "polymarket_baseline": baseline,
        "polymarket_plus_kalshi": augmented,
        "brier_improvement": baseline["brier"] - augmented["brier"],
        "log_loss_improvement": baseline["log_loss"] - augmented["log_loss"],
        "accuracy_improvement": augmented["accuracy"] - baseline["accuracy"],
        "brier_improvement_ci": paired_improvement(
            baseline_predictions, augmented_predictions, outcomes_test, "brier"
        ),
        "log_loss_improvement_ci": paired_improvement(
            baseline_predictions, augmented_predictions, outcomes_test, "log_loss"
        ),
        "augmented_weights": augmented_weights,
    }


def fetch_kalshi_markets(lookback_days: int) -> list[dict[str, Any]]:
    cutoff = int(time.time()) - lookback_days * 86400
    markets: dict[str, dict[str, Any]] = {}
    cursor = ""
    while True:
        query = {
            "series_ticker": KALSHI_SERIES,
            "status": "settled",
            "min_settled_ts": cutoff,
            "limit": 1000,
        }
        if cursor:
            query["cursor"] = cursor
        payload = http_json(f"{KALSHI_BASE}/markets?{urllib.parse.urlencode(query)}")
        for market in payload.get("markets", []):
            close_time = market.get("close_time") or market.get("expected_expiration_time")
            if close_time:
                markets[str(market["ticker"])] = {
                    "ticker": market["ticker"],
                    "close_ts": parse_timestamp(close_time),
                }
        cursor = str(payload.get("cursor") or "")
        if not cursor:
            break
    return sorted(markets.values(), key=lambda market: market["close_ts"])


def _chunks(values: list[Any], size: int) -> Iterable[list[Any]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def fetch_kalshi_candles(markets: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    if not markets:
        return {}
    result: dict[str, list[dict[str, Any]]] = {}
    for market_chunk in _chunks(markets, 20):
        tickers = [str(market["ticker"]) for market in market_chunk]
        start_ts = min(int(market["close_ts"]) for market in market_chunk) - 900
        end_ts = max(int(market["close_ts"]) for market in market_chunk)
        params = urllib.parse.urlencode(
            {
                "market_tickers": ",".join(tickers),
                "start_ts": start_ts,
                "end_ts": end_ts,
                "period_interval": 1,
            }
        )
        payload = http_json(f"{KALSHI_BASE}/markets/candlesticks?{params}")
        for item in payload.get("markets", []):
            ticker = item.get("market_ticker") or item.get("ticker")
            if ticker:
                result[str(ticker)] = item.get("candlesticks", [])
    return result


def fetch_polymarket_events(lookback_days: int) -> dict[int, dict[str, Any]]:
    cutoff = int(time.time()) - lookback_days * 86400 - 900
    events: dict[int, dict[str, Any]] = {}
    offset = 0
    while True:
        params = urllib.parse.urlencode(
            {
                "series_id": POLYMARKET_5M_SERIES_ID,
                "closed": "true",
                "limit": 100,
                "offset": offset,
                "order": "endDate",
                "ascending": "false",
            }
        )
        page = http_json(f"{GAMMA_BASE}/events?{params}")
        if not page:
            break
        reached_cutoff = False
        for event in page:
            slug = str(event.get("slug", ""))
            try:
                window_start = int(slug.rsplit("-", 1)[1])
            except (IndexError, ValueError):
                continue
            if window_start < cutoff:
                reached_cutoff = True
                continue
            market = (event.get("markets") or [{}])[0]
            try:
                prices = json.loads(market.get("outcomePrices") or "[]")
                tokens = json.loads(market.get("clobTokenIds") or "[]")
            except (TypeError, json.JSONDecodeError):
                continue
            if len(prices) < 2 or len(tokens) < 1:
                continue
            if prices[0] == "1":
                outcome = 1
            elif prices[1] == "1":
                outcome = 0
            else:
                continue
            events[window_start] = {
                "slug": slug,
                "outcome": outcome,
                "up_token": str(tokens[0]),
            }
        if reached_cutoff or len(page) < 100:
            break
        offset += 100
    return events


def fetch_opening_probability(window_start: int, event: dict[str, Any]) -> dict[str, Any] | None:
    params = urllib.parse.urlencode(
        {
            "market": event["up_token"],
            "startTs": window_start,
            "endTs": window_start + 60,
            "fidelity": 1,
        }
    )
    payload = http_json(f"{CLOB_BASE}/prices-history?{params}")
    history = payload.get("history", [])
    if not history:
        return None
    first = min(history, key=lambda point: int(point["t"]))
    probability = float(first["p"])
    if not 0 < probability < 1:
        return None
    return {
        "slug": event["slug"],
        "outcome": event["outcome"],
        "observed_ts": int(first["t"]),
        "probability": probability,
    }


def fetch_polymarket_probabilities(
    events: dict[int, dict[str, Any]], candidate_starts: set[int], workers: int
) -> dict[int, dict[str, Any]]:
    selected = [(start, event) for start, event in events.items() if start in candidate_starts]
    result: dict[int, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(fetch_opening_probability, start, event): start
            for start, event in selected
        }
        for future in as_completed(futures):
            start = futures[future]
            try:
                value = future.result()
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                continue
            if value:
                result[start] = value
    return result


def iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def render_report(validation: dict[str, Any], samples: list[FiveMinuteSample]) -> str:
    baseline = validation["polymarket_baseline"]
    augmented = validation["polymarket_plus_kalshi"]
    directionally_helpful = validation["brier_improvement"] > 0 and validation["log_loss_improvement"] > 0
    proven_helpful = (
        validation["brier_improvement_ci"]["ci95_low"] > 0
        and validation["log_loss_improvement_ci"]["ci95_low"] > 0
    )
    return f"""# Kalshi XRP 15m Shadow Validation

Generated: {iso(int(time.time()))}

## Scope

- Signal: Kalshi `KXXRP15M` one-minute executable midpoint.
- Target: Polymarket XRP 5m Up/Down outcome.
- Decision time: first Polymarket price in the first minute of each 5m window.
- Leakage guard: only Kalshi candles ending at or before the decision time.
- Validation: chronological 70/30 train/test split.

## Result

- Aligned samples: {len(samples)}
- Train / test: {validation['train_count']} / {validation['test_count']}
- Test period: {iso(validation['test_start'])} to {iso(validation['test_end'])}
- Polymarket-only Brier: {baseline['brier']:.6f}
- Polymarket + Kalshi Brier: {augmented['brier']:.6f}
- Brier improvement: {validation['brier_improvement']:+.6f}
- Brier improvement 95% CI: [{validation['brier_improvement_ci']['ci95_low']:+.6f}, {validation['brier_improvement_ci']['ci95_high']:+.6f}]
- Polymarket-only log loss: {baseline['log_loss']:.6f}
- Polymarket + Kalshi log loss: {augmented['log_loss']:.6f}
- Log-loss improvement: {validation['log_loss_improvement']:+.6f}
- Log-loss improvement 95% CI: [{validation['log_loss_improvement_ci']['ci95_low']:+.6f}, {validation['log_loss_improvement_ci']['ci95_high']:+.6f}]
- Accuracy improvement: {validation['accuracy_improvement']:+.2%}

Verdict: **{'STATISTICALLY HELPFUL in this holdout' if proven_helpful else 'DIRECTIONALLY HELPFUL, NOT PROVEN' if directionally_helpful else 'NOT HELPFUL in this holdout'}**.

This is a shadow research result, not an execution rule. Oracle differences, fees,
latency, and available depth remain outside these probability metrics.
"""


def run_backtest(args: argparse.Namespace) -> int:
    markets = fetch_kalshi_markets(args.lookback_days)
    if not markets:
        raise RuntimeError("no settled Kalshi XRP 15m markets found")
    candles = fetch_kalshi_candles(markets)
    events = fetch_polymarket_events(args.lookback_days)
    candidate_starts = {
        int(market["close_ts"]) - offset for market in markets for offset in (600, 300)
    }
    polymarket = fetch_polymarket_probabilities(events, candidate_starts, args.workers)
    samples = align_five_minute_samples(markets, candles, polymarket)
    validation = validate_chronologically(samples)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": iso(int(time.time())),
        "lookback_days": args.lookback_days,
        "validation": validation,
        "samples": [asdict(sample) for sample in samples],
    }
    (output_dir / "latest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    report = render_report(validation, samples)
    (output_dir / "latest.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


def run_snapshot(args: argparse.Namespace) -> int:
    kalshi_params = urllib.parse.urlencode(
        {"series_ticker": KALSHI_SERIES, "status": "open", "limit": 10}
    )
    kalshi = http_json(f"{KALSHI_BASE}/markets?{kalshi_params}")
    now = int(time.time())
    poly_start = now // 300 * 300
    polymarket = http_json(f"{GAMMA_BASE}/events?slug=xrp-updown-5m-{poly_start}")
    compact_kalshi = [
        {
            key: market.get(key)
            for key in (
                "ticker",
                "event_ticker",
                "close_time",
                "yes_bid_dollars",
                "yes_bid_size_fp",
                "yes_ask_dollars",
                "yes_ask_size_fp",
                "no_bid_dollars",
                "no_ask_dollars",
                "volume_fp",
                "open_interest_fp",
            )
        }
        for market in kalshi.get("markets", [])
    ]
    poly_event = polymarket[0] if polymarket else None
    poly_market = ((poly_event or {}).get("markets") or [{}])[0]
    compact_polymarket = None
    if poly_event:
        compact_polymarket = {
            "slug": poly_event.get("slug"),
            "title": poly_event.get("title"),
            "endDate": poly_event.get("endDate"),
            "outcomePrices": poly_market.get("outcomePrices"),
            "clobTokenIds": poly_market.get("clobTokenIds"),
        }
    record = {
        "observed_at": iso(now),
        "observed_ts": now,
        "kalshi_markets": compact_kalshi,
        "polymarket_event": compact_polymarket,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, separators=(",", ":")) + "\n")
    print(f"appended shadow snapshot to {output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    backtest = subparsers.add_parser("backtest", help="run leakage-safe historical validation")
    backtest.add_argument("--lookback-days", type=int, default=7)
    backtest.add_argument("--workers", type=int, default=8)
    backtest.add_argument("--output-dir", default="reports/kalshi-xrp15m")
    backtest.set_defaults(func=run_backtest)

    snapshot = subparsers.add_parser("snapshot", help="append current shadow market data")
    snapshot.add_argument("--output", default="data/kalshi-xrp15m-shadow.jsonl")
    snapshot.set_defaults(func=run_snapshot)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
