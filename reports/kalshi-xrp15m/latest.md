# Kalshi XRP 15m Shadow Validation

Generated: 2026-07-11T17:09:43Z

## Scope

- Signal: Kalshi `KXXRP15M` one-minute executable midpoint.
- Target: Polymarket XRP 5m Up/Down outcome.
- Decision time: first Polymarket price in the first minute of each 5m window.
- Leakage guard: only Kalshi candles ending at or before the decision time.
- Validation: chronological 70/30 train/test split.

## Result

- Aligned samples: 1317
- Train / test: 921 / 396
- Test period: 2026-07-09T14:35:04Z to 2026-07-11T16:55:04Z
- Polymarket-only Brier: 0.248127
- Polymarket + Kalshi Brier: 0.246946
- Brier improvement: +0.001181
- Brier improvement 95% CI: [-0.001324, +0.003686]
- Polymarket-only log loss: 0.689289
- Polymarket + Kalshi log loss: 0.686895
- Log-loss improvement: +0.002394
- Log-loss improvement 95% CI: [-0.002662, +0.007449]
- Accuracy improvement: +1.26%

Verdict: **DIRECTIONALLY HELPFUL, NOT PROVEN**.

This is a shadow research result, not an execution rule. Oracle differences, fees,
latency, and available depth remain outside these probability metrics.
