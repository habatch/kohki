#!/usr/bin/env bash
# Track A Phase 2: Ollama に新規 2 体を pull する.
#
#   phi4:14b        (Microsoft, 14B dense, ~9.1 GB GGUF Q4_K_M)
#   deepseek-r1:7b  (DeepSeek, 7B reasoning, ~4.7 GB GGUF Q4_K_M)
#
# Phase 1 既存:
#   qwen2.5:7b      (~4.7 GB)
#   bge-m3:latest   (RAG 用、Phase 2 でも継続使用)
#
# 合計 disk 使用量: 約 18 GB (qwen2.5 + phi-4 + deepseek-r1 + bge-m3)
#
# Usage:
#   bash scripts/ollama_pull_phase2.sh
#
# Idempotent: 既に installed のモデルはスキップ。

set -euo pipefail

NEW_MODELS=(phi4:14b deepseek-r1:7b)

# CLI が PATH に無い環境でも動くよう、~/bin/ollama も探す
OLLAMA_BIN="${OLLAMA_BIN:-}"
if [[ -z "$OLLAMA_BIN" ]]; then
  if command -v ollama >/dev/null 2>&1; then
    OLLAMA_BIN="$(command -v ollama)"
  elif [[ -x "$HOME/bin/ollama" ]]; then
    OLLAMA_BIN="$HOME/bin/ollama"
  else
    echo "ERROR: ollama CLI not found in PATH or ~/bin. Install or set OLLAMA_BIN."
    exit 1
  fi
fi
echo "Using ollama CLI: $OLLAMA_BIN"

echo "== Ollama pull (Phase 2 新規 2 体) =="

# Ollama サーバ稼働確認
if ! curl -fs http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "ERROR: Ollama server not running. Start it with 'ollama serve' or systemctl."
  exit 1
fi

INSTALLED=$(curl -fs http://localhost:11434/api/tags \
  | python3 -c "import sys,json; print(' '.join(m['name'] for m in json.load(sys.stdin).get('models',[])))")

echo "Currently installed: $INSTALLED"
echo

for m in "${NEW_MODELS[@]}"; do
  if echo "$INSTALLED" | grep -qw "$m"; then
    echo "  [skip] $m (already installed)"
    continue
  fi
  echo "  [pull] $m  (this may take several minutes...)"
  "$OLLAMA_BIN" pull "$m"
done

echo
echo "Done. Final model list:"
curl -fs http://localhost:11434/api/tags \
  | python3 -c "import sys,json; [print(' ',m['name'], m.get('details',{}).get('parameter_size','?')) for m in json.load(sys.stdin).get('models',[])]"
