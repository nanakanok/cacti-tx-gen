---
type: Reference
title: cacti-tx-gen Tests
description: Test suite structure, execution, and fixture inventory for cacti-tx-gen
tags:
  - testing
  - pytest
timestamp: "2026-07-01"
---

# Tests

## 実行方法

```bash
# 全テスト実行
pytest

# verbose 出力
pytest -v

# 特定テストファイル
pytest tests/test_extract.py

# 特定テストクラス/メソッド
pytest tests/test_extract.py::TestJPNAPYearly::test_yearly_avg_accuracy

# カバレッジ付き
pytest --cov=cacti_tx_gen
```

## テストファイル構成

| ファイル | テスト数 | 対象 |
| :--- | ---: | :--- |
| `test_extract.py` | 33 | 各IXグラフからの時系列抽出 |
| `test_generate.py` | 12 | OTG config 生成 |
| `test_convert.py` | 18 | NS3 シナリオスクリプト変換 + パイプライン round-trip |
| `test_cli.py` | 11 | CLI コマンド (extract / generate / convert-ns3) |
| `test_utils.py` | 18 | ユーティリティ関数 (parse_rate, detect_scale 等) |

## test_extract.py

グラフ画像 (PNG) から `bps` 時系列を抽出する各 Extractor の精度・構造テスト。

| クラス | 内容 |
| :--- | :--- |
| `TestJPIXExtractor` | JPIX daily グラフ。構造検証、AVG/MAX 精度 (10%以内)、リサンプリング |
| `TestBBIXExtractor` | BBIX daily グラフ。構造検証、AVG/MAX 精度、gridline キャリブレーション |
| `TestJPNAPExtractor` | JPNAP daily グラフ。構造検証、精度、y_max 手動指定 |
| `TestJPNAPYearly` | JPNAP yearly グラフ。avg/max 系列精度、band 検出、daily との非干渉 |
| `TestJPNAPHistory` | JPNAP history グラフ (~25年)。抽出確認、max ピーク精度、scale 自動検出 |
| `TestJPIXMinmax` | JPIX minmax グラフ (~550日)。minmax 検出、max > avg > min 順序、total_duration |
| `TestTimeScale` | TimeScale enum。duration/resample interval/time range の各スケール検証 |
| `TestExtractorOutput` | JSON シリアライズ可能性、時間の単調増加 |

## test_generate.py

`generate_otg_config()` の OTG フロー生成ロジック。

- 基本生成・フロー構造
- peak rate スケーリング
- duration 圧縮
- packet size / protocol / IP アドレス設定
- interval リサンプリング
- エラーケース (空ポイント、全ゼロ)

## test_convert.py

`convert_to_ns3()` で OTG config → NS3 Python スクリプト変換。

**TestConvertToNs3** — 単体テスト:
- 生成コードが `compile()` を通る (構文的に正しい Python)
- SCHEDULE、IP、protocol、packet size、link speed が出力に含まれる
- TCP/UDP 切替
- 空フローのエラー

**TestPipelineRoundTrip** — extract → OTG → NS3 の end-to-end 形状一致テスト:
- 各IXサンプル画像 (JPIX daily, BBIX daily, JPNAP daily, JPNAP yearly max, JPIX minmax avg) から抽出した時系列と、NS3 SCHEDULE のレートパターンの Pearson 相関係数が 0.90 以上であることを検証
- peak rate スケーリング精度 (1%以内)
- SCHEDULE の合計 duration がソース時系列と一致 (5%以内)
- 全レートが正値

## test_cli.py

Click CLI コマンドの統合テスト (`CliRunner` 使用)。

- `extract`: JPIX/BBIX/JPNAP の各 IX、IX 自動検出、stdout 出力、scale 指定/自動検出
- `generate`: 基本生成、duration 圧縮、各オプション (packet-size, protocol, src/dst-ip)
- `convert-ns3`: OTG → NS3 変換パイプライン
- `--help`: 各コマンドのヘルプ表示

## test_utils.py

CLI ユーティリティ関数の単体テスト。

- `_parse_rate`: 各単位 (Tbps, Gbps, Mbps, Kbps, bps, Gb/s)、float、不正入力
- `_parse_duration`: h/m/s、数値文字列、小数
- `_detect_ix`: ファイル名からの IX 自動検出
- `_detect_scale`: ファイル名/URL からの scale 自動検出 (daily/weekly/monthly/yearly)
- `_parse_total_duration`: d/y/mo 単位、複合 (2y6mo)、秒数直指定

## fixtures/

テスト用のグラフ画像。実際の IX トラフィックレポートから取得した PNG。

| ファイル | 説明 |
| :--- | :--- |
| `jpix_sample.png` | JPIX daily (24h) |
| `jpix_minmax_sample.png` | JPIX minmax (~550日、3系列: max/avg/min) |
| `bbix_sample.png` | BBIX daily (24h) |
| `jpnap_sample.png` | JPNAP daily (24h、pink fill) |
| `jpnap_yearly_sample.png` | JPNAP yearly (1年、red=max / purple=avg の2バンド) |
| `jpnap_history_sample.png` | JPNAP history (~25年、yearly と同じ2バンド構造) |
