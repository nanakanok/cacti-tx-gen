# ADR-0001: IX Traffic Replay Architecture

- **Status:** Accepted
- **Date:** 2026-07-01
- **Context:** IX (Internet Exchange) traffic reports (JPNAP, JPIX, BBIX) publish aggregate bandwidth graphs as PNG images. We need a tool to extract these traffic patterns and replay them using both physical traffic generators (via OTG) and NS3 simulation.

## Decision

### Goal

Reproduce the **relative bandwidth time-series pattern** from IX traffic graph images. The tool scales the pattern linearly to match the target environment's link speed (e.g., 4 Tb/s peak → 10 Gb/s).

### Pipeline

```
IX graph PNG → extract → timeseries JSON → generate → OTG config YAML → convert-ns3 → NS3 scenario .py
```

OTG config is the canonical intermediate representation. NS3 scenarios are derived from OTG, not generated independently.

### CLI Design

Subcommand architecture:

```
cacti-tx-gen extract   <image>          -o timeseries.json
cacti-tx-gen generate  <timeseries.json> --peak-rate 10Gbps -o config.yaml
cacti-tx-gen convert-ns3 <config.yaml>  -o scenario.py
```

### Image Extraction (extract)

- Automatic extraction via OpenCV + pytesseract (OCR for axis labels, AVG/MAX values)
- Area chart pixel analysis: detect fill-region upper boundary per X position → map to bps via Y-axis scale
- IX support order: **JPIX → BBIX → JPNAP** (simplest first; JPIX/BBIX have inline AVG/MAX for validation)
- Pluggable parser design: base class with per-IX subclasses

### Intermediate Format (timeseries JSON)

```json
{
  "source": "jpix",
  "extracted_at": "2026-07-01T12:00:00+09:00",
  "unit": "bps",
  "interval_sec": 300,
  "y_axis_max_bps": 3.59e12,
  "stats": {
    "avg_bps": 2.54e12,
    "max_bps": 3.59e12
  },
  "points": [
    {"t": 0, "bps": 2.1e12},
    {"t": 300, "bps": 2.15e12}
  ]
}
```

### OTG Config Generation (generate)

- One OTG flow per time slice (5-min default → 288 flows for 24h)
- Each flow: `duration` (fixed_seconds) + `rate` (bps), linearly scaled via `--peak-rate`
- Default packet: 1400 bytes, UDP, IPv4. Overridable via `--packet-size`, `--protocol`
- Time interval: `--interval` option (default 300s)
- Time compression: `--duration` compresses total replay time (e.g., `--duration 1h` → 288 flows × 12.5s each)

### NS3 Conversion (convert-ns3)

- Target: `OnOffApplication` with per-time-slice DataRate schedule
- Output: standalone NS3 Python scenario script
- Rate scaling uses the same `--peak-rate` logic

### Traffic Generator Support

Priority order for integration testing:

1. **ixia-c** (Community Edition, Docker) — OTG native, first validation target
2. **TRex** — via snappi-trex shim (stateless flows only)
3. **xdperf** — requires custom OTG adapter (no native OTG support)

### Technology Stack

- **Language:** Python
- **Package layout:** src layout + pyproject.toml
- **Dependencies:**
  - CLI: click
  - Image processing: OpenCV (cv2), numpy
  - OCR: pytesseract (requires system tesseract-ocr)
  - OTG: snappi
  - Testing: pytest

## Project Structure

```
cacti-tx-gen/
├── pyproject.toml
├── docs/adr/
├── src/
│   └── cacti_tx_gen/
│       ├── __init__.py
│       ├── cli.py
│       ├── extract/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── jpix.py
│       │   ├── bbix.py
│       │   └── jpnap.py
│       ├── generate/
│       │   ├── __init__.py
│       │   └── otg.py
│       └── convert/
│           ├── __init__.py
│           └── ns3.py
├── tests/
└── README.md
```

## Consequences

- OTG as the single source of truth simplifies the pipeline but couples NS3 output to OTG's flow model
- Per-time-slice flows may produce large configs (288 flows); TG implementations must handle sequential flow execution
- Image extraction accuracy depends on graph format consistency; IX-specific parsers are needed for each source
- pytesseract adds a system dependency (tesseract-ocr) that complicates containerization
