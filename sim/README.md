---
type: Simulation
title: sim — replaying an IX traffic graph in ns-3 and on TRex
description: ns-3 scenario, TRex driver, inputs, and measured throughput for replaying an IX traffic graph
tags:
  - ns3
  - trex
  - otg
  - traffic-generation
timestamp: "2026-09-04"
---

# sim — replay and throughput measurement

`cacti-tx-gen convert-ns3` emits an ns-3 scenario but never runs it, and the
scenario it emits prints nothing. This directory holds a scenario that does run,
a TRex driver that plays the same OTG config on real interfaces, the exact
inputs both were run with, and the throughput they produced — so the claim "the
OTG config reproduces the IX graph" is backed by measurement rather than by the
generated source alone.

Measured summary: [`results/RESULTS.md`](results/RESULTS.md). The one figure that
answers the question is
[`results/source_vs_output_48.png`](results/source_vs_output_48.png): the waveform
read off the source PNG, with what ns-3 and TRex actually put on the wire drawn
over it.

## Why the scenario here is C++ and not the generated .py

Two reasons, both about the generated script rather than the model:

1. `convert/ns3.py` emits `import ns.core` / `ns.core.StringValue`, the pybindgen
   API removed in ns-3.37. ns-3.37+ ships cppyy bindings with a flat namespace
   (`from ns import ns`, `ns.StringValue`), so the generated file does not import
   on any current ns-3.
2. The generated scenario calls `Simulator::Run()` and exits. There is no
   `PacketSink` readback, no `FlowMonitor`, no trace — nothing to compare against
   the schedule.

`ns3/cacti-replay.cc` keeps the generated model unchanged — two nodes on a
point-to-point link at `2 x peak slice rate` with 1 ms delay, one
`OnOffApplication` per time slice (`OnTime` = slice duration, `OffTime` = 0),
`PacketSink` on the receiver — and adds the measurement: cumulative
`PacketSink::GetTotalRx()` and the receiver's `PhyRxEnd` byte count sampled on a
fixed grid, written to CSV.

## Layout

```
sim/
├── analyze.py                      # per-slice comparison of a run against its schedule
├── plot.py                         # figures, including the input/output overlay
├── ns3/cacti-replay.cc             # the scenario (copy into ns-3 scratch/ to build)
├── trex/trex-replay.py             # plays the same OTG config on TRex
├── input/
│   ├── jpnap_sample.png            # the IX traffic graph everything starts from
│   ├── ts_jpnap.json               # waveform extracted from it
│   ├── otg_<tag>.yaml              # OTG config generated from that waveform
│   └── sched_<tag>.csv             # rate_bps,duration_sec per slice, fed to the scenario
└── results/
    ├── ns3_<tag>.csv / .log        # t,goodput_bps,wire_bps sampled during the run
    ├── trex_48.csv / .log          # t,tx_bps,rx_bps from the TRex port counters
    ├── per_slice_<tag>.csv         # written by analyze.py
    ├── input_waveform.png          # the extracted waveform on its own
    ├── extract_check.png           # that waveform laid over the graph it came from
    ├── ns3_<tag>.png               # schedule vs PacketSink, with the residual
    ├── trex_<tag>.png              # TRex vs schedule, same layout
    ├── source_vs_output_<tag>.png  # source waveform vs both outputs
    ├── source_vs_trex_<tag>.png    # source waveform vs the TRex output alone
    ├── ns3_overlay.png             # all scales normalised to their own peak
    └── RESULTS.md                  # measured numbers
```

`<tag>` names the run: `48` is 48 slices x 6 s at a 200 Mbps peak (the shape used
for the traffic-generator comparison); `100m`, `500m` and `1g` are 144 slices x 2 s
at 100 Mbps, 500 Mbps and 1 Gbps peaks.

## Reproducing

```bash
# 1. inputs (already committed under input/, regenerate if you want other scales)
cacti-tx-gen extract sim/input/jpnap_sample.png --ix jpnap -o sim/input/ts_jpnap.json
cacti-tx-gen generate sim/input/ts_jpnap.json \
    --peak-rate 200Mbps --interval 1800 --duration 288s -o sim/input/otg_48.yaml
python - <<'PY'
import yaml
cfg = yaml.safe_load(open("sim/input/otg_48.yaml"))
with open("sim/input/sched_48.csv", "w") as f:
    for fl in cfg["flows"]:
        f.write("%d,%s\n" % (fl["rate"]["bps"], fl["duration"]["fixed_seconds"]["seconds"]))
PY

# 2. build and run (ns-3.42, optimized; needs applications/internet/point-to-point)
cp sim/ns3/cacti-replay.cc $NS3/scratch/
cd $NS3 && ./ns3 build cacti-replay
./build/scratch/ns3.42-cacti-replay-optimized \
    --schedule=sim/input/sched_48.csv --out=sim/results/ns3_48.csv --sampleInterval=1.0

# 3. TRex: same config, streams chained so the engine runs the schedule itself
docker run -d --name cacti-trex --privileged fyzhang2001/snappi-trex
python sim/trex/trex-replay.py --config sim/input/otg_48.yaml --mode chained \
    --out sim/results/trex_48.csv

# 4. compare and draw
python sim/analyze.py 48
python sim/plot.py --input                              # the input side on its own
python sim/plot.py 48 --source                          # input vs both outputs
python sim/plot.py 48 --trex                            # TRex alone, and vs the input
python sim/plot.py 48 100m 500m 1g --source --overlay
```

