# Fake News Checker 2 Ver1

ニュース文、投稿文、主張文を入力すると、Gemini を使って真偽や誤解可能性を 6 段階で返す `FastAPI` アプリです。

## この Ver1 の方針

- 判定は次の 6 分類です
  - 信頼性が高い
  - おおむね正確
  - 判断保留
  - 誤解を招く可能性が高い
  - フェイクの可能性が高い
  - 未確認
- 要注意度は `0〜100%` で表示します
- `未確認` の場合は `?%` を表示します
- 理由は 1〜3 点の短い説明で返します
- 可能な範囲で根拠ソースを表示します
- URL入力時は本文抽出、著者名、公開日時、引用リンク数、段落数、見出し数、抽出品質を保持します
- `robots.txt` と規約候補ページを確認し、自動取得が危ないサイトは本文貼り付けのみ対応にします

## 入力

- `ページURL` または `ページ本文`
- 両方ある場合は本文を優先
- 本文は既定で最低 `10` 文字
- API入力は最大 `12000` 文字

## 出力

- 判定
- 要注意度
- 理由
- 根拠
- 補足
- モデルの確信度

## 実装メモ

- ローカルのヒューリスティックで一次判定を作ります
- Gemini API が使える場合は `google_search` と `url_context` を使って外部根拠比較を行います
- Gemini が失敗した場合はローカル一次判定にフォールバックします
- 根拠不足のケースは無理に断定せず `未確認` または `判断保留` に寄せます

## セットアップ

```powershell
cd "C:\Users\oneuk\OneDrive\Desktop\datamix\01 講義\05_インテグレーションステップ\fake-news-checker\Ver1"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

`.env` の `GEMINI_API_KEY` に Gemini の API キーを設定してください。
未設定でもローカル一次判定で動きます。

文字数や抽出条件は以下で調整できます。

- `MIN_TEXT_CHARS`
- `MIN_AUTO_EXTRACT_CHARS`
- `MAX_FETCH_CHARS`

## 起動

```powershell
python -m uvicorn app.main:app --reload
```

ブラウザで `http://127.0.0.1:8000` を開きます。

## 注意

- このアプリは完全な真偽保証をするものではありません
- とくに速報性の高い話題や根拠不足の話題は `未確認` になることがあります
- ログイン必須ページ、JavaScript依存ページ、PDF は本文抽出に失敗することがあります
- 規約や取得制限に触れる可能性があるサイトは自動取得せず、本文貼り付けのみ対応します
