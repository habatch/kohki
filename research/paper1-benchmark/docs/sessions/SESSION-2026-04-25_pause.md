# セッション中断ポイント — 2026-04-25 18:40 JST

電源節約のため作業中断。次セッション開始時の即時復元用ノート。

## 中断時の状態

| 項目 | 状態 |
|---|---|
| Phase 1 再現性実験 (5 モデル × 100 試行) | ✅ 完了、git commit 済 |
| RAG コード本体 (`rag/index.py`, `rag/query.py`) | ✅ 完成、ローカルにあり (まだ未 commit) |
| RAG 環境 (`.rag-env`, lancedb + pyarrow + tantivy + ollama) | ✅ uv venv 構築済 |
| Ollama 上の embed モデル (`bge-m3`, 1024 dim) | ✅ pull 済 |
| RAG indexing | ❌ **約 25 分実行後 kill** (in-memory 未投入のため全て破棄) |
| `.rag-db/` | 空 (4 KB の空ディレクトリのみ) |
| 全プロセス | 停止済 (Next.js x2 / Ollama / rag.index) |

## 次セッション開始時の手順

```bash
# 1. Ollama サーバを起動 (~/.bashrc が OLLAMA_MODELS を設定済)
nohup ~/bin/ollama serve > /tmp/ollama-server.log 2>&1 &

# 2. (任意) repro-viewer を起動
cd /home/kohki/research/paper1-benchmark/apps/repro-viewer && npm run dev > /tmp/repro-viewer.log 2>&1 &

# 3. RAG index を構築 — 速度別に 4 案
#    案 A: 高精度 bge-m3 全件 (~30-50 min)
cd /home/kohki/research/paper1-benchmark
.rag-env/bin/python -m rag.index --rebuild

#    案 D (推奨): 並列 embed で 3-4 倍速 (要 index.py 改修、別途実装予定)

#    案 B: nomic-embed-text に切替 (~5-8 min) — 別途実装要

#    案 C: 対象を docs / summary に絞る (~3-5 min) — INCLUDE_GLOBS 編集
```

## RAG indexing 速度問題の詳細 (次回対策)

- bge-m3 on CPU: 1 chunk 当たり **3.0-3.7 秒** (予想より重い)
- 推定 chunk 総数: **700-1000** (trial JSON ~400 + trial TXT ~400 + docs ~200)
- 純逐次実行で 35-50 分

### 推奨改善案 (次セッション着手項目)

1. **並列 embed**: `rag/index.py` の `embed_batch` を asyncio + httpx で 3-4 並列化 (10 行追加)
2. **進捗保存**: 100 chunk 毎に lancedb へ partial flush (kill 耐性 = 中断 → 再開時に既存 chunk skip)
3. **embed model 切替オプション**: `--model nomic-embed-text` でフォールバック可能に

## 中断時の git 未 commit ファイル

```
rag/__init__.py
rag/index.py
rag/query.py
docs/sessions/SESSION-2026-04-25_pause.md  (この file)
```

`.rag-env/` と `.rag-db/` は .gitignore に入れる必要あり (次セッションで処理)。

## Phase 1 後半の続き (RAG 構築後の予定)

| 順序 | 項目 | 予想時間 |
|---|---|---|
| 1 | RAG 構築完了 (案 D 並列化版) | 10-12 分 |
| 2 | RAG 動作確認クエリ (10 件) | 5 分 |
| 3 | (要 user 承認) DFT 検証実験 — 5 モデル提案 params で CsPbI3 SCF 並列実行 | 60-80 分壁時計 |
| 4 | DFT 結果と LLM 提案の比較レポート | 10 分 |
| 5 | (任意) v2 プロンプト 8 判断項目への user 回答収集 → repro-v2 実験 | TBD |

## バッテリ復帰後の最初のアクション

「セッション中断のノートを読む」と一言伝えていただければ、上記ノートを Read して即座に状態復元します。

git push しておきます。
