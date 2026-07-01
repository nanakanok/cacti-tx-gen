#!/usr/bin/env python3
"""Capture traffic stats from container veth interfaces and plot results.

Polls /sys/class/net/<iface>/statistics/ for tx/rx bytes at 1s intervals.
Produces a time-series CSV and a matplotlib graph comparing expected vs actual traffic.

Usage:
    # Monitor a containerlab interface during traffic generation
    python capture.py --iface <iface> --duration 60 --output results.png

    # Monitor a container's interface via docker exec
    python capture.py --container <name> --iface eth1 --duration 60 --output results.png

    # Compare with expected timeseries
    python capture.py --iface <iface> --duration 60 --expected timeseries.json --output results.png
"""

import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path


def read_bytes_local(iface, direction):
    """Read tx/rx bytes from sysfs."""
    path = f"/sys/class/net/{iface}/statistics/{direction}_bytes"
    try:
        return int(Path(path).read_text().strip())
    except FileNotFoundError:
        return None


def read_bytes_docker(container, iface, direction):
    """Read tx/rx bytes from a container via docker exec."""
    path = f"/sys/class/net/{iface}/statistics/{direction}_bytes"
    try:
        result = subprocess.run(
            ["docker", "exec", container, "cat", path],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError):
        pass
    return None


def capture(read_fn, duration, interval=1.0):
    """Capture byte counters and compute rates."""
    records = []
    prev_tx = read_fn("tx")
    prev_rx = read_fn("rx")
    if prev_tx is None:
        print("ERROR: cannot read interface stats", file=sys.stderr)
        sys.exit(1)

    t0 = time.time()
    while time.time() - t0 < duration:
        time.sleep(interval)
        elapsed = time.time() - t0
        tx = read_fn("tx")
        rx = read_fn("rx")

        tx_rate_bps = (tx - prev_tx) * 8 / interval
        rx_rate_bps = (rx - prev_rx) * 8 / interval

        records.append({
            "t": round(elapsed, 1),
            "tx_bps": round(tx_rate_bps, 0),
            "rx_bps": round(rx_rate_bps, 0),
        })

        prev_tx = tx
        prev_rx = rx

    return records


def save_csv(records, path):
    """Save captured records as CSV."""
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["t", "tx_bps", "rx_bps"])
        w.writeheader()
        w.writerows(records)


def plot(records, expected_path=None, output_path="results.png", title="Traffic Capture"):
    """Plot captured traffic and optionally overlay expected pattern."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t = [r["t"] for r in records]
    tx = [r["tx_bps"] for r in records]
    rx = [r["rx_bps"] for r in records]

    fig, ax = plt.subplots(figsize=(12, 5))

    ax.plot(t, tx, label="Actual TX (bps)", color="tab:blue", linewidth=1.5)
    ax.plot(t, rx, label="Actual RX (bps)", color="tab:green", linewidth=1.0, alpha=0.7)

    if expected_path:
        with open(expected_path) as f:
            expected = json.load(f)
        points = expected.get("points", [])
        if points:
            total_duration = max(r["t"] for r in records)
            source_duration = points[-1]["t"]
            scale = total_duration / source_duration if source_duration > 0 else 1.0

            source_max = max(p["bps"] for p in points)
            actual_max = max(max(tx), max(rx)) if tx else 1
            rate_scale = actual_max / source_max if source_max > 0 else 1.0

            et = [p["t"] * scale for p in points]
            ebps = [p["bps"] * rate_scale for p in points]
            ax.plot(et, ebps, label="Expected (scaled)", color="tab:red",
                    linewidth=1.5, linestyle="--", alpha=0.8)

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Rate (bps)")
    ax.set_title(title)
    ax.legend()
    ax.grid(True, alpha=0.3)

    unit, divisor = _auto_unit(max(max(tx, default=0), max(rx, default=0)))
    if divisor > 1:
        ax.set_ylabel(f"Rate ({unit})")
        ticks = ax.get_yticks()
        ax.set_yticklabels([f"{v/divisor:.1f}" for v in ticks])

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    print(f"Graph saved: {output_path}")
    plt.close(fig)


def _auto_unit(max_val):
    if max_val >= 1e12:
        return "Tbps", 1e12
    if max_val >= 1e9:
        return "Gbps", 1e9
    if max_val >= 1e6:
        return "Mbps", 1e6
    if max_val >= 1e3:
        return "Kbps", 1e3
    return "bps", 1


def main():
    parser = argparse.ArgumentParser(description="Capture and plot traffic stats")
    parser.add_argument("--iface", default=None,
                        help="Local interface name to monitor")
    parser.add_argument("--container", default=None,
                        help="Docker container name (monitor via docker exec)")
    parser.add_argument("--duration", type=float, default=60,
                        help="Capture duration in seconds")
    parser.add_argument("--interval", type=float, default=1.0,
                        help="Polling interval in seconds")
    parser.add_argument("--expected", default=None,
                        help="Expected timeseries JSON for overlay comparison")
    parser.add_argument("--output", default="results.png",
                        help="Output graph filename")
    parser.add_argument("--csv", default=None,
                        help="Also save raw data as CSV")
    parser.add_argument("--title", default="Traffic Capture",
                        help="Graph title")
    args = parser.parse_args()

    if not args.iface and not args.container:
        parser.error("Specify --iface or --container")

    if args.container:
        iface = args.iface or "eth1"
        read_fn = lambda d: read_bytes_docker(args.container, iface, d)
        print(f"Monitoring {args.container}:{iface} for {args.duration}s")
    else:
        read_fn = lambda d: read_bytes_local(args.iface, d)
        print(f"Monitoring {args.iface} for {args.duration}s")

    records = capture(read_fn, args.duration, args.interval)

    if args.csv:
        save_csv(records, args.csv)
        print(f"CSV saved: {args.csv}")

    plot(records, args.expected, args.output, args.title)


if __name__ == "__main__":
    main()
