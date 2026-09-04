# Replay results — ns-3 and TRex

Source: `tests/fixtures/jpnap_sample.png` (JPNAP Tokyo Total, daily, stated
max 4.03 Tb/s / mean 2.71 Tb/s). Extracted with `cacti-tx-gen extract`, scaled by
`cacti-tx-gen generate`, replayed by `ns3/cacti-replay.cc` on ns-3.42 (optimized).
Frame payload 1400 B, UDP, link = 2 x peak slice rate, 1 ms delay,
DropTail 1000p. Regenerate every number below with `python sim/analyze.py`.

## Per-slice rate and total volume

`err` is per-slice measured vs scheduled rate, over the slices carrying a real
rate (the 1 bps edge slices are excluded — see README).

| run | slices | slice | peak | live | goodput err mean / max | wire err mean | corr |
|---|---|---|---|---|---|---|---|
| `48`   | 48  | 6.0 s | 198.78 Mbps | 45/48   | −0.001% / 0.018% | +2.142% | 1.000000 |
| `100m` | 144 | 2.0 s |  99.56 Mbps | 139/144 | −0.004% / 0.149% | +2.139% | 1.000000 |
| `500m` | 144 | 2.0 s | 497.79 Mbps | 139/144 | −0.000% / 0.155% | +2.143% | 1.000000 |
| `1g`   | 144 | 2.0 s | 995.59 Mbps | 139/144 | +0.000% / 0.155% | +2.143% | 1.000000 |

| run | scheduled volume | PacketSink goodput | wire bytes | packets |
|---|---|---|---|---|
| `48`   |  4.7453 GB |  4.7452 GB (−0.0007%) |  4.8469 GB (+2.142%) |  3,389,448 |
| `100m` |  2.4214 GB |  2.4213 GB (−0.0039%) |  2.4732 GB (+2.139%) |  1,729,498 |
| `500m` | 12.1070 GB | 12.1069 GB (−0.0007%) | 12.3663 GB (+2.142%) |  8,647,760 |
| `1g`   | 24.2139 GB | 24.2138 GB (−0.0004%) | 24.7327 GB (+2.143%) | 17,295,582 |

No drops in any run: the link is provisioned at twice the peak slice rate, so the
device queue never builds.

## Input vs output

The tables above compare the output against the *schedule*. The question the
pipeline actually has to answer is whether the output matches the *input* — the
waveform read off the source PNG. `source_vs_output_<tag>.png` draws both;
`python sim/plot.py <tag> --source` prints the numbers.

Sampled at the instant `generate` sampled the source, over the live slices
(first and last excluded — see README):

| run | ns-3 vs input | TRex vs input |
|---|---|---|
| `48`   | r = 1.000000, median −0.00%, max 0.00%, RMSE 0.003 Mbps | r = 0.999962, median −0.00%, max 0.83%, RMSE 0.321 Mbps |
| `100m` | r = 1.000000, median −0.00%, max 0.02%, RMSE 0.004 Mbps | — |
| `500m` | r = 1.000000, median −0.00%, max 0.01%, RMSE 0.008 Mbps | — |
| `1g`   | r = 1.000000, median −0.00%, max 0.01%, RMSE 0.018 Mbps | — |

ns-3 lands on the input exactly: the residual is a flat line at zero, because
`OnOffApplication` holds the requested payload rate for the whole slice and the
link is provisioned at twice the peak, so nothing queues or drops. TRex stays
within ±0.83% of it on real interfaces.

The staircase in the figure is not error. `generate` resamples the source to one
point per slice and holds it — a zero-order hold — so the output is a staircase
around a curve by construction. How closely the staircase follows depends on the
slice count, which is a `--interval` choice, not a property of ns-3 or TRex.

## TRex

`sim/trex/trex-replay.py --mode chained` on TRex 2.90, same `otg_48.yaml`,
veth pair inside the container:

| | value |
|---|---|
| per-slice rate error | median −0.01%, max 0.98% |
| correlation with schedule | 0.999942 |
| packets transmitted | 3,389,508 vs 3,389,500 scheduled (+0.0002%) |
| loss | none (`ipackets == opackets`) |
| volume | 4.7446 GB vs 4.7453 GB scheduled (−0.01%) |
| timeline | runs 1.7 s early over 288 s |

The 1.7 s is structural, not jitter: a chained `STLTXSingleBurst` advances when
it has sent `total_pkts`, not when a wall clock says to. The slices the extractor
floored at 1 bps get `pps` rounded up to 1 and finish ahead of their nominal 6 s,
and everything after them shifts. Dropping the dead edge slices, or driving the
schedule from a time-based mode, removes it.

TRex needs no `Σ slice rate ≤ line rate` headroom the way an OTG controller does,
because only one stream is live at a time — the 200 Mbps peak config loads
unchanged.

## What this does and does not show

Reproduced: the OTG schedule, and through it the input waveform. ns-3 places
every slice at its scheduled rate and delivers the scheduled number of bytes, at
every scale tested, with the shape correlation at the floating-point limit. Peak
error stays under 0.01% and the worst single slice is 0.16% off. TRex reproduces
the same schedule on real interfaces to within 1%.

Not reproduced by ns-3, because it is lost upstream: the extraction is only as
good as the pixels. Against the values printed on the source graph, the extracted
series gives max 3.834 Tb/s (−4.9%) and mean 2.681 Tb/s (−1.1%) over its valid
samples, and the shape ratio mean/max lands at 0.6995 against the graph's 0.6725.
The 8 leading and 2 trailing samples come back as 0 bps, so the extracted minimum
is meaningless (0.745 vs 1.39 Tb/s stated) and the replay opens and closes with
idle slices. Whatever ns-3 reproduces, it reproduces that.

## Relation to the existing tests

`tests/test_convert.py::TestPipelineRoundTrip` correlates the *schedule text*
parsed out of the generated scenario against the extracted timeseries. It never
builds or runs ns-3. These runs close that gap by measuring what the simulator
actually transmits.
