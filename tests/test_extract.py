"""Tests for IX traffic graph extractors."""

import json
from pathlib import Path

import pytest

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
