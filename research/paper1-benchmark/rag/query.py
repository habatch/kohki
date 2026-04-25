"""RAG 検索 CLI — 自然言語クエリで上位 K 件を取得。

使用例:
    .rag-env/bin/python -m rag.query "ecutwfc 80 を提案した試行"
    .rag-env/bin/python -m rag.query --k 5 --json "Senegal MOU"
    .rag-env/bin/python -m rag.query --kind trial "qwen3 reasoning"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import lancedb
import ollama

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / ".rag-db"
TABLE_NAME = "paper1"
EMBED_MODEL = "bge-m3"


def embed(text: str) -> list[float]:
    r = ollama.embed(model=EMBED_MODEL, input=text)
    e = r.get("embeddings") or r.get("embedding")
    if isinstance(e, list) and e and isinstance(e[0], list):
        return e[0]
    if isinstance(e, list):
        return e
    raise RuntimeError(f"unexpected embed response: {r}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("query", nargs="+")
    p.add_argument("--k", type=int, default=10, help="上位 K 件 (default: 10)")
    p.add_argument("--kind", help="特定 kind に絞る (trial/doc/code/etc.)")
    p.add_argument("--path-prefix", help="特定 path prefix に絞る")
    p.add_argument("--json", action="store_true", help="JSON で出力")
    p.add_argument("--full", action="store_true", help="text を切り詰めず全文表示")
    args = p.parse_args()

    q = " ".join(args.query)
    if not DB_PATH.exists():
        print(f"index 未構築。先に: .rag-env/bin/python -m rag.index", file=sys.stderr)
        return 2

    db = lancedb.connect(str(DB_PATH))
    if TABLE_NAME not in db.table_names():
        print(f"table {TABLE_NAME!r} 無し。先に index 必要", file=sys.stderr)
        return 2

    tbl = db.open_table(TABLE_NAME)
    qvec = embed(q)

    search = tbl.search(qvec).limit(args.k * 3 if (args.kind or args.path_prefix) else args.k)
    df = search.to_pandas()

    # ポストフィルタ
    if args.kind:
        df = df[df["kind"] == args.kind]
    if args.path_prefix:
        df = df[df["path"].str.startswith(args.path_prefix)]
    df = df.head(args.k)

    if args.json:
        out = []
        for _, row in df.iterrows():
            out.append({
                "score": float(row["_distance"]),
                "path": row["path"],
                "kind": row["kind"],
                "text": row["text"] if args.full else row["text"][:500],
            })
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    print(f"\n=== クエリ: {q!r}  (top {len(df)} / dim={len(qvec)}) ===\n")
    for i, (_, row) in enumerate(df.iterrows(), 1):
        d = row["_distance"]
        text = row["text"] if args.full else row["text"][:300].replace("\n", " ")
        print(f"--- #{i:02d}  similarity={1-d:.3f}  [{row['kind']}]  {row['path']}")
        print(f"    {text}{'…' if not args.full and len(row['text']) > 300 else ''}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
