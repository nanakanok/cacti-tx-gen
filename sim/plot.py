#!/usr/bin/env python3
"""Plot an ns-3 replay run against the OTG slice schedule it was built from.

    python sim/plot.py 48              # -> sim/results/ns3_48.png
    python sim/plot.py 48 100m 500m 1g
    python sim/plot.py --overlay 48 100m 500m 1g   # -> sim/results/ns3_overlay.png
    python sim/plot.py --source 48                 # -> sim/results/source_vs_output_48.png
    python sim/plot.py --input                     # -> sim/results/input_waveform.png
                                                   #    sim/results/extract_check.png
    python sim/plot.py --trex 48                   # -> sim/results/trex_48.png
                                                   #    sim/results/source_vs_trex_48.png

Reads input/otg_<tag>.yaml and results/ns3_<tag>.csv; writes PNG next to the CSV.
--source additionally overlays the waveform extracted from the source IX graph
(input/ts_jpnap.json) with what ns-3 and TRex actually transmitted.
--input draws the input side on its own: the extracted waveform, and the same
waveform laid over the plot region of the IX graph it came from
(input/jpnap_sample.png).
--trex draws the TRex run on its own, and the TRex output over the input.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml

SIM = Path(__file__).resolve().parent

SCHED_FILL = "#c8ced7"
SCHED_LINE = "#9aa3b0"
GOODPUT = "#2a78d6"
WIRE = "#eb6834"
INK = "#12161c"
MUTED = "#828b98"
GRID = "#dde2e9"
TREX = "#1baf7a"
TREX_RAW = "#0d6b4b"
SOURCE = "#12161c"

# TRex port counters include the 4-byte FCS; the OTG rate refers to the 1400 B frame
TREX_FRAME_CORRECTION = 1400 / 1404


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


def load_source():
    """Waveform extracted from the source IX graph, before any resampling."""
    import json
    ts = json.loads((SIM / "input" / "ts_jpnap.json").read_text())
    pts = ts["points"]
    t = np.array([p["t"] for p in pts], float)
    bps = np.array([p["bps"] for p in pts], float)
    return t, bps


def load_trex(tag: str, dur: float, n: int):
    """Per-slice rate TRex actually delivered, on the schedule's slice grid.

    The chained burst streams advance when a burst has sent its packet count,
    not on a wall clock, so the whole schedule drifts by a fixed offset (the
    1 bps edge slices finish early). Recover that offset by cross-correlation
    and report it — it is a property of the run, not a fudge factor.
    """
    path = SIM / "results" / f"trex_{tag}.csv"
    if not path.exists():
        return None, None, None
    rows = list(csv.DictReader(path.open()))
    t = np.array([float(r["t"]) for r in rows])
    rx = np.array([float(r["rx_bps"]) for r in rows]) * TREX_FRAME_CORRECTION
    cfg = yaml.safe_load((SIM / "input" / f"otg_{tag}.yaml").read_text())
    exp = np.array([f["rate"]["bps"] for f in cfg["flows"]], float)
    live = exp > 1e5

    def binned(shift):
        out = np.zeros(n)
        for i in range(n):
            m = (t + shift > i * dur) & (t + shift <= (i + 1) * dur)
            out[i] = rx[m].mean() if m.any() else 0.0
        return out

    grid = np.arange(0, dur, 0.1)
    shift = max(grid, key=lambda sh: np.corrcoef(binned(sh)[live], exp[live])[0, 1])
    return binned(shift), float(shift), (t + shift, rx)


def style(ax):
    ax.set_facecolor("white")
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)


def edges(n, dur):
    """x/y sequences that draw one flat step per slice."""
    return np.repeat(np.arange(n + 1) * dur, 2)[1:-1]


def steps(v):
    return np.repeat(v, 2)


def plot_one(tag: str) -> Path:
    exp, meas, wire, dur = load(tag)
    n = len(exp)
    live = exp > 1e5
    x = edges(n, dur)
    scale = 1e6

    fig, (ax, ax2) = plt.subplots(
        2, 1, figsize=(11, 6.2), height_ratios=[3, 1], sharex=True,
        gridspec_kw={"hspace": 0.12},
    )
    fig.patch.set_facecolor("white")

    ax.fill_between(x, 0, steps(exp) / scale, color=SCHED_FILL, step=None,
                    label="OTG schedule", zorder=1)
    ax.plot(x, steps(exp) / scale, color=SCHED_LINE, linewidth=1.2, zorder=2)
    ax.plot(x, steps(wire) / scale, color=WIRE, linewidth=1.6,
            label="ns-3 NetDevice (wire)", zorder=3)
    ax.plot(x, steps(meas) / scale, color=GOODPUT, linewidth=1.8,
            label="ns-3 PacketSink (goodput)", zorder=4)
    style(ax)
    ax.set_ylabel("Rate (Mbps)", color=INK, fontsize=10)
    ax.set_xlim(0, n * dur)
    ax.set_ylim(0, max(exp.max(), wire.max()) / scale * 1.12)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK, loc="upper left", ncol=3)

    vol_s = (exp * dur).sum() / 8 / 1e9
    vol_m = (meas * dur).sum() / 8 / 1e9
    err = (meas[live] - exp[live]) / exp[live] * 100
    ax.set_title(
        f"ns-3 replay of {SIM.name}/input/otg_{tag}.yaml  —  {n} slices x {dur:g}s, "
        f"peak {exp.max()/scale:.1f} Mbps\n"
        f"goodput {vol_m:.4f} GB vs scheduled {vol_s:.4f} GB "
        f"({(vol_m-vol_s)/vol_s*100:+.4f}%), worst slice {np.abs(err).max():.3f}%",
        color=INK, fontsize=11, loc="left", pad=12,
    )

    e_all = np.where(live, (meas - exp) / np.where(live, exp, 1) * 100, np.nan)
    ew_all = np.where(live, (wire - exp) / np.where(live, exp, 1) * 100, np.nan)
    centers = (np.arange(n) + 0.5) * dur
    ax2.axhline(0, color=SCHED_LINE, linewidth=1)
    ax2.plot(centers, ew_all, color=WIRE, linewidth=1.4, marker="o", markersize=2.5,
             label="wire")
    ax2.plot(centers, e_all, color=GOODPUT, linewidth=1.4, marker="o", markersize=2.5,
             label="goodput")
    style(ax2)
    ax2.set_ylabel("Error (%)", color=INK, fontsize=10)
    ax2.set_xlabel("Time (s)", color=INK, fontsize=10)
    ax2.legend(frameon=False, fontsize=9, labelcolor=INK, loc="upper left", ncol=2)

    out = SIM / "results" / f"ns3_{tag}.png"
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {out.relative_to(SIM.parent)}")
    return out


def plot_overlay(tags: list[str]) -> Path:
    """All runs on one axis, each normalised to its own peak, to show the shape
    is scale-independent."""
    fig, ax = plt.subplots(figsize=(11, 4.4))
    fig.patch.set_facecolor("white")
    colors = [GOODPUT, WIRE, "#1baf7a", "#4a3aa7"]
    for i, tag in enumerate(tags):
        exp, meas, _, dur = load(tag)
        n = len(exp)
        x = edges(n, dur) / (n * dur)
        if i == 0:
            ax.fill_between(x, 0, steps(exp) / exp.max(), color=SCHED_FILL,
                            label="OTG schedule (normalised)", zorder=1)
        ax.plot(x, steps(meas) / exp.max(), color=colors[i % len(colors)],
                linewidth=1.5, label=f"{tag} (peak {exp.max()/1e6:.0f} Mbps)", zorder=2 + i)
    style(ax)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.12)
    ax.set_xlabel("Replay progress", color=INK, fontsize=10)
    ax.set_ylabel("Rate / peak", color=INK, fontsize=10)
    ax.set_title("ns-3 goodput normalised to each run's peak — the shape does not "
                 "depend on the target rate", color=INK, fontsize=11, loc="left", pad=12)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK, loc="lower right")
    out = SIM / "results" / "ns3_overlay.png"
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {out.relative_to(SIM.parent)}")
    return out


# Values printed on the source graph's own stats table, for the annotation
SOURCE_STATS = {"max": 4.03e12, "mean": 2.71e12, "min": 1.39e12}
SOURCE_IMAGE = "jpnap_sample.png"


def plot_input() -> list[Path]:
    """Draw the input side on its own.

    input_waveform.png  the extracted timeseries, in the source's own units
    extract_check.png   the same curve over the plot region of the PNG it was
                        read from, which is what makes the extraction checkable
                        by eye rather than only by the accuracy table
    """
    t, bps = load_source()
    hours = t / 3600
    live = bps > 0
    idx = np.flatnonzero(live)
    v = bps[live]
    out = []

    fig, ax = plt.subplots(figsize=(11, 4.4))
    fig.patch.set_facecolor("white")
    ax.fill_between(hours, 0, bps / 1e12, color=SCHED_FILL, zorder=1)
    ax.plot(hours, bps / 1e12, color=SOURCE, linewidth=1.5, zorder=3)
    for edge in (hours[: idx[0] + 1], hours[idx[-1]:]):
        if len(edge) > 1:
            ax.axvspan(edge[0], edge[-1], color=WIRE, alpha=0.10, zorder=0)
    for name, colour in (("max", WIRE), ("mean", GOODPUT)):
        ax.axhline(SOURCE_STATS[name] / 1e12, color=colour, linewidth=1.1,
                   linestyle="--", zorder=2,
                   label=f"graph's stated {name} {SOURCE_STATS[name]/1e12:.2f} Tb/s")
    style(ax)
    ax.set_xlim(0, hours[-1])
    ax.set_ylim(0, max(bps.max(), SOURCE_STATS["max"]) / 1e12 * 1.12)
    ax.set_xlabel("Extracted time base (h) — --scale daily assumes 24 h",
                  color=INK, fontsize=10)
    ax.set_ylabel("Rate (Tb/s)", color=INK, fontsize=10)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK, loc="lower right", ncol=2)
    ax.set_title(
        f"input waveform — {len(t)} samples from {SOURCE_IMAGE}\n"
        f"extracted max {v.max()/1e12:.3f} / mean {v.mean()/1e12:.3f} Tb/s "
        f"({(v.max()-SOURCE_STATS['max'])/SOURCE_STATS['max']*100:+.1f}% / "
        f"{(v.mean()-SOURCE_STATS['mean'])/SOURCE_STATS['mean']*100:+.1f}% vs the "
        f"graph), shaded: {idx[0]} leading + {len(t)-1-idx[-1]} trailing samples "
        f"read back as 0",
        color=INK, fontsize=11, loc="left", pad=12)
    dst = SIM / "results" / "input_waveform.png"
    fig.savefig(dst, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {dst.relative_to(SIM.parent)}")
    out.append(dst)

    src_png = SIM / "input" / SOURCE_IMAGE
    try:
        import cv2
        from cacti_tx_gen.extract.jpnap import JPNAPExtractor
    except ImportError as exc:
        print(f"  skipping extract_check.png ({exc}); install the package to draw it")
        return out
    img = cv2.imread(str(src_png))
    if img is None:
        print(f"  skipping extract_check.png ({src_png} not readable)")
        return out
    region = JPNAPExtractor()._detect_plot_region(img)
    import json
    y_max = json.loads((SIM / "input" / "ts_jpnap.json").read_text())["y_axis_max_bps"]
    crop = cv2.cvtColor(img[region["y0"]:region["y1"], region["x0"]:region["x1"]],
                        cv2.COLOR_BGR2RGB)

    fig, ax = plt.subplots(figsize=(11, 4.6))
    fig.patch.set_facecolor("white")
    ax.imshow(crop, extent=(0, hours[-1], 0, y_max / 1e12), aspect="auto",
              interpolation="antialiased", zorder=1)
    ax.plot(hours, bps / 1e12, color=GOODPUT, linewidth=1.8, zorder=2,
            label="extracted waveform")
    style(ax)
    ax.grid(False)
    ax.set_xlim(0, hours[-1])
    ax.set_ylim(0, y_max / 1e12)
    ax.set_xlabel("Extracted time base (h)", color=INK, fontsize=10)
    ax.set_ylabel("Rate (Tb/s)", color=INK, fontsize=10)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK, loc="upper left")
    ax.set_title(
        f"extraction check — {SOURCE_IMAGE} plot region "
        f"x[{region['x0']}:{region['x1']}] y[{region['y0']}:{region['y1']}], "
        f"y-axis full scale {y_max/1e12:.2f} Tb/s",
        color=INK, fontsize=11, loc="left", pad=12)
    dst = SIM / "results" / "extract_check.png"
    fig.savefig(dst, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {dst.relative_to(SIM.parent)}")
    out.append(dst)
    return out


def plot_trex(tag: str) -> Path | None:
    """The TRex run on its own: what the generator put on the wire against the
    schedule it was given, at both the sampling and the slice granularity."""
    exp, _, _, dur = load(tag)
    n = len(exp)
    live = exp > 1e5
    trex, shift, raw = load_trex(tag, dur, n)
    if trex is None:
        print(f"  no results/trex_{tag}.csv — skipping the TRex figure")
        return None
    rt, rrx = raw
    scale = 1e6
    x = edges(n, dur)

    fig, (ax, ax2) = plt.subplots(
        2, 1, figsize=(11, 6.2), height_ratios=[3, 1], sharex=True,
        gridspec_kw={"hspace": 0.12})
    fig.patch.set_facecolor("white")

    ax.fill_between(x, 0, steps(exp) / scale, color=SCHED_FILL, zorder=1,
                    label="OTG schedule")
    ax.plot(x, steps(exp) / scale, color=SCHED_LINE, linewidth=1.2, zorder=2)
    # the per-slice line sits under the raw samples: they coincide almost
    # exactly, which is the point - the rate is flat inside each burst
    ax.plot(x, steps(trex) / scale, color=TREX, linewidth=3.2, alpha=0.55, zorder=3,
            label="TRex rx, per slice")
    ax.plot(rt, rrx / scale, color=TREX_RAW, linewidth=0.9, zorder=4,
            label="TRex rx, 0.5 s samples")
    style(ax)
    ax.set_xlim(0, n * dur)
    ax.set_ylim(0, max(exp.max(), trex.max()) / scale * 1.14)
    ax.set_ylabel("Rate (Mbps)", color=INK, fontsize=10)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK, loc="upper left", ncol=3)

    err = (trex[live] - exp[live]) / exp[live] * 100
    vol_s = (exp * dur).sum() / 8 / 1e9
    vol_m = (trex * dur).sum() / 8 / 1e9
    ax.set_title(
        f"TRex replay of {SIM.name}/input/otg_{tag}.yaml — {n} chained burst "
        f"streams, {dur:g}s each, peak {exp.max()/scale:.1f} Mbps\n"
        f"per-slice median {np.median(err):+.2f}%, worst {np.abs(err).max():.2f}%, "
        f"{vol_m:.4f} GB vs {vol_s:.4f} GB scheduled ({(vol_m-vol_s)/vol_s*100:+.2f}%), "
        f"run finishes {shift:.1f}s early",
        color=INK, fontsize=11, loc="left", pad=12)

    e_all = np.where(live, (trex - exp) / np.where(live, exp, 1) * 100, np.nan)
    ax2.axhline(0, color=SCHED_LINE, linewidth=1)
    ax2.plot((np.arange(n) + 0.5) * dur, e_all, color=TREX, linewidth=1.4,
             marker="o", markersize=2.5)
    style(ax2)
    ax2.set_ylabel("Error (%)", color=INK, fontsize=10)
    ax2.set_xlabel("Replay time (s)", color=INK, fontsize=10)

    out = SIM / "results" / f"trex_{tag}.png"
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {out.relative_to(SIM.parent)}")
    return out


def plot_source_vs_output(tag: str, engines: tuple[str, ...] = ("ns3", "trex"),
                          out_name: str | None = None) -> Path:
    """The proof asked of the pipeline: does what came out match what went in?

    Overlays the waveform read off the source IX graph with the rate ns-3 and
    TRex actually delivered, both mapped onto the same axes so a 4 Tb/s IX day
    and a 200 Mbps replay can be compared directly. `engines` selects which
    outputs to draw, so the TRex run can be shown against the input on its own.
    """
    exp, meas, _, dur = load(tag)
    n = len(exp)
    live = exp > 1e5
    total = n * dur
    trex, shift, _ = load_trex(tag, dur, n)
    if "trex" not in engines:
        trex = None
    show_ns3 = "ns3" in engines

    st, sbps = load_source()
    # Map the source onto the replay axis the way generate_otg_config does:
    # it resamples the source to n points and holds each one for one slice, so
    # source sample k lands at the START of slice k, not at its centre.
    st_r = st / st[-1] * ((n - 1) * dur)
    # `generate` scales by peak_rate / source_max and then resamples, so the
    # schedule's own peak sits slightly below the requested one. Recover the
    # scale factor from the schedule itself rather than from either peak, so the
    # residual below is replay error and not a normalisation artefact.
    _at = np.interp(np.arange(n) * dur, st_r, sbps)
    _m = (exp > 1e5) & (_at > 1e5)
    factor = float((exp[_m] * _at[_m]).sum() / (_at[_m] ** 2).sum())
    sbps_r = sbps * factor

    scale = 1e6
    fig, (ax, ax2) = plt.subplots(
        2, 1, figsize=(11, 6.6), height_ratios=[3, 1], sharex=True,
        gridspec_kw={"hspace": 0.12})
    fig.patch.set_facecolor("white")

    ax.fill_between(st_r, 0, sbps_r / scale, color=SCHED_FILL, zorder=1)
    ax.plot(st_r, sbps_r / scale, color=SOURCE, linewidth=1.4, zorder=5,
            label="input: source IX graph")
    x = edges(n, dur)
    if show_ns3:
        ax.plot(x, steps(meas) / scale, color=GOODPUT, linewidth=1.8, zorder=4,
                label="output: ns-3 PacketSink")
    if trex is not None:
        ax.plot(x, steps(trex) / scale, color=TREX, linewidth=1.8, zorder=3,
                label=f"output: TRex rx (t{shift:+.1f}s)")
    style(ax)
    ax.set_xlim(0, total)
    ax.set_ylim(0, exp.max() / scale * 1.14)
    ax.set_ylabel("Rate (Mbps)", color=INK, fontsize=10)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK, loc="upper left", ncol=3)

    # Agreement against the input waveform, read at the instant the generator
    # sampled it. The first and last live slice are excluded: the extractor
    # returns 0 bps for the pixel columns outside the plotted fill, so the
    # source value interpolated across that boundary is meaningless.
    centres = np.arange(n) * dur
    src_at = np.interp(centres, st_r, sbps_r)
    idx = np.flatnonzero(live)
    ok = live & (src_at > 1e5)
    ok[idx[0]] = ok[idx[-1]] = False

    def agree(v):
        r = np.corrcoef(v[ok], src_at[ok])[0, 1]
        e = (v[ok] - src_at[ok]) / src_at[ok] * 100
        rmse = np.sqrt(np.mean((v[ok] - src_at[ok]) ** 2)) / scale
        return r, e, rmse

    r_ns3, e_ns3, rmse_ns3 = agree(meas)
    title = (f"input vs output — {tag}: {n} slices x {dur:g}s, "
             f"peak {exp.max()/scale:.1f} Mbps")
    if show_ns3:
        title += (f"\nns-3  r={r_ns3:.5f}  median {np.median(e_ns3):+.2f}%  "
                  f"RMSE {rmse_ns3:.2f} Mbps")
    else:
        title += "\n"
    if trex is not None:
        r_tx, e_tx, rmse_tx = agree(trex)
        title += (f"      TRex  r={r_tx:.5f}  median {np.median(e_tx):+.2f}%  "
                  f"RMSE {rmse_tx:.2f} Mbps")
    ax.set_title(title, color=INK, fontsize=11, loc="left", pad=12)

    ax2.axhline(0, color=SCHED_LINE, linewidth=1)
    if show_ns3:
        d_ns3 = np.where(ok, (meas - src_at) / np.where(ok, src_at, 1) * 100, np.nan)
        ax2.plot(centres, d_ns3, color=GOODPUT, linewidth=1.4, marker="o",
                 markersize=2.5, label="ns-3")
    if trex is not None:
        d_tx = np.where(ok, (trex - src_at) / np.where(ok, src_at, 1) * 100, np.nan)
        ax2.plot(centres, d_tx, color=TREX, linewidth=1.4, marker="o", markersize=2.5,
                 label="TRex")
    style(ax2)
    ax2.set_ylabel("Output − input (%)", color=INK, fontsize=10)
    ax2.set_xlabel("Replay time (s)", color=INK, fontsize=10)
    ax2.legend(frameon=False, fontsize=9, labelcolor=INK, loc="upper left", ncol=2)

    out = SIM / "results" / (out_name or f"source_vs_output_{tag}.png")
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {out.relative_to(SIM.parent)}")
    if show_ns3:
        print(f"  ns-3 vs input : r={r_ns3:.6f}  median {np.median(e_ns3):+.2f}%  "
              f"max|err| {np.abs(e_ns3).max():.2f}%  RMSE {rmse_ns3:.3f} Mbps")
    if trex is not None:
        print(f"  TRex vs input : r={r_tx:.6f}  median {np.median(e_tx):+.2f}%  "
              f"max|err| {np.abs(e_tx).max():.2f}%  RMSE {rmse_tx:.3f} Mbps "
              f"(time offset {shift:+.1f}s)")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("tags", nargs="*", default=["48"])
    ap.add_argument("--overlay", action="store_true",
                    help="also draw all tags normalised on one axis")
    ap.add_argument("--source", action="store_true",
                    help="also overlay the source IX waveform with the measured output")
    ap.add_argument("--input", action="store_true",
                    help="draw the input waveform on its own and over the source PNG")
    ap.add_argument("--trex", action="store_true",
                    help="draw the TRex run on its own, and TRex against the input")
    a = ap.parse_args()
    tags = a.tags or ["48"]
    if a.input:
        plot_input()
    for tag in tags:
        plot_one(tag)
        if a.source:
            plot_source_vs_output(tag)
        if a.trex:
            if plot_trex(tag) is not None:
                plot_source_vs_output(tag, engines=("trex",),
                                      out_name=f"source_vs_trex_{tag}.png")
    if a.overlay and len(tags) > 1:
        plot_overlay(tags)
