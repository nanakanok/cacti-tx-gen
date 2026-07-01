"""Tests for OTG config generation."""

import pytest

from cacti_tx_gen.generate.otg import generate_otg_config


@pytest.fixture
def sample_timeseries():
    return {
        "source": "test",
        "unit": "bps",
        "interval_sec": 300,
        "y_axis_max_bps": 1e12,
        "points": [
            {"t": 0, "bps": 1e12},
            {"t": 300, "bps": 2e12},
            {"t": 600, "bps": 3e12},
            {"t": 900, "bps": 2e12},
            {"t": 1200, "bps": 1e12},
        ],
    }


class TestGenerateOtgConfig:
    def test_basic_generation(self, sample_timeseries):
        config = generate_otg_config(
            sample_timeseries, peak_rate_bps=10e9
        )

        assert "flows" in config
        assert "ports" in config
        assert len(config["flows"]) > 0

    def test_flow_structure(self, sample_timeseries):
        config = generate_otg_config(
            sample_timeseries, peak_rate_bps=10e9
        )

        flow = config["flows"][0]
        assert "name" in flow
        assert "tx_rx" in flow
        assert "rate" in flow
        assert "duration" in flow
        assert "size" in flow
        assert "packet" in flow

    def test_peak_rate_scaling(self, sample_timeseries):
        config = generate_otg_config(
            sample_timeseries, peak_rate_bps=10e9
        )

        rates = [f["rate"]["bps"] for f in config["flows"]]
        assert max(rates) == pytest.approx(10e9, rel=0.01)

    def test_duration_compression(self, sample_timeseries):
        config = generate_otg_config(
            sample_timeseries,
            peak_rate_bps=10e9,
            total_duration_sec=60,
        )

        durations = [f["duration"]["fixed_seconds"]["seconds"]
                     for f in config["flows"]]
        total = sum(durations)
        assert total == pytest.approx(60, rel=0.1)

    def test_packet_size(self, sample_timeseries):
        config = generate_otg_config(
            sample_timeseries,
            peak_rate_bps=10e9,
            packet_size=512,
        )

        for flow in config["flows"]:
            assert flow["size"]["fixed"] == 512

    def test_protocol_udp(self, sample_timeseries):
        config = generate_otg_config(
            sample_timeseries, peak_rate_bps=10e9, protocol="udp"
        )

        headers = config["flows"][0]["packet"]
        header_types = [list(h.keys())[0] for h in headers]
        assert "udp" in header_types
        assert "tcp" not in header_types

    def test_protocol_tcp(self, sample_timeseries):
        config = generate_otg_config(
            sample_timeseries, peak_rate_bps=10e9, protocol="tcp"
        )

        headers = config["flows"][0]["packet"]
        header_types = [list(h.keys())[0] for h in headers]
        assert "tcp" in header_types
        assert "udp" not in header_types

    def test_ip_addresses(self, sample_timeseries):
        config = generate_otg_config(
            sample_timeseries,
            peak_rate_bps=10e9,
            src_ip="192.168.1.1",
            dst_ip="192.168.1.2",
        )

        headers = config["flows"][0]["packet"]
        ipv4 = [h for h in headers if "ipv4" in h][0]["ipv4"]
        assert ipv4["src"]["value"] == "192.168.1.1"
        assert ipv4["dst"]["value"] == "192.168.1.2"

    def test_interval_resampling(self, sample_timeseries):
        config = generate_otg_config(
            sample_timeseries,
            peak_rate_bps=10e9,
            interval_sec=600,
        )

        assert len(config["flows"]) < len(sample_timeseries["points"])

    def test_empty_points_raises(self):
        ts = {"source": "test", "points": []}
        with pytest.raises(ValueError):
            generate_otg_config(ts, peak_rate_bps=10e9)

    def test_zero_points_raises(self):
        ts = {"source": "test", "points": [
            {"t": 0, "bps": 0}, {"t": 300, "bps": 0}
        ]}
        with pytest.raises(ValueError):
            generate_otg_config(ts, peak_rate_bps=10e9)

    def test_ports_defined(self, sample_timeseries):
        config = generate_otg_config(
            sample_timeseries, peak_rate_bps=10e9
        )

        assert len(config["ports"]) == 2
        names = {p["name"] for p in config["ports"]}
        assert "tx" in names
        assert "rx" in names
