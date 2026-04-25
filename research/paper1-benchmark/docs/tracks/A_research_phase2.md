# Track A — Phase 2: AI 提案パラメータの物理的正確性研究

策定日: 2026-04-25
ステータス: **active** (Phase 1 完了直後に Phase 2 着手)
出発点: Phase 1 (repro-v1 + repro-v1-dft) の知見

## 中心研究課題

> **「LLM が生成した DFT パラメータは、実際に pw.x に投入したとき、どの程度の物理的正確性を示すか」を統計的・物理的に明らかにする**

これは旧 Phase 2-C「Ensemble + guardrail で解決する」とは異なり、
**「現状の LLM 提案 params の正確性を *測ること自体* を主目的とする**」 という研究志向。

## 今までの研究結果のサマリ (Phase 1 末時点)

- 5 LLM × 100 trial の repro-v1 で **再現性問題** が顕在化 (大型モデルは seed=42 でも揺れる)
- 5 LLM 提案 params で repro-v1-dft により **物理的正確性問題** も顕在化
  - E_total が 2 つの cluster に分離 (-749.30 vs -749.71、差 0.4 Ry = 5.4 eV)
  - 小型 LLM (qwen2.5:7b, llama-3.1-8b) は決定論的だが physics 不正確 (ecut 不足)
  - 大型 LLM (gpt-oss-120b, qwen3-32b, llama-3.3-70b) は応答揺れあるが physics 妥当

→ Phase 2 の課題は **「この知見を 1 材料 5 モデルから N 材料 N モデルにスケールし、定量化する」**

## Phase 2 の 3 主要 hypothesis (検証対象)

| 仮説 | 検証方法 |
|---|---|
| **H1**: LLM 提案の物理正確性は **モデルサイズ ~7B-120B 範囲で対数的に向上** する | 同材料・複数モデルで E_total 真値からの偏差を測る |
| **H2**: LLM 提案の正確性は **材料の複雑さ (重元素・遷移金属の有無) で系統的に低下** する | Tier A (軽元素半導体) → B (perovskite) → C (ドープ Si) 順に劣化 |
| **H3**: LLM 提案の物理正確性 と 応答再現性 は **独立** な指標である | repro-v1 の unique 数 と repro-v1-dft の E_total 偏差は無相関 |

## Phase 2 実行計画 (Step 1-7)

### Step 1: 評価指標の正式定義 (1 日)

| 指標 | 定義 | 測定方法 |
|---|---|---|
| **DFT 収束度** | E_total ∈ "converged" cluster (≤ 1 mRy/atom from infinite cutoff limit) | 各材料で reference convergence test を別途実施 |
| **物理的妥当性 (smearing)** | 絶縁体に metallic smearing 不採用 | LLM 応答 vs 材料種別の照合 |
| **物理的妥当性 (gap)** | DFT 出力の band gap が PBE 文献値の 30% 以内 | NSCF 必須 (今回は SCF のみ、要拡張) |
| **応答再現性** | 同 prompt N=100 試行での unique 数 (repro-v1 と同形式) | 既実装、流用 |
| **コスト効率** | 収束達成までの wall-time | 既出力ファイルから抽出 |

deliverable: `orchestrator/accuracy_metrics.py`

### Step 2: 評価データセット拡張 (材料側、1-2 週)

現状 N=1 (CsPbI3 のみ DFT 検証済) を **N=20** にスケール:

| 拡張対象 | 材料数 | 必要 pseudo (新規 DL) |
|---|---|---|
| Tier A 軽元素半導体 | Si, Ge, GaAs, GaP, InP, AlAs, ZnO, ZnS, CdS, CdTe (10 材料) | Ge, In, Zn, Cd, Te (5 元素) |
| Tier B perovskite + 2D | CsPbBr3, CsSnI3, MoS2, BiVO4, TiO2 (anatase) (5 材料) | Sn, Br, Mo, S, Bi, V, Ti (7 元素) |
| Tier C ドープ Si | Si64:P, Si64:B, Si64:Al, Si64:As, Si64:Sb (5 材料) | P, B, Al, Sb (4 元素) |

deliverable: `materials/pseudos/` 拡張、各材料 fixture CIF

### Step 3: 評価データセット拡張 (LLM 側、1-2 日)

現状 5 モデル を **8-10 モデル** にスケール:

| 追加モデル | 取得方法 |
|---|---|
| Gemini 2.0 Flash, 2.5 Flash, 2.5 Pro | API key 必要 (user 年齢制限のため不可、要再判断) |
| Groq mistral-saba, llama-4-scout (利用可なら) | Groq API key 既存 |
| Ollama 上の追加: phi-4:14b, deepseek-r1:7b | local DL |
| Claude Opus / Sonnet (将来予算が出たら) | Anthropic API key 必要 |

