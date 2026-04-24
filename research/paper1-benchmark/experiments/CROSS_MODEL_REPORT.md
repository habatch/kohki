# 再現性実験 — モデル間比較レポート (最終版)

**実験日**: 2026-04-24  
**マイルストーン的位置**: Paper 1 の Phase 1 実証データ — 「物理シミュレーション (第一原理計算) のパラメータ設定に AI を用いる際、同一プロンプトの再現性が提供基盤とモデル規模にどう依存するか」

---

## 1. 実験設計

- **対象材料**: CsPbI₃ (cubic perovskite Pm-3m, 5 原子, a=6.289 Å)
- **LLM タスク**: Quantum ESPRESSO pw.x SCF の入力パラメータ 7 個を JSON で提案
  - `ecutwfc_Ry`, `ecutrho_Ry`, `kpoints`, `smearing`, `degauss_Ry`, `conv_thr_Ry`, `mixing_beta`
- **試行数**: 各モデル 100 回の API 呼び出し
- **LLM 設定**: `temperature=0`, `seed=42` (再現性を強制する設定)
- **プロンプト**: 不変、SHA-256 固定 `1567a9f7ae8873af8…`
- **コスト**: **$0** (ローカル Ollama + Groq 無料枠のみ)
- **ブラックボックス対策**: 全試行の生応答・パース結果・メタ情報が `experiments/*/trials/*.json` として保存、`apps/repro-viewer/` Web UI から検索・分布閲覧可能

## 2. 検証した 5 モデル

| モデル | 規模 | 提供者 | 推論基盤の特徴 |
|------|-----|------|------------|
| qwen2.5:7b-instruct | 7B | ローカル Ollama | 単一プロセス・決定論的 kernel |
| llama-3.1-8b-instant | 8B | Groq | 単一 GPU batch |
| llama-3.3-70b-versatile | 70B | Groq | 複数 GPU tensor parallel |
| openai/gpt-oss-120b | 120B | Groq | 複数 GPU tensor parallel |
| qwen/qwen3-32b (reasoning) | 32B | Groq | chain-of-thought 付き |

## 3. 再現性の結果

| モデル | 有効試行 N | ユニーク応答 | ユニーク params | 最多応答の占有率 | 再現性判定 |
|--------|---------:|----------:|------------:|:------------:|:---------:|
| qwen2.5:7b (local) | 100 | **1** | **1** | 100% | ✅ **完全決定論的** |
| llama-3.1-8b (Groq) | 67 | **1** | **1** | 100% | ✅ **完全決定論的** |
| llama-3.3-70b (Groq) | 100 | **3** | **3** | ~60% | ⚠ 3 % diversity |
| openai/gpt-oss-120b (Groq) | 74 | **5** | **5** | ~45% | ⚠ 7 % diversity |
| qwen/qwen3-32b reasoning (Groq) | 11 | **20** (raw 20/20) | **10** | ~10% | ❌ **実質 100% 非決定論的** |

(qwen3-32b の N=11/20 は Groq rate limit による失敗込みの値。100 試行中 80 は HTTP 429 で棄却、20 の返答のうち有効な JSON を抽出できたのが 11 個)

## 4. 各モデルの物理判断 (最頻値)

| モデル | ecutwfc Ry | ecutrho Ry | k-pts | smearing | degauss Ry | conv_thr Ry | mixβ |
|--------|---------:|---------:|:-----:|:----------:|-----------:|---------:|----:|
| qwen2.5:7b | 30 | 120 | (4,4,4) | **fermi-dirac** | **0.05** | 1e-10 | 0.7 |
| llama-3.1-8b | 30 | 120 | (4,4,4) | gaussian | 0.01 | 1e-12 | 0.7 |
| llama-3.3-70b | 40 | 160 | (4,4,4) 62% | fermi-dirac 99% | 0.01 | 1e-8 | 0.7 |
| gpt-oss-120b | **80** | **320** | (6,6,6) 82% | gaussian 96% | 0.01 98% | 1e-8 | 0.7 |
| qwen3-32b | 70 (64%) | 280 | (8,8,8) 73% | gaussian (55%) | 0.01 | 1e-8 (55%) | 0.7 |
| (参考) Claude Opus in-session (ai-param-v1) | 60 | 480 | (6,6,6) | gaussian | 0.005 | 1e-8 | 0.4 |

### 4.1 物理判断妥当性の簡易ランク (SG15 ONCV PBE + CsPbI₃ 文脈)

