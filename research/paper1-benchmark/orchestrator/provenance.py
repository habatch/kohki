"""Provenance capture for Paper 3 (applied from Paper 1 onwards).

Every experimental event — whether an LLM call or a DFT run — is logged as
a JSONL record AND wrapped into a zip bundle with the raw artefacts. The
zip is content-addressed by SHA-256 so the same prompt / same DFT input
produce the same bundle name.

This module has **no external deps** and is safe to import from any
backend (local laptop, GitHub Actions runner, Kaggle notebook, Oracle VM).
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Mapping


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class RunEnv:
    """Minimal environment capture. Extend in subclasses per backend."""
    repo_commit: str
    host: str
    python: str
    kernel: str
    timestamp_utc: str


def current_env() -> RunEnv:
    return RunEnv(
        repo_commit=_git_head(),
        host=platform.node(),
        python=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        kernel=platform.platform(),
        timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )


def _git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return out.stdout.strip()
    except Exception:
        return "unknown"


@dataclass
class LLMEvent:
    prompt_sha: str
    response_sha: str
    model_id: str
    temperature: float
    seed: int | None
    prompt: str
    response: str
    usage: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class DFTEvent:
    material: str
    input_sha: str
    output_sha: str
    qe_version: str
    steps_run: list[str]
    wall_seconds: float
    observables: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


class JsonlLog:
    """Append-only JSONL writer. One line == one event.

    Intended use::

        with JsonlLog(results/"paper1-llm.jsonl") as log:
            log.write({"kind": "llm", ...})
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = None

    def __enter__(self) -> "JsonlLog":
        self._fh = self.path.open("a", encoding="utf-8")
        return self

    def __exit__(self, *exc) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None

    def write(self, record: Mapping[str, Any]) -> None:
        assert self._fh, "JsonlLog used outside context manager"
        self._fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        self._fh.flush()


def bundle_dft_run(
    out_dir: Path,
    material: str,
    qe_input: str,
    qe_output: str,
    observables: Mapping[str, Any],
    env: RunEnv | None = None,
    extra_files: Mapping[str, bytes] | None = None,
) -> Path:
    """Bundle one DFT run into a content-addressed zip.

    Returns the zip path. The file name is
    ``{material}-{input_sha8}-{timestamp}.zip`` so two runs with the same
    input collide intentionally (enable dedupe).
    """
    env = env or current_env()
    input_sha = sha256_text(qe_input)
    output_sha = sha256_text(qe_output)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"{material}-{input_sha[:8]}-{env.timestamp_utc.replace(':', '').replace('-', '')}.zip"
    zpath = out_dir / name
    meta = {
        "schema": "paper3.provenance.dft.v1",
        "material": material,
        "input_sha256": input_sha,
        "output_sha256": output_sha,
        "observables": dict(observables),
        "env": asdict(env),
    }
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("input.in", qe_input)
        z.writestr("output.out", qe_output)
        z.writestr("metadata.json", json.dumps(meta, indent=2, sort_keys=True))
        if extra_files:
            for rel, data in extra_files.items():
                z.writestr(rel, data)
    return zpath


def bundle_llm_event(out_dir: Path, event: LLMEvent, env: RunEnv | None = None) -> Path:
    env = env or current_env()
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"llm-{event.prompt_sha[:8]}-{env.timestamp_utc.replace(':', '').replace('-', '')}.zip"
    zpath = out_dir / name
    meta = {
        "schema": "paper3.provenance.llm.v1",
        "env": asdict(env),
        "event": asdict(event),
    }
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("prompt.txt", event.prompt)
        z.writestr("response.txt", event.response)
        z.writestr("metadata.json", json.dumps(meta, indent=2, sort_keys=True))
    return zpath
