"""Tests for CLI commands."""

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from cacti_tx_gen.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def runner():
    return CliRunner()


class TestExtractCommand:
    def test_extract_jpix(self, runner, tmp_path):
        output = tmp_path / "out.json"
        result = runner.invoke(main, [
            "extract", str(FIXTURES / "jpix_sample.png"),
            "--ix", "jpix", "--y-max", "4Tbps",
            "-o", str(output),
        ])

        assert result.exit_code == 0
        data = json.loads(output.read_text())
        assert data["source"] == "jpix"
        assert len(data["points"]) > 0

    def test_extract_bbix(self, runner, tmp_path):
        output = tmp_path / "out.json"
        result = runner.invoke(main, [
            "extract", str(FIXTURES / "bbix_sample.png"),
            "--ix", "bbix",
            "-o", str(output),
        ])

        assert result.exit_code == 0
        data = json.loads(output.read_text())
        assert data["source"] == "bbix"

    def test_extract_jpnap(self, runner, tmp_path):
        output = tmp_path / "out.json"
        result = runner.invoke(main, [
            "extract", str(FIXTURES / "jpnap_sample.png"),
            "--ix", "jpnap",
            "-o", str(output),
        ])

        assert result.exit_code == 0
        data = json.loads(output.read_text())
        assert data["source"] == "jpnap"

    def test_extract_auto_detect_ix(self, runner, tmp_path):
        output = tmp_path / "out.json"
        result = runner.invoke(main, [
            "extract", str(FIXTURES / "jpix_sample.png"),
            "--y-max", "4Tbps",
            "-o", str(output),
        ])

        assert result.exit_code == 0

    def test_extract_stdout(self, runner):
        result = runner.invoke(main, [
            "extract", str(FIXTURES / "jpix_sample.png"),
            "--ix", "jpix", "--y-max", "4Tbps",
        ])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["source"] == "jpix"


    def test_extract_with_scale(self, runner, tmp_path):
        output = tmp_path / "out.json"
        result = runner.invoke(main, [
            "extract", str(FIXTURES / "bbix_sample.png"),
            "--ix", "bbix", "--scale", "weekly",
            "-o", str(output),
        ])

        assert result.exit_code == 0
        data = json.loads(output.read_text())
        assert data["scale"] == "weekly"
        assert data["interval_sec"] == 1800
        last_t = data["points"][-1]["t"]
        assert last_t > 500000

    def test_extract_scale_auto_detect(self, runner, tmp_path):
        output = tmp_path / "out.json"
        result = runner.invoke(main, [
            "extract", str(FIXTURES / "jpnap_sample.png"),
            "--ix", "jpnap",
            "-o", str(output),
        ])

        assert result.exit_code == 0
        data = json.loads(output.read_text())
        assert data["scale"] == "daily"
        assert data["interval_sec"] == 300


class TestGenerateCommand:
    @pytest.fixture
    def timeseries_file(self, runner, tmp_path):
        output = tmp_path / "ts.json"
        runner.invoke(main, [
            "extract", str(FIXTURES / "jpix_sample.png"),
            "--ix", "jpix", "--y-max", "4Tbps",
            "-o", str(output),
        ])
        return output

    def test_generate_basic(self, runner, timeseries_file, tmp_path):
        output = tmp_path / "config.yaml"
        result = runner.invoke(main, [
            "generate", str(timeseries_file),
            "--peak-rate", "10Gbps",
            "-o", str(output),
        ])

        assert result.exit_code == 0
        config = yaml.safe_load(output.read_text())
        assert "flows" in config
        assert len(config["flows"]) > 0

    def test_generate_with_duration(self, runner, timeseries_file, tmp_path):
        output = tmp_path / "config.yaml"
        result = runner.invoke(main, [
            "generate", str(timeseries_file),
            "--peak-rate", "10Gbps",
            "--duration", "10m",
            "-o", str(output),
        ])

        assert result.exit_code == 0
        config = yaml.safe_load(output.read_text())
        durations = [f["duration"]["fixed_seconds"]["seconds"]
                     for f in config["flows"]]
        assert sum(durations) == pytest.approx(600, rel=0.1)

    def test_generate_with_options(self, runner, timeseries_file, tmp_path):
        output = tmp_path / "config.yaml"
        result = runner.invoke(main, [
            "generate", str(timeseries_file),
            "--peak-rate", "1Gbps",
            "--packet-size", "512",
            "--protocol", "tcp",
            "--src-ip", "192.168.1.1",
            "--dst-ip", "192.168.1.2",
            "-o", str(output),
        ])

        assert result.exit_code == 0
        config = yaml.safe_load(output.read_text())
        flow = config["flows"][0]
        assert flow["size"]["fixed"] == 512


class TestConvertNs3Command:
    @pytest.fixture
    def otg_config_file(self, runner, tmp_path):
        ts_file = tmp_path / "ts.json"
        runner.invoke(main, [
            "extract", str(FIXTURES / "jpix_sample.png"),
            "--ix", "jpix", "--y-max", "4Tbps",
            "-o", str(ts_file),
        ])
        config_file = tmp_path / "config.yaml"
        runner.invoke(main, [
            "generate", str(ts_file),
            "--peak-rate", "10Gbps",
            "--duration", "10m",
            "-o", str(config_file),
        ])
        return config_file

    def test_convert_ns3(self, runner, otg_config_file, tmp_path):
        output = tmp_path / "scenario.py"
        result = runner.invoke(main, [
            "convert-ns3", str(otg_config_file),
            "-o", str(output),
        ])

        assert result.exit_code == 0
        script = output.read_text()
        compile(script, str(output), "exec")


class TestHelpMessages:
    def test_main_help(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Generate traffic" in result.output

    def test_extract_help(self, runner):
        result = runner.invoke(main, ["extract", "--help"])
        assert result.exit_code == 0
        assert "--ix" in result.output

    def test_generate_help(self, runner):
        result = runner.invoke(main, ["generate", "--help"])
        assert result.exit_code == 0
        assert "--peak-rate" in result.output

    def test_convert_ns3_help(self, runner):
        result = runner.invoke(main, ["convert-ns3", "--help"])
        assert result.exit_code == 0
