"""各 experiments/*/trials から partial summary.json を出力。
実験の Python プロセスが次の 10 試行 milestone に到達する前でも、
Web UI に途中経過を見せられる。
"""
from __future__ import annotations
import hashlib, json, statistics, sys
from collections import Counter
from pathlib import Path

def _str_key(v):
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(str(x) for x in v) + "]"
    return str(v)

def refresh(exp_dir: Path) -> bool:
    trials_dir = exp_dir / "trials"
    results_dir = exp_dir / "results"
    prompts_dir = exp_dir / "prompts"
    rows = []
    for p in sorted(trials_dir.glob("*.json")):
        try:
            rows.append(json.loads(p.read_text()))
        except Exception:
            continue
    if not rows:
        return False

    prompt_file = next(iter(prompts_dir.glob("*.txt")), None)
    prompt_sha = (
        hashlib.sha256(prompt_file.read_bytes()).hexdigest()
        if prompt_file else ""
    )
    valid = [r for r in rows if r.get("params_valid")]
    distros = {}
    for k in ("ecutwfc","ecutrho","smearing","degauss","conv_thr","mixing_beta"):
        distros[k] = dict(Counter(_str_key(r["params"][k]) for r in valid).most_common())
    distros["kpoints"] = dict(Counter(_str_key(r["params"]["kpoints"]) for r in valid).most_common())
    rh = Counter(r["response_sha256"] for r in rows)
    ph = Counter(hashlib.sha256(json.dumps(r["params"], sort_keys=True).encode()).hexdigest() for r in valid)

    def st(f):
        vs = [r["params"][f] for r in valid if isinstance(r["params"].get(f), (int, float))]
        if not vs: return None
        return {"mean": statistics.mean(vs), "stdev": statistics.stdev(vs) if len(vs)>1 else 0.0,
                "min": min(vs), "max": max(vs), "n": len(vs)}

    walls = [r["wall_seconds"] for r in rows if isinstance(r.get("wall_seconds"), (int, float))]
    summary = {
        "schema": "paper3.repro.v1",
        "experiment": exp_dir.name,
        "status": "in_progress",
        "n_trials": len(rows),
        "n_valid": len(valid),
        "n_parse_failures": len(rows) - len(valid),
        "model": rows[0].get("model"),
        "temperature": rows[0].get("temperature"),
        "seed_base": rows[0].get("seed"),
        "prompt_sha256": prompt_sha,
        "wall_seconds_total": round(sum(walls), 1),
        "wall_seconds_per_trial_mean": round(statistics.mean(walls), 2) if walls else None,
        "unique_response_count": len(rh),
        "unique_param_set_count": len(ph),
        "fully_reproducible_response": len(rh) == 1,
        "fully_reproducible_params": len(ph) == 1,
        "param_distributions": distros,
        "response_hash_counts": dict(rh.most_common()),
        "param_set_hash_counts": dict(ph.most_common()),
        "stats": {f"{k}_Ry" if k != "mixing_beta" else k: st(k)
                  for k in ("ecutwfc","ecutrho","degauss","conv_thr","mixing_beta")},
    }
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))
    return True


def main() -> int:
    root = Path(__file__).resolve().parent
    updated = []
    for exp in sorted(root.iterdir()):
        if exp.is_dir() and (exp / "trials").is_dir():
            if refresh(exp):
                n = len(list((exp / "trials").glob("*.json")))
                updated.append((exp.name, n))
    for name, n in updated:
        print(f"  updated {name:<50} n={n}")
    print(f"{len(updated)} experiments refreshed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
