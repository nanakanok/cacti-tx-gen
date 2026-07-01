"""Tests for CLI utility functions."""

import pytest
from click import ClickException

from cacti_tx_gen.cli import _parse_rate, _parse_duration, _parse_total_duration, _detect_ix, _detect_scale


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


class TestDetectScale:
    def test_bbix_daily(self):
        assert _detect_scale("TK_d.png") == "daily"

    def test_bbix_weekly(self):
        assert _detect_scale("total_w.png") == "weekly"

    def test_bbix_monthly(self):
        assert _detect_scale("TK_m.png") == "monthly"

    def test_bbix_yearly(self):
        assert _detect_scale("total_y.png") == "yearly"

    def test_jpnap_daily(self):
        assert _detect_scale("jpnap_tokyo_day.png") == "daily"

    def test_jpnap_yearly(self):
        assert _detect_scale("jpnap_total_year.png") == "yearly"

    def test_jpix_24h(self):
        assert _detect_scale("TOTAL.In.png") == "daily"

    def test_url_bbix_weekly(self):
        assert _detect_scale("https://www.bbix.net/bbix_traffic/total_w.png") == "weekly"

    def test_url_jpnap_yearly(self):
        assert _detect_scale("https://www.jpnap.net/assets/traffic/jpnap_tokyo_year.png") == "yearly"

    def test_unknown_defaults_daily(self):
        assert _detect_scale("unknown_graph.png") == "daily"


class TestParseTotalDuration:
    def test_days(self):
        assert _parse_total_duration("550d") == 550 * 86400

    def test_years(self):
        assert _parse_total_duration("27y") == 27 * 365 * 86400

    def test_months(self):
        assert _parse_total_duration("18mo") == 18 * 30 * 86400

    def test_combined(self):
        assert _parse_total_duration("2y6mo") == (2 * 365 + 6 * 30) * 86400

    def test_raw_seconds(self):
        assert _parse_total_duration("86400") == 86400
