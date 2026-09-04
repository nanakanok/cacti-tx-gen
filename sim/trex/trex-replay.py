#!/usr/bin/env python3
"""Replay a cacti-tx-gen OTG config on TRex.

Two ways to give the config a time axis:
  --mode chained    one STLStream per slice, chained with next=/self_start=False,
                    so the TRex engine itself runs the schedule (no client round-trips)
  --mode client     start one flow at a time from the client (what lab/trex/validate.py does)
Samples per-port stats while traffic runs and writes a rate CSV.
"""
import argparse, json, subprocess, sys, tempfile
from pathlib import Path
import yaml

ap = argparse.ArgumentParser()
ap.add_argument("--container", default="cacti-trex")
ap.add_argument("--config", required=True)
ap.add_argument("--mode", choices=["chained", "client"], default="chained")
ap.add_argument("--out", required=True)
args = ap.parse_args()

otg = yaml.safe_load(open(args.config))
flows = []
for f in otg["flows"]:
    flows.append({"name": f["name"], "rate_bps": int(f["rate"]["bps"]),
                  "dur": f["duration"]["fixed_seconds"]["seconds"],
                  "size": f["size"]["fixed"]})
total = sum(f["dur"] for f in flows)
print("flows=%d mode=%s total=%.1fs peak=%.1f Mbps"
      % (len(flows), args.mode, total, max(f["rate_bps"] for f in flows) / 1e6))

script = '''#!/usr/bin/env python3
import sys, os, time, json
sys.path.insert(0, "/v2.90/automation/trex_control_plane/interactive")
os.environ["TREX_EXT_LIBS"] = "/v2.90/external_libs"
from trex.stl.api import *

FLOWS = json.loads(r\'\'\'%s\'\'\')
MODE = "%s"
SAMPLE = 0.5

def pkt(size):
    return STLPktBuilder(pkt=Ether() / IP(src="10.0.0.1", dst="10.0.0.2")
                         / UDP(sport=12000, dport=12001) / ("X" * max(1, size - 42)))

def run():
    c = STLClient(server="127.0.0.1")
    c.connect(); c.reset(ports=[0, 1])
    c.set_port_attr(ports=[0, 1], promiscuous=True)
    series = []

    streams = []
    for i, f in enumerate(FLOWS):
        pps = max(1, int(round(f["rate_bps"] / (f["size"] * 8))))
        total_pkts = max(1, int(round(pps * f["dur"])))
        kw = dict(name=f["name"], packet=pkt(f["size"]),
                  mode=STLTXSingleBurst(pps=pps, total_pkts=total_pkts))
        if MODE == "chained":
            kw["self_start"] = (i == 0)
            if i + 1 < len(FLOWS):
                kw["next"] = FLOWS[i + 1]["name"]
        streams.append(STLStream(**kw))

    nominal = sum(f["dur"] for f in FLOWS)
    c.clear_stats()
    t0 = time.time()
    if MODE == "chained":
        c.add_streams(streams, ports=[0])
        c.start(ports=[0])
        prev = (0.0, 0, 0)
        while time.time() - t0 < nominal + 4:
            time.sleep(SAMPLE)
            s = c.get_stats()
            now = time.time() - t0
            tx = s[0].get("obytes", 0); rx = s[1].get("ibytes", 0)
            dt = now - prev[0]
            if dt > 0:
                series.append({"t": round(now, 3),
                               "tx_bps": round((tx - prev[1]) * 8 / dt, 1),
                               "rx_bps": round((rx - prev[2]) * 8 / dt, 1)})
            prev = (now, tx, rx)
    else:
        prev = (0.0, 0, 0)
        for i, f in enumerate(FLOWS):
            c.remove_all_streams(ports=[0])
            c.add_streams(streams[i], ports=[0])
            c.start(ports=[0])
            target = t0 + sum(g["dur"] for g in FLOWS[:i + 1])
            while time.time() < target:
                time.sleep(min(SAMPLE, max(0.02, target - time.time())))
                s = c.get_stats()
                now = time.time() - t0
                tx = s[0].get("obytes", 0); rx = s[1].get("ibytes", 0)
                dt = now - prev[0]
                if dt > 0:
                    series.append({"t": round(now, 3),
                                   "tx_bps": round((tx - prev[1]) * 8 / dt, 1),
                                   "rx_bps": round((rx - prev[2]) * 8 / dt, 1)})
                prev = (now, tx, rx)
    wall = time.time() - t0
    s = c.get_stats()
    print("WALL:%%.3f" %% wall)
    print("TOTAL:%%s" %% json.dumps({"opackets": s[0].get("opackets", 0),
                                    "ipackets": s[1].get("ipackets", 0),
                                    "obytes": s[0].get("obytes", 0),
                                    "ibytes": s[1].get("ibytes", 0)}))
    print("SERIES:%%s" %% json.dumps(series))
    c.disconnect()

run()
''' % (json.dumps(flows), args.mode)

tmp = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False)
tmp.write(script); tmp.close()
subprocess.run(["docker", "cp", tmp.name, f"{args.container}:/tmp/trex_run.py"], check=True,
               capture_output=True)
r = subprocess.run(["docker", "exec", args.container, "python3", "/tmp/trex_run.py"],
                   capture_output=True, text=True, timeout=int(total) + 180)
series = None; totals = None; wall = None
for line in r.stdout.splitlines():
    if line.startswith("SERIES:"):
        series = json.loads(line[7:])
    elif line.startswith("TOTAL:"):
        totals = json.loads(line[6:])
    elif line.startswith("WALL:"):
        wall = float(line[5:])
    else:
        print(line)
if r.returncode != 0:
    print(r.stderr[-2000:], file=sys.stderr); sys.exit(1)
print("wall=%.2fs (nominal %.1fs)" % (wall, total))
print("totals:", totals)
import csv
with open(args.out, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["t", "tx_bps", "rx_bps"]); w.writeheader(); w.writerows(series)
print("wrote", args.out)
Path(tmp.name).unlink(missing_ok=True)
