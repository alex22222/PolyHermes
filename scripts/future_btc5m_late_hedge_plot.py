#!/usr/bin/env python3
"""Export the offline hedge replay figures (requires matplotlib)."""
import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["text.parse_math"] = False


def plot(directory):
    directory = Path(directory)
    report = json.loads((directory / "report.json").read_text())
    fig, axes = plt.subplots(2, 1, figsize=(11, 8), layout="constrained")
    specifications = [("reverse10", "baselinePnl", "Original $1 only", "#2679b8"),
                      ("reverse10", "pnl", "Original $1 + reverse $10", "#d1495b"),
                      ("reverse10_cap90", "pnl", "Reverse $10, max price 90c", "#d89b26"),
                      ("reverse1", "pnl", "Original $1 + reverse $1", "#4c956c")]
    for name, field, label, color in specifications:
        with (directory / f"{name}-rounds.csv").open() as stream:
            rows = list(csv.DictReader(stream))
        equity = [0]
        for row in rows:
            equity.append(equity[-1] + float(row[field]))
        axes[0].plot(equity, label=label, color=color, linewidth=1.6)
    axes[0].axhline(0, color="#777777", linewidth=0.7)
    axes[0].set(xlabel="Eligible rounds, chronological order", ylabel="Cumulative net P&L (USD)",
                title=f"BTC 5m: {report['cachedRounds']} sampled markets | historical trade proxy replay")
    axes[0].legend(loc="best", fontsize=9)
    axes[0].grid(alpha=0.15)
    prices = [0.80 + index * 0.001 for index in range(200)]
    entry = 0.70
    good = [10 / price - 11 - 0.07 * (1 - entry) - 0.7 * (1 - price) for price in prices]
    bad = [1 / entry - 11 - 0.07 * (1 - entry) - 0.7 * (1 - price) for price in prices]
    axes[1].plot(prices, good, label="Reverse side wins", color="#4c956c")
    axes[1].plot(prices, bad, label="Original side recovers and wins", color="#d1495b")
    axes[1].axhline(0, color="#777777", linewidth=0.7)
    axes[1].axvline(0.90173, color="#777777", linestyle="--", linewidth=0.9)
    axes[1].annotate("Above ~90.17c: both outcomes lose", (0.905, 0.15), fontsize=9)
    axes[1].set(xlabel="Reverse buy price (USD per share)", ylabel="Combined round P&L (USD)",
                title="Payoff arithmetic: original $1 at 70c, reverse $10, fee rate 0.07")
    axes[1].legend(loc="lower left", fontsize=9)
    axes[1].grid(alpha=0.15)
    fig.suptitle("Research only | no historical order-book depth or verified Future fills", fontsize=11)
    fig.savefig(directory / "equity-and-payoff.png", dpi=170)
    fig.savefig(directory / "equity-and-payoff.pdf")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    plot(parser.parse_args().directory)
