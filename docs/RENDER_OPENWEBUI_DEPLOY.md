# Open WebUI を Render.com に Deploy する手順

研究バディ (CCAGI / Anthropic 依存なし) を cloud で 24/7 稼働させる構成。

## 構成全体像

```
[ User Browser ]
      ↓
[ Render.com Web Service ]   無料 24/7
   Open WebUI (chat UI)
      ↓ OpenAI-compatible API
[ Groq Cloud ]               無料 30 RPM
   Llama 3.3 70B / qwen3-32b / gpt-oss-120b
```

- 月額: 0 円 (Render 無料 + Groq 無料)
- ライセンス剥奪リスク: 0 (CCAGI / Anthropic 不使用)
- アクセス: 任意ブラウザから (PC, スマホ, タブレット)

## Deploy 手順 (10 分)

### 1. Render.com アカウント作成

1. https://render.com にアクセス
2. "Sign Up" → "GitHub でログイン" (簡単)
3. GitHub 連携を承認

### 2. Blueprint Deploy

1. Render Dashboard → 左メニュー "Blueprints" → "New Blueprint Instance"
2. リポジトリ選択: `habatch/kohki` (本リポジトリ)
3. Render が `render.yaml` を自動検出 → 表示される設定を確認
4. 下にスクロールして **環境変数 OPENAI_API_KEY** を入力
   - 値: 既存 Groq API key (`gsk_...`)
   - 取得元: `~/.config/paper1/groq.env`
5. "Apply" クリック → ~5-10 分で deploy 完了

### 3. 初回アクセス + Admin 作成

1. Render Dashboard で URL 確認 (例: `https://openwebui-buddy.onrender.com`)
2. URL アクセス → "Sign Up" 画面
3. **最初に登録した user が admin になる** ので必ず自分で先に作成
4. メール + パスワードで登録 (本物のメールでなくて OK、ローカル管理用)

### 4. 動作確認

1. 左下の Settings → Models → Groq の各モデルが選択肢に出ているか確認
2. 新規 chat → "Hello" を送信
3. Llama 3.3 70B 等から応答が返ってくれば成功

## 制限事項 (無料 tier)

| 項目 | 制限 | 影響 |
|---|---|---|
| RAM | 512 MB | 起動遅め、機能制限済 |
| CPU | 0.1 vCPU | 応答 1-2 秒遅延 |
| Sleep | 15 分 inactive で sleep | access 時 30-60 秒 wake-up |
| Disk | ephemeral | 再起動で会話 history 消失 |
| 時間 | 750 hr/月 | 1 service 24/7 で 744 hr 消費、ぎり OK |

## 永続化したい場合 (oprtional, $1/月)

```yaml
# render.yaml に追記
disk:
  name: openwebui-data
  mountPath: /app/backend/data
  sizeGB: 1   # $1/月
```

これで会話 history、admin アカウント、設定が永続化される。

## 故障時の fallback

- Render が動かない → ローカル PC で `pip install open-webui` → `open-webui serve`
- Groq が rate limit → OpenRouter free tier に切替 (環境変数 1 行変更)
- 全部ダメ → Aider (terminal 軽量) 単独で凌ぐ

## セキュリティ注意事項

- `WEBUI_AUTH=True` (本 yaml で設定済) → 必ずログイン要求
- 初回登録 admin の email + パスワード を strong に
- API key は **Render Dashboard 上のみ** に保存、git には絶対 commit しない
- 公開 URL = 認証ありなのでブルートフォース対策に長いパスワード推奨

## Customer Cloud / CCAGI との関係

```
本構成は CCAGI と完全独立:
  - LLM: Groq (Customer Cloud 関係なし)
  - UI: Render (Customer Cloud 関係なし)
  - Storage: GitHub repo (Customer Cloud 関係なし)
  - 認証: 自前 (Customer Cloud 関係なし)

CCAGI ライセンス剥奪されても本構成は何の影響も受けない。
研究継続性を担保する独立 backup として位置付け。
```
