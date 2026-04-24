# 無料クラウド LLM の API キー取得・配置

費用 0 円で利用できる Gemini と Groq の API キー取得手順です。
両方とも **クレジットカード登録不要**、Google アカウントだけで完結します。

## 1. Google Gemini (推奨)

### キー取得 (5 分)

1. https://aistudio.google.com/apikey にアクセス
2. Google アカウントでログイン
3. 「Get API key」→ 「Create API key in new project」
4. 表示された `AIza...` で始まる文字列をコピー

### 無料枠 (2026-04 時点)

| モデル | 1 分あたり | 1 日あたり | 備考 |
|------|---------|---------|------|
| gemini-2.0-flash-001 | 15 req | 1,500 req | 推奨デフォルト |
| gemini-2.5-flash | 10 req | 250 req | より新、quota 厳しめ |
| gemini-2.5-pro | 5 req | 100 req | 上位モデル、慎重に |

100 試行なら gemini-2.0-flash で 7 分以内に完走可能。

## 2. Groq Cloud

### キー取得 (3 分)

1. https://console.groq.com/keys にアクセス
2. 無料アカウント作成 (Google / GitHub / メール)
3. 「Create API Key」→ 任意名（例: `paper1-repro`）
4. `gsk_...` で始まる文字列をコピー（**1 度しか表示されない**）

### 無料枠

| モデル | 1 分 | 1 日 | コメント |
|--------|----|-----|--------|
| llama-3.3-70b-versatile | 30 | 14,400 | 70B 級、推奨 |
| llama-3.1-8b-instant | 30 | 14,400 | 高速軽量 |
| qwen-qwq-32b | 30 | 14,400 | 推論強化 |
| deepseek-r1-distill-llama-70b | 30 | 14,400 | DeepSeek 蒸留 |

100 試行が ~5 分で完走できる速度（Groq は推論が極速）。

## 3. ローカル配置

`~/.config/paper1/` に既に保管 dir を準備済みです。次のコマンドで貼り付け:

```bash
# Gemini
read -s -p "Paste GEMINI_API_KEY: " K && \
  printf 'GEMINI_API_KEY=%s\n' "$K" > ~/.config/paper1/gemini.env && \
  chmod 600 ~/.config/paper1/gemini.env && unset K && echo " saved"

# Groq
read -s -p "Paste GROQ_API_KEY: " K && \
  printf 'GROQ_API_KEY=%s\n' "$K" > ~/.config/paper1/groq.env && \
  chmod 600 ~/.config/paper1/groq.env && unset K && echo " saved"
```

`~/.bashrc` の paper1 ブロックを更新して自動 source させます:

```bash
# 一度だけ実行
grep -q 'gemini.env' ~/.bashrc || cat >> ~/.bashrc <<'BLOCK'
[ -f "$HOME/.config/paper1/gemini.env" ] && . "$HOME/.config/paper1/gemini.env"
[ -f "$HOME/.config/paper1/groq.env" ]   && . "$HOME/.config/paper1/groq.env"
BLOCK
```

新しいシェルを開けば `echo $GEMINI_API_KEY` `echo $GROQ_API_KEY` で確認可能。

## 4. 動作テスト (~10 秒)

```bash
cd /home/kohki/research/paper1-benchmark
python3 -c "
from llm.cloud import GeminiClient, GroqClient
g = GeminiClient('gemini-2.0-flash-001')
r = g.ask('Reply with the JSON {\"ok\":true} only.', temperature=0)
print('Gemini:', r.text[:80])

q = GroqClient('llama-3.3-70b-versatile')
r = q.ask('Reply with the JSON {\"ok\":true} only.', temperature=0)
print('Groq:', r.text[:80])
"
```

両方 `{"ok":true}` 系の応答が返れば成功。

## 5. 100 試行を Gemini で実行

```bash
cd /home/kohki/research/paper1-benchmark/experiments/repro-v1
python3 run_cloud.py --provider gemini --model gemini-2.0-flash-001 \
  --n 100 --temperature 0.0 --seed 42
```

結果は `experiments/repro-v1-gemini-gemini-2.0-flash-001/` に同じ形式で出力され、
repro-viewer (http://localhost:3001) からそのまま閲覧可能。

## 注意事項

- **キーは私 (Claude Code) には見せないでください**。環境変数経由で読まれるだけで十分
- 無料枠はサービス側で予告なく変更される可能性あり。気付いたら CLOUD_LLM_SETUP.md に追記
- API key は **1 つでも 1 つの実験は走る**。両方なくても片方ずつ進められる
