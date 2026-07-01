import json
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import click
import requests

from cacti_tx_gen.extract import EXTRACTORS, TimeScale
from cacti_tx_gen.generate.otg import generate_otg_config
from cacti_tx_gen.convert.ns3 import convert_to_ns3

SCALE_CHOICES = [s.value for s in TimeScale]


@click.group()
def main():
    """Generate traffic from IX traffic report graphs via OTG."""


@main.command()
@click.argument("image")
@click.option("-o", "--output", type=click.Path(), default=None,
              help="Output JSON file (default: stdout)")
@click.option("--ix", type=click.Choice(list(EXTRACTORS.keys())),
              default=None, help="IX type (auto-detected if omitted)")
@click.option("--y-max", type=str, default=None,
              help="Y-axis maximum value (e.g., 4Tbps, 8Tbps). Auto-detected if omitted.")
@click.option("--scale", type=click.Choice(SCALE_CHOICES), default=None,
              help="Graph time scale (auto-detected from filename if omitted).")
@click.option("--total-duration", type=str, default=None,
              help="Explicit total duration of graph (e.g., 550d, 27y). Overrides --scale duration.")
@click.option("--series", type=click.Choice(["max", "avg", "min"]), default="avg",
              help="Which series to extract from minmax graphs (default: avg).")
def extract(image, output, ix, y_max, scale, total_duration, series):
    """Extract time-series data from an IX traffic graph image.

    IMAGE can be a local file path or an HTTPS URL.
    Supported scales: daily (24h), weekly (7d), monthly (30d), yearly (365d).
    For JPIX minmax graphs, use --total-duration and --series.
    """
    image_path = _resolve_image(image)
    try:
        if ix is None:
            ix = _detect_ix(image)

        if scale is None:
            scale = _detect_scale(image)
        time_scale = TimeScale(scale)

        y_max_bps = _parse_rate(y_max) if y_max else None
        total_dur_sec = _parse_total_duration(total_duration) if total_duration else None
        extractor = EXTRACTORS[ix](y_max_bps=y_max_bps, scale=time_scale,
                                   total_duration_sec=total_dur_sec, series=series)
        timeseries = extractor.extract(image_path)

        resample_interval = extractor._get_default_resample_interval()
        resampled_points = extractor._resample(timeseries["points"], resample_interval)
        timeseries["points"] = resampled_points
        timeseries["interval_sec"] = resample_interval
        timeseries["scale"] = scale
        if total_dur_sec:
            timeseries["total_duration_sec"] = total_dur_sec
        if series != "avg":
            timeseries["series"] = series

        data = json.dumps(timeseries, indent=2, ensure_ascii=False)
        if output:
            with open(output, "w") as f:
                f.write(data)
            click.echo(f"Wrote {output}")
        else:
            click.echo(data)
    finally:
        if image_path != image:
            Path(image_path).unlink(missing_ok=True)


@main.command()
@click.argument("timeseries", type=click.Path(exists=True))
@click.option("-o", "--output", type=click.Path(), default=None,
              help="Output OTG YAML file (default: stdout)")
@click.option("--peak-rate", type=str, required=True,
              help="Target peak rate (e.g., 10Gbps, 1Gbps)")
@click.option("--interval", type=int, default=300,
              help="Time slice interval in seconds (default: 300)")
@click.option("--duration", type=str, default=None,
              help="Compress total replay to this duration (e.g., 1h, 30m)")
@click.option("--packet-size", type=int, default=1400,
              help="Packet size in bytes (default: 1400)")
@click.option("--protocol", type=click.Choice(["udp", "tcp"]), default="udp",
              help="L4 protocol (default: udp)")
@click.option("--src-ip", type=str, default="10.0.0.1",
              help="Source IP address")
@click.option("--dst-ip", type=str, default="10.0.0.2",
              help="Destination IP address")
