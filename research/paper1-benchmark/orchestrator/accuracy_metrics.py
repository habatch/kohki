"""Track A Phase 2 — LLM 提案 DFT パラメータの正確性指標.

Phase 1 で得た 5 LLM × CsPbI3 の repro-v1-dft 結果から、Phase 2 では
N 材料 × M モデル の cell 全件に対して以下 5 指標を算出する。

指標一覧 (Step 1 deliverable):

1. **DFT 収束度** (`evaluate_convergence`)
   E_total が「converged cluster」内にあるか。ここでは reference
   convergence test で得た無限 cutoff 極限値からの偏差 (mRy/atom) が
   閾値 (default 1 mRy/atom) 以下なら converged 判定。

2. **物理的妥当性 — smearing** (`evaluate_smearing_for_insulator`)
   絶縁体 / 半導体に metallic smearing (`mp` / `mv`) や過剰な
   `degauss` (≥ 0.02 Ry) が採用されていないか。
   採用していたら不適切と判定 (gap が smearing で潰れる)。

3. **物理的妥当性 — band gap** (`evaluate_band_gap`)
   DFT 出力の gap が PBE 文献値の ±30% 以内か。
   PBE は実験値より 30-50% 過小評価されるが、PBE 同士なら ±30%
   以内に収まるはず (cutoff/k 不足だと外れる)。

4. **応答再現性** (`evaluate_reproducibility`)
   repro-v1 と同形式: 同 prompt N 試行で得られた unique
   param-set 数 / 全試行数。1 ならば完全再現。

5. **コスト効率** (`evaluate_cost_efficiency`)
   converged になるまでの wall_seconds。比較用の指標で
   絶対閾値ではなく対象材料内の相対値で意味を持つ。

集約:

- `score_cell()` — 1 cell (= 1 LLM × 1 material) の全指標を一括評価
- `aggregate_by_model()` / `aggregate_by_material()` — 集計ヘルパ

依存: stdlib のみ。`qe_parser.Observables` を入力に取る。
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, asdict, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from .qe_parser import Observables


# ---------------------------------------------------------------------------
# 結果型 — 各指標は同じ shape の MetricResult を返す
# ---------------------------------------------------------------------------

class MetricStatus(str, Enum):
    """4 値判定。

    PASS:       評価基準を満たす
    FAIL:       評価基準を満たさない (SCF が走った上で物理的に不適切)
    UNPHYSICAL: LLM 提案 params が物理的に成立せず、pw.x が SCF 開始前に reject
                (ecutwfc 過小 / pseudo 不在 / 等。FAIL とは別カテゴリで集計推奨)
    UNKNOWN:    入力欠損や reference 未登録で判定不能
    """
    PASS = "pass"
    FAIL = "fail"
    UNPHYSICAL = "unphysical"
    UNKNOWN = "unknown"


@dataclass
class MetricResult:
    name: str
    status: MetricStatus
    value: float | None          # 観測された数値 (eV, Ry, sec, count, etc.)
    threshold: float | None      # 判定に使った閾値
    reason: str                  # 人間用 1 行説明
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


# ---------------------------------------------------------------------------
# 材料側 reference (Step 2 で各材料 fixture に登録)
# ---------------------------------------------------------------------------

@dataclass
class MaterialReference:
    """1 材料についての真値 / 参照値.

    ``e_total_converged_Ry_per_atom`` は別途実施する reference
    convergence test (ecut sweep) で得る無限 cutoff 極限。
    ``band_gap_PBE_eV`` は PBE 文献値 (Materials Project / NOMAD)。
    """
    formula: str
    n_atoms: int
    is_insulator: bool                    # True なら smearing 不要
    e_total_converged_Ry_per_atom: float | None = None
    band_gap_PBE_eV: float | None = None
    band_gap_source: str = ""             # 引用元 (mp-id, doi など)


# ---------------------------------------------------------------------------
# 1. DFT 収束度
# ---------------------------------------------------------------------------

# Phase 1 経験則: CsPbI3 で「未収束」と「収束」cluster 間の差は
# 約 0.4 Ry / 5 原子 = 80 mRy/atom (cf. SUMMARY.md)。
#
# 三段閾値 — 論文では複数併記する:
#   ultra-strict (1 meV/atom = 0.0735 mRy/atom):
#                         TritonDFT (Wang et al. 2026) の strict 基準と互換。
#                         非常に厳しい、ほぼ wave function 収束限界。
#   strict       (1 mRy/atom):
#                         QE/DFT ベンチマーク慣習の「真の収束」値。
#                         無限 cutoff 極限と区別できない精度。
#   loose        (5 mRy/atom):
#                         形成エネルギー比較 / スクリーニング目的なら
#                         実用上十分とされる値。
# strict / loose の両方で評価して PASS/WARN/FAIL の 3 段判定にする。
# ultra_strict は extra に pass フラグを立て、TritonDFT 互換 metric として
# 集計時に使用。
ULTRA_STRICT_CONVERGENCE_THRESHOLD_MRY_PER_ATOM = 0.0735  # = 1 meV/atom
STRICT_CONVERGENCE_THRESHOLD_MRY_PER_ATOM = 1.0
LOOSE_CONVERGENCE_THRESHOLD_MRY_PER_ATOM = 5.0
DEFAULT_CONVERGENCE_THRESHOLD_MRY_PER_ATOM = STRICT_CONVERGENCE_THRESHOLD_MRY_PER_ATOM

# 1 meV ↔ mRy 変換係数 (Rydberg 定数 13.605693 eV/Ry より)
MEV_PER_MRY = 13.605693


def evaluate_convergence(
    obs: Observables,
    ref: MaterialReference,
    threshold_mRy_per_atom: float = DEFAULT_CONVERGENCE_THRESHOLD_MRY_PER_ATOM,
    loose_threshold_mRy_per_atom: float = LOOSE_CONVERGENCE_THRESHOLD_MRY_PER_ATOM,
) -> MetricResult:
    """E_total が無限 cutoff 極限から ``threshold`` 以内か判定.

    三段判定:
      - pre_scf_error あり                            → UNPHYSICAL
      - deviation ≤ strict (default 1 mRy/atom)       → PASS
      - strict < deviation ≤ loose (default 5)         → PASS だが extra に warn=True
      - deviation > loose                              → FAIL

    UNPHYSICAL は「物理的に成立しない LLM 提案」で、論文では
    convergence/non-convergence とは独立カテゴリで集計推奨。
    """
    if obs.pre_scf_error:
        return MetricResult(
            name="convergence",
            status=MetricStatus.UNPHYSICAL,
            value=None,
            threshold=threshold_mRy_per_atom,
            reason=f"pw.x が SCF 開始前に reject ({obs.pre_scf_error}) - LLM 提案 params が物理的に不適切",
            extra={"pre_scf_error": obs.pre_scf_error},
        )
    if not obs.converged:
        return MetricResult(
            name="convergence",
            status=MetricStatus.FAIL,
            value=None,
            threshold=threshold_mRy_per_atom,
            reason="SCF が converged フラグなしで終了",
        )
    if obs.total_energy_Ry is None or obs.n_atoms is None:
        return MetricResult(
            name="convergence",
            status=MetricStatus.UNKNOWN,
            value=None,
            threshold=threshold_mRy_per_atom,
            reason="total_energy_Ry または n_atoms がパース不能",
        )
    if ref.e_total_converged_Ry_per_atom is None:
        return MetricResult(
            name="convergence",
            status=MetricStatus.UNKNOWN,
            value=None,
            threshold=threshold_mRy_per_atom,
            reason=f"{ref.formula}: reference convergence E が未登録",
        )

    e_per_atom = obs.total_energy_Ry / obs.n_atoms
    deviation_mRy = abs(e_per_atom - ref.e_total_converged_Ry_per_atom) * 1000.0

    strict_pass = deviation_mRy <= threshold_mRy_per_atom
    loose_pass = deviation_mRy <= loose_threshold_mRy_per_atom

    if strict_pass:
        status = MetricStatus.PASS
        reason = (
            f"|E_total/atom - ref| = {deviation_mRy:.2f} mRy/atom "
            f"≤ strict {threshold_mRy_per_atom} mRy/atom"
        )
    elif loose_pass:
        # 形成エネルギー比較なら実用 OK だが厳密収束は未達。
        # 論文では WARN として独立カテゴリにすべき。ここでは FAIL を返す
        # (status は strict 基準で判定) が、extra に loose_pass=True を立てる。
        status = MetricStatus.FAIL
        reason = (
            f"|E_total/atom - ref| = {deviation_mRy:.2f} mRy/atom "
            f"(strict {threshold_mRy_per_atom} 超過、loose {loose_threshold_mRy_per_atom} 内 — "
            f"実用基準では許容範囲)"
        )
    else:
        status = MetricStatus.FAIL
        reason = (
            f"|E_total/atom - ref| = {deviation_mRy:.2f} mRy/atom "
            f"> loose {loose_threshold_mRy_per_atom} mRy/atom (実用基準でも未収束)"
        )

    ultra_strict_pass = deviation_mRy <= ULTRA_STRICT_CONVERGENCE_THRESHOLD_MRY_PER_ATOM
    return MetricResult(
        name="convergence",
        status=status,
        value=deviation_mRy,
        threshold=threshold_mRy_per_atom,
        reason=reason,
        extra={
            "e_per_atom_Ry": e_per_atom,
            "e_ref_per_atom_Ry": ref.e_total_converged_Ry_per_atom,
            "ultra_strict_threshold_mRy_per_atom": ULTRA_STRICT_CONVERGENCE_THRESHOLD_MRY_PER_ATOM,
            "strict_threshold_mRy_per_atom": threshold_mRy_per_atom,
            "loose_threshold_mRy_per_atom": loose_threshold_mRy_per_atom,
            "ultra_strict_pass": ultra_strict_pass,    # TritonDFT 互換 metric (1 meV/atom)
            "strict_pass": strict_pass,
            "loose_pass": loose_pass,
            "deviation_meV_per_atom": deviation_mRy * MEV_PER_MRY,
        },
    )


# ---------------------------------------------------------------------------
# 2. 物理的妥当性 — smearing
# ---------------------------------------------------------------------------

# 絶縁体に対して許容される smearing kind。`gaussian` は本来不要だが
# 慣習的に許容される (degauss が十分小さければ)。
INSULATOR_ALLOWED_SMEARINGS = {"gaussian", "fixed", "none"}
# `mp` (Methfessel-Paxton), `mv` (Marzari-Vanderbilt), `fd` (fermi-dirac)
# は本来は金属用。絶縁体に使うと band gap を smearing で潰す。
INSULATOR_FORBIDDEN_SMEARINGS = {"mp", "methfessel-paxton", "mv", "marzari-vanderbilt",
                                  "fd", "fermi-dirac"}
# degauss が大きすぎると gaussian でも gap を潰す。経験則で 0.02 Ry
# (~ 0.27 eV) を上限に置く。
INSULATOR_MAX_DEGAUSS_RY = 0.02
# metallic smearing でも degauss が極端に小さい (≤ 0.01 Ry) 場合は
# gap 潰し効果が無視できる場合がある (Phase 1 の llama-3.3-70b 例)。
# このときは status=FAIL のまま extra に soft_warn フラグを立てる。
SMEARING_SOFT_DEGAUSS_RY = 0.01


def evaluate_smearing_for_insulator(
    smearing: str | None,
    degauss_Ry: float | None,
    ref: MaterialReference,
) -> MetricResult:
    """絶縁体 / 半導体に metallic smearing が採用されていないか判定.

    金属に対しては常に PASS を返す (smearing 必須なので)。

    metallic smearing が採用されていても degauss が極端に小さい
    (≤ 0.01 Ry) 場合は extra["soft_warn"]=True を立てる
    (Phase 1 llama-3.3-70b の fermi-dirac+degauss=0.01 のような微妙ケース)。
    """
    if not ref.is_insulator:
        return MetricResult(
            name="smearing_validity",
            status=MetricStatus.PASS,
            value=None,
            threshold=None,
            reason=f"{ref.formula} は金属扱い (smearing 任意)",
        )
    if smearing is None:
        return MetricResult(
            name="smearing_validity",
            status=MetricStatus.UNKNOWN,
            value=None,
            threshold=None,
            reason="LLM 提案に smearing kind が無い",
        )

    kind = smearing.lower().strip()
    if kind in INSULATOR_FORBIDDEN_SMEARINGS:
        soft = (degauss_Ry is not None and degauss_Ry <= SMEARING_SOFT_DEGAUSS_RY)
        reason = (
            f"絶縁体 {ref.formula} に metallic smearing `{kind}` が採用された"
        )
        if soft:
            reason += (
                f" (ただし degauss={degauss_Ry} Ry ≤ {SMEARING_SOFT_DEGAUSS_RY} Ry "
                "で gap 潰し効果は実用上小さい — soft_warn)"
            )
        return MetricResult(
            name="smearing_validity",
            status=MetricStatus.FAIL,
            value=None,
            threshold=None,
            reason=reason,
            extra={
                "smearing": kind,
                "degauss_Ry": degauss_Ry,
                "soft_warn": soft,
            },
        )

    # 許容 kind (gaussian など) でも degauss が過大なら FAIL
    if degauss_Ry is not None and degauss_Ry > INSULATOR_MAX_DEGAUSS_RY:
        return MetricResult(
            name="smearing_validity",
            status=MetricStatus.FAIL,
            value=degauss_Ry,
            threshold=INSULATOR_MAX_DEGAUSS_RY,
            reason=(
                f"絶縁体 {ref.formula} で degauss={degauss_Ry} Ry > "
                f"{INSULATOR_MAX_DEGAUSS_RY} Ry (gap が smearing で潰れる)"
            ),
            extra={"smearing": kind, "soft_warn": False},
        )

    return MetricResult(
        name="smearing_validity",
        status=MetricStatus.PASS,
        value=degauss_Ry,
        threshold=INSULATOR_MAX_DEGAUSS_RY,
        reason=f"絶縁体に対し許容範囲: smearing={kind}, degauss={degauss_Ry}",
        extra={"smearing": kind, "soft_warn": False},
    )


# ---------------------------------------------------------------------------
# 3. 物理的妥当性 — band gap
# ---------------------------------------------------------------------------

DEFAULT_GAP_TOLERANCE = 0.30  # ±30% (PBE 同士なら通常満たす)


def evaluate_band_gap(
    obs: Observables,
    ref: MaterialReference,
    tolerance: float = DEFAULT_GAP_TOLERANCE,
) -> MetricResult:
    """DFT 出力の band gap と PBE 文献値の相対誤差を判定.

    SCF のみだと QE は HOMO/LUMO を出力しない場合がある (NSCF 必要)。
    その場合は UNKNOWN を返す。
    """
    if ref.band_gap_PBE_eV is None:
        return MetricResult(
            name="band_gap_validity",
            status=MetricStatus.UNKNOWN,
            value=obs.band_gap_eV,
            threshold=tolerance,
            reason=f"{ref.formula}: PBE 文献 gap が未登録",
        )
    if obs.band_gap_eV is None:
        return MetricResult(
            name="band_gap_validity",
            status=MetricStatus.UNKNOWN,
            value=None,
            threshold=tolerance,
            reason="DFT 出力に gap 情報なし (SCF のみだと NSCF 必要)",
        )

    ref_gap = ref.band_gap_PBE_eV
    if ref_gap == 0:
        # 金属判定済みなのに insulator=True が立っている異常系
        return MetricResult(
            name="band_gap_validity",
            status=MetricStatus.UNKNOWN,
            value=obs.band_gap_eV,
            threshold=tolerance,
            reason=f"{ref.formula}: 文献 gap=0 で相対誤差計算不可",
        )

    rel_err = abs(obs.band_gap_eV - ref_gap) / ref_gap
    status = MetricStatus.PASS if rel_err <= tolerance else MetricStatus.FAIL
    return MetricResult(
        name="band_gap_validity",
        status=status,
        value=rel_err,
        threshold=tolerance,
        reason=(
            f"DFT gap={obs.band_gap_eV:.3f} eV vs PBE ref={ref_gap:.3f} eV → "
            f"{rel_err*100:.1f}% ({'≤' if status == MetricStatus.PASS else '>'} "
            f"{tolerance*100:.0f}%)"
        ),
        extra={
            "dft_gap_eV": obs.band_gap_eV,
            "ref_gap_eV": ref_gap,
            "ref_source": ref.band_gap_source,
        },
    )


# ---------------------------------------------------------------------------
# 4. 応答再現性 (repro-v1 と同形式)
# ---------------------------------------------------------------------------

@dataclass
class ReproStats:
    """再現性 cell の生データ (param_set hash の Counter 等)."""
    n_trials: int
    n_unique_param_sets: int
    fully_reproducible: bool
    most_common_fraction: float          # 最頻 param-set の割合


def evaluate_reproducibility(
    param_set_hashes: list[str] | dict[str, int],
) -> MetricResult:
    """同 prompt N 試行から得た param-set hash 列を unique 数で評価.

    ``param_set_hashes`` は list[str] (各試行の hash) でも dict[str, int]
    (hash → count) でも受ける。

    判定基準:
    - unique=1 なら PASS (完全再現)
    - それ以外は FAIL (重大: 再現性なしは研究で許容できない)
    """
    if isinstance(param_set_hashes, dict):
        counts = dict(param_set_hashes)
        n_trials = sum(counts.values())
    else:
        from collections import Counter
        counts = dict(Counter(param_set_hashes))
        n_trials = len(param_set_hashes)

    if n_trials == 0:
        return MetricResult(
            name="reproducibility",
            status=MetricStatus.UNKNOWN,
            value=None,
            threshold=1.0,
            reason="試行 0 件",
        )

    n_unique = len(counts)
    most_common = max(counts.values())
    most_common_frac = most_common / n_trials
    status = MetricStatus.PASS if n_unique == 1 else MetricStatus.FAIL

    return MetricResult(
        name="reproducibility",
        status=status,
        value=float(n_unique),
        threshold=1.0,
        reason=(
            f"{n_trials} 試行で unique param-set = {n_unique} 種"
            f" (最頻 {most_common_frac*100:.1f}%)"
        ),
        extra={
            "n_trials": n_trials,
            "n_unique_param_sets": n_unique,
            "most_common_fraction": most_common_frac,
        },
    )


# ---------------------------------------------------------------------------
# 5'. 物理的成立性 (LLM 提案 params で pw.x が起動できたか) — 独立指標
# ---------------------------------------------------------------------------

def evaluate_physical_feasibility(obs: Observables) -> MetricResult:
    """LLM 提案 params が pw.x で物理的に成立するかを単独評価.

    convergence とは独立に「そもそも計算が始められたか」を判定。
    SCF 不収束 (converged=False で SCF 反復が走った) と
    SCF 起動不可 (pre_scf_error あり) を区別する。

    返り値:
      PASS:        pw.x が SCF iteration を実行できた (収束/未収束問わず)
      UNPHYSICAL:  pre_scf_error あり (LLM 提案 params が物理破綻)
      UNKNOWN:     output.out が無い・パース不能
    """
    if obs.pre_scf_error:
        return MetricResult(
            name="physical_feasibility",
            status=MetricStatus.UNPHYSICAL,
            value=None,
            threshold=None,
            reason=f"pw.x が SCF 開始前に reject ({obs.pre_scf_error})",
            extra={"pre_scf_error": obs.pre_scf_error},
        )
    if obs.n_scf_iter is None and obs.total_energy_Ry is None:
        return MetricResult(
            name="physical_feasibility",
            status=MetricStatus.UNKNOWN,
            value=None,
            threshold=None,
            reason="output に SCF iteration 痕跡なし、原因未特定",
        )
    return MetricResult(
        name="physical_feasibility",
        status=MetricStatus.PASS,
        value=None,
        threshold=None,
        reason=f"pw.x SCF iteration 実行確認 (iter={obs.n_scf_iter})",
    )


# ---------------------------------------------------------------------------
# 5. コスト効率 (wall-time)
# ---------------------------------------------------------------------------

def evaluate_cost_efficiency(
    obs: Observables,
    max_wall_seconds: float | None = None,
) -> MetricResult:
    """wall-time を返す。閾値が与えられた場合のみ PASS/FAIL を出す.

    絶対閾値は材料サイズに強く依存するので、通常は値だけ返して
    `aggregate_by_material()` で材料内の最速モデルを基準に正規化する。
    """
    if obs.wall_seconds is None:
        return MetricResult(
            name="cost_efficiency",
            status=MetricStatus.UNKNOWN,
            value=None,
            threshold=max_wall_seconds,
            reason="wall_seconds がパース不能",
        )

    if max_wall_seconds is None:
        return MetricResult(
            name="cost_efficiency",
            status=MetricStatus.PASS,    # 閾値なしなら値だけ返して PASS
            value=obs.wall_seconds,
            threshold=None,
            reason=f"wall = {obs.wall_seconds:.0f} s (閾値なし)",
        )

    status = MetricStatus.PASS if obs.wall_seconds <= max_wall_seconds else MetricStatus.FAIL
    return MetricResult(
        name="cost_efficiency",
        status=status,
        value=obs.wall_seconds,
        threshold=max_wall_seconds,
        reason=f"wall = {obs.wall_seconds:.0f} s (閾値 {max_wall_seconds:.0f} s)",
    )


# ---------------------------------------------------------------------------
# 集約 — 1 cell = 1 (LLM, material) の全指標スコア
# ---------------------------------------------------------------------------

@dataclass
class CellScore:
    """1 (LLM, material) cell に対する全指標."""
    model: str
    formula: str
    physical_feasibility: MetricResult
    convergence: MetricResult
    smearing_validity: MetricResult
    band_gap_validity: MetricResult
    reproducibility: MetricResult | None    # repro データが揃ったときのみ
    cost_efficiency: MetricResult

    def n_pass(self) -> int:
        return sum(
            1 for m in self._metrics()
            if m is not None and m.status == MetricStatus.PASS
        )

    def n_fail(self) -> int:
        return sum(
            1 for m in self._metrics()
            if m is not None and m.status == MetricStatus.FAIL
        )

    def n_unphysical(self) -> int:
        return sum(
            1 for m in self._metrics()
            if m is not None and m.status == MetricStatus.UNPHYSICAL
        )

    def n_unknown(self) -> int:
        return sum(
            1 for m in self._metrics()
            if m is not None and m.status == MetricStatus.UNKNOWN
        )

    def overall_status(self) -> MetricStatus:
        """4 段階判定:
            UNPHYSICAL があれば全体 UNPHYSICAL (= LLM 提案が物理破綻)
            FAIL があれば全体 FAIL
            PASS が 1 つでもあれば PASS
            それ以外は UNKNOWN
        """
        if self.n_unphysical() > 0:
            return MetricStatus.UNPHYSICAL
        if self.n_fail() > 0:
            return MetricStatus.FAIL
        if self.n_pass() > 0:
            return MetricStatus.PASS
        return MetricStatus.UNKNOWN

    def _metrics(self) -> list[MetricResult | None]:
        return [
            self.physical_feasibility,
            self.convergence,
            self.smearing_validity,
            self.band_gap_validity,
            self.reproducibility,
            self.cost_efficiency,
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "formula": self.formula,
            "overall_status": self.overall_status().value,
            "n_pass": self.n_pass(),
            "n_fail": self.n_fail(),
            "n_unknown": self.n_unknown(),
            "metrics": {
                m.name: m.to_dict()
                for m in self._metrics() if m is not None
            },
        }


def score_cell(
    model: str,
    obs: Observables,
    ref: MaterialReference,
    proposed_smearing: str | None,
    proposed_degauss_Ry: float | None,
    repro_param_hashes: list[str] | dict[str, int] | None = None,
    max_wall_seconds: float | None = None,
) -> CellScore:
    """1 (LLM, material) cell の全指標を計算."""
    return CellScore(
        model=model,
        formula=ref.formula,
        physical_feasibility=evaluate_physical_feasibility(obs),
        convergence=evaluate_convergence(obs, ref),
        smearing_validity=evaluate_smearing_for_insulator(
            proposed_smearing, proposed_degauss_Ry, ref
        ),
        band_gap_validity=evaluate_band_gap(obs, ref),
        reproducibility=(
            evaluate_reproducibility(repro_param_hashes)
            if repro_param_hashes is not None else None
        ),
        cost_efficiency=evaluate_cost_efficiency(obs, max_wall_seconds),
    )


# ---------------------------------------------------------------------------
# 集計ヘルパ — 複数 cell をモデル別 / 材料別に丸める
# ---------------------------------------------------------------------------

def aggregate_by_model(cells: Iterable[CellScore]) -> dict[str, dict[str, Any]]:
    """モデル横断で集計: PASS 率, 平均 wall, etc."""
    by_model: dict[str, list[CellScore]] = {}
    for c in cells:
        by_model.setdefault(c.model, []).append(c)

    out: dict[str, dict[str, Any]] = {}
    for model, group in by_model.items():
        n = len(group)
        n_pass_overall = sum(1 for c in group if c.overall_status() == MetricStatus.PASS)
        walls = [
            c.cost_efficiency.value
            for c in group
            if c.cost_efficiency.value is not None
        ]
        out[model] = {
            "n_cells": n,
            "overall_pass_rate": n_pass_overall / n if n else 0.0,
            "convergence_pass_rate": _rate(group, "convergence"),
            "smearing_pass_rate": _rate(group, "smearing_validity"),
            "band_gap_pass_rate": _rate(group, "band_gap_validity"),
            "reproducibility_pass_rate": _rate_optional(group, "reproducibility"),
            "wall_seconds_mean": statistics.mean(walls) if walls else None,
            "wall_seconds_stdev": statistics.stdev(walls) if len(walls) > 1 else 0.0,
        }
    return out


def aggregate_by_material(cells: Iterable[CellScore]) -> dict[str, dict[str, Any]]:
    """材料横断で集計: どのモデルが落ちやすいか、最速モデルは誰か."""
    by_mat: dict[str, list[CellScore]] = {}
    for c in cells:
        by_mat.setdefault(c.formula, []).append(c)

    out: dict[str, dict[str, Any]] = {}
    for formula, group in by_mat.items():
        n = len(group)
        walls = [
            (c.model, c.cost_efficiency.value)
            for c in group
            if c.cost_efficiency.value is not None
        ]
        fastest = min(walls, key=lambda x: x[1]) if walls else (None, None)
        out[formula] = {
            "n_models": n,
            "overall_pass_rate": sum(1 for c in group if c.overall_status() == MetricStatus.PASS) / n,
            "convergence_pass_rate": _rate(group, "convergence"),
            "fastest_model": fastest[0],
            "fastest_wall_seconds": fastest[1],
            "models_failed": [
                c.model for c in group if c.overall_status() == MetricStatus.FAIL
            ],
        }
    return out


def _rate(cells: list[CellScore], metric_name: str) -> float:
    """指定 metric が PASS の割合 (UNKNOWN は分母から除く)."""
    known = []
    for c in cells:
        m = getattr(c, metric_name)
        if m is not None and m.status != MetricStatus.UNKNOWN:
            known.append(m.status == MetricStatus.PASS)
    if not known:
        return 0.0
    return sum(known) / len(known)


def _rate_optional(cells: list[CellScore], metric_name: str) -> float | None:
    """metric が None (= 未測定) の cell が混じる場合の rate."""
    known = []
    for c in cells:
        m = getattr(c, metric_name)
        if m is not None and m.status != MetricStatus.UNKNOWN:
            known.append(m.status == MetricStatus.PASS)
    if not known:
        return None
    return sum(known) / len(known)


# ---------------------------------------------------------------------------
# Reference 永続化 (Step 2 で各材料 fixture から読む)
# ---------------------------------------------------------------------------

def load_reference_toml(path: str | Path) -> MaterialReference:
    """Reference を TOML から読む.

    形式::

        formula = "CsPbI3"
        n_atoms = 5
        is_insulator = true
        e_total_converged_Ry_per_atom = -149.94103
        band_gap_PBE_eV = 1.48
        band_gap_source = "Materials Project mp-1069538"
    """
    import tomllib
    with Path(path).open("rb") as f:
        d = tomllib.load(f)
    return MaterialReference(
        formula=d["formula"],
        n_atoms=int(d["n_atoms"]),
        is_insulator=bool(d["is_insulator"]),
        e_total_converged_Ry_per_atom=d.get("e_total_converged_Ry_per_atom"),
        band_gap_PBE_eV=d.get("band_gap_PBE_eV"),
        band_gap_source=d.get("band_gap_source", ""),
    )
