# repro-v1-dft — 5 LLM 提案 params で CsPbI3 SCF 検証 (最終結果)

実施日: 2026-04-25
材料: CsPbI3 (cubic perovskite Pm-3m, 5 atoms, a=6.289 Å)
バックエンド: GitHub Actions (matrix 並列、QE 7.5, conda-forge)
費用: $0

## 5 モデル DFT 検証 結果表

| モデル | ecutwfc | ecutrho | k-pts (full) | smearing | degauss | iter | **E_total Ry** | **Fermi eV** | wall (s) | k-pts (IBZ) |
|---|---:|---:|:---:|:---:|---:|:---:|---:|---:|---:|---:|
| qwen2.5:7b | 30 | 120 | (4,4,4) | **fermi-dirac** | **0.05** | 8 | **−749.34758** | **5.993** | 770 | 10 |
| llama-3.1-8b | 30 | 120 | (4,4,4) | gaussian | 0.01 | 10 | **−749.30317** | 5.716 | 858 | 10 |
| llama-3.3-70b | 40 | 160 | (4,4,4) | fermi-dirac | 0.01 | 7 | −749.68139 | 5.583 | 719 | 10 |
| gpt-oss-120b | 80 | 320 | (6,6,6) | gaussian | 0.01 | 7 | **−749.70482** | 5.710 | 1,726 | 20 |
| qwen3-32b | 70 | 280 | (8,8,8) | gaussian | 0.01 | 7 | **−749.70516** | 5.709 | 2,933 | 35 |
| 参考: Claude Opus (ai-param-v1) | 60 | 480 | (6,6,6) | gaussian | 0.005 | 9 | −749.70395 | 6.007 | 1,832 | 10 |
| 参考: rule-based | 40 | 320 | (4,4,4) | gaussian | 0.01 | 9 | −749.68192 | 5.716 | 816 | 10 |

## 物理学的に重要な発見

### 発見 1: E_total が 2 つの cluster に明確分離

| cluster | E_total 範囲 | 該当モデル | params 特徴 |
|---|---|---|---|
| **「未収束」cluster** | −749.30 〜 −749.35 Ry | qwen2.5:7b, llama-3.1-8b | ecutwfc = 30 Ry (Pb 5d 半コアに不足) |
| **「収束」cluster** | −749.68 〜 −749.71 Ry | llama-3.3-70b, gpt-oss-120b, qwen3-32b, Claude Opus | ecutwfc ≥ 40 Ry |

差分 ≈ **0.4 Ry (5.4 eV)** — 物理計算として致命的に大きい。形成エネルギー比較や材料スクリーニングで誤った結論を導く規模。

### 発見 2: 「小型 LLM は決定論的だが物理的に間違える」 を数値実証

- **C4 claim** (Phase 1 中核 5 主張) を直接補強するデータ
- qwen2.5:7b の "fermi-dirac + degauss=0.05" は **pw.x を crash させない** が、Fermi energy が **+0.28 eV 偽位置** に出る (smearing が gap を埋める artifact)
- llama-3.1-8b は smearing は正しい (gaussian) が ecut が浅すぎて E_total 未収束

→ 「LLM 提案が DFT で動くか」と「物理的に正しいか」は **別の話**。動くだけなら 5/5 OK、物理的に妥当なのは 3/5。

### 発見 3: コスパ評価

| モデル | E_total 収束度 | wall s | 評価 |
|---|---|---:|---|
| **llama-3.3-70b** | ✅ 収束 | **719** | ★★★ 最良 (収束 + 最速) |
| gpt-oss-120b | ✅ 収束 | 1,726 | ★★ |
| qwen3-32b | ✅ 収束 | 2,933 | ★ (k=8³ 過剰) |
| qwen2.5:7b | ✗ 未収束 + 物理 wrong | 770 | ☆ 速いが誤値 |
| llama-3.1-8b | ✗ 未収束 | 858 | ☆ 速いが未収束 |

## Phase 1 の論証完了

| Paper 1 主張 | 裏付けデータ |
|---|---|
| ① cloud 大型 LLM は seed=42 でも応答揺れる | repro-v1 N=100 |
| ② Reasoning モデルは特に非決定論的 | qwen3-32b 11/11 unique |
| ③ 小型 LLM は決定論的 | qwen2.5:7b, llama-3.1-8b 100/100 一致 |
| ④ **小型 LLM の決定論性は物理的妥当性を保証しない** | **本実験の DFT 検証 (E_total 0.4 Ry ずれ)** |
| ⑤ 大型 LLM は揺れるが揺れの中身は概ね物理妥当 | gpt-oss-120b/qwen3-32b/llama-3.3-70b 全て E_total -749.68〜-749.71 |
| ⑥ 実用には ensemble + DFT 検証 + 研究者判断が必要 | 上記 ①-⑤ の総合 |

## 再現可能性 (provenance)

各 zip bundle に以下を同梱:
- `prediction.json` — 元 LLM 提案 + メタ
- `input.in` — pw.x 入力 (SHA-256 ID)
- `output.out` — pw.x 完全出力
- `metadata.json` — schema `paper3.provenance.ai-param.v1`、env hash 含む
- `summary.json` — observables 14 項目

再パース: `python3 -m orchestrator parse <bundle.zip>`
