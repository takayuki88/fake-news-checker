# fake-news-checker

情報の真偽を判定する `FastAPI` ベースのフェイクニュースチェッカーです。
このリポジトリには、段階的に改善してきた `Ver1` `Ver2` `Ver3` `Ver4` `Ver5` と、発表資料をまとめています。

## リポジトリ構成

- `Ver1`
  - 初期版のアプリ
- `Ver2`
  - 現在の主な改善対象
  - 5段階判定と評価スクリプト、評価バンドル出力を含む
- `Ver3`
  - `Ver2` を発展させた検証用バージョン
  - 実データセットや収集スクリプトを多く含む
- `Ver4`
  - OpenAI 一次レビューと Gemini 根拠確認の比較検証用バージョン
- `Ver5`
  - `Ver3` をベースに、Gemini 一次判定案をより強く取り入れる実験用バージョン
- `presentation`
  - 発表資料と生成スクリプト

## 現在の主対象

現状の精度改善は主に `Ver2` を対象に進めています。
評価用データセットや個別の検証では `Ver3` の testdata を参照することがあります。

## 主な機能

- ニュース文、投稿文、主張文の真偽判定
- `正確 / ほぼ正確 / 判断保留 / 不正確 / 誤り` の5段階分類
- 要注意度スコアの表示
- 根拠リンクと補足説明の提示
- URL からの本文抽出
- Gemini を使った外部根拠比較
- データセット評価と可視化

## セットアップ

よく使うのは `Ver2` か `Ver3` です。Gemini 一次判定を強めた実験をしたい場合は `Ver5` を使います。例として `Ver2` のセットアップは次のとおりです。

```powershell
cd "C:\Users\oneuk\OneDrive\Desktop\datamix\01 講義\05_インテグレーションステップ\fake-news-checker\Ver2"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

`.env` の `GEMINI_API_KEY` に API キーを設定すると、Gemini を使った検証が有効になります。

## アプリ起動

```powershell
cd "C:\Users\oneuk\OneDrive\Desktop\datamix\01 講義\05_インテグレーションステップ\fake-news-checker\Ver2"
python -m uvicorn app.main:app --reload
```

ブラウザで `http://127.0.0.1:8000` を開きます。

## 評価運用メモ

`Ver2` `Ver3` `Ver5` には dataset 実行と評価可視化の仕組みがあります。

- `dataset_runner.py` は簡略スキーマ dataset の直読みに対応
- `plot_evaluation.py` は評価画像の出力に対応
- `Ver2/scripts/export_evaluation_bundle.ps1` で評価バンドルを一括出力

評価画像は `evaluation_outputs/<timestamp>/plots` に次の 5 枚を出す運用です。

- `evaluation_dashboard.png`
- `confusion_matrix.png`
- `summary_metrics.png`
- `per_class_metrics.png`
- `evaluation_overview.png`

## よく使うファイル

- [`Ver2/app/analyzer.py`](c:/Users/oneuk/OneDrive/Desktop/datamix/01 講義/05_インテグレーションステップ/fake-news-checker/Ver2/app/analyzer.py)
- [`Ver2/app/dataset_runner.py`](c:/Users/oneuk/OneDrive/Desktop/datamix/01 講義/05_インテグレーションステップ/fake-news-checker/Ver2/app/dataset_runner.py)
- [`Ver2/scripts/export_evaluation_bundle.ps1`](c:/Users/oneuk/OneDrive/Desktop/datamix/01 講義/05_インテグレーションステップ/fake-news-checker/Ver2/scripts/export_evaluation_bundle.ps1)
- [`Ver3/testdata/real_article_dataset_v2.json`](c:/Users/oneuk/OneDrive/Desktop/datamix/01 講義/05_インテグレーションステップ/fake-news-checker/Ver3/testdata/real_article_dataset_v2.json)

## 補足

各バージョンごとの詳細な仕様や起動方法は、それぞれの README を参照してください。

- [`Ver1/README.md`](c:/Users/oneuk/OneDrive/Desktop/datamix/01 講義/05_インテグレーションステップ/fake-news-checker/Ver1/README.md)
- [`Ver2/README.md`](c:/Users/oneuk/OneDrive/Desktop/datamix/01 講義/05_インテグレーションステップ/fake-news-checker/Ver2/README.md)
- [`Ver3/README.md`](c:/Users/oneuk/OneDrive/Desktop/datamix/01 講義/05_インテグレーションステップ/fake-news-checker/Ver3/README.md)
- [`Ver4/README.md`](c:/Users/oneuk/OneDrive/Desktop/datamix/01 講義/05_インテグレーションステップ/fake-news-checker/Ver4/README.md)
- [`Ver5/README.md`](c:/Users/oneuk/OneDrive/Desktop/datamix/01 講義/05_インテグレーションステップ/fake-news-checker/Ver5/README.md)
