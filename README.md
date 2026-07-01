# cacti-tx-gen

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)

A CLI tool that extracts traffic patterns from IX (Internet Exchange) traffic report PNG images and generates traffic generator configs — replay real-world IX traffic shapes on lab equipment or in NS3 simulation.

## Overview

Japanese IX operators (JPNAP, JPIX, BBIX) publish daily aggregate bandwidth graphs as MRTG/RRDtool-style PNG area charts. These graphs show 24-hour traffic patterns that are useful for capacity planning, but there's no machine-readable data behind them — just pixels.

cacti-tx-gen reads those PNGs, extracts the bandwidth time-series via OpenCV pixel analysis, and produces traffic generator configs that reproduce the same traffic shape at any target link speed.

```
IX graph PNG ──→ extract ──→ timeseries JSON ──→ generate ──→ OTG config YAML ──→ convert-ns3 ──→ NS3 scenario .py
```

The pipeline uses [OTG (Open Traffic Generator)](https://otg.dev/) as the canonical intermediate format. NS3 scenarios are derived from OTG, not generated independently.

## Features

- **Three IX parsers**: JPIX, BBIX, JPNAP — each tuned to its graph's color scheme, axis layout, and gridline spacing
- **Gridline calibration**: auto-detects Y-axis scale from gridline positions (critical for BBIX which doesn't start at 0)
- **HSV color detection**: finds the fill-top boundary per pixel column using color-space analysis, not edge detection
- **Linear scaling**: `--peak-rate` maps the source peak (e.g., 4 Tb/s) to the target (e.g., 10 Gb/s) while preserving the relative shape
- **Time compression**: `--duration` compresses 24h of traffic into any target duration (e.g., 1h, 10m)
- **OTG output**: one flow per time-slice with fixed rate + duration, compatible with ixia-c, TRex (via snappi-trex), and other OTG-capable generators
- **NS3 conversion**: generates a standalone Python scenario using OnOffApplication with rate schedule

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Optional system dependency for OCR-based axis reading (not required — Y-axis scale is auto-detected from gridlines or specified via `--y-max`):

```bash
sudo apt install tesseract-ocr   # Debian/Ubuntu
```

## Quick Start

```bash
# 1. Extract time-series from an IX traffic graph
cacti-tx-gen extract jpnap_tokyo_day.png --ix jpnap -o timeseries.json

# 2. Generate OTG config scaled to 10 Gbps peak, compressed to 10 minutes
cacti-tx-gen generate timeseries.json --peak-rate 10Gbps --duration 10m -o config.yaml

# 3. Convert to NS3 scenario
cacti-tx-gen convert-ns3 config.yaml -o scenario.py
```

## CLI Reference

### `cacti-tx-gen extract <image>`

Extract time-series data from an IX traffic graph PNG.

| Option | Description |
|---|---|
| `--ix` | IX type: `jpix`, `bbix`, `jpnap` (auto-detected from filename if omitted) |
| `--y-max` | Y-axis maximum (e.g., `4Tbps`). Auto-detected from gridlines if omitted |
| `-o` | Output JSON file (default: stdout) |

### `cacti-tx-gen generate <timeseries.json>`

Generate OTG config from time-series JSON.

| Option | Default | Description |
|---|---|---|
| `--peak-rate` | (required) | Target peak rate (e.g., `10Gbps`, `1Gbps`) |
| `--interval` | `300` | Time slice interval in seconds |
| `--duration` | (full) | Compress replay to this duration (e.g., `1h`, `30m`, `10m`) |
| `--packet-size` | `1400` | Packet size in bytes |
| `--protocol` | `udp` | L4 protocol: `udp` or `tcp` |
| `--src-ip` | `10.0.0.1` | Source IP address |
| `--dst-ip` | `10.0.0.2` | Destination IP address |

### `cacti-tx-gen convert-ns3 <config.yaml>`

Convert OTG config YAML to a standalone NS3 Python scenario.

| Option | Description |
|---|---|
| `-o` | Output Python file (default: stdout) |

## Extraction Accuracy

Validated against known AVG/MAX values from each IX's stats text:

| IX | MAX error | AVG error |
|---|---|---|
| JPIX | < 2% | < 2.5% |
| BBIX | < 0.5% | < 0.5% |
| JPNAP | < 1.5% | < 1% |

## Implementation Status

| Component | Status | Description |
|---|---|---|
| `extract/base.py` | Done | Base extractor ABC: HSV fill-top detection, pixel-to-bps mapping, resampling |
| `extract/jpix.py` | Done | JPIX parser: green fill, tick-based plot region detection |
| `extract/bbix.py` | Done | BBIX parser: gridline calibration for non-zero Y-axis baseline |
| `extract/jpnap.py` | Done | JPNAP parser: pink fill, gridline-based Y-axis auto-detection |
| `generate/otg.py` | Done | OTG config generation: per-slice flows, rate scaling, time compression |
| `convert/ns3.py` | Done | NS3 scenario generation: OnOffApplication with rate schedule |
| `cli.py` | Done | CLI with `extract`, `generate`, `convert-ns3` subcommands |
| Tests | Done | 64 tests (extract, generate, convert, CLI integration, utilities) |
| TG validation | Planned | End-to-end test with ixia-c / TRex / xdperf |

## Project Structure

```
cacti-tx-gen/
├── pyproject.toml
├── docs/adr/
│   └── 0001-ix-traffic-replay-architecture.md
├── src/cacti_tx_gen/
│   ├── cli.py                  # Click CLI entry point
│   ├── extract/
│   │   ├── base.py             # BaseExtractor ABC
│   │   ├── jpix.py             # JPIX parser
│   │   ├── bbix.py             # BBIX parser
│   │   └── jpnap.py            # JPNAP parser
│   ├── generate/
│   │   └── otg.py              # OTG config generator
│   └── convert/
│       └── ns3.py              # NS3 scenario converter
└── tests/
    ├── fixtures/               # Sample IX graph PNGs
    ├── test_extract.py         # Extractor unit tests
    ├── test_generate.py        # OTG generation tests
    ├── test_convert.py         # NS3 conversion tests
    ├── test_cli.py             # CLI integration tests
    └── test_utils.py           # Utility function tests
```

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Traffic Generator Support

Priority order for integration testing:

1. **ixia-c** (Community Edition, Docker) — OTG native, first validation target
2. **TRex** — via snappi-trex shim (stateless flows only)
3. **xdperf** — requires custom OTG adapter (no native OTG support)

## License

MIT

<details>
<summary>日本語</summary>

# cacti-tx-gen

IX（Internet Exchange）のトラフィックレポート PNG 画像からトラフィックパターンを抽出し、トラフィックジェネレータの設定を生成する CLI ツールです。実際の IX トラフィックの形状をラボ機器上や NS3 シミュレーションで再現できます。

## 概要

日本の IX 事業者（JPNAP、JPIX、BBIX）は、MRTG/RRDtool 形式の PNG 面グラフとして日次の集約帯域グラフを公開しています。これらのグラフは 24 時間のトラフィックパターンを示しており、キャパシティプランニングに有用ですが、背後に機械可読なデータはなく、ピクセルだけです。

cacti-tx-gen はこれらの PNG を読み取り、OpenCV のピクセル解析で帯域時系列を抽出し、任意のターゲットリンク速度で同じトラフィック形状を再現するトラフィックジェネレータ設定を生成します。

```
IX グラフ PNG ──→ extract ──→ 時系列 JSON ──→ generate ──→ OTG 設定 YAML ──→ convert-ns3 ──→ NS3 シナリオ .py
```

パイプラインは [OTG (Open Traffic Generator)](https://otg.dev/) を正規の中間フォーマットとして使用します。NS3 シナリオは OTG から派生し、独立して生成はしません。

## 特長

- **3 つの IX パーサ**: JPIX、BBIX、JPNAP — それぞれのグラフの配色、軸レイアウト、グリッド線間隔に合わせてチューニング
- **グリッド線キャリブレーション**: グリッド線位置から Y 軸スケールを自動検出（Y 軸が 0 始まりでない BBIX で特に重要）
- **HSV 色検出**: エッジ検出ではなく色空間解析で、ピクセル列ごとに塗りつぶしの上端境界を検出
- **線形スケーリング**: `--peak-rate` でソースのピーク（例: 4 Tb/s）をターゲット（例: 10 Gb/s）にマッピングし、相対的な形状を保持
- **時間圧縮**: `--duration` で 24 時間分のトラフィックを任意の長さ（例: 1h、10m）に圧縮
- **OTG 出力**: タイムスライスごとに固定レート＋固定時間のフローを 1 つ生成。ixia-c、TRex（snappi-trex 経由）など OTG 対応ジェネレータと互換
- **NS3 変換**: レートスケジュール付き OnOffApplication を使用するスタンドアロン Python シナリオを生成

## セットアップ

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

OCR による軸読み取り用のオプションのシステム依存パッケージ（必須ではありません — Y 軸スケールはグリッド線から自動検出されるか、`--y-max` で指定可能）:

```bash
sudo apt install tesseract-ocr   # Debian/Ubuntu
```

## 使い方

```bash
# 1. IX トラフィックグラフから時系列を抽出
cacti-tx-gen extract jpnap_tokyo_day.png --ix jpnap -o timeseries.json

# 2. ピーク 10 Gbps、10 分に圧縮した OTG 設定を生成
cacti-tx-gen generate timeseries.json --peak-rate 10Gbps --duration 10m -o config.yaml

# 3. NS3 シナリオに変換
cacti-tx-gen convert-ns3 config.yaml -o scenario.py
```

## CLI リファレンス

### `cacti-tx-gen extract <image>`

IX トラフィックグラフ PNG から時系列データを抽出。

| オプション | 説明 |
|---|---|
| `--ix` | IX タイプ: `jpix`、`bbix`、`jpnap`（省略時はファイル名から自動検出） |
| `--y-max` | Y 軸最大値（例: `4Tbps`）。省略時はグリッド線から自動検出 |
| `-o` | 出力 JSON ファイル（デフォルト: 標準出力） |

### `cacti-tx-gen generate <timeseries.json>`

時系列 JSON から OTG 設定を生成。

| オプション | デフォルト | 説明 |
|---|---|---|
| `--peak-rate` | (必須) | ターゲットピークレート（例: `10Gbps`、`1Gbps`） |
| `--interval` | `300` | タイムスライス間隔（秒） |
| `--duration` | (全体) | リプレイをこの時間に圧縮（例: `1h`、`30m`、`10m`） |
| `--packet-size` | `1400` | パケットサイズ（バイト） |
| `--protocol` | `udp` | L4 プロトコル: `udp` または `tcp` |
| `--src-ip` | `10.0.0.1` | 送信元 IP アドレス |
| `--dst-ip` | `10.0.0.2` | 宛先 IP アドレス |

### `cacti-tx-gen convert-ns3 <config.yaml>`

OTG 設定 YAML をスタンドアロン NS3 Python シナリオに変換。

| オプション | 説明 |
|---|---|
| `-o` | 出力 Python ファイル（デフォルト: 標準出力） |

## 抽出精度

各 IX の統計テキストの既知 AVG/MAX 値に対して検証:

| IX | MAX 誤差 | AVG 誤差 |
|---|---|---|
| JPIX | < 2% | < 2.5% |
| BBIX | < 0.5% | < 0.5% |
| JPNAP | < 1.5% | < 1% |

## 実装状況

| コンポーネント | 状態 | 説明 |
|---|---|---|
| `extract/base.py` | 完了 | 基底 Extractor ABC: HSV 塗りつぶし上端検出、ピクセル→bps 変換、リサンプリング |
| `extract/jpix.py` | 完了 | JPIX パーサ: 緑色塗りつぶし、ティックベースのプロット領域検出 |
| `extract/bbix.py` | 完了 | BBIX パーサ: Y 軸が 0 始まりでないためグリッド線キャリブレーション必須 |
| `extract/jpnap.py` | 完了 | JPNAP パーサ: ピンク色塗りつぶし、グリッド線ベースの Y 軸自動検出 |
| `generate/otg.py` | 完了 | OTG 設定生成: スライスごとのフロー、レートスケーリング、時間圧縮 |
| `convert/ns3.py` | 完了 | NS3 シナリオ生成: レートスケジュール付き OnOffApplication |
| `cli.py` | 完了 | `extract`、`generate`、`convert-ns3` サブコマンド付き CLI |
| テスト | 完了 | 64 テスト（extract、generate、convert、CLI 統合、ユーティリティ） |
| TG 実機検証 | 予定 | ixia-c / TRex / xdperf でのエンドツーエンドテスト |

## プロジェクト構成

```
cacti-tx-gen/
├── pyproject.toml
├── docs/adr/
│   └── 0001-ix-traffic-replay-architecture.md
├── src/cacti_tx_gen/
│   ├── cli.py                  # Click CLI エントリポイント
│   ├── extract/
│   │   ├── base.py             # BaseExtractor ABC
│   │   ├── jpix.py             # JPIX パーサ
│   │   ├── bbix.py             # BBIX パーサ
│   │   └── jpnap.py            # JPNAP パーサ
│   ├── generate/
│   │   └── otg.py              # OTG 設定ジェネレータ
│   └── convert/
│       └── ns3.py              # NS3 シナリオコンバータ
└── tests/
    ├── fixtures/               # IX グラフサンプル PNG
    ├── test_extract.py         # Extractor ユニットテスト
    ├── test_generate.py        # OTG 生成テスト
    ├── test_convert.py         # NS3 変換テスト
    ├── test_cli.py             # CLI 統合テスト
    └── test_utils.py           # ユーティリティ関数テスト
```

## 開発

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## トラフィックジェネレータ対応

統合テストの優先順位:

1. **ixia-c**（Community Edition、Docker）— OTG ネイティブ、最初の検証ターゲット
2. **TRex** — snappi-trex シム経由（ステートレスフローのみ）
3. **xdperf** — カスタム OTG アダプタが必要（OTG ネイティブ非対応）

</details>
