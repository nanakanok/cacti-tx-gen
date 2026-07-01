"""Tests for NS3 conversion."""

import pytest

from cacti_tx_gen.convert.ns3 import convert_to_ns3


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
