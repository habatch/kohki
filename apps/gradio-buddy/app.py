"""Gradio Chat UI — 軽量 LLM 研究バディ (HF Spaces 推奨)

Open WebUI が 512 MB RAM tier で起動しない場合の pivot 案。
Gradio は ~150 MB で動くので HF Spaces / Render 無料 tier で確実 deploy 可。

機能:
  - chat (multi-turn conversation)
  - Groq cloud (OpenAI 互換) 経由で Llama / Qwen / gpt-oss 全モデル選択可
  - System prompt カスタマイズ
  - 会話 history (session 内のみ、永続化なし)

Deploy 先候補:
  - Hugging Face Spaces (推奨、完全無料、SSE 対応):
      pip install gradio openai
      → app.py を Space に push
  - Render free (512 MB OK、sleep あり)
  - ローカル PC: python app.py → http://localhost:7860
"""

import os
import gradio as gr
from openai import OpenAI

# Groq cloud (OpenAI 互換) として使う
client = OpenAI(
    api_key=os.environ.get("GROQ_API_KEY") or os.environ.get("OPENAI_API_KEY", ""),
    base_url="https://api.groq.com/openai/v1",
)

# Groq で利用可能なモデル一覧 (2026-04 時点)
AVAILABLE_MODELS = [
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "qwen/qwen3-32b",
    "llama-3.1-8b-instant",
    "qwen-qwq-32b",
]

DEFAULT_SYSTEM_PROMPT = """You are a research assistant specialized in:
- First-principles calculations (DFT, Quantum ESPRESSO)
- Computational materials science
- LLM benchmarking methodology

Be concise, technical, and honest about uncertainty."""


def respond(
    message: str,
    history: list,
    system_prompt: str,
    model_id: str,
    temperature: float,
    max_tokens: int,
) -> str:
    """1 会話ターンの応答生成."""
    messages = [{"role": "system", "content": system_prompt}]
    for prev in history:
        if isinstance(prev, dict):
            messages.append(prev)
        else:
            # gradio messages format によっては list[tuple] でくる場合がある
            user_msg, ai_msg = prev
            messages.append({"role": "user", "content": user_msg})
            if ai_msg:
                messages.append({"role": "assistant", "content": ai_msg})
    messages.append({"role": "user", "content": message})

    try:
        resp = client.chat.completions.create(
            model=model_id,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )
        return resp.choices[0].message.content or "(empty response)"
    except Exception as e:
        return f"⚠ Groq API error: {e}"


with gr.Blocks(title="Research Buddy") as demo:
    gr.Markdown("# 🧪 Research Buddy (Groq cloud 経由、CCAGI 不依存)")

    with gr.Row():
        with gr.Column(scale=4):
            chatbot = gr.Chatbot(type="messages", height=600)
            msg = gr.Textbox(label="Message", placeholder="Ask anything…")

        with gr.Column(scale=1):
            model_id = gr.Dropdown(
                choices=AVAILABLE_MODELS,
                value=AVAILABLE_MODELS[0],
                label="Model",
            )
            temperature = gr.Slider(0.0, 2.0, value=0.0, step=0.1, label="Temperature")
            max_tokens = gr.Slider(256, 8192, value=2048, step=256, label="Max tokens")
            system_prompt = gr.Textbox(
                value=DEFAULT_SYSTEM_PROMPT,
                lines=8,
                label="System prompt",
            )

    def user_send(message, history):
        return "", history + [{"role": "user", "content": message}]

    def bot_reply(history, system_prompt, model_id, temperature, max_tokens):
        user_message = history[-1]["content"]
        # bot reply 生成 (history 末尾の user message を渡す前の history を渡す)
        prior = history[:-1]
        reply = respond(user_message, prior, system_prompt, model_id, temperature, max_tokens)
        history.append({"role": "assistant", "content": reply})
        return history

    msg.submit(user_send, [msg, chatbot], [msg, chatbot]).then(
        bot_reply,
        [chatbot, system_prompt, model_id, temperature, max_tokens],
        chatbot,
    )


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", 7860)),
    )