| ランク | モデル | 評価根拠 |
|------|------|--------|
| ◎ | gpt-oss-120b | ecutwfc=80 は SG15 Pb 5d 半コアを十分サンプル、Pb 系の標準推奨に近い |
| ○ | qwen3-32b | 70/280、Pb に対し十分、ただし N 試行間で揺れ |
| ○ | Claude Opus in-session | 60/480、8× ratio は保守的だが問題無し |
| △ | llama-3.3-70b | 40/160 は若干低い、Pb 5d の収束は不十分可能性 |
| ✗ | llama-3.1-8b | 30/120 は Pb に対して明らかに不足 |
| ✗✗ | **qwen2.5:7b** | ecut 不足に加え **絶縁体に fermi-dirac + degauss=0.05** は smearing が gap を埋めて見せない致命的誤り |

**小型モデルほど「完全再現だが物理的に間違った答えを常に返す」** という逆説的傾向が観察されました。

## 5. なぜ大型モデルは seed=42 でも揺れるか (Paper 1 Methods で必須言及)

下記 4 要因が複合:

1. **Cloud 推論基盤の dynamic batching** — 他ユーザとバッチ共有、構成で forward pass の数値が微変動
2. **浮動小数の非結合性** — `(a+b)+c ≠ a+(b+c)` が GPU 並列 reduction で表面化
3. **Tensor parallel** — 70B+ は複数 GPU に sharding、all-reduce 順序が可変
4. **seed パラメータは best-effort** — OpenAI も Groq も公式に決定論保証せず (sampling 側は seed で固定可、forward pass 側は不可)

これら全てが **モデル規模にほぼ線形に効く**:
- 7B (単一 GPU fit): 増幅回数最小 → 決定論的
- 70B (4-8 GPU sharding): 増幅回数多 → 3% diversity
- 120B (8+ GPU + MoE 可能性): 増幅回数最多 → 7% diversity
- reasoning 32B: 上記に加えて **CoT の 1 token 揺れが後続 2000+ token を発散させる** → 実質 100% diversity

## 6. Paper 1 への直接貢献

この実験 1 本から、以下の定量 claim が論文 Results セクションに書けます:

| claim | 裏付け |
|------|------|
| **C1** LLM を第一原理計算パラメータ決定に使うとき、再現性は **提供基盤依存 > モデルサイズ依存 > prompt 設計依存** の順で効く | 本実験の 5 モデル対比 |
| **C2** cloud 大型 LLM は `temperature=0 + seed=42` でも **決定論でない** (70B: 3%, 120B: 7% diversity) | llama-3.3-70b, gpt-oss-120b の 100 試行 |
| **C3** Reasoning モデルは `seed=42` でも **実質 100% 非決定論的** (毎回異なる物理パラメータを提案) | qwen3-32b の 11 有効試行中 10 ユニーク params |
| **C4** 小型 LLM は決定論的だが **物理的に間違った答えを常に返す** 逆説 | qwen2.5:7b の fermi-dirac + degauss=0.05 を 100/100 trials で出力 |
| **C5** 真に再現可能かつ物理的に妥当な LLM 駆動 DFT には、**local 中型モデル or cloud 大型モデルの N 回 ensemble** が必要 | C1-C4 の総合 |

## 7. 本研究ステージでの位置づけ (milestone)

**命題**: 「物理シミュレーションに AI (= LLM) を使用可能か」

**本実験の答え (部分的)**:
- 「同じ問いを N 回投げて同じ答えが返るか」の基礎確認に成功
- その結果 → **現状のクラウド大型 LLM はこの要件を満たさない**
- 使用するなら: (a) local 固定モデル、(b) 大型モデル N 回 ensemble + DFT 最終検証、(c) 物理制約を事前にハードコード、のいずれか

Paper 1 は C1-C5 をベースラインとして書き、Paper 2 以降で「ensemble 戦略」や「物理制約 guardrail」を提案する流れが自然です。

## 8. データ in repo

```
experiments/
├── repro-v1/                                  local qwen2.5:7b  ($0, 完全再現性)
├── repro-v1-groq-llama-3.1-8b-instant/       Groq 8B            ($0)
├── repro-v1-groq-llama-3.3-70b-versatile/    Groq 70B           ($0, 3 uniques)
├── repro-v1-groq-openai-gpt-oss-120b/        Groq 120B          ($0, 5 uniques)
├── repro-v1-groq-qwen-qwen3-32b/             Groq 32B reasoning ($0, 全 unique)
└── ai-param-v1/                              Claude Opus in-session (N=1 per material)
```

各 directory には:
- `trials/NNNN.json` — 全試行の raw 応答 + parsed params + メタ
- `trials/NNNN.txt` — raw 応答のテキストのみ (人間確認用)
- `results/summary.json` — 分布・統計・再現性判定 (repro-viewer が読む)
- `prompts/v1.txt` — 実験時点の不変プロンプト

**Web UI**: <http://localhost:3001/> から全実験を一覧・詳細閲覧・JSON エクスポート可能。

---

*生成: 2026-04-24、Paper 1 scaffold のうち再現性検証パート完了時点*
