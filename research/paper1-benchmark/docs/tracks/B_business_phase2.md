# Track B — Phase 2: 研究者向け第一原理計算サポートツール (parked)

策定日: 2026-04-25
ステータス: **parked** (Track A の研究結果蓄積後に再評価予定)

## ビジネス命題

> **「研究者の第一原理計算を根本的にサポートする仕組みとアプリを作り、これを売る」**

## 5 つの設計原則 (R1-R5)

| # | 原則 | 帰結 |
|---|---|---|
| R1 | 研究者が常に最終判断者 | ツールは "提案" のみ、決定はしない |
| R2 | AI は判断系から退場、自動化系に注力 | param 推奨や物理解釈は AI が出さない。代わりに反復計算・集計・可視化を担う |
| R3 | 全出力に "AI が触ったか" のタグ付け | 文字列 / 数値 / プロット 各段階で source を可視化 |
| R4 | 研究者の override が常に可能 | あらゆる設定を YAML / CLI で覆せる、強制されるものなし |
| R5 | provenance は徹底、再現性は研究者が確認できる粒度で | 実行コマンド / 入力 / 出力 / 環境ハッシュ全て zip |

## 7 機能 (F1-F7)

| # | 機能 | AI 関与 | 中核タスク |
|---|---|:---:|---|
| **F1** | 収束テスト自動ランナー | ✗ ゼロ | ecut/k 等の sweep を Actions で並列実行、結果を curve に |
| **F2** | リテラチャ参照値プル + 並置 | ✗ ゼロ | MP/NOMAD/OQMD API から既往値を取得、my-result と並置 |
| **F3** | ボイラープレート生成器 | ✗ ゼロ | 新規材料の入力ファイル雛形 (placeholder 付) |
| **F4** | 既往計算 provenance 検索 (RAG) | △ embed のみ | 過去 trial を自然言語で意味検索 |
| **F5** | publication-quality plot | ✗ ゼロ | 数値 → matplotlib 固定テンプレで論文用 PDF/SVG |
| **F6** | 反復実験の状態 dashboard | ✗ ゼロ | 進行中ジョブ + 完了 artifact の web UI |
| **F7** | 論文パラメータ抽出 + 比較 | △ extraction | PDF → 構造化抽出 (citation 必須) + 既往 my-result と並置 + 不足項目ハイライト |

## 競合との差別化 (3 軸)

### 軸 A: セットアップ 0 分の provenance + クラウド分散

- AiiDA の provenance は世界最高だが、MongoDB+daemon+plugin で **数日のセットアップ**
- atomate2 も同様
- Winmostar は provenance が弱い
- **本ツール**: pip install 相当のみ、GitHub Actions で計算、provenance zip 自動

### 軸 B: 過去計算の自然言語検索 (RAG)

- 主要 DFT ツールに semantic search は存在しない (formula 名・タグ検索止まり)
- **本ツール**: bge-m3 + lancedb で「ecut=80 を選んだ過去 trial」「絶縁体に fermi-dirac を提案した応答」が一発検索可能

### 軸 C: AI 関与の transparent labeling

- 既存ツールは AI を全く使わない (Winmostar/MedeA は完全決定論)
- AI を入れるツールは関与境界が曖昧
- **本ツール**: 全出力に source タグ強制 (R3)

## 競合比較表

| 機能 | Winmostar (商用) | MedeA (商用) | AiiDA (OSS) | atomate2 (OSS) | ASE (OSS) | Materials Project (Web) | **本ツール** |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 3D 構造 GUI 編集 | ◎ | ◎ | ✗ | ✗ | △ | ○ | ✗ |
| マルチコード対応 | ◎ 10+ | ◎ 10+ | ○ プラグイン | ○ | ○ | △ | ✗ (QE 専用) |
| 自動収束テスト | △ 手動 | ○ | ○ workflow | ◎ | ✗ | — | ◎ F1 |
| 文献値プル + 並置 | ✗ | △ 内蔵 DB | ✗ | ✗ | ✗ | ◎ ブラウザ | ◎ F2 |
| publication plot | ○ | ○ | ✗ | △ | △ | ✗ | ○ F5 |
| provenance bundle | ✗ | ○ | **◎** | ◎ | ✗ | ✗ | ◎ F6 |
| クラウド分散 (HPC 不要) | ✗ | ○ 有料 | ○ 要設定 | ○ 要設定 | ✗ | ✗ | ◎ Actions |
| 過去計算の自然言語検索 | ✗ | ✗ | △ | △ | ✗ | △ | ◎ RAG |
| 価格 | ¥30-50万/seat/年 | ¥100万+/seat/年 | $0 | $0 | $0 | $0 | $0 (OSS) |
| セットアップ難度 | 低 | 低 | 高 | 高 | 中 | なし | 低 |
| AI 関与の透明性 | n/a | n/a | n/a | n/a | n/a | n/a | ◎ source tag |

