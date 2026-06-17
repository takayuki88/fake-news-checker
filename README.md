# fake-news-checker

情報の真偽を判定する `FastAPI` ベースのフェイクニュースチェッカーです。
ニュース記事、SNS投稿、短い主張文を入力すると、5段階の判定、要注意度、理由、根拠リンクを返します。

主成果版は `Ver4` です。
GPTによる一次レビューとGeminiによる外部根拠確認を組み合わせ、最新再評価では100件データセットでAccuracy 87.0%、Macro F1 87.0%を確認しました。

## 採用担当者向けポートフォリオ

就職活動用に、主成果版である `Ver4` だけを抽出した [`portfolio/`](portfolio/) を用意しています。
`Ver1` から `Ver4` は試行錯誤と比較検証の履歴であり、まずは `portfolio/README.md` を確認してください。

画面例、評価結果、構成説明は `portfolio/` にまとめています。

## リポジトリ構成

- `Ver1`
  - 初期版のアプリ
- `Ver2`
  - 5段階判定へ整理した改善版
  - 5段階判定と評価スクリプト、評価バンドル出力を含む
- `Ver3`
  - `Ver2` を発展させた検証用バージョン
  - 実データセットや収集スクリプトを多く含む
- `Ver4`
  - GPT一次レビューとGemini外部根拠確認を組み合わせた主成果版
- `presentation`
  - 発表資料と生成スクリプト
  - 発表時点の資料を残しているため、portfolioの最新再評価とは数値が異なる場合があります

## 主な機能

- ニュース文、投稿文、主張文の真偽判定
- `正確 / ほぼ正確 / 判断保留 / 不正確 / 誤り` の5段階分類
- 要注意度スコアの表示
- 根拠リンクと補足説明の提示
- URL からの本文抽出
- GPTを使った一次レビュー
- Geminiを使った外部根拠比較
- データセット評価と可視化

## セットアップ

まず確認する場合は `portfolio/` を使ってください。

```powershell
cd portfolio
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

`.env` に `OPENAI_API_KEY` と `GEMINI_API_KEY` を設定すると、GPT一次レビューとGemini外部根拠確認が有効になります。
未設定でもローカル判定中心で動作します。

## アプリ起動

```powershell
cd portfolio
python -m uvicorn app.main:app --reload
```

ブラウザで `http://127.0.0.1:8000` を開きます。

## 評価運用メモ

`portfolio` と `Ver4` には dataset 実行と評価可視化の仕組みがあります。

- `dataset_runner.py` は簡略スキーマ dataset の直読みに対応
- `plot_evaluation.py` は評価画像の出力に対応
- 評価成果物は `evaluation_outputs/<timestamp>/` に保存

評価画像は `evaluation_outputs/<timestamp>/plots` に次の 5 枚を出す運用です。

- `evaluation_dashboard.png`
- `confusion_matrix.png`
- `summary_metrics.png`
- `per_class_metrics.png`
- `evaluation_overview.png`

## よく使うファイル

- [`portfolio/README.md`](portfolio/README.md)
- [`portfolio/app/analyzer.py`](portfolio/app/analyzer.py)
- [`portfolio/app/dataset_runner.py`](portfolio/app/dataset_runner.py)
- [`portfolio/docs/screenshots.md`](portfolio/docs/screenshots.md)
- [`portfolio/docs/evaluation_summary.md`](portfolio/docs/evaluation_summary.md)

## 補足

各バージョンごとの詳細な仕様や起動方法は、それぞれの README を参照してください。

- [`Ver1/README.md`](Ver1/README.md)
- [`Ver2/README.md`](Ver2/README.md)
- [`Ver3/README.md`](Ver3/README.md)
- [`Ver4/README.md`](Ver4/README.md)
