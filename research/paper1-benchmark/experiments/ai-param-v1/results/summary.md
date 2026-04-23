# ai-param-v1 — cross-material summary

Materials: **3**, all using LLM-chosen pw.x params.

| material | converged | SCF iter | ecutwfc / ecutrho Ry | k-points | conv_thr | mixing β | E_total Ry | Fermi eV | gap eV | wall s |
|----------|:---------:|:--------:|:-------------------:|:--------:|:--------:|:--------:|-----------:|---------:|-------:|-------:|
| CsPbI3 | ✓ | 9 | 60/480 | (6, 6, 6) | 1e-08 | 0.40 | -749.704 | 6.0069 | - | 1832.21 |
| GaAs | ✓ | 10 | 60/480 | (8, 8, 8) | 1e-10 | 0.50 | -144.021 | 7.4971 | - | 1881.82 |
| Si | ✓ | 6 | 30/240 | (8, 8, 8) | 1e-10 | 0.70 | -15.7646 | 6.5374 | - | 519.23 |

**LLM model**: `claude-opus-4-7[1m] (Claude Code CLI session, non-reproducible)` (same for all rows)

Every value above is reproducible from the per-material bundle (`{formula}.zip`) via `python3 -m orchestrator parse`.