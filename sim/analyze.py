#!/usr/bin/env python3
"""Compare an ns-3 replay run against the OTG slice schedule it was built from.

    python sim/analyze.py 48          # uses input/otg_48.yaml + results/ns3_48.csv
    python sim/analyze.py 1g 500m 100m 48

Writes results/per_slice_<tag>.csv (scheduled vs measured per slice) and prints
the summary numbers quoted in results/RESULTS.md.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
import yaml

SIM = Path(__file__).resolve().parent


def load(tag: str):
    cfg = yaml.safe_load((SIM / "input" / f"otg_{tag}.yaml").read_text())
    exp = np.array([f["rate"]["bps"] for f in cfg["flows"]], float)
    dur = cfg["flows"][0]["duration"]["fixed_seconds"]["seconds"]
    rows = list(csv.DictReader((SIM / "results" / f"ns3_{tag}.csv").open()))
    t = np.array([float(r["t"]) for r in rows])
    gp = np.array([float(r["goodput_bps"]) for r in rows])
    wr = np.array([float(r["wire_bps"]) for r in rows])
    n = len(exp)
    meas = np.zeros(n)
    wire = np.zeros(n)
    for i in range(n):
        m = (t > i * dur) & (t <= (i + 1) * dur)
        meas[i] = gp[m].mean() if m.any() else 0.0
        wire[i] = wr[m].mean() if m.any() else 0.0
    return exp, meas, wire, dur


def summarize(tag: str) -> None:
    exp, meas, wire, dur = load(tag)
    # slices whose scheduled rate is a real value, not the 1 bps floor the
    # generator writes for the zero samples at the edges of the extracted graph
    live = exp > 1e5
    err = (meas[live] - exp[live]) / exp[live] * 100
    errw = (wire[live] - exp[live]) / exp[live] * 100
    vol_s = (exp * dur).sum() / 8 / 1e9
    vol_m = (meas * dur).sum() / 8 / 1e9
    vol_w = (wire * dur).sum() / 8 / 1e9

    print(f"=== {tag}: {len(exp)} slices x {dur}s, peak {exp.max()/1e6:.2f} Mbps ===")
    print(f"  live slices           : {live.sum()}/{len(exp)}")
    print(f"  goodput vs schedule   : mean {err.mean():+.3f}%  max|err| {np.abs(err).max():.3f}%")
    print(f"  wire    vs schedule   : mean {errw.mean():+.3f}%  max|err| {np.abs(errw).max():.3f}%")
    print(f"  correlation           : {np.corrcoef(meas, exp)[0, 1]:.6f}")
    print(f"  peak  scheduled {exp.max()/1e6:.3f} Mbps -> measured {meas.max()/1e6:.3f} Mbps "
          f"({(meas.max()-exp.max())/exp.max()*100:+.3f}%)")
    print(f"  volume scheduled {vol_s:.4f} GB -> goodput {vol_m:.4f} GB "
          f"({(vol_m-vol_s)/vol_s*100:+.4f}%), wire {vol_w:.4f} GB "
          f"({(vol_w-vol_s)/vol_s*100:+.4f}%)")

    out = SIM / "results" / f"per_slice_{tag}.csv"
    with out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["slice", "t_start_s", "sched_bps", "goodput_bps", "wire_bps",
                    "goodput_err_pct", "wire_err_pct"])
        for i in range(len(exp)):
            e = (meas[i] - exp[i]) / exp[i] * 100 if exp[i] > 1e5 else ""
            ew = (wire[i] - exp[i]) / exp[i] * 100 if exp[i] > 1e5 else ""
            w.writerow([i, round(i * dur, 3), int(exp[i]), round(meas[i], 1), round(wire[i], 1),
                        round(e, 4) if e != "" else "", round(ew, 4) if ew != "" else ""])
    print(f"  wrote {out.relative_to(SIM.parent)}")


if __name__ == "__main__":
    for tag in (sys.argv[1:] or ["48"]):
        summarize(tag)
