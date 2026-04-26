"""Track A Phase 2 — Step 4 Main 実験ランナー (7 LLM × 10 材料 × N trials).

Phase 1 の repro-v1 / repro-v1-dft + Phase 2 の calibration を経て、
本ステップでは N=10 材料 × 7 (or 6) LLM すべてを横断的に回す。

設計:
  - 1 (LLM, material) cell につき N=10 trials を回す (default)
  - 出力構造:
        trials/{model_tag}/{material_slug}/{i:04d}.json
        results/{model_tag}/{material_slug}/summary.json
  - 既に取得済 cell (summary.json が存在) は skip → re-run で安全に追記可能

  - LLM 呼び出しは ``llm/registry.py`` の LLMSpec.provider に応じて
    ``llm/ollama.py`` (ollama) と ``llm/cloud.py`` (groq) を選択
    (anthropic は今回未対応、後で追加可)

使い方:
    source ~/.config/paper1/groq.env  # GROQ_API_KEY
    python3 experiments/step4-main/run_main.py            # 全 cell 実行
    python3 experiments/step4-main/run_main.py --models qwen25-7b --materials Si  # 1 cell だけ
    python3 experiments/step4-main/run_main.py --n 5      # N=5 で smoke
    python3 experiments/step4-main/run_main.py --skip-existing
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
import time
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from llm.registry import ALL_MODELS, LLMSpec
from llm.ollama import OllamaClient

EXP_DIR = Path(__file__).resolve().parent
PROMPT_TEMPLATE = (EXP_DIR / "prompts" / "template.txt").read_text()
MATERIALS_TOML = EXP_DIR / "materials" / "n10.toml"
TRIALS_DIR = EXP_DIR / "trials"
RESULTS_DIR = EXP_DIR / "results"


# ---------------------------------------------------------------------------
# Material loading & prompt rendering
# ---------------------------------------------------------------------------

def load_materials() -> list[dict[str, Any]]:
    with MATERIALS_TOML.open("rb") as f:
        return tomllib.load(f)["material"]


def render_prompt(material: dict[str, Any]) -> str:
    out = PROMPT_TEMPLATE
    out = out.replace("{{FORMULA}}", material["formula"])
    out = out.replace("{{STRUCTURE_DESCRIPTION}}", material["structure_description"])
    out = out.replace("{{LATTICE_DESCRIPTION}}", material["lattice_description"])
    out = out.replace("{{N_ATOMS}}", str(material["n_atoms"]))
    return out


# ---------------------------------------------------------------------------
# Response parsing (Phase 1 流用 + reasoning モデル <think> 対応)
# ---------------------------------------------------------------------------

def parse_response_json(text: str) -> dict[str, Any] | None:
    text_clean = re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL)
    if not text_clean.strip():
        text_clean = text
    try:
        return json.loads(text_clean)
    except Exception:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text_clean, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    m = re.search(r"\{.*\}", text_clean, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return None


def normalize_params(parsed: dict[str, Any] | None) -> dict[str, Any] | None:
    if not parsed:
        return None
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


# ---------------------------------------------------------------------------
# LLM client dispatch
# ---------------------------------------------------------------------------

def call_llm(spec: LLMSpec, prompt: str, seed: int) -> tuple[str, dict[str, Any], float]:
    """provider 別に LLM を呼び、(text, usage, wall_seconds) を返す."""
    if spec.provider == "ollama":
        npred = 4096 if spec.is_reasoning else 512
        c = OllamaClient(
            model_id=spec.model_id,
            temperature=0.0,
            seed=seed,
            num_predict=npred,
            timeout=900,
        )
        r = c.ask(prompt)
        return r.text, r.usage, r.wall_seconds

    if spec.provider == "groq":
        # Groq は llm/cloud.py の GroqClient を使う
        from llm.cloud import GroqClient
        max_tokens = 4096 if spec.is_reasoning else 512
        c = GroqClient(model_id=spec.model_id)
        r = c.ask(prompt, temperature=0.0, seed=seed, max_tokens=max_tokens)
        return r.text, r.usage, r.wall_seconds

    raise NotImplementedError(f"provider {spec.provider!r} not yet supported in run_main")


# ---------------------------------------------------------------------------
# 1 cell (LLM, material) 実行
# ---------------------------------------------------------------------------

def run_cell(spec: LLMSpec, material: dict[str, Any], n: int, seed_base: int,
             skip_existing: bool) -> None:
    cell_trials = TRIALS_DIR / spec.tag / material["slug"]
    cell_results = RESULTS_DIR / spec.tag / material["slug"]
    summary_path = cell_results / "summary.json"

    if skip_existing and summary_path.exists():
        print(f"  [skip] {spec.tag}/{material['slug']} (summary.json exists)")
        return

    cell_trials.mkdir(parents=True, exist_ok=True)
    cell_results.mkdir(parents=True, exist_ok=True)

    prompt = render_prompt(material)
    prompt_sha = hashlib.sha256(prompt.encode()).hexdigest()

    print(f"  [run ] {spec.tag}/{material['slug']}  n={n}")
    started = time.time()
    rows: list[dict[str, Any]] = []

    for i in range(n):
        seed = seed_base + i  # 各 trial で seed を変えて分布を測る
        try:
            text, usage, wall = call_llm(spec, prompt, seed=seed)
        except Exception as e:
            print(f"     [{i:03d}] FAIL: {e}", file=sys.stderr)
            continue

        parsed = parse_response_json(text)
        params = normalize_params(parsed)

        record = {
            "trial_index": i,
            "model_tag": spec.tag,
            "model_id": spec.model_id,
            "material_slug": material["slug"],
            "material_formula": material["formula"],
            "temperature": 0.0,
            "seed": seed,
            "prompt_sha256": prompt_sha,
            "response_text": text,
            "response_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "parsed_json": parsed,
            "params": params,
            "params_valid": params is not None,
            "wall_seconds": wall,
            "usage": usage,
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        rows.append(record)
        (cell_trials / f"{i:04d}.json").write_text(
            json.dumps(record, indent=2, sort_keys=True)
        )

        elapsed = time.time() - started
        eta = (elapsed / (i + 1)) * (n - i - 1) if i + 1 < n else 0
        print(f"     [{i+1:03d}/{n}] valid={params is not None} wall={wall:.1f}s eta={eta:.0f}s",
              flush=True)

    write_summary(rows, spec, material, prompt_sha, summary_path, started)


def write_summary(rows: list[dict[str, Any]], spec: LLMSpec, material: dict[str, Any],
                  prompt_sha: str, summary_path: Path, started: float) -> None:
    n = len(rows)
    valid = [r for r in rows if r["params_valid"]]

    # parameter 分布
    keys = ("ecutwfc", "ecutrho", "smearing", "degauss", "conv_thr", "mixing_beta")
    distros: dict[str, dict[str, int]] = {}
    for k in keys:
        c = Counter(_str_key(r["params"][k]) for r in valid)
        distros[k] = dict(c.most_common())
    distros["kpoints"] = dict(
        Counter(_str_key(r["params"]["kpoints"]) for r in valid).most_common()
    )

    response_hashes = Counter(r["response_sha256"] for r in rows)
    param_hashes = Counter(
        hashlib.sha256(json.dumps(r["params"], sort_keys=True).encode()).hexdigest()
        for r in valid
    )

    # mode params (最頻 param-set の 1 個)
    mode_params: dict[str, Any] | None = None
    if valid:
        from collections import Counter as _C
        param_keys = [
            (json.dumps(r["params"], sort_keys=True), r["params"])
            for r in valid
        ]
        kc = _C(k for k, _ in param_keys)
        most_common_key, _ = kc.most_common(1)[0]
        mode_params = next(p for k, p in param_keys if k == most_common_key)

    summary = {
        "schema": "paper3.step4-main.v1",
        "experiment": "step4-main",
        "model_tag": spec.tag,
        "model_id": spec.model_id,
        "model_family": spec.family,
        "model_size_B": spec.parameter_count_B,
        "is_reasoning": spec.is_reasoning,
        "material_slug": material["slug"],
        "material_formula": material["formula"],
        "material_tier": material["tier"],
        "n_trials": n,
        "n_valid": len(valid),
        "n_parse_failures": n - len(valid),
        "prompt_sha256": prompt_sha,
        "wall_seconds_total": round(time.time() - started, 1),
        "wall_seconds_per_trial_mean": round(
            statistics.mean([r["wall_seconds"] for r in rows if r["wall_seconds"]]), 2
        ) if rows else None,
        "unique_response_count": len(response_hashes),
        "unique_param_set_count": len(param_hashes),
        "fully_reproducible_response": len(response_hashes) == 1,
        "fully_reproducible_params": len(param_hashes) == 1,
        "param_distributions": distros,
        "mode_params": mode_params,
        "param_set_hash_counts": dict(param_hashes.most_common()),
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True))


def _str_key(v: Any) -> str:
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(str(x) for x in v) + "]"
    return str(v)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=10, help="trials per cell (default 10)")
    p.add_argument("--models", help="comma-separated model tags filter (default: all)")
    p.add_argument("--materials", help="comma-separated material slugs filter")
    p.add_argument("--seed-base", type=int, default=42)
    p.add_argument("--skip-existing", action="store_true",
                   help="skip cells whose summary.json already exists")
    p.add_argument("--exclude-models", default="phi4-14b",
                   help="comma-separated tags to exclude (default: phi4-14b due to RAM)")
    args = p.parse_args()

    materials = load_materials()
    if args.materials:
        wanted = set(args.materials.split(","))
        materials = [m for m in materials if m["slug"] in wanted]

    models = ALL_MODELS
    if args.models:
        wanted = set(args.models.split(","))
        models = [m for m in models if m.tag in wanted]
    if args.exclude_models:
        ex = set(args.exclude_models.split(","))
        models = [m for m in models if m.tag not in ex]

    print(f"== Step 4 main runner ==")
    print(f"  models    : {[m.tag for m in models]}")
    print(f"  materials : {[m['slug'] for m in materials]}")
    print(f"  n_trials  : {args.n}")
    print(f"  total     : {len(models) * len(materials)} cells, "
          f"{len(models) * len(materials) * args.n} LLM calls")
    print()

    started = time.time()
    for spec in models:
        for material in materials:
            run_cell(spec, material, n=args.n, seed_base=args.seed_base,
                     skip_existing=args.skip_existing)

    print(f"\nDone. total wall: {time.time() - started:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
