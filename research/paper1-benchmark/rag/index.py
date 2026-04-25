"""汎用 RAG indexer — bge-m3 (Ollama) + lancedb (Rust core)。

対象: experiments/, docs/, materials/, *.md, *.toml, *.json (trial), *.txt (trial)
インデックス先: .rag-db/ (lancedb)
埋め込み: Ollama bge-m3, 1024 dim, 多言語

使用例:
    .rag-env/bin/python -m rag.index             # 全件 index
    .rag-env/bin/python -m rag.index --rebuild   # 既存削除して全 index
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Iterable

import lancedb
import ollama
import pyarrow as pa
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / ".rag-db"
TABLE_NAME = "paper1"
EMBED_MODEL = "bge-m3"
EMBED_DIM = 1024

# どのファイルを index するか
INCLUDE_GLOBS = [
    "experiments/**/*.json",
    "experiments/**/*.txt",
    "experiments/**/*.md",
    "docs/**/*.md",
    "materials/*.toml",
    "*.md",
    "llm/*.py",
    "orchestrator/*.py",
    "apps/repro-viewer/app/**/*.tsx",
    "apps/repro-viewer/lib/**/*.ts",
    ".github/workflows/*.yml",
]
EXCLUDE_DIRS = {".rag-db", ".rag-env", "node_modules", "__pycache__", ".next", ".git", "tmp", "pseudo"}

# テキスト分割: ~600 文字 ≒ ~400 トークン (日本語) / ~150 トークン (英語)
CHUNK_CHARS = 600
CHUNK_OVERLAP = 100


def chunk_text(text: str, max_chars: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """素朴な文字数ベース分割。境界で半端に切らないよう改行を優先。"""
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []
    chunks: list[str] = []
    pos = 0
    while pos < len(text):
        end = min(pos + max_chars, len(text))
        # 改行優先で境界を探す (max_chars の 80% 以降の最後の改行)
        if end < len(text):
            cut_zone_start = pos + int(max_chars * 0.8)
            nl = text.rfind("\n", cut_zone_start, end)
            if nl > 0:
                end = nl
        chunks.append(text[pos:end].strip())
        if end >= len(text):
            break
        pos = max(end - overlap, pos + 1)
    return [c for c in chunks if c]


def iter_files(root: Path) -> Iterable[Path]:
    seen: set[Path] = set()
    for pattern in INCLUDE_GLOBS:
        for p in root.glob(pattern):
            if not p.is_file():
                continue
            if any(part in EXCLUDE_DIRS for part in p.parts):
                continue
            try:
                if p.stat().st_size > 1_000_000:  # 1 MB 超は対象外
                    continue
            except OSError:
                continue
            if p in seen:
                continue
            seen.add(p)
            yield p


def make_chunks_for(path: Path) -> Iterable[dict]:
    """ファイルから (chunk text, metadata) を生成。種別に応じて整形。"""
    rel = path.relative_to(ROOT)
    suffix = path.suffix
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return

    # JSON は整形して 1 chunk に
    if suffix == ".json":
        try:
            obj = json.loads(text)
        except Exception:
            obj = None
        if obj is not None:
            # trial JSON の場合: 重要フィールドだけに絞る
            if isinstance(obj, dict) and "response_text" in obj and "params" in obj:
                # LLM trial record
                pretty = json.dumps({
                    "trial_index": obj.get("trial_index"),
                    "model": obj.get("model"),
                    "params": obj.get("params"),
                    "params_valid": obj.get("params_valid"),
                    "response_text": obj.get("response_text", "")[:3000],
                }, ensure_ascii=False, indent=2)
                yield {"text": pretty, "path": str(rel), "kind": "trial"}
                return
            else:
                pretty = json.dumps(obj, ensure_ascii=False, indent=2)
                for ch in chunk_text(pretty):
                    yield {"text": ch, "path": str(rel), "kind": "json"}
                return

    # それ以外はテキスト分割
    kind = {".md": "doc", ".txt": "trial-text", ".toml": "config",
            ".py": "code", ".tsx": "code", ".ts": "code", ".yml": "ci"}.get(suffix, "text")
    for ch in chunk_text(text):
        yield {"text": ch, "path": str(rel), "kind": kind}


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Ollama API で batch embed。"""
    out: list[list[float]] = []
    # bge-m3 は 1 つずつ送るのが安定
    for t in texts:
        r = ollama.embed(model=EMBED_MODEL, input=t)
        emb = r.get("embeddings") or r.get("embedding")
        if isinstance(emb, list) and emb and isinstance(emb[0], list):
            out.append(emb[0])
        elif isinstance(emb, list):
            out.append(emb)
        else:
            raise RuntimeError(f"unexpected embed response: {r}")
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--rebuild", action="store_true", help="既存 DB を削除して再構築")
    args = p.parse_args()

    db = lancedb.connect(str(DB_PATH))

    # rebuild するなら drop
    if args.rebuild and TABLE_NAME in db.table_names():
        db.drop_table(TABLE_NAME)

    # ファイル列挙 + chunk 生成
    print("[1/3] 対象ファイル列挙 + chunk 化…")
    rows: list[dict] = []
    for path in iter_files(ROOT):
        for chunk_meta in make_chunks_for(path):
            text = chunk_meta["text"]
            cid = hashlib.sha256(f"{chunk_meta['path']}::{text[:64]}::{len(text)}".encode()).hexdigest()[:16]
            rows.append({
                "id": cid,
                "path": chunk_meta["path"],
                "kind": chunk_meta["kind"],
                "text": text,
            })
    print(f"  → chunk 総数: {len(rows)}")

    # 既存 table と差分を取る (chunk id ベース)
    existing_ids: set[str] = set()
    if TABLE_NAME in db.table_names():
        try:
            tbl = db.open_table(TABLE_NAME)
            existing_df = tbl.to_pandas()
            existing_ids = set(existing_df["id"].tolist())
        except Exception:
            pass

    new_rows = [r for r in rows if r["id"] not in existing_ids]
    print(f"  → 新規 chunk: {len(new_rows)} (既存 {len(existing_ids)} skip)")

    if not new_rows and TABLE_NAME in db.table_names():
        print("[完了] 差分無し、index は最新")
        return 0

    # embedding を生成
    print(f"[2/3] embedding 計算 (bge-m3 経由)…")
    t0 = time.time()
    embeddings: list[list[float]] = []
    BATCH = 16
    for i in tqdm(range(0, len(new_rows), BATCH)):
        batch = new_rows[i:i + BATCH]
        embs = embed_batch([r["text"] for r in batch])
        embeddings.extend(embs)
    print(f"  → {len(embeddings)} embedding 生成 ({time.time()-t0:.1f}s)")

    # PyArrow テーブル作成 → lancedb 投入
    print("[3/3] lancedb に投入…")
    arrow_table = pa.table({
        "id": [r["id"] for r in new_rows],
        "path": [r["path"] for r in new_rows],
        "kind": [r["kind"] for r in new_rows],
        "text": [r["text"] for r in new_rows],
        "vector": pa.array(embeddings, type=pa.list_(pa.float32(), EMBED_DIM)),
    })

    if TABLE_NAME in db.table_names():
        tbl = db.open_table(TABLE_NAME)
        tbl.add(arrow_table)
    else:
        tbl = db.create_table(TABLE_NAME, arrow_table)

    print(f"[完了] {tbl.count_rows()} chunks indexed → {DB_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