def generate(timeseries, output, peak_rate, interval, duration,
             packet_size, protocol, src_ip, dst_ip):
    """Generate OTG config from time-series JSON."""
    with open(timeseries) as f:
        ts_data = json.load(f)

    peak_rate_bps = _parse_rate(peak_rate)
    duration_sec = _parse_duration(duration) if duration else None

    config = generate_otg_config(
        ts_data,
        peak_rate_bps=peak_rate_bps,
        interval_sec=interval,
        total_duration_sec=duration_sec,
        packet_size=packet_size,
        protocol=protocol,
        src_ip=src_ip,
        dst_ip=dst_ip,
    )

    import yaml
    data = yaml.dump(config, default_flow_style=False, allow_unicode=True)
    if output:
        with open(output, "w") as f:
            f.write(data)
        click.echo(f"Wrote {output}")
    else:
        click.echo(data)


@main.command("convert-ns3")
@click.argument("otg_config", type=click.Path(exists=True))
@click.option("-o", "--output", type=click.Path(), default=None,
              help="Output NS3 Python scenario (default: stdout)")
def convert_ns3_cmd(otg_config, output):
    """Convert OTG config to NS3 scenario script."""
    import yaml
    with open(otg_config) as f:
        config = yaml.safe_load(f)

    script = convert_to_ns3(config)
    if output:
        with open(output, "w") as f:
            f.write(script)
        click.echo(f"Wrote {output}")
    else:
        click.echo(script)


def _resolve_image(image: str) -> str:
    """Download image to a temp file if it's a URL, otherwise return as-is."""
    parsed = urlparse(image)
    if parsed.scheme in ("http", "https"):
        resp = requests.get(image, timeout=30)
        resp.raise_for_status()
        suffix = Path(parsed.path).suffix or ".png"
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        tmp.write(resp.content)
        tmp.close()
        click.echo(f"Downloaded {image} ({len(resp.content)} bytes)")
        return tmp.name
    if not Path(image).exists():
        raise click.ClickException(f"File not found: {image}")
    return image


def _detect_scale(image: str) -> str:
    """Auto-detect graph time scale from filename or URL."""
    name = Path(urlparse(image).path).name.lower()
    if name.endswith("_w.png"):
        return "weekly"
    if name.endswith("_m.png"):
        return "monthly"
    if name.endswith(("_y.png", "_year.png")):
        return "yearly"
    if "_year" in name or "_history" in name:
        return "yearly"
    return "daily"


def _detect_ix(image_path: str) -> str:
    """Auto-detect IX type from filename."""
    name = image_path.lower()
    for ix_name in EXTRACTORS:
        if ix_name in name:
            return ix_name
    raise click.ClickException(
        f"Cannot auto-detect IX type from '{image_path}'. Use --ix option.")


def _parse_rate(rate_str: str) -> float:
    """Parse rate string like '10Gbps' to bps."""
    rate_str = rate_str.strip().lower()
    multipliers = {
        "tbps": 1e12, "tb/s": 1e12,
        "gbps": 1e9,  "gb/s": 1e9,
        "mbps": 1e6,  "mb/s": 1e6,
        "kbps": 1e3,  "kb/s": 1e3,
        "bps": 1,     "b/s": 1,
    }
    for suffix, mult in multipliers.items():
        if rate_str.endswith(suffix):
            return float(rate_str[: -len(suffix)]) * mult
    raise click.ClickException(f"Cannot parse rate '{rate_str}'")


def _parse_duration(dur_str: str) -> float:
    """Parse duration string like '1h', '30m', '10s' to seconds."""
    dur_str = dur_str.strip().lower()
    multipliers = {"h": 3600, "m": 60, "s": 1}
    for suffix, mult in multipliers.items():
        if dur_str.endswith(suffix):
            return float(dur_str[: -len(suffix)]) * mult
    return float(dur_str)


def _parse_total_duration(dur_str: str) -> float:
    """Parse total duration like '550d', '18mo', '27y', '2y6mo' to seconds."""
    import re
    dur_str = dur_str.strip().lower()
    total = 0.0
    for match in re.finditer(r"([\d.]+)\s*(y|mo|d|h)", dur_str):
        val = float(match.group(1))
        unit = match.group(2)
        if unit == "y":
            total += val * 365 * 86400
        elif unit == "mo":
            total += val * 30 * 86400
        elif unit == "d":
            total += val * 86400
        elif unit == "h":
            total += val * 3600
    if total > 0:
        return total
    try:
        return float(dur_str)
    except ValueError:
        raise click.ClickException(f"Cannot parse total duration '{dur_str}'")
