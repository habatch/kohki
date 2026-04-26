"""再現性 (reproducibility) 実験ランナー — v1.

同じプロンプトを Ollama 上の qwen2.5:7b に N 回投げ、毎回の生応答 +
パース後パラメータ + メタ情報を保存する。

使い方:
    python3 run.py --n 100              # 本番 100 試行
    python3 run.py --n 5                # パイロット
    python3 run.py --n 100 --temperature 0.0 --seed 42

出力:
    trials/{i:04d}.json     全試行の生データ (1 ファイル / 試行)
    trials/{i:04d}.txt      生応答のテキストのみ (人間用)
    results/summary.jsonl   1 試行 1 行のサマリ
    results/summary.json    集計統計 (mean / std / unique counts / etc.)
    results/summary.md      人間用の表
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

EXP_DIR = Path(__file__).resolve().parent
PROMPT_FILE = EXP_DIR / "prompts" / "v1.txt"
TRIALS_DIR = EXP_DIR / "trials"
RESULTS_DIR = EXP_DIR / "results"

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "deepseek-r1:7b"


def call_ollama(model: str, prompt: str, temperature: float, seed: int | None) -> dict[str, Any]:
    body = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            # deepseek-r1 は reasoning モデルで <think>...</think> ブロックが
            # 長いため 256 だと JSON 部分が出る前に切られる。Phase 1 の
            # qwen3-32b で同事故 (max_tokens=512 truncation) を経験済み。
            "num_predict": 4096,
        },
    }
    if seed is not None:
        body["options"]["seed"] = int(seed)
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL,
        data=data,
        headers={"content-type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=600) as r:
        payload = json.load(r)
    payload["_wall_seconds"] = time.time() - t0
    return payload


def parse_response_json(text: str) -> dict[str, Any] | None:
    """生応答から JSON ブロックだけ抜き出してパース。
    余計な ``` フェンスや前後文字が混じっても拾えるようにする。

    deepseek-r1 は <think>...</think> ブロックを先頭に出すので、
    それを剥がしてから JSON を探す。
    """
    # 0. <think>...</think> を除去 (deepseek-r1 reasoning モデル対応)
    text_clean = re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL)
    if not text_clean.strip():
        text_clean = text   # think しか出力しなかった場合は原文に戻す
    # 1. そのまま JSON として読めるか
    try:
        return json.loads(text_clean)
    except Exception:
        pass
    # 2. ```json ... ``` フェンス内を抜く
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text_clean, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # 3. 最初の { から対応する } まで貪欲抽出
    m = re.search(r"\{.*\}", text_clean, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return None


def normalize_params(parsed: dict[str, Any] | None) -> dict[str, Any] | None:
    """LLM 応答からアプリ側の正規化キーへ変換。失敗したら None。"""
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


def run(n: int, model: str, temperature: float, seed_base: int | None) -> None:
    TRIALS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    prompt = PROMPT_FILE.read_text()
    prompt_sha = hashlib.sha256(prompt.encode()).hexdigest()

    summary_path = RESULTS_DIR / "summary.jsonl"
    summary_path.unlink(missing_ok=True)

    started = time.time()
    print(f"始動: model={model} n={n} temperature={temperature} "
          f"seed_base={seed_base} prompt_sha={prompt_sha[:12]}…")

    rows: list[dict[str, Any]] = []
    for i in range(n):
        # Each trial uses the same prompt. seed advances if provided so the
        # caller can tell repeated calls with seed=fixed apart from different
        # seeds.  For the strict reproducibility test set seed=fixed.
        seed = seed_base
        try:
            res = call_ollama(model, prompt, temperature, seed)
        except Exception as e:
            print(f"  [{i:03d}] FAIL: {e}", file=sys.stderr)
            continue

        raw_response = res.get("response", "")
        parsed = parse_response_json(raw_response)
        params = normalize_params(parsed)

        record = {
            "trial_index": i,
            "model": model,
            "temperature": temperature,
            "seed": seed,
            "prompt_sha256": prompt_sha,
            "response_text": raw_response,
            "response_sha256": hashlib.sha256(raw_response.encode()).hexdigest(),
            "parsed_json": parsed,
            "params": params,
            "params_valid": params is not None,
            "wall_seconds": res.get("_wall_seconds"),
            "ollama_eval_count": res.get("eval_count"),
            "ollama_eval_duration_s": (res.get("eval_duration") or 0) / 1e9,
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        rows.append(record)

        # Persist this trial individually for human inspection
        (TRIALS_DIR / f"{i:04d}.json").write_text(json.dumps(record, indent=2, sort_keys=True))
        (TRIALS_DIR / f"{i:04d}.txt").write_text(raw_response)
        with summary_path.open("a") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")

        elapsed = time.time() - started
        remain = (elapsed / (i + 1)) * (n - i - 1)
        print(f"  [{i+1:03d}/{n}] valid={params is not None} "
              f"wall={record['wall_seconds']:.1f}s tokens={record['ollama_eval_count']} "
              f"elapsed={elapsed:.0f}s remaining≈{remain:.0f}s")

        # 10 試行毎に partial summary を書いて Web UI 側からも進捗が見える
        if (i + 1) % 10 == 0 or (i + 1) == n:
            write_summary(rows, model, temperature, seed_base, prompt_sha, started, partial=(i + 1) < n)

    # 最終サマリ（partial フラグ無しで上書き）
    write_summary(rows, model, temperature, seed_base, prompt_sha, started, partial=False)


def write_summary(
    rows: list[dict[str, Any]],
    model: str,
    temperature: float,
    seed_base: int | None,
    prompt_sha: str,
    started: float,
    partial: bool = False,
) -> None:
    """trials を解析して summary.json と summary.md を出力。
    partial=True の場合は途中経過扱いで status を 'in_progress' にする。"""
    n = len(rows)
    valid = [r for r in rows if r["params_valid"]]

    # 値ごとの分布 (JSON 互換のため key は str に) ----------------------
    keys = ("ecutwfc", "ecutrho", "smearing", "degauss", "conv_thr", "mixing_beta")
    distros: dict[str, dict[str, int]] = {}
    for k in keys:
        c = Counter(_str_key(r["params"][k]) for r in valid)
        distros[k] = dict(c.most_common())
    distros["kpoints"] = dict(
        Counter(_str_key(r["params"]["kpoints"]) for r in valid).most_common()
    )

    # 完全一致 (parsed_json レベル)
    response_hashes = Counter(r["response_sha256"] for r in rows)
    param_hashes = Counter(
        hashlib.sha256(json.dumps(r["params"], sort_keys=True).encode()).hexdigest()
        for r in valid
    )

    def stats(field: str) -> dict[str, float] | None:
        vals = [r["params"][field] for r in valid if isinstance(r["params"][field], (int, float))]
        if not vals:
            return None
        return {
            "mean": statistics.mean(vals),
            "stdev": statistics.stdev(vals) if len(vals) > 1 else 0.0,
            "min": min(vals),
            "max": max(vals),
            "n": len(vals),
        }

    total_wall = time.time() - started
    summary = {
        "schema": "paper3.repro.v1",
        "experiment": "repro-v1",
        "status": "in_progress" if partial else "completed",
        "n_trials": n,
        "n_valid": len(valid),
        "n_parse_failures": n - len(valid),
        "model": model,
        "temperature": temperature,
        "seed_base": seed_base,
        "prompt_sha256": prompt_sha,
        "wall_seconds_total": round(total_wall, 1),
        "wall_seconds_per_trial_mean": round(
            statistics.mean([r["wall_seconds"] for r in rows if r["wall_seconds"]]), 2
        ) if rows else None,
        "unique_response_count": len(response_hashes),
        "unique_param_set_count": len(param_hashes),
        "fully_reproducible_response": len(response_hashes) == 1,
        "fully_reproducible_params": len(param_hashes) == 1,
        "param_distributions": distros,
        "response_hash_counts": dict(response_hashes.most_common()),
        "param_set_hash_counts": dict(param_hashes.most_common()),
        "stats": {
            "ecutwfc_Ry":   stats("ecutwfc"),
            "ecutrho_Ry":   stats("ecutrho"),
            "degauss_Ry":   stats("degauss"),
            "conv_thr_Ry":  stats("conv_thr"),
            "mixing_beta":  stats("mixing_beta"),
        },
    }
    (RESULTS_DIR / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))
    write_markdown(summary)
    print()
    print(f"完了 — {n}/{n} 試行、有効パース {len(valid)}、"
          f"全応答ユニーク数 {len(response_hashes)}、ユニーク param セット {len(param_hashes)}")
    print(f"  → {RESULTS_DIR / 'summary.md'}")


def write_markdown(summary: dict[str, Any]) -> None:
    """human-readable summary.md を出力。"""
    lines = [
        f"# 再現性実験 repro-v1 — 結果サマリ",
        "",
        f"- 試行回数: **{summary['n_trials']}** (うち有効パース {summary['n_valid']})",
        f"- モデル: `{summary['model']}` / temperature={summary['temperature']} / seed_base={summary['seed_base']}",
        f"- 総 wall: {summary['wall_seconds_total']} 秒 ({summary['wall_seconds_per_trial_mean']} 秒/試行)",
        f"- プロンプト SHA-256: `{summary['prompt_sha256'][:16]}…`",
        "",
        "## 完全再現性",
        "",
        f"- ユニークな生応答 (response_sha256) の数: **{summary['unique_response_count']}**",
        f"  → {'**完全再現**: 100% 同じテキスト' if summary['fully_reproducible_response'] else 'テキストレベルでは揺れている'}",
        f"- ユニークな param セットの数: **{summary['unique_param_set_count']}**",
        f"  → {'**完全再現**: 100% 同じパラメータ' if summary['fully_reproducible_params'] else 'パラメータレベルで揺れている'}",
        "",
        "## パラメータ別分布",
        "",
    ]
    distros = summary["param_distributions"]
    for k in ("ecutwfc", "ecutrho", "kpoints", "smearing", "degauss", "conv_thr", "mixing_beta"):
        d = distros.get(k, {})
        lines.append(f"### {k}")
        lines.append("")
        lines.append("| 値 | 出現回数 | 割合 |")
        lines.append("|----|--------:|----:|")
        total = sum(d.values()) or 1
        for v, c in d.items():
            lines.append(f"| `{v}` | {c} | {c/total*100:.1f}% |")
        lines.append("")
    if summary["stats"].get("ecutwfc_Ry"):
        lines.append("## 数値統計 (有効試行のみ)")
        lines.append("")
        lines.append("| パラメータ | 平均 | 標準偏差 | 最小 | 最大 |")
        lines.append("|----------|----:|------:|-----:|-----:|")
        for label, key in [
            ("ecutwfc Ry",  "ecutwfc_Ry"),
            ("ecutrho Ry",  "ecutrho_Ry"),
            ("degauss Ry",  "degauss_Ry"),
            ("conv_thr Ry", "conv_thr_Ry"),
            ("mixing_beta", "mixing_beta"),
        ]:
            s = summary["stats"][key]
            if s:
                lines.append(f"| {label} | {s['mean']:.6g} | {s['stdev']:.4g} | {s['min']:.6g} | {s['max']:.6g} |")
    (RESULTS_DIR / "summary.md").write_text("\n".join(lines) + "\n")


def _str_key(v: Any) -> str:
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(str(x) for x in v) + "]"
    return str(v)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=100)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--seed", type=int, default=42, help="Ollama に渡す seed (固定)")
    args = p.parse_args()
    run(args.n, args.model, args.temperature, args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