Scenario options: `--schedule`, `--out`, `--protocol` (udp/tcp), `--packetSize`,
`--sampleInterval` (0 = one sample per slice), `--linkFactor`, `--queueSize`.

`trex/trex-replay.py --mode chained` builds one `STLStream` per slice with
`STLTXSingleBurst`, `self_start=False` and `next=<following slice>`, so the whole
schedule runs inside the TRex engine off a single `start()`. `--mode client`
reproduces what `lab/trex/validate.py` does — one flow at a time driven from the
client — for comparison. Neither is needed for ns-3, which gets the time axis
from the scenario itself.

## The input

`input/jpnap_sample.png` is the graph the whole pipeline starts from — a copy of
`tests/fixtures/jpnap_sample.png`, kept here so a run is reproducible from this
directory alone. `results/extract_check.png` lays the extracted waveform over
that PNG's detected plot region, which is the cheapest way to see whether the
extraction is following the right boundary; `results/input_waveform.png` is the
waveform on its own against the max/mean the graph prints in its own stats table.

Two properties of this fixture carry through every measurement below:

- The extracted peak is 4.9% under the stated 4.03 Tb/s and the mean 1.1% under
  the stated 2.71 Tb/s. The replay reproduces the extracted waveform, so it
  inherits that.
- 8 leading and 2 trailing samples come back as 0 bps — pixel columns outside the
  plotted fill — which is where the dead slices at the start and end of every
  replay come from, and why the extracted minimum (0.745 Tb/s against a stated
  1.39) is not usable.

The time axis is the tool's, not the graph's: this graph actually spans 32 h
(06/30 04:00 to 07/01 12:00) while `--scale daily` assumes 24 h. Nothing here
depends on it — `generate --duration` rescales the axis anyway, and the rates are
untouched — but an absolute-time reading of `ts_jpnap.json` would be wrong by a
third.

## Reading the numbers

Two rates are recorded because the OTG `rate.bps` means different things on
either side of the pipeline:

- `goodput_bps` — `PacketSink` payload bytes. ns-3's `OnOffApplication` treats
  `DataRate` as the payload rate, so this is what the schedule asks for and it
  matches to within 0.16% on every run here.
- `wire_bps` — bytes on the receiving `PointToPointNetDevice`, i.e. payload plus
  IP + UDP + PPP (30 B on a 1400 B payload). It sits +2.14% above the scheduled
  number by construction.

A hardware or software traffic generator reads the same `rate.bps` as a frame
rate on the wire, so the same config moves a measurably different number of
application bytes in ns-3 than it does on a generator. Compare against
`goodput_bps` when the question is "how much data did the application move" and
against `wire_bps` when it is "how loaded was the link".

`ns3_<tag>.png` plots the schedule against `goodput_bps` only. Those two are the
same quantity, so the residual there is replay error and nothing else; drawing
`wire_bps` on the same axis would put a constant +2.14% of framing next to it and
invite reading header overhead as error. The wire numbers are in `RESULTS.md`,
in every `ns3_<tag>.csv`, and in the `wire_err_pct` column of
`per_slice_<tag>.csv`.

`source_vs_output_<tag>.png` compares against the *input* rather than against the
schedule, so it has to undo what `generate` did: the source is placed on the
replay axis with sample *k* at the start of slice *k* (the generator holds each
resampled point for one slice — a zero-order hold, which is why the output is a
staircase around the input curve), and the rate scale is recovered by fitting the
schedule to the source rather than by dividing the two peaks. The first and last
live slice are left out of the residual: the extractor returns 0 bps outside the
plotted fill, so a source value interpolated across that edge means nothing.

`trex_<tag>.png` draws the TRex run against the schedule at two granularities at
once: the 0.5 s port-counter samples and the same data averaged per slice. They
sit on top of each other, which is the thing worth seeing — the rate is flat
inside each burst, so the sampling granularity does not change the answer.

TRex's port counters include the 4-byte FCS, which `plot.py` divides out, and its
chained bursts advance on packet count rather than on a wall clock, so the run
drifts by a fixed offset that `plot.py` recovers by cross-correlation and prints
in the legend.

The first and last few slices of every run carry a scheduled rate of 1 bps.
That is not the simulation: the extractor returns 0 bps for the pixel columns
outside the plotted fill at either edge of the source graph, and
`generate_otg_config` floors those at 1 bps. `analyze.py` excludes them.
