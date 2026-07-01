"""Tests for NS3 conversion."""

import re
from pathlib import Path

import numpy as np
import pytest

from cacti_tx_gen.convert.ns3 import convert_to_ns3
from cacti_tx_gen.extract.jpix import JPIXExtractor
from cacti_tx_gen.extract.bbix import BBIXExtractor
from cacti_tx_gen.extract.jpnap import JPNAPExtractor
from cacti_tx_gen.extract.base import TimeScale
from cacti_tx_gen.generate.otg import generate_otg_config

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_otg_config():
    return {
        "flows": [
            {
                "name": "slice_0000",
                "tx_rx": {"port": {"tx_name": "tx", "rx_name": "rx"}},
                "rate": {"bps": 5000000000},
                "duration": {"fixed_seconds": {"seconds": 10.0}},
                "size": {"fixed": 1400},
                "packet": [
                    {"ethernet": {
                        "dst": {"value": "00:00:02:00:00:01"},
                        "src": {"value": "00:00:01:00:00:01"},
                    }},
                    {"ipv4": {
                        "src": {"value": "10.0.0.1"},
                        "dst": {"value": "10.0.0.2"},
                    }},
                    {"udp": {
                        "src_port": {"value": 12000},
                        "dst_port": {"value": 12001},
                    }},
                ],
            },
            {
                "name": "slice_0001",
                "tx_rx": {"port": {"tx_name": "tx", "rx_name": "rx"}},
                "rate": {"bps": 10000000000},
                "duration": {"fixed_seconds": {"seconds": 10.0}},
                "size": {"fixed": 1400},
                "packet": [
                    {"ethernet": {
                        "dst": {"value": "00:00:02:00:00:01"},
                        "src": {"value": "00:00:01:00:00:01"},
                    }},
                    {"ipv4": {
                        "src": {"value": "10.0.0.1"},
                        "dst": {"value": "10.0.0.2"},
                    }},
                    {"udp": {
                        "src_port": {"value": 12000},
                        "dst_port": {"value": 12001},
                    }},
                ],
            },
        ],
        "ports": [
            {"name": "tx", "location": "localhost:5555"},
            {"name": "rx", "location": "localhost:5556"},
        ],
    }


class TestConvertToNs3:
    def test_generates_valid_python(self, sample_otg_config):
        script = convert_to_ns3(sample_otg_config)
        compile(script, "<ns3_scenario>", "exec")

    def test_contains_schedule(self, sample_otg_config):
        script = convert_to_ns3(sample_otg_config)

        assert "SCHEDULE" in script
        assert "(5000000000, 10.000)" in script
        assert "(10000000000, 10.000)" in script

    def test_contains_ip_addresses(self, sample_otg_config):
        script = convert_to_ns3(sample_otg_config)

        assert 'SRC_IP = "10.0.0.1"' in script
        assert 'DST_IP = "10.0.0.2"' in script

    def test_contains_protocol(self, sample_otg_config):
        script = convert_to_ns3(sample_otg_config)

        assert 'PROTOCOL = "udp"' in script

    def test_tcp_protocol(self, sample_otg_config):
        for flow in sample_otg_config["flows"]:
            flow["packet"] = [
                h for h in flow["packet"] if "udp" not in h
            ] + [{"tcp": {"src_port": {"value": 80}, "dst_port": {"value": 80}}}]

        script = convert_to_ns3(sample_otg_config)
        assert 'PROTOCOL = "tcp"' in script

    def test_contains_ns3_imports(self, sample_otg_config):
        script = convert_to_ns3(sample_otg_config)

        assert "import ns.core" in script
        assert "import ns.network" in script
        assert "import ns.applications" in script

    def test_contains_main_function(self, sample_otg_config):
        script = convert_to_ns3(sample_otg_config)

        assert "def main():" in script
        assert 'if __name__ == "__main__":' in script

    def test_link_speed_auto_calculated(self, sample_otg_config):
        script = convert_to_ns3(sample_otg_config)
        assert "LINK_SPEED" in script

    def test_empty_flows_raises(self):
        with pytest.raises(ValueError):
            convert_to_ns3({"flows": []})

    def test_packet_size_in_output(self, sample_otg_config):
        script = convert_to_ns3(sample_otg_config)
        assert "PACKET_SIZE = 1400" in script


def _parse_ns3_schedule(script: str) -> list[tuple[int, float]]:
    """Extract SCHEDULE entries from NS3 script as [(rate_bps, duration), ...]."""
    m = re.search(r"SCHEDULE\s*=\s*\[(.*?)\]", script, re.DOTALL)
    assert m, "SCHEDULE not found in NS3 script"
    return [(int(r), float(d)) for r, d in re.findall(r"\((\d+),\s*([\d.]+)\)", m.group(1))]


def _schedule_to_timeseries(schedule: list[tuple[int, float]]) -> tuple[list[float], list[float]]:
    """Convert SCHEDULE to (times, rates) arrays at each slice midpoint."""
    times, rates = [], []
    t = 0.0
    for rate, dur in schedule:
        times.append(t + dur / 2)
        rates.append(float(rate))
        t += dur
    return times, rates


def _correlation(a: list[float], b: list[float]) -> float:
    """Pearson correlation coefficient between two sequences."""
    a_arr = np.array(a)
    b_arr = np.array(b)
    if len(a_arr) != len(b_arr) or len(a_arr) < 2:
        return 0.0
    a_norm = a_arr - a_arr.mean()
    b_norm = b_arr - b_arr.mean()
    denom = np.sqrt(np.sum(a_norm ** 2) * np.sum(b_norm ** 2))
    if denom == 0:
        return 1.0
    return float(np.sum(a_norm * b_norm) / denom)


