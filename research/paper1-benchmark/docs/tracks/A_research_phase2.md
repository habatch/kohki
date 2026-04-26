# Track A — Phase 2: AI 提案パラメータの物理的正確性研究

策定日: 2026-04-25
ステータス: **active** (Phase 1 完了直後に Phase 2 着手)
出発点: Phase 1 (repro-v1 + repro-v1-dft) の知見

**改訂履歴**:
- 2026-04-25: 初版 (3 hypothesis H1-H3、5 LLM × 20 材料 plan)
- 2026-04-26 朝: ensemble 統合 (H4-H6 追加、4 ensemble 手法)、N=10 確定
- 2026-04-26 午後: **TritonDFT (arXiv 2603.03372) 発見後の再位置付け**
  - 同テーマで 8 LLM (proprietary) × 68 材料の先行研究があった
  - 本研究の差別化軸 (open-source LLM / reasoning 軸 / ensemble / repro) を明確化
  - 1 meV/atom 互換 metric 追加、NiO (磁性系) 追加 (TritonDFT 直接対比)

## 中心研究課題 (TritonDFT 後の再定義)

> **「Open-source LLM 単独 + Ensemble 集約は、proprietary agentic 系 (TritonDFT)
>   と比べて第一原理計算 param 提案でどこまで実用的か?」**

旧版 ("LLM 提案 params の正確性を測ること自体") は TritonDFT に既に踏まれており、
本研究は **proprietary 一辺倒の状況に対する OSS + ensemble の代替提示** として
位置付け直す。これは「測定」から「**測定 + 代替提案**」への研究目標 upgrade。

これは旧 Phase 2-C「Ensemble + guardrail で解決する」と異なり、
**「現状の LLM 提案 params の正確性を *測ること自体* を主目的とする**」 という研究志向。

## 今までの研究結果のサマリ (Phase 1 末時点)

- 5 LLM × 100 trial の repro-v1 で **再現性問題** が顕在化 (大型モデルは seed=42 でも揺れる)
- 5 LLM 提案 params で repro-v1-dft により **物理的正確性問題** も顕在化
  - E_total が 2 つの cluster に分離 (-749.30 vs -749.71、差 0.4 Ry = 5.4 eV)
  - 小型 LLM (qwen2.5:7b, llama-3.1-8b) は決定論的だが physics 不正確 (ecut 不足)
  - 大型 LLM (gpt-oss-120b, qwen3-32b, llama-3.3-70b) は応答揺れあるが physics 妥当

→ Phase 2 の課題は **「この知見を 1 材料 5 モデルから N 材料 N モデルにスケールし、定量化する」**

## Phase 2 の 6 主要 hypothesis (検証対象)

### 個別 LLM 評価 (H1-H3、Phase 2 の中核)

| 仮説 | 検証方法 |
|---|---|
| **H1**: LLM 提案の物理正確性は **モデルサイズ ~7B-120B 範囲で対数的に向上** する | 同材料・複数モデルで E_total 真値からの偏差を測る |
| **H2**: LLM 提案の正確性は **材料の複雑さ (重元素・遷移金属の有無) で系統的に低下** する | Tier A (軽元素半導体) → B (perovskite) → C (ドープ Si) 順に劣化 |
| **H3**: LLM 提案の物理正確性 と 応答再現性 は **独立** な指標である | repro-v1 の unique 数 と repro-v1-dft の E_total 偏差は無相関 |

### Ensemble 評価 (H4-H6、2026-04-26 追加)

研究プランの方針 (= AI/LLM の能力上限を探る) に沿って ensemble 手法を統合。
個別 LLM が物理的に不適切な提案をする場合、複数 LLM の組み合わせや物理ガード
レールで救済できるか — を統計的に検証する。

