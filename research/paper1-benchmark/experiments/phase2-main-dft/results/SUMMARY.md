# Phase 2 Main DFT — accuracy summary (auto-generated)

## 7 LLM × 10 materials + 4 ensemble methods

### 個別 LLM cells

| material | model_tag | overall | conv (mRy/atom) | smearing | E_total Ry | wall s |
|---|---|---|---|---|---|---|
| AlN | gptoss-120b | pass | 0.54 | pass | -317.0434 | 525 |
| AlN | llama31-8b | fail | 378.83 | pass | -315.5259 | 393 |
| AlN | llama33-70b | fail | 2.63 | fail | -317.0307 | 1101 |
| AlN | qwen25-7b | fail | 376.15 | fail | -315.5366 | 620 |
| AlN | qwen3-32b | fail | 2.64 | pass | -317.0307 | 1540 |
| BiVO4 | gptoss-120b | pass | 0.01 | pass | -812.4052 | 3519 |
| BiVO4 | llama31-8b | fail | 12.88 | pass | -812.2508 | 7260 |
| BiVO4 | llama33-70b | fail | 189.04 | pass | -810.1369 | 3014 |
| BiVO4 | qwen25-7b | fail | 590.84 | fail | -805.3152 | 12000 |
| BiVO4 | qwen3-32b | fail | 12.90 | fail | -812.2506 | 12660 |
| CsPbI3 | gptoss-120b | pass | 0.64 | pass | -749.7051 | 3160 |
| CsPbI3 | llama31-8b | fail | 79.75 | pass | -749.3032 | 781 |
| CsPbI3 | llama33-70b | fail | 4.11 | fail | -749.6814 | 707 |
| CsPbI3 | qwen25-7b | fail | 70.87 | fail | -749.3476 | 771 |
| CsPbI3 | qwen3-32b | fail | 0.58 | fail | -749.7048 | 2123 |
| GaAs | gptoss-120b | fail | 6.37 | fail | -144.0267 | 1608 |
| GaAs | llama31-8b | fail | 3325.70 | pass | -137.3625 | 315 |
| GaAs | llama33-70b | fail | 654.54 | fail | -142.7049 | 1269 |
| GaAs | qwen25-7b | fail | 3311.54 | fail | -137.3909 | 270 |
| GaAs | qwen3-32b | fail | 1589.40 | fail | -140.8352 | 1347 |
| Ge | gptoss-120b | fail | 9.15 | pass | -283.1496 | 1945 |
| Ge | llama31-8b | fail | 212.36 | pass | -282.7066 | 437 |
| Ge | llama33-70b | fail | 8.43 | pass | -283.1481 | 1708 |
| Ge | qwen25-7b | fail | 210.74 | pass | -282.7098 | 395 |
| Ge | qwen3-32b | fail | 8.43 | pass | -283.1481 | 2092 |
| MoS2 | gptoss-120b | fail | 0.01 | fail | -178.2432 | 3151 |
| MoS2 | llama31-8b | fail | 1.90 | fail | -178.2375 | 458 |
| MoS2 | llama33-70b | pass | 0.88 | pass | -178.2405 | 2555 |
| MoS2 | qwen25-7b | fail | 1.86 | fail | -178.2376 | 405 |
| MoS2 | qwen3-32b | pass | 0.01 | pass | -178.2432 | 2665 |
| NiO | deepseekr1-7b | unphysical | n/a | unknown | n/a | n/a |
| NiO | gptoss-120b | pass | n/a | pass | -340.1790 | 1452 |
| NiO | llama31-8b | fail | n/a | fail | -340.1586 | 1945 |
| NiO | llama33-70b | fail | n/a | fail | -340.1638 | 1677 |
| NiO | qwen25-7b | fail | n/a | fail | -336.9269 | 296 |
| NiO | qwen3-32b | fail | n/a | fail | -340.1588 | 1637 |
| Si | gptoss-120b | fail | 6.73 | pass | -15.7656 | 594 |
| Si | llama31-8b | pass | 0.62 | pass | -15.7509 | 146 |
| Si | llama33-70b | fail | 6.68 | fail | -15.7655 | 613 |
| Si | qwen25-7b | pass | 0.62 | pass | -15.7509 | 132 |
| Si | qwen3-32b | fail | 6.21 | pass | -15.7646 | 1024 |
| ZnO | gptoss-120b | fail | 0.03 | fail | -864.6905 | 1161 |
| ZnO | llama31-8b | fail | 3700.45 | pass | -849.8885 | 652 |
| ZnO | llama33-70b | fail | 11.12 | pass | -864.6459 | 347 |
| ZnO | qwen25-7b | fail | 3697.51 | fail | -849.9003 | 1957 |
| ZnO | qwen3-32b | fail | 10.69 | pass | -864.6476 | 1970 |