deliverable: `llm/cloud.py` 拡張

### Step 4: 全組合せ実験 (中規模 N×M、~1 週)

20 材料 × 8 モデル = **160 実験 cell**。各 cell で:
- LLM に params 提案させる (10 試行で再現性も同時測定)
- 提案された params で DFT 実行
- DFT 結果から評価指標 5 種を抽出
- bundle 化して provenance zip

総 DFT job 数: 160 × 1 (代表 params) = 160 ジョブ。
GitHub Actions max-parallel 20 で wall **~3-5 時間**。費用 $0。

deliverable: `experiments/track-a-phase2/` 配下に 160 bundle

### Step 5: 統計解析 (1 週)

検証する 3 hypotheses について:

| H | 解析手法 |
|---|---|
| H1 (モデルサイズ vs 正確性) | log(model_params) vs E_total 偏差の log-linear fit |
| H2 (材料複雑度 vs 正確性) | 材料を「軽元素・重元素・遷移金属・ドープ」に分類し ANOVA |
| H3 (再現性 vs 正確性 独立性) | 各 LLM の (unique_count, mean_E_dev) を散布図、Pearson 相関 |

deliverable: `analyses/track-a-phase2/` 配下に Jupyter notebook + figures

### Step 6: 論文 draft 作成 (2 週)

target journal: npj Computational Materials, Digital Discovery, NPJ Quantum Materials のいずれか
- 論文タイトル草案: "Quantitative assessment of LLM-proposed first-principles parameters: a 8-model × 20-material benchmark"
- main figure: H1 のスケーリング、H2 の材料群比較、H3 の独立性
- supplementary: 全 160 cell の生データ + raw provenance

deliverable: `papers/track-a-phase2/draft.md` + figures

### Step 7: peer review 対応 (随時)

provenance bundle を arxiv supplementary に同梱、査読者が任意 cell を再現可能に。

## Phase 2 全体のタイムライン

| Phase 2 Step | 工数 | 累積週 |
|---|---|---|
| 1 評価指標定義 | 1 日 | 0.2 |
| 2 材料データセット拡張 | 1-2 週 | 1.5 |
| 3 LLM データセット拡張 | 2 日 | 1.7 |
| 4 全組合せ実験 | 1 週 | 2.7 |
| 5 統計解析 | 1 週 | 3.7 |
| 6 論文 draft | 2 週 | 5.7 |
| 7 査読対応 | 随時 (3-6 ヶ月) | — |

= **約 6 週間で論文 submission** が現実的なゴール。

## Phase 2 実行前に判断必要な事項

| 判断 | 選択肢 |
|---|---|
| Step 2 の材料 20 件で十分か | (a) 20 件で進める、(b) 50 件にスケールアップ |
| Step 3 の追加 LLM をどこまで含めるか | (a) Groq + Ollama の無料枠のみ、(b) Anthropic 有料 API も導入 |
| Step 4 の DFT 計算で NSCF / bands も含めるか | (a) SCF のみ (現状)、(b) NSCF 追加 (gap 評価可、計算量 3x) |
| 論文化を本気で目指すか | (a) Yes (Step 6-7 やる)、(b) 内部研究のみ (Step 5 で stop) |

## Phase 3 以降の展望 (草案)

Phase 2 が完了した時点で見えてくる可能性 (現時点では未確定):

- **Phase 3-A**: LLM の物理推論能力の介入実験 (prompt 工夫で改善するか)
- **Phase 3-B**: 物理制約 prompt + DFT-in-the-loop での fine-tuning
- **Phase 3-C**: ベンチマーク標準化 (他研究者が同じテストを走らせる仕組み)

これらは Phase 2 結果次第で取捨選択。

## 共通基盤との関係

Track A は以下の既存資産を **読み取り専用 / 拡張専用** で利用:

- `experiments/repro-v1/` (Phase 1 取得済 LLM 100 試行データ × 5 モデル)
- `experiments/repro-v1-dft/` (Phase 1 取得済 DFT 検証 5 件)
- `experiments/ai-param-v1/` (Claude Opus 提案 + DFT 検証 3 件)
- `orchestrator/` (DFT 実行・解析パイプライン)
- `materials/pseudos/` (SG15 ONCV PBE-1.2)
- `.github/workflows/ai-param-experiment.yml` (DFT 並列実行 workflow)
- `rag/` (1291 chunks の semantic 検索基盤)

Track B のために予約された機能 (F1-F7) には **手を付けない** (Track B 復活時に着手)。
