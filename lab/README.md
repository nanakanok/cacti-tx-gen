---
type: Playbook
title: cacti-tx-gen Lab
description: Containerlab-based validation environments for ixia-c, TRex, and xdperf traffic generators
tags:
  - lab
  - containerlab
  - ixia-c
  - trex
  - xdperf
timestamp: "2026-07-01"
---

# Lab — トラフィック生成の検証環境

[containerlab](https://containerlab.dev/) を使って OTG config をトラフィックジェネレータで実行し、生成パターンを検証する。

## 前提条件

- Docker
- [containerlab](https://containerlab.dev/install/)
- Python 3.10+ (validate スクリプト用)

## ディレクトリ構成

```
lab/
├── capture.py              # 汎用キャプチャ＆グラフ生成ツール
├── ixia-c/                 # ixia-c (Keysight OTG) 検証環境
│   ├── topology.clab.yml
│   ├── validate.py
│   ├── config.yaml         # サンプル OTG config
│   └── timeseries.json     # サンプル時系列
├── trex/                   # TRex 検証環境
│   ├── topology.clab.yml
│   ├── docker-compose.yml  # 代替起動用
│   ├── validate.py
│   └── trex_external_libs/ # TRex Python ライブラリ
└── xdperf/                 # xdperf (XDP) 検証環境
    ├── topology.clab.yml
    ├── Dockerfile
    ├── validate.py
    ├── xdp-generic-fallback.sh
    └── xdp-generic-fallback.patch
```

## トラフィックジェネレータ比較

| TG | プロトコル | API | 備考 |
| :--- | :--- | :--- | :--- |
| **ixia-c** | OTG ネイティブ | snappi (Python) | CE 版はフロー数 256 制限 |
| **TRex** | STL (Stateless) | TRex Python API | コンテナ内で実行。per-second 統計取得可能 |
| **xdperf** | XDP/eBPF | CLI + Wasm プラグイン | veth ではネイティブ XDP 不可→generic fallback パッチ適用 |

## 使い方

### 1. ixia-c

```bash
# トポロジ起動
sudo containerlab deploy -t lab/ixia-c/topology.clab.yml

# 検証 (サンプル config)
python lab/ixia-c/validate.py

# cacti-tx-gen の OTG config を使う場合
python lab/ixia-c/validate.py --otg-config lab/ixia-c/config.yaml --max-flows 10

# 停止
sudo containerlab destroy -t lab/ixia-c/topology.clab.yml
```

### 2. TRex

```bash
# containerlab で起動
sudo containerlab deploy -t lab/trex/topology.clab.yml

# または docker-compose
cd lab/trex && docker compose up -d

# 検証 (グラフ出力付き)
python lab/trex/validate.py --graph lab/trex/traffic_results.png

# OTG config 指定
python lab/trex/validate.py --otg-config path/to/config.yaml --max-flows 5 --graph results.png

# 停止
sudo containerlab destroy -t lab/trex/topology.clab.yml
```

### 3. xdperf

```bash
# Docker イメージビルド (初回のみ)
docker build -t cacti-xdperf:latest lab/xdperf/

# トポロジ起動
sudo containerlab deploy -t lab/xdperf/topology.clab.yml

# 検証
python lab/xdperf/validate.py

# OTG config 指定
python lab/xdperf/validate.py --otg-config path/to/config.yaml --max-flows 5

# 停止
sudo containerlab destroy -t lab/xdperf/topology.clab.yml
```

## capture.py — 汎用キャプチャツール

トラフィック生成中にインターフェースの TX/RX レートをキャプチャし、CSV + グラフを出力する。期待値 (timeseries JSON) とのオーバーレイ比較も可能。

```bash
# ローカルインターフェース監視
python lab/capture.py --iface eth0 --duration 60 --output results.png

# コンテナのインターフェース監視
python lab/capture.py --container clab-cacti-trex-trex --iface eth1 \
    --duration 60 --expected timeseries.json --output results.png --csv results.csv
```

## xdperf XDP generic fallback

xdperf は XDP ネイティブモードでの attach を試みるが、veth インターフェースではネイティブ XDP が利用できない。`xdp-generic-fallback.patch` は dummy RX プログラムの attach に失敗した場合 `XDPGenericMode` へフォールバックするよう修正する。Dockerfile のビルド時に自動適用される。

## 検証結果例

各 `validate.py` は以下の出力:
- **PASS** — フレーム送受信成功
- **PARTIAL PASS** — バイナリ/プラグイン正常だが XDP attach 不可 (xdperf)
- **FAIL** — フレーム送信なし

TRex の `validate.py` は `--graph` オプションで per-second TX/RX レートのグラフを出力する (`traffic_results.png`)。