class TestPipelineRoundTrip:
    """End-to-end: extract → OTG generate → NS3 convert → verify shape match."""

    def _run_pipeline(self, extractor, image_name, peak_rate=10e9, interval=300):
        result = extractor.extract(str(FIXTURES / image_name))
        resampled = extractor._resample(result["points"],
                                        extractor._get_default_resample_interval())
        ts = {**result, "points": resampled,
              "interval_sec": extractor._get_default_resample_interval()}
        otg = generate_otg_config(ts, peak_rate_bps=peak_rate, interval_sec=interval)
        script = convert_to_ns3(otg)
        compile(script, "<ns3_scenario>", "exec")
        schedule = _parse_ns3_schedule(script)
        return ts, otg, schedule

    def test_jpix_daily_shape(self):
        ext = JPIXExtractor(y_max_bps=4.0e12)
        ts, otg, schedule = self._run_pipeline(ext, "jpix_sample.png")

        source_bps = [p["bps"] for p in ts["points"]]
        _, sched_rates = _schedule_to_timeseries(schedule)
        corr = _correlation(
            np.interp(np.linspace(0, 1, 50), np.linspace(0, 1, len(source_bps)), source_bps),
            np.interp(np.linspace(0, 1, 50), np.linspace(0, 1, len(sched_rates)), sched_rates),
        )
        assert corr > 0.95, f"Shape correlation {corr:.3f} too low"

    def test_bbix_daily_shape(self):
        ext = BBIXExtractor()
        ts, otg, schedule = self._run_pipeline(ext, "bbix_sample.png")

        source_bps = [p["bps"] for p in ts["points"]]
        _, sched_rates = _schedule_to_timeseries(schedule)
        corr = _correlation(
            np.interp(np.linspace(0, 1, 50), np.linspace(0, 1, len(source_bps)), source_bps),
            np.interp(np.linspace(0, 1, 50), np.linspace(0, 1, len(sched_rates)), sched_rates),
        )
        assert corr > 0.95, f"Shape correlation {corr:.3f} too low"

    def test_jpnap_daily_shape(self):
        ext = JPNAPExtractor()
        ts, otg, schedule = self._run_pipeline(ext, "jpnap_sample.png")

        source_bps = [p["bps"] for p in ts["points"]]
        _, sched_rates = _schedule_to_timeseries(schedule)
        corr = _correlation(
            np.interp(np.linspace(0, 1, 50), np.linspace(0, 1, len(source_bps)), source_bps),
            np.interp(np.linspace(0, 1, 50), np.linspace(0, 1, len(sched_rates)), sched_rates),
        )
        assert corr > 0.95, f"Shape correlation {corr:.3f} too low"

    def test_jpnap_yearly_max_shape(self):
        ext = JPNAPExtractor(scale=TimeScale.YEARLY, series="max")
        ts, otg, schedule = self._run_pipeline(ext, "jpnap_yearly_sample.png",
                                               interval=86400)

        source_bps = [p["bps"] for p in ts["points"]]
        _, sched_rates = _schedule_to_timeseries(schedule)
        corr = _correlation(
            np.interp(np.linspace(0, 1, 50), np.linspace(0, 1, len(source_bps)), source_bps),
            np.interp(np.linspace(0, 1, 50), np.linspace(0, 1, len(sched_rates)), sched_rates),
        )
        assert corr > 0.90, f"Shape correlation {corr:.3f} too low"

    def test_jpix_minmax_avg_shape(self):
        ext = JPIXExtractor(y_max_bps=5.0e12, total_duration_sec=550 * 86400, series="avg")
        ts, otg, schedule = self._run_pipeline(ext, "jpix_minmax_sample.png",
                                               interval=86400)

        source_bps = [p["bps"] for p in ts["points"]]
        _, sched_rates = _schedule_to_timeseries(schedule)
        corr = _correlation(
            np.interp(np.linspace(0, 1, 50), np.linspace(0, 1, len(source_bps)), source_bps),
            np.interp(np.linspace(0, 1, 50), np.linspace(0, 1, len(sched_rates)), sched_rates),
        )
        assert corr > 0.90, f"Shape correlation {corr:.3f} too low"

    def test_peak_rate_scaling(self):
        """NS3 schedule peak should match the requested peak rate."""
        ext = JPIXExtractor(y_max_bps=4.0e12)
        _, _, schedule = self._run_pipeline(ext, "jpix_sample.png", peak_rate=1e9)
        max_rate = max(r for r, _ in schedule)
        assert max_rate == pytest.approx(1e9, rel=0.01)

    def test_schedule_covers_full_duration(self):
        """NS3 schedule total duration should match the source time span."""
        ext = BBIXExtractor()
        ts, _, schedule = self._run_pipeline(ext, "bbix_sample.png")
        sched_total = sum(d for _, d in schedule)
        source_total = ts["points"][-1]["t"]
        assert sched_total == pytest.approx(source_total, rel=0.05)

    def test_all_rates_positive(self):
        """Every NS3 schedule entry should have a positive rate."""
        ext = JPNAPExtractor()
        _, _, schedule = self._run_pipeline(ext, "jpnap_sample.png")
        for rate, dur in schedule:
            assert rate >= 1
            assert dur > 0