### Ensemble cells

| material | ensemble | overall | conv (mRy/atom) | smearing | E_total Ry | wall s |
|---|---|---|---|---|---|---|
| AlN | ensemble-A | fail | 2.66 | pass | -317.0306 | 858 |
| AlN | ensemble-B | fail | 1.87 | pass | -317.0338 | 991 |
| AlN | ensemble-C | fail | 2.67 | pass | -317.0306 | 643 |
| AlN | ensemble-E | pass | 0.54 | pass | -317.0434 | 675 |
| BiVO4 | ensemble-A | fail | 12.88 | pass | -812.2508 | 6000 |
| BiVO4 | ensemble-B | fail | 16.35 | pass | -812.2091 | 4260 |
| BiVO4 | ensemble-C | fail | 12.90 | pass | -812.2505 | 3321 |
| BiVO4 | ensemble-E | fail | 12.90 | fail | -812.2506 | 12600 |
| CsPbI3 | ensemble-A | fail | 4.11 | fail | -749.6814 | 704 |
| CsPbI3 | ensemble-B | fail | 0.54 | fail | -749.7046 | 1619 |
| CsPbI3 | ensemble-C | pass | 0.24 | pass | -749.7031 | 1602 |
| CsPbI3 | ensemble-E | fail | 0.58 | fail | -749.7048 | 2116 |
| GaAs | ensemble-A | fail | 1589.34 | fail | -140.8353 | 1351 |
| GaAs | ensemble-B | fail | 65.71 | fail | -143.8825 | 1000 |
| GaAs | ensemble-C | fail | 3325.70 | pass | -137.3625 | 319 |
| GaAs | ensemble-E | fail | 6.37 | fail | -144.0267 | 1607 |
| Ge | ensemble-A | fail | 8.32 | pass | -283.1479 | 2093 |
| Ge | ensemble-B | fail | 8.69 | pass | -283.1487 | 1060 |
| Ge | ensemble-C | fail | 8.32 | pass | -283.1479 | 2079 |
| Ge | ensemble-E | fail | 9.15 | pass | -283.1496 | 1952 |
| MoS2 | ensemble-A | pass | 0.88 | pass | -178.2405 | 3139 |
| MoS2 | ensemble-B | pass | 0.17 | pass | -178.2427 | 2276 |
| MoS2 | ensemble-E | pass | 0.01 | pass | -178.2432 | 2923 |
| NiO | ensemble-A | fail | n/a | fail | -340.1703 | 1420 |
| NiO | ensemble-B | fail | n/a | fail | -340.1841 | 1685 |
| NiO | ensemble-C | pass | n/a | pass | -340.1790 | 1749 |
| NiO | ensemble-E | fail | n/a | fail | -340.1588 | 1655 |
| Si | ensemble-A | fail | 6.21 | pass | -15.7646 | 585 |
| Si | ensemble-B | fail | 6.35 | pass | -15.7649 | 451 |
| Si | ensemble-C | fail | 5.46 | pass | -15.7631 | 291 |
| Si | ensemble-E | fail | 6.73 | pass | -15.7656 | 612 |
| ZnO | ensemble-A | fail | 11.04 | pass | -864.6462 | 480 |
| ZnO | ensemble-B | fail | 7.80 | pass | -864.6592 | 1100 |
| ZnO | ensemble-C | fail | 11.04 | pass | -864.6462 | 587 |
| ZnO | ensemble-E | fail | 0.03 | fail | -864.6905 | 1164 |

## Per-model aggregate (個別 LLM のみ)

| model_tag | n_cells | pass | fail | **unphysical** | conv_pass | smearing_pass | wall mean s |
|---|---|---|---|---|---|---|---|
| deepseekr1-7b | 1 | 0/1 (0%) | 0/1 | **1/1** | 0% | 0% | 0 |
| gptoss-120b | 9 | 4/9 (44%) | 5/9 | **0/9** | 56% | 67% | 1902 |
| llama31-8b | 9 | 1/9 (11%) | 8/9 | **0/9** | 11% | 78% | 1376 |
| llama33-70b | 9 | 1/9 (11%) | 8/9 | **0/9** | 11% | 44% | 1443 |
| qwen25-7b | 9 | 1/9 (11%) | 8/9 | **0/9** | 11% | 22% | 1872 |
| qwen3-32b | 9 | 1/9 (11%) | 8/9 | **0/9** | 22% | 56% | 3006 |

## ⚠ Unphysical proposals — LLM が物理的に成立しない params を提案

| cell | reason |
|---|---|
| NiO-deepseekr1-7b | no artifact uploaded — DFT likely failed before bundle (probable pre-SCF rejection) |
