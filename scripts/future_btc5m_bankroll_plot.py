#!/usr/bin/env python3
"""Export the September USD100 offline bankroll replay figure."""
import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as dates
import matplotlib.pyplot as plt
plt.rcParams["text.parse_math"] = False


def plot(directory):
    directory = Path(directory)
    report = json.loads((directory / "bankroll-report.json").read_text())
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True, layout="constrained")
    specifications = [("baseline", "Original $1 only", "#2679b8", "-"),
                      ("reverse10", "Original $1 + reverse $10", "#d1495b", "-"),
                      ("reverse10_extra1pct", "Reverse $10 + hypothetical 1% fee", "#d89b26", "--"),
                      ("reverse10_creditDelay5m", "Reverse $10 + 5 min credit delay", "#4c956c", "--")]
    for name, label, color, style in specifications:
        with (directory / f"{name}-bankroll.csv").open() as stream:
            rows = list(csv.DictReader(stream))
        timestamps = [datetime.fromisoformat(row["roundBj"]) for row in rows]
        equity = [float(row["equityEnd"]) for row in rows]
        end = report["scenarios"][name]["monthEndEquityUsd"]
        axes[0].plot(timestamps, equity, label=f"{label}: ${end:.2f}", color=color, linestyle=style, linewidth=1.5)
        peak = 100
        drawdowns = []
        for value in equity:
            peak = max(peak, value)
            drawdowns.append(peak - value)
        axes[1].plot(timestamps, drawdowns, color=color, linestyle=style, linewidth=1.3)
    axes[0].axhline(100, color="#777777", linewidth=0.8)
    axes[0].axhline(0, color="#777777", linewidth=0.8)
    axes[0].set(ylabel="Closed-round equity (USD)", title="Starting funds $100 | fixed stakes | no deposits or borrowing")
    axes[0].legend(fontsize=8, loc="best")
    axes[1].set(ylabel="Drawdown from previous peak (USD)", xlabel="September 2026, Beijing dates")
    axes[1].xaxis.set_major_formatter(dates.DateFormatter("%m-%d", tz=ZoneInfo("Asia/Shanghai")))
    for axis in axes:
        axis.grid(alpha=0.15)
    fig.suptitle("BTC5m historical-trade proxy replay | 8,640 rounds | not verified Future fills", fontsize=12)
    fig.savefig(directory / "bankroll-equity.png", dpi=170)
    fig.savefig(directory / "bankroll-equity.pdf")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    plot(parser.parse_args().directory)
