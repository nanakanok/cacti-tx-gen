"""Generate OTG config from time-series data."""

from __future__ import annotations

import math


def generate_otg_config(
    timeseries: dict,
    peak_rate_bps: float,
    interval_sec: int = 300,
    total_duration_sec: float | None = None,
    packet_size: int = 1400,
    protocol: str = "udp",
    src_ip: str = "10.0.0.1",
    dst_ip: str = "10.0.0.2",
    src_mac: str = "00:00:01:00:00:01",
    dst_mac: str = "00:00:02:00:00:01",
) -> dict:
    """Generate OTG config YAML from time-series JSON.

    Returns a dict suitable for yaml.dump().
    """
    points = timeseries["points"]
    if not points:
        raise ValueError("No data points in timeseries")

    source_max_bps = max(p["bps"] for p in points)
    if source_max_bps <= 0:
        raise ValueError("All data points are zero")

    scale_factor = peak_rate_bps / source_max_bps

    resampled = _resample_points(points, interval_sec)

    if total_duration_sec is not None:
        original_total = len(resampled) * interval_sec
        time_scale = total_duration_sec / original_total
        slice_duration = interval_sec * time_scale
    else:
        slice_duration = float(interval_sec)

    flows = []
    for i, point in enumerate(resampled):
        rate_bps = point["bps"] * scale_factor
        rate_bps = max(1.0, rate_bps)

        flow = _build_flow(
            index=i,
            rate_bps=rate_bps,
            duration_sec=slice_duration,
            packet_size=packet_size,
            protocol=protocol,
            src_ip=src_ip,
            dst_ip=dst_ip,
            src_mac=src_mac,
            dst_mac=dst_mac,
        )
        flows.append(flow)

    config = {
        "flows": flows,
        "ports": [
            {"name": "tx", "location": "localhost:5555"},
            {"name": "rx", "location": "localhost:5556"},
        ],
    }

    return config


def _resample_points(points: list[dict], interval_sec: int) -> list[dict]:
    """Resample points to uniform interval."""
    if not points:
        return []

    if len(points) == 1:
        return points

    total_duration = points[-1]["t"]
    if total_duration <= 0:
        return [points[0]]

    import numpy as np

    n_samples = int(total_duration / interval_sec) + 1
    t_orig = np.array([p["t"] for p in points])
    bps_orig = np.array([p["bps"] for p in points])

    t_new = np.linspace(0, total_duration, n_samples)
    bps_new = np.interp(t_new, t_orig, bps_orig)

    return [
        {"t": round(float(t), 1), "bps": round(float(b), 0)}
        for t, b in zip(t_new, bps_new)
    ]


def _build_flow(
    index: int,
    rate_bps: float,
    duration_sec: float,
    packet_size: int,
    protocol: str,
    src_ip: str,
    dst_ip: str,
    src_mac: str,
    dst_mac: str,
) -> dict:
    """Build a single OTG flow definition."""
    flow = {
        "name": f"slice_{index:04d}",
        "tx_rx": {
            "port": {
                "tx_name": "tx",
                "rx_name": "rx",
            },
        },
        "rate": {
            "bps": int(rate_bps),
        },
        "duration": {
            "fixed_seconds": {
                "seconds": round(duration_sec, 3),
            },
        },
        "size": {
            "fixed": packet_size,
        },
        "packet": _build_packet_headers(protocol, src_ip, dst_ip, src_mac, dst_mac),
    }
    return flow


def _build_packet_headers(
    protocol: str,
    src_ip: str,
    dst_ip: str,
    src_mac: str,
    dst_mac: str,
) -> list[dict]:
    """Build L2-L4 packet header stack."""
    headers = [
        {
            "ethernet": {
                "dst": {"value": dst_mac},
                "src": {"value": src_mac},
            },
        },
        {
            "ipv4": {
                "src": {"value": src_ip},
                "dst": {"value": dst_ip},
            },
        },
    ]

    if protocol == "udp":
        headers.append({
            "udp": {
                "src_port": {"value": 12000},
                "dst_port": {"value": 12001},
            },
        })
    elif protocol == "tcp":
        headers.append({
            "tcp": {
                "src_port": {"value": 12000},
                "dst_port": {"value": 12001},
            },
        })

    return headers
