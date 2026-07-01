"""Tests for CLI utility functions."""

import pytest
from click import ClickException

from cacti_tx_gen.cli import _parse_rate, _parse_duration, _detect_ix


class TestParseRate:
    def test_gbps(self):
        assert _parse_rate("10Gbps") == 10e9

    def test_tbps(self):
        assert _parse_rate("4Tbps") == 4e12

    def test_mbps(self):
        assert _parse_rate("100Mbps") == 100e6

    def test_kbps(self):
        assert _parse_rate("500Kbps") == 500e3

    def test_bps(self):
        assert _parse_rate("1000bps") == 1000

    def test_slash_notation(self):
        assert _parse_rate("10Gb/s") == 10e9

    def test_float_rate(self):
        assert _parse_rate("2.5Gbps") == 2.5e9

    def test_invalid_raises(self):
        with pytest.raises(ClickException):
            _parse_rate("10xyz")


class TestParseDuration:
    def test_hours(self):
        assert _parse_duration("1h") == 3600

    def test_minutes(self):
        assert _parse_duration("30m") == 1800

    def test_seconds(self):
        assert _parse_duration("60s") == 60

    def test_numeric_string(self):
        assert _parse_duration("300") == 300

    def test_fractional(self):
        assert _parse_duration("0.5h") == 1800


class TestDetectIx:
    def test_jpix(self):
        assert _detect_ix("/path/to/jpix_graph.png") == "jpix"

    def test_bbix(self):
        assert _detect_ix("/path/to/bbix_traffic.png") == "bbix"

    def test_jpnap(self):
        assert _detect_ix("/path/to/jpnap_tokyo.png") == "jpnap"

    def test_unknown_raises(self):
        with pytest.raises(ClickException):
            _detect_ix("/path/to/unknown_graph.png")
