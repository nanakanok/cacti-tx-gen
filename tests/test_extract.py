"""Tests for IX traffic graph extractors."""

import json
from pathlib import Path

import pytest

from cacti_tx_gen.extract.base import TimeScale, SCALE_DURATION_SEC, SCALE_RESAMPLE_SEC
from cacti_tx_gen.extract.jpix import JPIXExtractor
from cacti_tx_gen.extract.bbix import BBIXExtractor
from cacti_tx_gen.extract.jpnap import JPNAPExtractor

FIXTURES = Path(__file__).parent / "fixtures"


class TestJPIXExtractor:
    def test_extract_returns_valid_structure(self):
        ext = JPIXExtractor(y_max_bps=4.0e12)
        result = ext.extract(str(FIXTURES / "jpix_sample.png"))

        assert result["source"] == "jpix"
        assert result["unit"] == "bps"
        assert "points" in result
        assert "interval_sec" in result
        assert "y_axis_max_bps" in result
        assert len(result["points"]) > 0

    def test_extract_points_have_t_and_bps(self):
        ext = JPIXExtractor(y_max_bps=4.0e12)
        result = ext.extract(str(FIXTURES / "jpix_sample.png"))

        for point in result["points"]:
            assert "t" in point
            assert "bps" in point
            assert point["bps"] >= 0

    def test_extract_accuracy(self):
        """Validate against known JPIX values: AVG~2.54T, MAX~3.59T."""
        ext = JPIXExtractor(y_max_bps=4.0e12)
        result = ext.extract(str(FIXTURES / "jpix_sample.png"))

        bps_values = [p["bps"] for p in result["points"] if p["bps"] > 0]
        avg_bps = sum(bps_values) / len(bps_values)
        max_bps = max(bps_values)

        assert max_bps == pytest.approx(3.59e12, rel=0.1)
        assert avg_bps == pytest.approx(2.54e12, rel=0.1)

    def test_resample_to_300s(self):
        ext = JPIXExtractor(y_max_bps=4.0e12)
        result = ext.extract(str(FIXTURES / "jpix_sample.png"))
        resampled = ext._resample(result["points"], 300)

        assert len(resampled) == 288 or len(resampled) == 289
        for i in range(1, len(resampled)):
            dt = resampled[i]["t"] - resampled[i - 1]["t"]
            assert dt == pytest.approx(300, rel=0.01)


class TestBBIXExtractor:
    def test_extract_returns_valid_structure(self):
        ext = BBIXExtractor()
        result = ext.extract(str(FIXTURES / "bbix_sample.png"))

        assert result["source"] == "bbix"
        assert len(result["points"]) > 0

    def test_extract_accuracy(self):
        """Validate against known BBIX values: AVG~4.59T, MAX~7.14T."""
        ext = BBIXExtractor()
        result = ext.extract(str(FIXTURES / "bbix_sample.png"))

        bps_values = [p["bps"] for p in result["points"] if p["bps"] > 0]
        avg_bps = sum(bps_values) / len(bps_values)
        max_bps = max(bps_values)

        assert max_bps == pytest.approx(7.14e12, rel=0.1)
        assert avg_bps == pytest.approx(4.59e12, rel=0.1)

    def test_gridline_calibration_sets_y_min(self):
        ext = BBIXExtractor()
        ext.extract(str(FIXTURES / "bbix_sample.png"))

        assert ext._y_min_bps > 0


class TestJPNAPExtractor:
    def test_extract_returns_valid_structure(self):
        ext = JPNAPExtractor()
        result = ext.extract(str(FIXTURES / "jpnap_sample.png"))

        assert result["source"] == "jpnap"
        assert len(result["points"]) > 0

    def test_extract_accuracy(self):
        """Validate against known JPNAP values: Mean~2.71T, Max~4.03T."""
        ext = JPNAPExtractor()
        result = ext.extract(str(FIXTURES / "jpnap_sample.png"))

        bps_values = [p["bps"] for p in result["points"] if p["bps"] > 0]
        avg_bps = sum(bps_values) / len(bps_values)
        max_bps = max(bps_values)

        assert max_bps == pytest.approx(4.03e12, rel=0.1)
        assert avg_bps == pytest.approx(2.71e12, rel=0.1)

    def test_y_max_override(self):
        ext = JPNAPExtractor(y_max_bps=5.0e12)
        result = ext.extract(str(FIXTURES / "jpnap_sample.png"))

        assert result["y_axis_max_bps"] == 5.0e12


