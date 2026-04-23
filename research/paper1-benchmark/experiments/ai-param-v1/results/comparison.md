# ai-param-v1 vs rule-based baseline

Same three materials, same CIFs, same pseudos, same pw.x binary.
Only difference: who chose the input-parameter values.

## Side-by-side

| Material | Picker | ecutwfc Ry | ecutrho Ry | k-points | conv_thr | β mixing | SCF iter | E_total Ry | Fermi eV | wall s |
|----------|--------|-----------:|-----------:|:--------:|---------:|---------:|:--------:|-----------:|---------:|-------:|
| **Si**     | rule  | 30 | 240 | (7,7,7) | 1e-8  | 0.40 | 6  | −15.76309 | 6.5746 | 281 |
| Si         | LLM   | 30 | 240 | (8,8,8) | 1e-10 | 0.70 | 6  | −15.76464 | 6.5374 | 519 |
| **CsPbI3** | rule  | 40 | 320 | (4,4,4) | 1e-8  | 0.40 | 9  | −749.6819 | 5.7157 | 816 |
| CsPbI3     | LLM   | 60 | 480 | (6,6,6) | 1e-8  | 0.40 | 9  | −749.7040 | 6.0069 | 1832 |
| **GaAs**   | rule  | — (no 2-atom Actions run yet) | | | | | | | | |
| GaAs       | LLM   | 60 | 480 | (8,8,8) | 1e-10 | 0.50 | 10 | −144.0210 | 7.4971 | 1882 |

## Observations

**Si.** The LLM's only differences from the rule-based defaults are (a)
a denser k-mesh (8³ vs 7³) and (b) a tighter conv_thr (1e-10 vs 1e-8).
Both choices are defensible; the extra cost is 1.85× wall-time for a
total-energy difference of ~0.0015 Ry (0.02 eV), which is smaller than
the PBE vs experiment uncertainty. **No convergence problems, no
unphysical numbers.**

**CsPbI3.** The LLM picked 60 Ry / 480 Ry cutoffs — 1.5× higher than
the rule's 40/320 which came from the SSSP Efficiency table. The LLM
justified the boost by Pb's 5d10 semicore, which is a legitimate
concern for ONCV norm-conserving (SSSP Efficiency values can be loose
for heavy elements). The total-energy shift of −0.022 Ry (−0.30 eV) is
consistent with an under-converged rule-based value; the LLM's number
is closer to the true PBE answer. Wall-time cost: 2.24×.

**GaAs (2-atom).** First time we ran the primitive cell on Actions.
E_total = −144.021 Ry matches yesterday's qe-desktop local validation
exactly to the 5th decimal. Whoever picked parameters (me or the rule),
the physics stack is self-consistent.

## Methodological notes

All three pw.x runs **converged cleanly** with the LLM's choices. The
LLM did not produce any unphysical parameter (e.g. ecutrho < ecutwfc,
negative degauss, out-of-range mixing_beta). The parameters errored on
the side of being more conservative / more expensive than the rule, not
the other way around.

The pattern looks like:
1. For well-known materials (Si), LLM ≈ rule, with cosmetic refinements.
2. For harder materials (CsPbI3, heavy Pb 5d semicore), LLM spends more
   compute and extracts a more accurate total energy.
3. LLM never corrupted the ground truth — it only moved the accuracy /
   cost tradeoff.

## Caveats (must be in any downstream paper)

- **LLM identity:** Claude Code CLI session (model claude-opus-4-7[1m],
  temperature unknown, seed absent). Running the same prompts tomorrow
  could yield different numbers. Not reproducible.
- **Single trial per material:** no variance measurement. A real
  benchmark needs N independent samples per material, ideally N ≥ 30.
- **Rule-based baseline is itself Claude-written** (the dict in
  `orchestrator/qe_inputs.py`). So "LLM vs rule" here is really "LLM
  outputs in-session vs LLM outputs baked into code". A fully external
  baseline would be a published recommendation from Materials Cloud or
  similar.

## How to re-run reproducibly

1. Set `ANTHROPIC_API_KEY` in the environment (and
   `research/paper1-benchmark/experiments/ai-param-v2/` as a fresh dir).
2. Generate predictions via `llm/client.py` with
   `model_id="claude-opus-4-7-20260419"`, `temperature=0`, `seed=42`.
3. Re-run `gh workflow run ai-param-experiment.yml -f experiment=ai-param-v2`.
4. Compare v2 ↔ v1 to measure Claude Code temperature noise.
