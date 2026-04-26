"""汎用 RAG indexer — bge-m3 (Ollama batch input) + lancedb。

主な改良 (旧版から):
  - **server-side batch inference**: ollama.embed に array input を渡し、
    1 リクエストで N 件まとめて embed (~4× 速度)
  - **incremental flush**: BATCH 件ごとに lancedb へ部分投入 (kill 耐性)
  - **stdout flush**: tqdm + flush=True で進捗が即時見える
  - **既存 chunk skip**: chunk id (sha256) で de-dupe

対象: experiments/, docs/, materials/, *.md, *.toml, *.json (trial), *.txt
インデックス先: .rag-db/
埋め込み: Ollama bge-m3, 1024 dim, 多言語

使用例:
    .rag-env/bin/python -u -m rag.index
    .rag-env/bin/python -u -m rag.index --rebuild
    .rag-env/bin/python -u -m rag.index --batch 64 --limit 100
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Iterable

import httpx
import lancedb
import ollama
import pyarrow as pa
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / ".rag-db"
TABLE_NAME = "paper1"
EMBED_MODEL = "bge-m3"
EMBED_DIM = 1024

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

CHUNK_CHARS = 600
CHUNK_OVERLAP = 100


def chunk_text(text: str, max_chars: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []
    chunks: list[str] = []
    pos = 0
    while pos < len(text):
        end = min(pos + max_chars, len(text))
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
                if p.stat().st_size > 1_000_000:
                    continue
            except OSError:
                continue
            if p in seen:
                continue
            seen.add(p)
            yield p


def make_chunks_for(path: Path) -> Iterable[dict]:
    rel = path.relative_to(ROOT)
    suffix = path.suffix
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return

    if suffix == ".json":
        try:
            obj = json.loads(text)
        except Exception:
            obj = None
        if obj is not None:
            if isinstance(obj, dict) and "response_text" in obj and "params" in obj:
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

    kind = {".md": "doc", ".txt": "trial-text", ".toml": "config",
            ".py": "code", ".tsx": "code", ".ts": "code", ".yml": "ci"}.get(suffix, "text")
    for ch in chunk_text(text):
        yield {"text": ch, "path": str(rel), "kind": kind}


def embed_array(texts: list[str]) -> list[list[float]]:
    """Ollama の array 入力 (server-side batch inference)。逐次版。"""
    if not texts:
        return []
    r = ollama.embed(model=EMBED_MODEL, input=texts)
    embs = r.get("embeddings") or r.get("embedding")
    if isinstance(embs, list) and embs and isinstance(embs[0], list):
        return embs
    if isinstance(embs, list):
        return [embs]
    raise RuntimeError(f"unexpected embed response: {r}")


async def _embed_one_async(client: httpx.AsyncClient, texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    r = await client.post(
        "http://localhost:11434/api/embed",
        json={"model": EMBED_MODEL, "input": texts},
        timeout=600.0,
    )
    r.raise_for_status()
    data = r.json()
    embs = data.get("embeddings") or data.get("embedding")
    if isinstance(embs, list) and embs and isinstance(embs[0], list):
        return embs
    if isinstance(embs, list):
        return [embs]
    raise RuntimeError(f"unexpected embed response: {data}")


async def _embed_concurrent_async(batches: list[list[str]], concurrency: int) -> list[list[list[float]]]:
    """N 個の batch を concurrency 同時に投げる。"""
    sem = asyncio.Semaphore(concurrency)
    results: list[list[list[float]]] = [None] * len(batches)  # type: ignore

    async with httpx.AsyncClient() as client:
        async def _one(idx: int, texts: list[str]):
            async with sem:
                results[idx] = await _embed_one_async(client, texts)

        await asyncio.gather(*[_one(i, b) for i, b in enumerate(batches)])

    return results


def embed_concurrent(batches: list[list[str]], concurrency: int) -> list[list[list[float]]]:
    """asyncio + httpx で concurrency 並列に embed。"""
    return asyncio.run(_embed_concurrent_async(batches, concurrency))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--rebuild", action="store_true", help="既存 DB を削除")
    p.add_argument("--batch", type=int, default=32, help="1 リクエストの件数 (default 32)")
    p.add_argument("--concurrency", type=int, default=3, help="同時並行 batch リクエスト数 (default 3)")
    p.add_argument("--limit", type=int, default=0, help="先頭 N chunk のみ (テスト用、0 で全件)")
    args = p.parse_args()

    db = lancedb.connect(str(DB_PATH))

    if args.rebuild and TABLE_NAME in db.table_names():
        db.drop_table(TABLE_NAME)

    print("[1/3] ファイル列挙 + chunk 化…", flush=True)
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
    print(f"  → 候補 chunk 総数: {len(rows)}", flush=True)

    existing_ids: set[str] = set()
    if TABLE_NAME in db.table_names():
        try:
            tbl_existing = db.open_table(TABLE_NAME)
            existing_df = tbl_existing.to_pandas()
            existing_ids = set(existing_df["id"].tolist())
        except Exception:
            pass

    new_rows = [r for r in rows if r["id"] not in existing_ids]
    if args.limit > 0:
        new_rows = new_rows[: args.limit]
    print(f"  → 新規 chunk: {len(new_rows)} (既存 {len(existing_ids)} skip)", flush=True)

    if not new_rows and TABLE_NAME in db.table_names():
        print("[完了] 差分無し、index は最新", flush=True)
        return 0

    print(f"[2/3] embedding (batch={args.batch}, server-side batch)…", flush=True)
    t0 = time.time()
    total = len(new_rows)
    flushed = 0

    # 空テーブル先行作成 (race 回避 + 1 件目から add)
    if TABLE_NAME not in db.list_tables():
        empty_arrow = pa.table({
            "id":     pa.array([], type=pa.string()),
            "path":   pa.array([], type=pa.string()),
            "kind":   pa.array([], type=pa.string()),
            "text":   pa.array([], type=pa.string()),
            "vector": pa.array([], type=pa.list_(pa.float32(), EMBED_DIM)),
        })
        db.create_table(TABLE_NAME, empty_arrow)
    tbl = db.open_table(TABLE_NAME)

    pbar = tqdm(total=total, unit="chunk", file=sys.stdout, ncols=80, dynamic_ncols=False)
    for i in range(0, total, args.batch):
        batch_rows = new_rows[i:i + args.batch]
        try:
            embs = embed_array([r["text"] for r in batch_rows])
        except Exception as e:
            print(f"\n  [WARN] batch {i}-{i+len(batch_rows)} 失敗: {e}", file=sys.stderr, flush=True)
            pbar.update(len(batch_rows))
            continue

        if len(embs) != len(batch_rows):
            print(f"\n  [WARN] embed count mismatch", file=sys.stderr, flush=True)
            pbar.update(len(batch_rows))
            continue

        # 即時 flush で kill 耐性
        arrow_table = pa.table({
            "id":     [r["id"] for r in batch_rows],
            "path":   [r["path"] for r in batch_rows],
            "kind":   [r["kind"] for r in batch_rows],
            "text":   [r["text"] for r in batch_rows],
            "vector": pa.array(embs, type=pa.list_(pa.float32(), EMBED_DIM)),
        })
        tbl.add(arrow_table)
        flushed += len(batch_rows)
        pbar.update(len(batch_rows))
    pbar.close()

    elapsed = time.time() - t0
    rate = flushed / elapsed if elapsed > 0 else 0
    print(f"  → {flushed}/{total} chunks flushed ({elapsed:.1f}s, {rate:.2f} chunk/s)", flush=True)

    print("[3/3] 完了確認…", flush=True)
    if TABLE_NAME in db.table_names():
        tbl = db.open_table(TABLE_NAME)
        print(f"  → DB 内 chunk 総数: {tbl.count_rows()} → {DB_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