## 時間削減の試算 (per material)

| ステップ | 従来 | 本ツール | 削減 |
|---|---|---|---|
| (b) cutoff 候補検討 | 30 分〜2 時間 | 5 分 (RAG) | 約 40 分 |
| (c) 収束テスト setup | 1-2 時間 | 5 分 (CLI) | 約 1 時間 |
| (e) 収束カーブ判定 | 30 分〜1 時間 | 30 分 (人間判断) | 0 |
| (f) 本番 input 作成 | 30 分 | 5 分 | 25 分 |
| (h) 後処理 (NSCF, bands) | 1-2 時間 | 30 分 | 約 1 時間 |
| (i) 文献値比較 | 1-2 時間 | 5 分 | 約 1.5 時間 |
| (j) 論文 plot | 1-3 時間 | 15 分 | 約 1.5 時間 |
| (k) provenance | 0 分 (省略) | 0 分 (自動) | 品質向上のみ |
| **合計研究者時間** | 5-12 時間/材料 | 1.5-2 時間/材料 | **約 4-10 時間/材料 短縮** |

100 材料スクリーニングで **400-1000 時間 = 10-25 週間 短縮** 試算。

## 実装ロードマップ (parked、再開時に実行)

| Step | 内容 | 工数 | 依存 |
|---|---|---|---|
| 0 | 旧 Phase 2-C 構想を archive | 30 分 | — |
| 1 | F1: sweep CLI | 2-3 時間 | 既存 Actions workflow |
| 2 | F2: literature lookup | 2 時間 | MP API key |
| 3 | F3: テンプレ生成器 | 1 時間 | 既存 qe_inputs.py |
| 4 | F4: RAG 検索 CLI 拡張 | 1 時間 | 進行中 RAG 完成 (済) |
| 5 | F5: プロット生成 | 2 時間 | matplotlib 導入 |
| 6 | F6: dashboard 拡張 | 2-3 時間 | 既存 repro-viewer |
| 7 | F7: 論文抽出 + 比較 | 4-6 時間 | F4, PDF lib |
| 8 | docs/ ユーザーガイド | 2 時間 | 全 step 完了 |

合計 **17-22 時間 (= 1.5-2 週間規模)**

## ビジネスモデル候補 (草案、未確定)

| モデル | 内容 | 課題 |
|---|---|---|
| (a) OSS + サポート | 本体 GitHub OSS、商用サポート契約 | サポート需要は ラボ規模次第 |
| (b) Managed cloud | 自社運営の DFT-as-a-Service | 計算コストが収益を圧迫 |
| (c) Enterprise on-prem | ライセンス販売 (Winmostar 風) | OSS だと買う理由が薄い |
| (d) Plugin / Add-on for Winmostar | Winmostar 上で動く add-on を売る | 提携必要 |
| (e) Education + consulting | 大学院教育用 license + 研究室 onboarding consulting | 規模出にくい |

→ 現時点で確定なし、Track A 結果が出てから市場性を再評価。

## 再開条件

Track B を Phase 2 として再開する判定:
1. Track A の Phase 2 が完了し、研究結果に基づく明確な position が出ていること
2. ビジネス側に十分な時間 (人月) を割ける状態にあること
3. 競合状況に大きな変化が無いこと (例: Winmostar が同等 OSS 出すと価値半減)
