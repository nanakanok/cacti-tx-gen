#!/usr/bin/env python3
"""Validate cacti-tx-gen OTG config against TRex.

Runs TRex STL API from inside the container (avoids Python version conflicts).
Generates a TRex script, copies it into the container, and executes it.
Optionally captures per-second stats and generates a traffic graph.

Usage:
    python validate.py [--container NAME] [--otg-config PATH] [--graph results.png]
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Validate OTG config on TRex")
    parser.add_argument("--container", default="clab-cacti-trex-trex",
                        help="TRex container name")
    parser.add_argument("--otg-config", default=None,
                        help="OTG config YAML")
    parser.add_argument("--max-flows", type=int, default=5,
                        help="Max flows to validate")
    parser.add_argument("--graph", default=None,
                        help="Output graph filename (e.g. results.png)")
    args = parser.parse_args()

    if args.otg_config:
        import yaml
        with open(args.otg_config) as f:
            otg_config = yaml.safe_load(f)
    else:
        otg_config = _sample_config()

    flows = otg_config["flows"][:args.max_flows]
    print(f"Validating {len(flows)} flows on TRex ({args.container})")

    script = _generate_trex_script(flows)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
        tmp.write(script)
        tmp_path = tmp.name

    try:
        subprocess.run(
            ["docker", "cp", tmp_path, f"{args.container}:/tmp/validate_trex.py"],
            check=True, capture_output=True,
        )

        result = subprocess.run(
            ["docker", "exec", args.container,
             "python3", "/tmp/validate_trex.py"],
            capture_output=True, text=True, timeout=180,
        )

        timeseries = None
        for line in result.stdout.splitlines():
            if line.startswith("TIMESERIES:"):
                timeseries = json.loads(line[len("TIMESERIES:"):])
            else:
                print(line)

        if result.stderr:
            print(result.stderr, file=sys.stderr)

        if result.returncode != 0:
            print("FAIL", file=sys.stderr)
            sys.exit(1)

        if args.graph and timeseries:
            _plot(timeseries, args.graph)

    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _plot(timeseries, output_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t = [p["t"] for p in timeseries]
    tx_bps = [p["tx_bps"] for p in timeseries]
    rx_bps = [p["rx_bps"] for p in timeseries]

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(t, tx_bps, label="TX (bps)", color="tab:blue", linewidth=1.5)
    ax.plot(t, rx_bps, label="RX (bps)", color="tab:green", linewidth=1.5)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Rate (bps)")
    ax.set_title("TRex Traffic Validation")
    ax.legend()
    ax.grid(True, alpha=0.3)

    max_val = max(max(tx_bps, default=0), max(rx_bps, default=0))
    if max_val >= 1e6:
        ax.set_ylabel("Rate (Mbps)")
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v/1e6:.1f}"))
    elif max_val >= 1e3:
        ax.set_ylabel("Rate (Kbps)")
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v/1e3:.1f}"))

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    print(f"Graph saved: {output_path}")
    plt.close(fig)


def _generate_trex_script(flows):
    flow_defs = []
    for i, f in enumerate(flows):
        rate_bps = max(1000, int(f["rate"]["bps"]))
        duration = max(1.0, min(f["duration"]["fixed_seconds"]["seconds"], 10.0))
        pkt_size = f["size"]["fixed"]

        src_ip = "10.0.0.1"
        dst_ip = "10.0.0.2"
        src_port = 12000
        dst_port = 12001
        proto = "udp"

        for hdr in f.get("packet", []):
            if "ipv4" in hdr:
                src_ip = hdr["ipv4"]["src"]["value"]
                dst_ip = hdr["ipv4"]["dst"]["value"]
            if "udp" in hdr:
                proto = "udp"
                src_port = hdr["udp"]["src_port"]["value"]
                dst_port = hdr["udp"]["dst_port"]["value"]
            if "tcp" in hdr:
                proto = "tcp"
                src_port = hdr["tcp"]["src_port"]["value"]
                dst_port = hdr["tcp"]["dst_port"]["value"]

        flow_defs.append({
            "name": f["name"],
            "rate_bps": rate_bps,
            "duration": duration,
            "pkt_size": pkt_size,
            "src_ip": src_ip,
            "dst_ip": dst_ip,
            "src_port": src_port,
            "dst_port": dst_port,
            "proto": proto,
        })

    flows_json = json.dumps(flow_defs)

    return (
        '#!/usr/bin/env python3\n'
        'import sys, time, json\n'
        'sys.path.insert(0, "/v2.90/automation/trex_control_plane/interactive")\n'
        'import os\n'
        'os.environ["TREX_EXT_LIBS"] = "/v2.90/external_libs"\n'
        '\n'
        'from trex.stl.api import *\n'
        '\n'
        'FLOWS = json.loads(\'' + flows_json + '\')\n'
        '\n'
        'def run():\n'
        '    c = STLClient(server="127.0.0.1")\n'
        '    timeseries = []\n'
        '    try:\n'
        '        c.connect()\n'
        '        c.reset()\n'
        '        print("Connected to TRex, ports: " + str(c.get_all_ports()))\n'
        '\n'
        '        total_tx = 0\n'
        '        t0 = time.time()\n'
        '\n'
        '        for i, fd in enumerate(FLOWS):\n'
        '            if fd["proto"] == "udp":\n'
        '                l4 = UDP(sport=fd["src_port"], dport=fd["dst_port"])\n'
        '            else:\n'
        '                l4 = TCP(sport=fd["src_port"], dport=fd["dst_port"])\n'
        '\n'
        '            pkt = STLPktBuilder(\n'
        '                pkt=Ether() / IP(src=fd["src_ip"], dst=fd["dst_ip"]) / l4 / ("X" * max(1, fd["pkt_size"] - 42))\n'
        '            )\n'
        '\n'
        '            pps = max(1, int(fd["rate_bps"] / (fd["pkt_size"] * 8)))\n'
        '            total_pkts = max(1, int(pps * fd["duration"]))\n'
        '            stream = STLStream(\n'
        '                packet=pkt,\n'
        '                mode=STLTXSingleBurst(pps=pps, total_pkts=total_pkts),\n'
        '            )\n'
        '\n'
        '            c.remove_all_streams(ports=[0])\n'
        '            c.add_streams(stream, ports=[0])\n'
        '            c.clear_stats()\n'
        '            c.start(ports=[0])\n'
        '\n'
        '            while c.is_traffic_active():\n'
        '                time.sleep(1.0)\n'
        '                s = c.get_stats()\n'
        '                tx_bps = s[0].get("tx_bps", 0)\n'
        '                rx_bps = s[1].get("rx_bps", 0)\n'
        '                elapsed = round(time.time() - t0, 1)\n'
        '                timeseries.append({"t": elapsed, "tx_bps": tx_bps, "rx_bps": rx_bps})\n'
        '\n'
        '            stats = c.get_stats()\n'
        '            tx_pkts = stats[0].get("opackets", 0)\n'
        '            rx_pkts = stats[1].get("ipackets", 0)\n'
        '            total_tx += tx_pkts\n'
        '            print("  Flow %d (%s): tx=%d rx=%d rate=%dbps" % (i, fd["name"], tx_pkts, rx_pkts, fd["rate_bps"]))\n'
        '\n'
        '        if total_tx > 0:\n'
        '            print("PASS: %d total frames transmitted" % total_tx)\n'
        '        else:\n'
        '            print("FAIL: no frames transmitted")\n'
        '            sys.exit(1)\n'
        '\n'
        '    finally:\n'
        '        print("TIMESERIES:" + json.dumps(timeseries))\n'
        '        c.disconnect()\n'
        '\n'
        'if __name__ == "__main__":\n'
        '    run()\n'
    )


def _sample_config():
    return {
        "flows": [
            {
                "name": "test_flow_0",
                "rate": {"bps": 1000000},
                "duration": {"fixed_seconds": {"seconds": 5.0}},
                "size": {"fixed": 512},
                "packet": [
                    {"ethernet": {"dst": {"value": "00:00:02:00:00:01"}, "src": {"value": "00:00:01:00:00:01"}}},
                    {"ipv4": {"src": {"value": "10.0.0.1"}, "dst": {"value": "10.0.0.2"}}},
                    {"udp": {"src_port": {"value": 12000}, "dst_port": {"value": 12001}}},
                ],
            },
        ],
    }


if __name__ == "__main__":
    main()
