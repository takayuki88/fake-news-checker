# Fake News Checker Portfolio

このフォルダは、Fake News Checkerの完成版として `Ver4` を抽出し、就職活動用ポートフォリオとして読みやすく整理したものです。
リポジトリ直下の `Ver1` から `Ver4` は試行錯誤と比較検証の履歴であり、採用担当者向けの主な確認対象はこの `portfolio/` です。

## 何を作ったか

ニュース記事やSNS投稿の真偽確認を支援するAIアプリケーションです。
AIが最終判断を代替するのではなく、人間が確認すべき情報を絞り込み、判定理由や根拠リンクを確認しやすくすることを目的にしています。

判定は次の5段階です。

- 正確
- ほぼ正確
- 判断保留
- 不正確
- 誤り

## なぜ作ったか

誤情報は短時間で拡散されることがあります。
一方で、本文の自然さだけでは真偽を判断できず、外部根拠、数字、時期、人物名、文脈を確認する必要があります。

そこで、LLMによる論点整理と外部根拠確認を組み合わせ、人間の確認作業を効率化するツールとして設計しました。

## システム構成

```text
入力
  ↓
ローカル一次判定
  ↓
GPT一次レビュー
  ↓
Gemini外部根拠確認
  ↓
補正ルール
  ↓
5段階判定
```

Ver4ではモデル再学習ではなく、LLM出力と外部根拠確認結果をどう5段階ラベルへ変換するかのキャリブレーションを重視しました。

## 主な機能

- 記事本文、投稿文、短い主張文の真偽判定
- URLからの記事本文抽出
- GPTによる一次レビュー
- Geminiによる外部根拠確認
- 判定理由、補足説明、根拠リンクの提示
- 要注意度スコアの表示
- データセット評価と混同行列による分析
- pytestによる自動テスト

## 評価結果

5ラベル各20件、合計100件のbalanced datasetで最新再評価しました。

| 指標 | 結果 |
| --- | ---: |
| sample count | 100 |
| accuracy | 0.8700 |
| macro F1 | 0.8698 |
| weighted F1 | 0.8698 |
| mismatches | 13 |

判断保留は安定していました。
一方で、「正確」「ほぼ正確」「不正確」「誤り」の境界に誤分類が残り、次の改善対象が明確になりました。

## 技術スタック

- Python
- FastAPI
- HTML / CSS
- OpenAI API
- Gemini API
- pytest
- JSON / CSV dataset
- Accuracy、Macro F1、confusion matrixによる評価

## 採用担当者に見てほしい点

- 誤情報確認という実課題に対して、AIを確認支援ツールとして設計したこと
- APIを呼び出すだけでなく、外部根拠確認と補正ルールを組み合わせたこと
- 最新再評価でAccuracy 87.0%、Macro F1 87.0%を確認したこと
- 残った誤分類を分析し、次の改善方針まで整理したこと

## フォルダ構成

```text
portfolio/
├─ app/                 Webアプリ本体
├─ scripts/             データ作成、評価、可視化スクリプト
├─ testdata/            評価用データ、分析メモ
├─ tests/               自動テスト
├─ evaluation_outputs/  最新の評価結果
├─ docs/                ポートフォリオ説明資料
├─ requirements.txt
├─ pytest.ini
└─ .env.example
```

## セットアップ

```powershell
cd portfolio
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

`.env` にAPIキーを設定すると、GPT一次レビューとGemini外部根拠確認が有効になります。

```dotenv
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AIza...
```

APIキーが未設定の場合、一部のLLM機能はスキップされ、ローカル判定中心で動作します。

## 起動

```powershell
cd portfolio
python -m uvicorn app.main:app --reload
```

ブラウザで `http://127.0.0.1:8000` を開きます。

## 評価結果の確認

- [評価JSON](evaluation_outputs/20260613-0023/eval_real_article_dataset_v2_use_gemini.json)
- [予測結果JSON](evaluation_outputs/20260613-0023/predictions_real_article_dataset_v2_use_gemini.json)
- [評価サマリー](docs/evaluation_summary.md)
- [システム構成](docs/architecture.md)
- [今後の改善](docs/future_work.md)