class TestJPNAPYearly:
    def test_yearly_avg_accuracy(self):
        """Validate JPNAP yearly avg series: Mean~2.67T, Max~3.02T."""
        ext = JPNAPExtractor(scale=TimeScale.YEARLY)
        result = ext.extract(str(FIXTURES / "jpnap_yearly_sample.png"))

        bps_values = [p["bps"] for p in result["points"] if p["bps"] > 0]
        avg_bps = sum(bps_values) / len(bps_values)
        max_bps = max(bps_values)

        assert avg_bps == pytest.approx(2.67e12, rel=0.1)
        assert max_bps == pytest.approx(3.02e12, rel=0.1)

    def test_yearly_max_accuracy(self):
        """Validate JPNAP yearly max series: Mean~3.94T."""
        ext = JPNAPExtractor(scale=TimeScale.YEARLY, series="max")
        result = ext.extract(str(FIXTURES / "jpnap_yearly_sample.png"))

        bps_values = [p["bps"] for p in result["points"] if p["bps"] > 0]
        avg_bps = sum(bps_values) / len(bps_values)

        assert avg_bps == pytest.approx(3.94e12, rel=0.1)

    def test_yearly_max_gt_avg(self):
        results = {}
        for s in ("max", "avg"):
            ext = JPNAPExtractor(scale=TimeScale.YEARLY, series=s)
            result = ext.extract(str(FIXTURES / "jpnap_yearly_sample.png"))
            bps = [p["bps"] for p in result["points"] if p["bps"] > 0]
            results[s] = sum(bps) / len(bps)

        assert results["max"] > results["avg"]

    def test_daily_not_banded(self):
        """Daily graph should not trigger band detection (no red fill)."""
        ext = JPNAPExtractor()
        result = ext.extract(str(FIXTURES / "jpnap_sample.png"))
        bps = [p["bps"] for p in result["points"] if p["bps"] > 0]
        avg_bps = sum(bps) / len(bps)
        assert avg_bps == pytest.approx(2.71e12, rel=0.1)


class TestJPNAPHistory:
    def test_history_extracts(self):
        """History graph (~25y span) should extract non-zero points."""
        ext = JPNAPExtractor(scale=TimeScale.YEARLY, total_duration_sec=25 * 365 * 86400)
        result = ext.extract(str(FIXTURES / "jpnap_history_sample.png"))

        bps_values = [p["bps"] for p in result["points"] if p["bps"] > 0]
        assert len(bps_values) > 100
        assert result["y_axis_max_bps"] > 8e12

    def test_history_max_peak(self):
        """History max series should capture recent peaks (~8T)."""
        ext = JPNAPExtractor(scale=TimeScale.YEARLY, total_duration_sec=25 * 365 * 86400,
                             series="max")
        result = ext.extract(str(FIXTURES / "jpnap_history_sample.png"))

        bps_values = [p["bps"] for p in result["points"] if p["bps"] > 0]
        max_bps = max(bps_values)

        assert max_bps == pytest.approx(8.16e12, rel=0.1)

    def test_history_max_gt_avg(self):
        results = {}
        for s in ("max", "avg"):
            ext = JPNAPExtractor(scale=TimeScale.YEARLY, total_duration_sec=25 * 365 * 86400,
                                 series=s)
            result = ext.extract(str(FIXTURES / "jpnap_history_sample.png"))
            bps = [p["bps"] for p in result["points"] if p["bps"] > 0]
            results[s] = sum(bps) / len(bps)

        assert results["max"] > results["avg"]

    def test_detect_scale_history(self):
        from cacti_tx_gen.cli import _detect_scale
        assert _detect_scale("jpnap_tokyo_history.png") == "yearly"
        assert _detect_scale("jpnap_tokyo_history_in.png") == "yearly"


