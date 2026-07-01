import json
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import click
import requests

from cacti_tx_gen.extract import EXTRACTORS
from cacti_tx_gen.generate.otg import generate_otg_config
from cacti_tx_gen.convert.ns3 import convert_to_ns3


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
def extract(image, output, ix, y_max):
    """Extract time-series data from an IX traffic graph image.

    IMAGE can be a local file path or an HTTPS URL.
    """
    image_path = _resolve_image(image)
    try:
        if ix is None:
            ix = _detect_ix(image)

        y_max_bps = _parse_rate(y_max) if y_max else None
        extractor = EXTRACTORS[ix](y_max_bps=y_max_bps)
        timeseries = extractor.extract(image_path)

        resampled_points = extractor._resample(timeseries["points"], 300)
        timeseries["points"] = resampled_points
        timeseries["interval_sec"] = 300

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
