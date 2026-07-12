# Kalshi XRP 15m Shadow Loop

## Goal

Determine whether Kalshi XRP 15m information improves leakage-safe Polymarket XRP 5m trend probabilities without changing live execution.

## Trigger

- Collector: `com.polyhermes.kalshi-xrp15m-shadow`, every 60 seconds.
- Backtest: `python3 scripts/kalshi_xrp15m_shadow.py backtest --lookback-days 7`.

## Stop Condition

- At least 7 days of aligned samples.
- Chronological holdout has positive Brier and log-loss improvement.
- Both paired 95% confidence interval lower bounds are above zero before the signal can be considered for a trading guard.

## Current Result

- [x] Leakage-safe window alignment and stale-quote guard implemented.
- [x] Live shadow snapshot command implemented.
- [x] Launchd collector installed and verified with exit code `0`.
- [x] Seven-day historical replay completed with 1,317 aligned samples.
- [x] Brier improvement: `+0.001181`, 95% CI `[-0.001324, +0.003686]`.
- [x] Log-loss improvement: `+0.002394`, 95% CI `[-0.002662, +0.007449]`.
- [ ] Statistical stop condition met.

## Decision

Kalshi is directionally helpful in the current holdout, but the evidence is not statistically sufficient. Keep it shadow-only and collect another 7 days before reevaluation.

## Next Iteration

Run the same fixed model after another 7 days. Do not tune thresholds against the current holdout. Promote only if both confidence interval lower bounds become positive.
