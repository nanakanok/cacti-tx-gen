---
type: CLI Tool
title: cacti-tx-gen
description: IX traffic report PNG images from JPNAP/JPIX/BBIX to OTG/NS3 traffic generator configs
tags:
  - traffic-generation
  - ix
  - otg
  - ns3
  - opencv
timestamp: "2026-07-01"
---

# cacti-tx-gen

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)

A CLI tool that extracts traffic patterns from IX (Internet Exchange) traffic report PNG images and generates traffic generator configs — replay real-world IX traffic shapes on lab equipment or in NS3 simulation.

## Overview

Japanese IX operators (JPNAP, JPIX, BBIX) publish aggregate bandwidth graphs as MRTG/RRDtool-style PNG area charts at various time scales (daily, weekly, monthly, yearly). These graphs are useful for capacity planning, but there's no machine-readable data behind them — just pixels.

cacti-tx-gen reads those PNGs (from local files or directly from IX URLs), extracts the bandwidth time-series via OpenCV pixel analysis, and produces traffic generator configs that reproduce the same traffic shape at any target link speed.

```
IX graph PNG ──→ extract ──→ timeseries JSON ──→ generate ──→ OTG config YAML ──→ convert-ns3 ──→ NS3 scenario .py
```

The pipeline uses [OTG (Open Traffic Generator)](https://otg.dev/) as the canonical intermediate format. NS3 scenarios are derived from OTG, not generated independently.

## Features

- **Three IX parsers**: JPIX, BBIX, JPNAP — each tuned to its graph's color scheme, axis layout, and gridline spacing
- **Multi-scale extraction**: supports daily (24h), weekly (7d), monthly (30d), and yearly (365d) graph scales — auto-detected from filename
- **Multi-series extraction**: JPIX minmax graphs (max/avg/min) and JPNAP yearly/history graphs (max/avg) — select via `--series`
- **Arbitrary time spans**: `--total-duration` for non-standard durations (e.g., `550d` for JPIX minmax, `25y` for JPNAP history)
- **HTTPS URL input**: fetch graphs directly from IX traffic pages (e.g., `https://www.bbix.net/bbix_traffic/total_w.png`)
- **Gridline calibration**: auto-detects Y-axis scale from gridline positions or Y-axis label positions (critical for BBIX which doesn't start at 0)
- **HSV color detection**: finds the fill-top boundary per pixel column using color-space analysis, not edge detection
- **Band detection**: automatically distinguishes single-fill daily graphs from multi-band yearly/history graphs (red=max, purple=avg)
- **Linear scaling**: `--peak-rate` maps the source peak (e.g., 4 Tb/s) to the target (e.g., 10 Gb/s) while preserving the relative shape
- **Time compression**: `--duration` compresses traffic into any target duration (e.g., 1h, 10m)
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
# 1. Extract time-series from an IX traffic graph (local file or URL)
cacti-tx-gen extract jpnap_tokyo_day.png --ix jpnap -o timeseries.json
cacti-tx-gen extract https://www.bbix.net/bbix_traffic/total_d.png --ix bbix -o timeseries.json

# Extract from non-daily scales (auto-detected from filename, or explicit --scale)
cacti-tx-gen extract https://www.bbix.net/bbix_traffic/total_w.png -o weekly.json       # weekly
cacti-tx-gen extract https://www.jpnap.net/assets/traffic/jpnap_tokyo_year.png -o yearly.json  # yearly

# Extract specific series from multi-band graphs
cacti-tx-gen extract jpnap_yearly.png --series max -o yearly_max.json     # JPNAP yearly max band
cacti-tx-gen extract jpix_minmax.png --series min --total-duration 550d -o jpix_min.json  # JPIX minmax min series

# Extract from history graphs (~25 year span)
cacti-tx-gen extract jpnap_history.png --total-duration 25y -o history.json

# 2. Generate OTG config scaled to 10 Gbps peak, compressed to 10 minutes
cacti-tx-gen generate timeseries.json --peak-rate 10Gbps --duration 10m -o config.yaml

# 3. Convert to NS3 scenario
cacti-tx-gen convert-ns3 config.yaml -o scenario.py
```

## CLI Reference

### `cacti-tx-gen extract <image>`

Extract time-series data from an IX traffic graph. IMAGE can be a local file path or an HTTPS URL.

| Option | Description |
|---|---|
| `--ix` | IX type: `jpix`, `bbix`, `jpnap` (auto-detected from filename if omitted) |
| `--scale` | Graph time scale: `daily`, `weekly`, `monthly`, `yearly` (auto-detected from filename if omitted) |
| `--y-max` | Y-axis maximum (e.g., `4Tbps`). Auto-detected from gridlines if omitted |
| `--total-duration` | Explicit total duration (e.g., `550d`, `25y`, `2y6mo`). Overrides `--scale` duration |
| `--series` | Series to extract from multi-band graphs: `max`, `avg` (default), `min` |
| `-o` | Output JSON file (default: stdout) |

Scale auto-detection from filename:

| Pattern | Scale | Duration | Resample interval |
|---|---|---|---|
| `*_d.png`, `*_day.png`, `TOTAL.In.png` | daily | 24h | 300s (5min) |
| `*_w.png` | weekly | 7d | 1800s (30min) |
| `*_m.png` | monthly | 30d | 7200s (2h) |
| `*_y.png`, `*_year.png`, `*_history*` | yearly | 365d | 86400s (1d) |

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

| IX | Graph type | MAX error | AVG error |
|---|---|---|---|
| JPIX | daily | < 2% | < 2.5% |
| JPIX | minmax (~550d, max/avg/min series) | < 5% | < 5% |
| BBIX | daily | < 0.5% | < 0.5% |
| JPNAP | daily | < 1.5% | < 1% |
| JPNAP | yearly (max/avg series) | < 10% | < 10% |
| JPNAP | history (~25y, max/avg series) | < 10% | < 10% |

## Implementation Status

| Component | Status | Description |
|---|---|---|
| `extract/base.py` | Done | Base extractor ABC: HSV fill-top detection, pixel-to-bps mapping, resampling |
| `extract/jpix.py` | Done | JPIX parser: green fill, tick-based plot region detection, minmax graph support (3-series) |
| `extract/bbix.py` | Done | BBIX parser: gridline calibration for non-zero Y-axis baseline |
| `extract/jpnap.py` | Done | JPNAP parser: pink/red/purple band detection, daily/yearly/history support, Y-axis label fallback |
| `generate/otg.py` | Done | OTG config generation: per-slice flows, rate scaling, time compression |
| `convert/ns3.py` | Done | NS3 scenario generation: OnOffApplication with rate schedule |
| `cli.py` | Done | CLI with `extract`, `generate`, `convert-ns3` subcommands; URL input, scale auto-detection |
| Tests | Done | 110 tests (extract, generate, convert, CLI integration, utilities, pipeline round-trip) |
| TG validation | Done | Validated on ixia-c, TRex, xdperf via containerlab |

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
├── tests/
│   ├── README.md               # Test documentation
│   ├── fixtures/               # Sample IX graph PNGs (daily, yearly, history, minmax)
│   ├── test_extract.py         # Extractor unit tests
│   ├── test_generate.py        # OTG generation tests
│   ├── test_convert.py         # NS3 conversion tests
│   ├── test_cli.py             # CLI integration tests
│   └── test_utils.py           # Utility function tests
└── lab/
    ├── README.md               # Lab documentation
    ├── capture.py              # sysfs-based traffic capture + matplotlib graph
    ├── ixia-c/                 # ixia-c containerlab topology + snappi validate
    ├── trex/                   # TRex containerlab topology + STL API validate
    └── xdperf/                 # xdperf containerlab topology + OTG adapter
```

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Traffic Generator Validation

All three TGs validated on [containerlab](https://containerlab.dev/) with back-to-back veth topologies:

| TG | Result | Method | Notes |
|---|---|---|---|
| **ixia-c** (Community Edition) | PASS | snappi API (OTG native) | 256 flows/port max, min rate 672 bps |
| **TRex** v2.90 | PASS | STL API via container exec | snappi-trex lacks `fixed_seconds`; native STL used |
| **xdperf** | PASS | Custom OTG adapter | Patched for XDP generic mode fallback on veth |

### Lab topologies

```bash
# Deploy and validate
containerlab deploy -t lab/ixia-c/topology.clab.yml
python lab/ixia-c/validate.py

containerlab deploy -t lab/trex/topology.clab.yml
python lab/trex/validate.py --graph lab/trex/traffic_results.png

containerlab deploy -t lab/xdperf/topology.clab.yml
python lab/xdperf/validate.py
```

### xdperf generic mode patch

xdperf's `AttachXDP` call doesn't fall back to generic mode when driver mode is unavailable (veth interfaces). The Dockerfile applies a patch that adds the same `XDPGenericMode` fallback that `probe/xdp.go` already implements.

### Traffic graphing

TRex validate supports `--graph` to plot per-second TX/RX rates from the TRex Stats API:

```bash
python lab/trex/validate.py --otg-config config.yaml --graph results.png
```

## License

MIT

<details>
<summary>日本語</summary>

# cacti-tx-gen

IX（Internet Exchange）のトラフィックレポート PNG 画像からトラフィックパターンを抽出し、トラフィックジェネレータの設定を生成する CLI ツールです。実際の IX トラフィックの形状をラボ機器上や NS3 シミュレーションで再現できます。

## 概要

日本の IX 事業者（JPNAP、JPIX、BBIX）は、MRTG/RRDtool 形式の PNG 面グラフとして集約帯域グラフを各種タイムスケール（日次、週次、月次、年次）で公開しています。これらのグラフはキャパシティプランニングに有用ですが、背後に機械可読なデータはなく、ピクセルだけです。

cacti-tx-gen はこれらの PNG を（ローカルファイルまたは IX の URL から直接）読み取り、OpenCV のピクセル解析で帯域時系列を抽出し、任意のターゲットリンク速度で同じトラフィック形状を再現するトラフィックジェネレータ設定を生成します。

```
IX グラフ PNG ──→ extract ──→ 時系列 JSON ──→ generate ──→ OTG 設定 YAML ──→ convert-ns3 ──→ NS3 シナリオ .py
```

パイプラインは [OTG (Open Traffic Generator)](https://otg.dev/) を正規の中間フォーマットとして使用します。NS3 シナリオは OTG から派生し、独立して生成はしません。

## 特長

- **3 つの IX パーサ**: JPIX、BBIX、JPNAP — それぞれのグラフの配色、軸レイアウト、グリッド線間隔に合わせてチューニング
- **マルチスケール抽出**: 日次（24h）、週次（7d）、月次（30d）、年次（365d）のグラフスケールに対応 — ファイル名から自動検出
- **マルチ系列抽出**: JPIX minmax グラフ（max/avg/min）や JPNAP yearly/history グラフ（max/avg）— `--series` で選択
- **任意の時間幅**: `--total-duration` で非標準期間を指定（例: JPIX minmax `550d`、JPNAP history `25y`）
- **HTTPS URL 入力**: IX トラフィックページから直接グラフを取得（例: `https://www.bbix.net/bbix_traffic/total_w.png`）
- **グリッド線キャリブレーション**: グリッド線位置またはY軸ラベル位置から Y 軸スケールを自動検出（Y 軸が 0 始まりでない BBIX で特に重要）
- **HSV 色検出**: エッジ検出ではなく色空間解析で、ピクセル列ごとに塗りつぶしの上端境界を検出
- **バンド検出**: 単色 daily グラフとマルチバンド yearly/history グラフ（red=max、purple=avg）を自動判別
- **線形スケーリング**: `--peak-rate` でソースのピーク（例: 4 Tb/s）をターゲット（例: 10 Gb/s）にマッピングし、相対的な形状を保持
- **時間圧縮**: `--duration` でトラフィックを任意の長さ（例: 1h、10m）に圧縮
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
# 1. IX トラフィックグラフから時系列を抽出（ローカルファイルまたは URL）
cacti-tx-gen extract jpnap_tokyo_day.png --ix jpnap -o timeseries.json
cacti-tx-gen extract https://www.bbix.net/bbix_traffic/total_d.png --ix bbix -o timeseries.json

# 日次以外のスケールで抽出（ファイル名から自動検出、または --scale で明示指定）
cacti-tx-gen extract https://www.bbix.net/bbix_traffic/total_w.png -o weekly.json       # 週次
cacti-tx-gen extract https://www.jpnap.net/assets/traffic/jpnap_tokyo_year.png -o yearly.json  # 年次

# マルチバンドグラフから特定系列を抽出
cacti-tx-gen extract jpnap_yearly.png --series max -o yearly_max.json     # JPNAP yearly max バンド
cacti-tx-gen extract jpix_minmax.png --series min --total-duration 550d -o jpix_min.json  # JPIX minmax min 系列

# history グラフ（～25 年スパン）から抽出
cacti-tx-gen extract jpnap_history.png --total-duration 25y -o history.json

# 2. ピーク 10 Gbps、10 分に圧縮した OTG 設定を生成
cacti-tx-gen generate timeseries.json --peak-rate 10Gbps --duration 10m -o config.yaml

# 3. NS3 シナリオに変換
cacti-tx-gen convert-ns3 config.yaml -o scenario.py
```

## CLI リファレンス

### `cacti-tx-gen extract <image>`

IX トラフィックグラフから時系列データを抽出。IMAGE はローカルファイルパスまたは HTTPS URL。

| オプション | 説明 |
|---|---|
| `--ix` | IX タイプ: `jpix`、`bbix`、`jpnap`（省略時はファイル名から自動検出） |
| `--scale` | グラフのタイムスケール: `daily`、`weekly`、`monthly`、`yearly`（省略時はファイル名から自動検出） |
| `--y-max` | Y 軸最大値（例: `4Tbps`）。省略時はグリッド線から自動検出 |
| `--total-duration` | 明示的な全体期間（例: `550d`、`25y`、`2y6mo`）。`--scale` の期間を上書き |
| `--series` | マルチバンドグラフから抽出する系列: `max`、`avg`（デフォルト）、`min` |
| `-o` | 出力 JSON ファイル（デフォルト: 標準出力） |

ファイル名からのスケール自動検出:

| パターン | スケール | 期間 | リサンプリング間隔 |
|---|---|---|---|
| `*_d.png`、`*_day.png`、`TOTAL.In.png` | daily | 24h | 300s（5分） |
| `*_w.png` | weekly | 7d | 1800s（30分） |
| `*_m.png` | monthly | 30d | 7200s（2時間） |
| `*_y.png`、`*_year.png`、`*_history*` | yearly | 365d | 86400s（1日） |

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

| IX | グラフ種別 | MAX 誤差 | AVG 誤差 |
|---|---|---|---|
| JPIX | daily | < 2% | < 2.5% |
| JPIX | minmax（~550日、max/avg/min 系列） | < 5% | < 5% |
| BBIX | daily | < 0.5% | < 0.5% |
| JPNAP | daily | < 1.5% | < 1% |
| JPNAP | yearly（max/avg 系列） | < 10% | < 10% |
| JPNAP | history（~25年、max/avg 系列） | < 10% | < 10% |

## 実装状況

| コンポーネント | 状態 | 説明 |
|---|---|---|
| `extract/base.py` | 完了 | 基底 Extractor ABC: HSV 塗りつぶし上端検出、ピクセル→bps 変換、リサンプリング |
| `extract/jpix.py` | 完了 | JPIX パーサ: 緑色塗りつぶし、ティックベースのプロット領域検出、minmax グラフ対応（3 系列） |
| `extract/bbix.py` | 完了 | BBIX パーサ: Y 軸が 0 始まりでないためグリッド線キャリブレーション必須 |
| `extract/jpnap.py` | 完了 | JPNAP パーサ: pink/red/purple バンド検出、daily/yearly/history 対応、Y 軸ラベルフォールバック |
| `generate/otg.py` | 完了 | OTG 設定生成: スライスごとのフロー、レートスケーリング、時間圧縮 |
| `convert/ns3.py` | 完了 | NS3 シナリオ生成: レートスケジュール付き OnOffApplication |
| `cli.py` | 完了 | `extract`、`generate`、`convert-ns3` サブコマンド付き CLI; URL 入力、スケール自動検出 |
| テスト | 完了 | 102 テスト（extract、generate、convert、CLI 統合、ユーティリティ、スケール検出） |
| TG 実機検証 | 完了 | ixia-c / TRex / xdperf を containerlab で検証済み |

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
├── tests/
│   ├── README.md               # テストドキュメント
│   ├── fixtures/               # IX グラフサンプル PNG（daily、yearly、history、minmax）
│   ├── test_extract.py         # Extractor ユニットテスト
│   ├── test_generate.py        # OTG 生成テスト
│   ├── test_convert.py         # NS3 変換テスト
│   ├── test_cli.py             # CLI 統合テスト
│   └── test_utils.py           # ユーティリティ関数テスト
└── lab/
    ├── README.md               # ラボドキュメント
    ├── capture.py              # sysfs ベースのトラフィックキャプチャ + matplotlib グラフ
    ├── ixia-c/                 # ixia-c containerlab トポロジ + snappi 検証
    ├── trex/                   # TRex containerlab トポロジ + STL API 検証
    └── xdperf/                 # xdperf containerlab トポロジ + OTG アダプタ
```

## 開発

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## トラフィックジェネレータ検証

3 つの TG を [containerlab](https://containerlab.dev/) のバックトゥバック veth トポロジで検証済み:

| TG | 結果 | 方式 | 備考 |
|---|---|---|---|
| **ixia-c**（Community Edition） | PASS | snappi API（OTG ネイティブ） | ポートあたり最大 256 フロー、最小レート 672 bps |
| **TRex** v2.90 | PASS | STL API（コンテナ内実行） | snappi-trex は `fixed_seconds` 未対応のため STL API 直接使用 |
| **xdperf** | PASS | カスタム OTG アダプタ | veth 用 XDP generic mode フォールバックパッチ適用 |

### ラボトポロジ

```bash
# デプロイと検証
containerlab deploy -t lab/ixia-c/topology.clab.yml
python lab/ixia-c/validate.py

containerlab deploy -t lab/trex/topology.clab.yml
python lab/trex/validate.py --graph lab/trex/traffic_results.png

containerlab deploy -t lab/xdperf/topology.clab.yml
python lab/xdperf/validate.py
```

### xdperf generic mode パッチ

xdperf の `AttachXDP` 呼び出しは、ドライバーモードが利用不可能な場合（veth インターフェース）に generic mode へフォールバックしません。Dockerfile で `probe/xdp.go` に既に実装されている `XDPGenericMode` フォールバックと同様のパッチを適用しています。

### トラフィックグラフ化

TRex validate は `--graph` オプションで TRex Stats API から 1 秒ごとの TX/RX レートをプロットできます:

```bash
python lab/trex/validate.py --otg-config config.yaml --graph results.png
```

</details>
