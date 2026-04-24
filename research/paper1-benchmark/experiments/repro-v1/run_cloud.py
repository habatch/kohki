"""再現性 (reproducibility) 実験ランナー — クラウド LLM 版。

run.py の Ollama 呼び出しを Gemini / Groq に差し替えただけで、入出力
形式・サマリ生成は完全に同形式 (summary.json / summary.md / trials/)。
これにより repro-viewer から差替え無しで閲覧可能。

使い方:
    GEMINI_API_KEY=... python3 run_cloud.py \
        --provider gemini --model gemini-2.0-flash-001 --n 100

    GROQ_API_KEY=... python3 run_cloud.py \
        --provider groq --model llama-3.3-70b-versatile --n 100

    # サブディレクトリで結果を分離 (1 モデル 1 実験)
    python3 run_cloud.py --provider groq --model llama-3.3-70b-versatile \
        --n 100 --subdir gemini-flash-2.0-100x

出力先 (デフォルト):
    experiments/repro-v1-{provider}-{model_safe}/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

# 親 dir 経由で llm.cloud を import
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from llm.cloud import make_client, CloudResponse  # noqa: E402

EXP_DIR = Path(__file__).resolve().parent
PROMPT_FILE = EXP_DIR / "prompts" / "v1.txt"


def parse_response_json(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try: return json.loads(m.group(1))
        except Exception: pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try: return json.loads(m.group(0))
        except Exception: pass
    return None


def normalize_params(parsed: dict[str, Any] | None) -> dict[str, Any] | None:
    if not parsed: return None
    try:
        return {
            "ecutwfc": float(parsed["ecutwfc_Ry"]),
            "ecutrho": float(parsed["ecutrho_Ry"]),
            "kpoints": [int(x) for x in parsed["kpoints"]],
            "smearing": str(parsed["smearing"]),
            "degauss": float(parsed["degauss_Ry"]),
            "conv_thr": float(parsed["conv_thr_Ry"]),
            "mixing_beta": float(parsed["mixing_beta"]),
        }
    except (KeyError, ValueError, TypeError):
        return None


def _str_key(v: Any) -> str:
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(str(x) for x in v) + "]"
    return str(v)


def write_summary(rows, model: str, temperature: float, seed: int | None,
                  prompt_sha: str, started: float, results_dir: Path,
                  partial: bool = False) -> None:
    n = len(rows)
    valid = [r for r in rows if r["params_valid"]]

    distros: dict[str, dict[str, int]] = {}
    for k in ("ecutwfc","ecutrho","smearing","degauss","conv_thr","mixing_beta"):
        distros[k] = dict(Counter(_str_key(r["params"][k]) for r in valid).most_common())
    distros["kpoints"] = dict(Counter(_str_key(r["params"]["kpoints"]) for r in valid).most_common())

    response_hashes = Counter(r["response_sha256"] for r in rows)
    param_hashes = Counter(
        hashlib.sha256(json.dumps(r["params"], sort_keys=True).encode()).hexdigest()
        for r in valid
    )

    def stats(field: str) -> dict[str, float] | None:
        vals = [r["params"][field] for r in valid
                if isinstance(r["params"][field], (int, float))]
        if not vals: return None
        return {"mean": statistics.mean(vals),
                "stdev": statistics.stdev(vals) if len(vals) > 1 else 0.0,
                "min": min(vals), "max": max(vals), "n": len(vals)}

    summary = {
        "schema": "paper3.repro.v1",
        "experiment": results_dir.parent.name,
        "status": "in_progress" if partial else "completed",
        "n_trials": n,
        "n_valid": len(valid),
        "n_parse_failures": n - len(valid),
        "model": model,
        "temperature": temperature,
        "seed_base": seed,
        "prompt_sha256": prompt_sha,
        "wall_seconds_total": round(time.time() - started, 1),
        "wall_seconds_per_trial_mean": round(
            statistics.mean([r["wall_seconds"] for r in rows]), 2) if rows else None,
        "unique_response_count": len(response_hashes),
        "unique_param_set_count": len(param_hashes),
        "fully_reproducible_response": len(response_hashes) == 1,
        "fully_reproducible_params": len(param_hashes) == 1,
        "param_distributions": distros,
        "response_hash_counts": dict(response_hashes.most_common()),
        "param_set_hash_counts": dict(param_hashes.most_common()),
        "stats": {
            f"{k}_Ry" if k != "mixing_beta" else k: stats(k)
            for k in ("ecutwfc","ecutrho","degauss","conv_thr","mixing_beta")
        },
    }
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))


def run(provider: str, model: str, n: int, temperature: float, seed: int | None,
        out_root: Path, max_tokens: int = 512) -> None:
    trials_dir = out_root / "trials"
    results_dir = out_root / "results"
    prompts_dir = out_root / "prompts"
    for d in (trials_dir, results_dir, prompts_dir): d.mkdir(parents=True, exist_ok=True)

    prompt = PROMPT_FILE.read_text()
    prompt_sha = hashlib.sha256(prompt.encode()).hexdigest()
    (prompts_dir / "v1.txt").write_text(prompt)   # snapshot for portability

    client = make_client(provider, model)
    print(f"始動: provider={provider} model={model} n={n} "
          f"temperature={temperature} seed={seed} "
          f"prompt_sha={prompt_sha[:12]}…")

    started = time.time()
    rows: list[dict[str, Any]] = []
    for i in range(n):
        try:
            resp: CloudResponse = client.ask(prompt, temperature=temperature, seed=seed, max_tokens=max_tokens)
        except Exception as e:
            print(f"  [{i:03d}] FAIL: {e}", file=sys.stderr)
            continue

        parsed = parse_response_json(resp.text)
        params = normalize_params(parsed)
        record = {
            "trial_index": i,
            "model": resp.model_id,
            "provider": provider,
            "temperature": temperature,
            "seed": seed,
            "prompt_sha256": prompt_sha,
            "response_text": resp.text,
            "response_sha256": hashlib.sha256(resp.text.encode()).hexdigest(),
            "parsed_json": parsed,
            "params": params,
            "params_valid": params is not None,
            "wall_seconds": resp.wall_seconds,
            "ollama_eval_count": resp.usage.get("completionTokenCount") or
                                 resp.usage.get("completion_tokens") or
                                 resp.usage.get("totalTokenCount") or 0,
            "ollama_eval_duration_s": resp.wall_seconds,
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        rows.append(record)
        (trials_dir / f"{i:04d}.json").write_text(json.dumps(record, indent=2, sort_keys=True))
        (trials_dir / f"{i:04d}.txt").write_text(resp.text)

        elapsed = time.time() - started
        remain = (elapsed / (i + 1)) * (n - i - 1)
        print(f"  [{i+1:03d}/{n}] valid={params is not None} "
              f"wall={resp.wall_seconds:.1f}s "
              f"elapsed={elapsed:.0f}s remaining≈{remain:.0f}s")

        if (i + 1) % 10 == 0 or (i + 1) == n:
            write_summary(rows, model, temperature, seed, prompt_sha, started,
                          results_dir, partial=(i + 1) < n)

    write_summary(rows, model, temperature, seed, prompt_sha, started,
                  results_dir, partial=False)
    print()
    print(f"完了 — {len(rows)}/{n} 試行")
    print(f"  → {results_dir / 'summary.json'}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--provider", required=True, choices=["gemini", "groq"])
    p.add_argument("--model", required=True,
                   help="例: gemini-2.0-flash-001, llama-3.3-70b-versatile")
    p.add_argument("--n", type=int, default=100)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--subdir", default=None,
                   help="experiments/<subdir>/ に出力。省略時は experiments/repro-v1-<provider>-<model_safe>")
    p.add_argument("--max-tokens", type=int, default=512,
                   help="応答の最大トークン数。reasoning モデルは 4096 程度必要")
    args = p.parse_args()

    safe = re.sub(r"[^a-zA-Z0-9_.-]", "-", args.model)
    sub = args.subdir or f"repro-v1-{args.provider}-{safe}"
    out_root = EXP_DIR.parent / sub
    run(args.provider, args.model, args.n, args.temperature, args.seed, out_root,
        max_tokens=args.max_tokens)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