class TestJPIXMinmax:
    def test_detect_minmax(self):
        ext = JPIXExtractor(y_max_bps=5.0e12, total_duration_sec=550 * 86400)
        ext.extract(str(FIXTURES / "jpix_minmax_sample.png"))
        assert ext._is_minmax == True

    def test_regular_not_minmax(self):
        ext = JPIXExtractor(y_max_bps=4.0e12)
        ext.extract(str(FIXTURES / "jpix_sample.png"))
        assert ext._is_minmax == False

    def test_max_gt_avg_gt_min(self):
        results = {}
        for s in ("max", "avg", "min"):
            ext = JPIXExtractor(y_max_bps=5.0e12, total_duration_sec=550 * 86400, series=s)
            result = ext.extract(str(FIXTURES / "jpix_minmax_sample.png"))
            bps = [p["bps"] for p in result["points"] if p["bps"] > 0]
            results[s] = sum(bps) / len(bps)

        assert results["max"] > results["avg"]
        assert results["avg"] > results["min"]

    def test_total_duration_override(self):
        ext = JPIXExtractor(y_max_bps=5.0e12, total_duration_sec=550 * 86400)
        result = ext.extract(str(FIXTURES / "jpix_minmax_sample.png"))
        last_t = result["points"][-1]["t"]
        assert last_t > 500 * 86400


class TestTimeScale:
    def test_daily_duration(self):
        ext = JPIXExtractor(y_max_bps=4.0e12, scale=TimeScale.DAILY)
        assert ext._get_total_duration_sec() == 86400.0

    def test_weekly_duration(self):
        ext = BBIXExtractor(scale=TimeScale.WEEKLY)
        assert ext._get_total_duration_sec() == 604800.0

    def test_monthly_duration(self):
        ext = BBIXExtractor(scale=TimeScale.MONTHLY)
        assert ext._get_total_duration_sec() == 2592000.0

    def test_yearly_duration(self):
        ext = JPNAPExtractor(scale=TimeScale.YEARLY)
        assert ext._get_total_duration_sec() == 31536000.0

    def test_default_resample_daily(self):
        ext = JPIXExtractor(y_max_bps=4.0e12)
        assert ext._get_default_resample_interval() == 300

    def test_default_resample_weekly(self):
        ext = BBIXExtractor(scale=TimeScale.WEEKLY)
        assert ext._get_default_resample_interval() == 1800

    def test_default_resample_yearly(self):
        ext = JPNAPExtractor(scale=TimeScale.YEARLY)
        assert ext._get_default_resample_interval() == 86400

    def test_weekly_extract_time_range(self):
        ext = BBIXExtractor(scale=TimeScale.WEEKLY)
        result = ext.extract(str(FIXTURES / "bbix_sample.png"))
        last_t = result["points"][-1]["t"]
        assert last_t > 500000

    def test_yearly_extract_time_range(self):
        ext = JPNAPExtractor(scale=TimeScale.YEARLY)
        result = ext.extract(str(FIXTURES / "jpnap_sample.png"))
        last_t = result["points"][-1]["t"]
        assert last_t > 30000000


class TestExtractorOutput:
    def test_json_serializable(self):
        ext = JPIXExtractor(y_max_bps=4.0e12)
        result = ext.extract(str(FIXTURES / "jpix_sample.png"))

        serialized = json.dumps(result)
        deserialized = json.loads(serialized)
        assert deserialized["source"] == "jpix"

    def test_points_monotonically_increasing_time(self):
        ext = JPIXExtractor(y_max_bps=4.0e12)
        result = ext.extract(str(FIXTURES / "jpix_sample.png"))

        for i in range(1, len(result["points"])):
            assert result["points"][i]["t"] >= result["points"][i - 1]["t"]
