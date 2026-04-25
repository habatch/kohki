# PROJECT TRACKS — 2 軸への分岐宣言

実施日: 2026-04-25 (Phase 1 完了直後)

本プロジェクトは Phase 1 の知見をもとに、これ以降 **2 つの独立トラック** に分岐します。両トラックは並行して保存・管理されますが、**どちらが現在 active か** は `docs/CURRENT.md` に明示します。

## Track A: 研究テーマ (active)

> **「AI が生成したパラメーターは、物理的に計算させたときにどの程度の正確性を持つのか」 を統計的・物理的に明らかにする**

- 旧 Phase 2-C「Ensemble + guardrail」の核問題意識を継承し、「ensemble で解決」ではなく「**現状の AI 提案 params の正確性を測ること自体を研究テーマ**」に再定義
- Phase 1 の repro-v1 (LLM 100 試行) + repro-v1-dft (5 モデル DFT 検証) が出発データセット
- 詳細: [`docs/tracks/A_research_phase2.md`](tracks/A_research_phase2.md)

## Track B: ビジネスアイデア (parked)

> **「研究者の第一原理計算を根本的にサポートする仕組みとアプリを作り、これを売る」**

- F1-F7 の 7 機能 (収束 sweep / 文献値 pull / template / RAG / plot / dashboard / 論文抽出比較) を持つ軽量 QE パイプラインの製品化
- Winmostar / AiiDA / atomate2 等の既存ツールとの差別化分析済
- 現在は **保留** (Track A の研究データ蓄積後に再評価)
- 詳細: [`docs/tracks/B_business_phase2.md`](tracks/B_business_phase2.md)

## トラック関係図

```
Phase 1 (完了)
  │
  ├── repro-v1 (LLM 100 試行 × 5 モデル)
  └── repro-v1-dft (5 モデル提案 → DFT 検証)
        │
        ▼
   ┌──────────────────────────────────────────┐
   │   分岐 (本ドキュメント)                    │
   └──────────────────────────────────────────┘
        │                              │
        ▼ active                       ▼ parked
   ┌────────────┐               ┌────────────┐
   │  Track A   │               │  Track B   │
   │  研究        │               │  ビジネス     │
   │  Phase 2:   │               │  Phase 2:   │
   │  AI param   │               │  研究者支援   │
   │  accuracy   │               │  ツール (F1-F7)│
   └────────────┘               └────────────┘
        │
        ▼
    (Phase 3, 4, ... 順次定義)
```

## 切替手順

| 操作 | 方法 |
|---|---|
| 現在のトラック確認 | `cat docs/CURRENT.md` |
| トラック切替 | `docs/CURRENT.md` を編集 (active / parked タグ変更) |
| トラック内 phase 進行 | 各 track の Phase 番号を逐次インクリメント |

## 共通基盤 (両トラックで共有)

両トラックが利用する共通インフラ:

| 共通基盤 | 内容 |
|---|---|
| `orchestrator/` | DFT 入力生成・解析 (qe_inputs, qe_parser, provenance) |
| `llm/` | LLM クライアント (cloud.py: Gemini/Groq, client.py: Anthropic) |
| `apps/repro-viewer/` | Next.js 可視化 UI |
| `experiments/` | 実験データ蓄積 |
| `materials/` | 材料カタログ (Tier A/B/C) + fixture CIF + pseudo |
| `rag/` | bge-m3 + lancedb 索引 (Track A の解析、Track B の F4 両用) |
| `.github/workflows/` | qe-batch.yml, ai-param-experiment.yml |

両トラックの開発はこれらを **共有・破壊しない** 形で進めます。
