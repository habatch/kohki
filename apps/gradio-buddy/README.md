---
title: Research Buddy
emoji: 🧪
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: "4.40.0"
app_file: app.py
pinned: false
---

# Research Buddy (Gradio + Groq)

Open WebUI が Render 512 MB tier で起動しない場合の **軽量 pivot 案**。

## Hugging Face Spaces deploy (推奨、完全無料)

1. https://huggingface.co/new-space で New Space 作成
2. SDK: **Gradio**
3. Space hardware: **CPU basic** (free)
4. Repository visibility: Private (推奨、Groq API key を含むため)
5. 作成後、本ディレクトリの内容 (app.py, requirements.txt, README.md) を git push
6. Settings → Repository secrets で `GROQ_API_KEY` 追加
7. 自動 build → ~3-5 分で Live

## ローカル起動

```bash
cd apps/gradio-buddy
pip install -r requirements.txt
export GROQ_API_KEY=$(grep GROQ_API_KEY ~/.config/paper1/groq.env | cut -d= -f2)
python app.py
# → http://localhost:7860
```

## Render.com deploy (オプション、512 MB tier で確実動作)

`render.yaml` 作成して repo に commit:

```yaml
services:
  - type: web
    name: gradio-buddy
    runtime: python
    buildCommand: pip install -r apps/gradio-buddy/requirements.txt
    startCommand: cd apps/gradio-buddy && python app.py
    plan: free
    region: singapore
    envVars:
      - key: GROQ_API_KEY
        sync: false
      - key: PORT
        value: "10000"
```

## 機能

- Multi-turn chat
- Model 選択 (Llama 3.3 70B / qwen3-32b / gpt-oss-120b 等)
- System prompt カスタマイズ
- Temperature / max tokens 調整

## 制限

- 会話 history は session 内のみ (リロードで消える)
- ファイル upload なし (RAG なし)
- 基本機能のみ

→ Open WebUI の代替として「最低限の chat バディ」を確保する用途。
