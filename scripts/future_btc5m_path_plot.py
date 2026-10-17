#!/usr/bin/env python3
"""Export scientific figures for BTC proxy-path and filter research."""
import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import statistics
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as dates
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt

plt.rcParams["text.parse_math"] = False
LABELS = {"baseline": "$1 only", "original": "$1 + reverse $10",
          "volatility10bp": "Past 60s range <=0.10%", "cap90": "Reverse price cap 90c",
          "agreement": "Spot + TWAP agree", "sustained10": "Agreement for 10s",
          "distance": "Distance vs recent noise", "combined": "Cap + agreement + distance"}
COLORS = {"baseline": "#2679b8", "original": "#d1495b", "volatility10bp": "#ab792c",
          "cap90": "#8e71ad", "agreement": "#777777", "sustained10": "#3b9277",
          "distance": "#795548", "combined": "#dd8744"}
TYPES = {"PRICE_SOURCE_UNCERTAINTY": "Source uncertainty",
         "MODERATE_PROXY_CROSSING": "Moderate proxy crossing",
         "SPOT_REVERSE_TWAP_STILL_ORIGINAL": "Spot / TWAP disagreement",
         "LARGE_PROXY_REVERSAL": "Large proxy reversal",
         "SMALL_PROXY_CROSSING": "Small proxy crossing",
         "BTC_ALREADY_AGAINST_HEDGE_AT_TRIGGER": "BTC proxy already opposed"}


def draw_path(axis, row, path, left=0):
    for symbol, color, style in (("BTCUSDT", "#2679b8", "-"), ("BTCUSDC", "#8f9ca7", ":")):
        candles = path[symbol]
        by_second = {r[0]: r for r in candles}
        opening = statistics.mean(by_second[t][4] for t in range(-60, 0))
        x = [t + 1 for t in range(left, 300)]
        axis.plot(x, [by_second[t][4] - opening for t in range(left, 300)],
                  color=color, linestyle=style, linewidth=1, label=f"{symbol} 1s close")
        if symbol == "BTCUSDT":
            twap = [statistics.mean(by_second[s][4] for s in range(t - 59, t + 1)) - opening for t in range(left, 300)]
            axis.plot(x, twap, color="#aa67a6", linewidth=1.25, label="USDT trailing 60s mean")
    trigger = row["observedSecond"] + 1
    axis.axhline(0, color="#444444", linewidth=.9)
    axis.axvline(trigger, color="#d1495b", linestyle="--", linewidth=1, label="Reverse decision")
    axis.scatter([300], [row["chainlinkFinalGapUsd"]], marker="D", color="#222222", s=25,
                 zorder=5, label="Published Chainlink final delta")
    axis.axvspan(max(left, 220), 300, color="#e7d9c5", alpha=.2)
    timestamp = datetime.fromisoformat(row["roundBj"])
    axis.set_title(f"{timestamp:%m-%d %H:%M} BJ | reverse {row['reverseSide']} | winner {row['winner']}\n"
                   f"{TYPES[row['category']]} | tail range {row['tailRangeBps']/100:.3f}%", fontsize=8)
    axis.set(xlim=(left, 305), xlabel="Seconds after round open", ylabel="Delta from opening mean (USD)")
    axis.tick_params(labelsize=7)
    axis.grid(alpha=.15)


def plot(directory):
    directory = Path(directory)
    report = json.loads((directory / "path-filter-report.json").read_text())
    targets = {r["start"] for r in report["losses"]}
    paths = {}
    with (directory / "btc-seconds.jsonl").open() as stream:
        for line in stream:
            row = json.loads(line)
            if row["start"] in targets:
                paths[row["start"]] = row
    with PdfPages(directory / "27-btc-paths.pdf") as pdf:
        for page in range(3):
            fig, axes = plt.subplots(3, 3, figsize=(15, 11), layout="constrained")
            for axis, row in zip(axes.flat, report["losses"][page * 9:page * 9 + 9]):
                draw_path(axis, row, paths[row["start"]])
            handles, labels = axes[0, 0].get_legend_handles_labels()
            fig.legend(handles, labels, loc="outside lower center", ncol=3, fontsize=8)
            fig.suptitle(f"27 funded reverse losses | BTC exchange proxies | page {page+1}/3\n"
                         "Each pair is anchored to its preceding-60s opening mean; exact Chainlink ticks unavailable.", fontsize=11)
            pdf.savefig(fig)
            fig.savefig(directory / f"27-btc-paths-page{page+1}.png", dpi=170)
            plt.close(fig)
    selected = [r for r in report["losses"] if r["roundBj"].startswith("2026-09-10")]
    fig, axes = plt.subplots(2, 1, figsize=(11, 8), layout="constrained")
    for axis, row in zip(axes, selected):
        draw_path(axis, row, paths[row["start"]], left=190)
        axis.title.set_fontsize(10)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncol=3, fontsize=8)
    fig.suptitle("September 10: two losses with different BTC paths\nExchange proxies, not exact Chainlink second-level reports", fontsize=12)
    fig.savefig(directory / "sept10-two-losses.png", dpi=180)
    fig.savefig(directory / "sept10-two-losses.pdf")
    plt.close(fig)
    fig, axes = plt.subplots(2, 1, figsize=(12, 10), layout="constrained")
    for name in ("baseline", "original", "volatility10bp", "cap90", "sustained10", "combined"):
        with (directory / f"{name}-bankroll.csv").open() as stream:
            rows = list(csv.DictReader(stream))
        timestamps = [datetime.fromisoformat(r["roundBj"]) for r in rows]
        equity = [float(r["equityEnd"]) for r in rows]
        axes[0].plot(timestamps, equity, color=COLORS[name], linewidth=1.2,
                     label=f"{LABELS[name]}: ${equity[-1]:.2f}")
    axes[0].axhline(100, color="#666666", linewidth=.6)
    axes[0].set(ylabel="Closed-round equity (USD)", title="Full September: $100 on Sep 1, no additional funds")
    axes[0].legend(fontsize=8, loc="best")
    axes[0].xaxis.set_major_formatter(dates.DateFormatter("%m-%d", tz=ZoneInfo("Asia/Shanghai")))
    names = list(LABELS)
    final = [report["policies"][name]["validationSeparate100Bankroll"]["monthEndEquityUsd"] for name in names]
    bars = axes[1].barh([LABELS[name] for name in names], final, color=[COLORS[name] for name in names])
    axes[1].bar_label(bars, labels=[f"${x:.2f}" for x in final], padding=4, fontsize=8)
    axes[1].axvline(100, color="#666666", linewidth=.7)
    axes[1].set(xlim=(0, max(105, max(final) * 1.12)), xlabel="Ending cash (USD)",
                title="Chronological check: separate $100 started Sep 16; exploratory, not untouched out-of-sample")
    axes[1].invert_yaxis()
    for axis in axes:
        axis.grid(alpha=.15)
    fig.suptitle("Filtering losing examples does not establish profitable performance\nHistorical trade-print execution proxies; no verified Future fills", fontsize=12)
    fig.savefig(directory / "filter-equity.png", dpi=170)
    fig.savefig(directory / "filter-equity.pdf")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    plot(parser.parse_args().directory)