| 仮説 | 検証方法 |
|---|---|
| **H4**: Ensemble (= 複数 LLM の集計) は **個別 LLM より物理正確性が高い** | (A) parameter-wise voting / (B) accuracy 加重 / の 2 ensemble を post-hoc 計算し、個別 LLM 平均と比較 |
| **H5**: 物理ガードレール (例: 絶縁体に metallic smearing 禁止) を追加すると **ensemble の正確性は向上する** | (C) guardrail + voting と (A) を比較 |
| **H6**: 材料種別ルーティング (MoE 風) は **単一 LLM より有効** | (E) 材料を Tier A/B/C で分け、各 Tier で最も正確だった LLM を割り当てた仮想 ensemble を構築、個別 LLM 平均と比較 |

### Ensemble 手法定義 (Phase 2 で計算する 4 手法)

| 手法 | 内容 | 追加 LLM call | 追加 DFT |
|---|---|---|---|
| **(A) parameter-wise voting** | 各 LLM 提案の最頻 mode params を「N LLM 全体の中央値 / 最頻」で集計 | 0 | 0 (post-hoc 解析のみ) |
| **(B) accuracy 加重平均** | Phase 2 の H1 結果から各 LLM に accuracy weight を付与し加重平均、leave-one-out で循環回避 | 0 | 0 |
| **(C) guardrail + voting** | 物理制約 (smearing/ecut/degauss range) で不合理提案をフィルタ、残りで (A) | 0 | 0 |
| **(E) MoE 材料ルーティング** | 各 Tier で最良の LLM を選び、材料種別で割り当てた virtual ensemble | 0 | 0 |

**Phase 2 では ensemble 検証用 DFT を当初行わない方針 (2026-04-26 朝)** だったが、
**午後にユーザ判断で 40 ensemble cell の DFT も実行に変更**。GH Actions ai-param-experiment.yml
で個別 50 cell + ensemble 39 cell + NiO 拡張 10 cell = 99 cell を並列実行。

### TritonDFT 対比評価 (H7、2026-04-26 午後 追加)

| 仮説 | 検証方法 |
|---|---|
| **H7**: Open-source LLM (qwen / llama / phi / deepseek 系) は proprietary LLM (GPT-5 / Claude / Gemini) と DFT param 提案の正確性で **どこまで肩を並べるか** | TritonDFT (Wang et al. 2026) の 1 meV/atom pass rate と本研究の OSS LLM 結果を同 metric で並置。同 LLM サイズ帯 (~70B) で OSS と proprietary の gap を測定 |
| **H8** (派生): 磁性系では OSS LLM も proprietary LLM 同様に失敗するか | NiO で 5 OSS LLM の DFT+U / nspin / starting_magnetization 言及率を測定し、TritonDFT 報告 (proprietary 全 LLM <6% pass) と比較 |

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

- 論文タイトル草案 (2026-04-26 午後 改訂、TritonDFT 後の re-positioning 版):
  "Are open-source LLMs and ensemble methods competitive with proprietary
   agentic systems for first-principles parameter selection?
   A complementary 7-LLM × 11-material benchmark with 1 meV/atom accuracy
   and reproducibility metrics"

- 旧版 (ensemble 統合版、TritonDFT 発見前):
  "Can ensemble methods make LLMs reliable for first-principles parameter
   selection? A 5-model × 10-material study with 4 ensemble baselines"

- main figure:
  - Fig 1: H1 LLM サイズ vs 正確性 (log-linear) — open-source / proprietary 軸を色分け
  - Fig 2: H2 材料群比較 (Tier A/B/C + 磁性 NiO) — TritonDFT との pass rate 並置
  - Fig 3: H3 再現性 (unique 数) vs 正確性 (E_total deviation) 散布図 — N=10 trials 由来
  - Fig 4: H4 ensemble vs 個別 LLM の 1 meV/atom pass rate
  - Fig 5: H5 guardrail 効果 (ensemble C vs A の差分)
  - Fig 6: H6 MoE 材料ルーティング vs 単一 LLM
  - Fig 7: TritonDFT 既往データとの直接対比表 (open-source と proprietary の同条件比較)

- supplementary:
  - 全 cell 生データ (LLM call response + DFT input/output + provenance)
  - ensemble post-hoc 解析の中間ファイル
  - reference convergence test 全 ecut sweep カーブ
  - NiO の magnetic config 議論 (LLM が DFT+U / nspin=2 を提案しなかった事実)

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
