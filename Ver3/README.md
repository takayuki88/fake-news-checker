# Fake News Checker Ver3

ニュース文、投稿文、主張文を入力すると、Gemini を使って真偽や誤解可能性を 5 段階で返す `FastAPI` アプリです。

## この Ver3 の方針

- 判定は次の 5 分類です
  - 正確
  - ほぼ正確
  - 判断保留
  - 不正確
  - 誤り
- 要注意度は `0〜100%` で表示します
- Gemini の役割を 2 つに分けます
  - 外部根拠比較
  - 本文の書き振り評価
- Gemini の書き振り評価は既定でオフです
- 真偽は外部根拠を主にして決めます
- 書き振り評価は危なさを見る補助情報として別表示します
- 書き振り評価が低くても、それだけで信頼性は上げません
- 書き振り評価が高くても、それだけで `誤り` にはしません
- ただし書き振り評価が `80%` 以上のときは、確認優先度として `status` を人手確認寄りにします
- URL入力時は本文抽出、著者名、公開日時、引用リンク数、段落数、見出し数、抽出品質を保持します
- URL入力時は既定で `hard block` と `robots.txt` を確認します
- 規約候補ページの探索は既定で無効にし、必要時だけ有効化できます

## 入力

- `ページURL` または `ページ本文`
- 両方ある場合は本文を優先
- 本文は既定で最低 `10` 文字
- API入力は最大 `12000` 文字
- URL なしの短い主張文は自動で `短文claim評価モード` として扱い、記事メタデータ不足だけでは減点しません
- 開発用に `skip_policy_check` を有効にすると、URL入力時の規約確認をスキップできます
- 必要時だけ `.env` で `STRICT_POLICY_RESEARCH=true` を設定すると、規約候補ページ探索を有効化できます

## 出力

- 判定
- 要注意度
- 理由
- 根拠
- 補足
- モデルの確信度
- 書き振り評価（Gemini またはローカル補助）
- 実行時間の簡易内訳（開発用）

## 実装メモ

- Gemini に一次判定案を作らせつつ、ローカルのヒューリスティックを補助情報として使います
- Gemini API が使える場合は `google_search` と `url_context` を使って外部根拠比較を行います
- 同じ Gemini 呼び出しの中で、本文の書き振りも別枠で採点します
- 最終判定は、Gemini の一次判定案と外部根拠比較を中心に決めます
- 書き振り評価はスコアに直接混ぜず、別カードで見せます
- ローカル補助の書き振り評価も、出典数や信頼度ではなく書き振り関連シグナルだけで作ります
- 書き振り評価が `80%` 以上のときだけ、`status` を `人による確認推奨` に寄せます
- Gemini が失敗した場合はローカル判定とローカル補助の書き振り表示にフォールバックします
- URL入力時の既定動作は、`hard block + robots.txt` を維持し、重い規約候補ページ探索は行いません
- 画面では開発用に、規約確認スキップと実行時間の簡易計測を確認できます

## セットアップ

```powershell
cd "C:\Users\oneuk\OneDrive\Desktop\datamix\講義\05_インテグレーションステップ\fake-news-checker\Ver3"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

`.env` の `GEMINI_API_KEY` に Gemini の API キーを設定してください。
Ver3 は基本的に Gemini を使う前提です。
API キー未設定時だけローカル判定にフォールバックします。
Gemini の書き振り評価を有効にしたい場合だけ `GEMINI_STYLE_REVIEW_ENABLED=true` を追加してください。
規約候補ページ探索を使いたい場合だけ `STRICT_POLICY_RESEARCH=true` を追加してください。

## 起動

```powershell
python -m uvicorn app.main:app --reload
```

ブラウザで `http://127.0.0.1:8000` を開きます。

## 性能評価

5区分の `Accuracy / Precision / Recall / F1 / Macro F1 / Weighted F1 / Confusion Matrix` を確認したいときは、評価用 JSON を用意して次を実行します。

```powershell
python -m app.evaluation .\eval_cases.json --truth-key expected.verdict --pred-key predicted.verdict --output-json .\eval_report.json
```

`eval_cases.json` は次のような形です。

```json
[
  {
    "id": "case-1",
    "expected": { "verdict": "誤り" },
    "predicted": { "verdict": "不正確" }
  },
  {
    "id": "case-2",
    "expected": { "verdict": "正確" },
    "predicted": { "verdict": "正確" }
  }
]
```

この評価では 5区分の分類レポートに加えて、`誤り` を陽性とした二値の `Precision / Recall / F1` もあわせて出力します。

`dataset_runner` から直接つなぐ場合は、まず予測 JSON を作ります。

```powershell
python -m app.dataset_runner .\eval_cases.json --output-json .\predictions.json
```

このリポジトリには、公開 verdict の 5区分を評価する 100 件 dataset も同梱しています。
この `real_article_dataset.json` は、`正確 / ほぼ正確 / 判断保留 / 不正確 / 誤り` を含みます。
判定対象は `analysis_text` の中心命題で、`正確 / ほぼ正確 / 判断保留 / 不正確 / 誤り` を各20件ずつ含みます。
`正確 / ほぼ正確` は JFC、FactCheck Navi が集約した日本系ファクトチェック記事、InFact、神戸新聞、Snopes の日本関連記事を基にした実在ネット記事ケースです。
`analysis_text` は全ケースで日本語要約にそろえています。
短文 dataset には `analysis_mode / claim_text / review_focus / human_note / contested_span` の補助列も持たせています。
同じフォルダにある `*_reading_guide.csv` は、人が見返すための補助一覧です。

### `analysis_text` 抽出ガイドライン

- `analysis_text` は、記事本文の中心命題のうち `expected.verdict` を直接決める判定対象文だけを書きます
- 判定対象は「記事の説明全体」ではなく、「その記事が最終的に true / false / hold と判定している核の主張」です
- `analysis_text` には、`正確です` `誤りです` `ほぼ正確です` `根拠不明です` のような判定文を入れません
- `Snopes は True と判定` `JFC が誤りと判断` `〜とされた` のような評価メタ文も入れません
- `〜と言われているが` という書き方を使う場合でも、最終的に判定したい命題そのものが読める形に寄せます
- 主語、対象、時点、数量、地域、比較対象など、真偽が変わる条件は落とさず残します
- 記事本文が訂正記事でも、`analysis_text` には「訂正の説明」全体ではなく、記事が読者に最終的に判断させたい命題を書きます
- 目安は 1〜2 文で、読んだだけでその文自体を `expected.verdict` に照らして判定できる状態にします

例:

- `正確` 側:
  - `G7が6000億ドルを途上国インフラ投資に回すことは事実で、見出しの日本円表記は日本の全額負担を意味しない。`
- `誤り` 側:
  - `川口市の検挙人数178人のうち外国籍は135人で約76%を占め、検挙された人の約4人に3人が外国籍だ。`

```powershell
python -m app.dataset_runner --dataset real --output-json .\predictions_real.json --print-evaluation --evaluation-output .\eval_real.json
```

上の `dataset_runner` は既定で Gemini を使います。
`--no-gemini` を付けない場合は、実行前に Gemini 接続 preflight を 1 回だけ行い、接続や認証に失敗したら dataset 全体を回す前に停止します。
ローカル判定だけで回したいときだけ `--no-gemini` を付けてください。

```powershell
python -m app.dataset_runner --dataset real --no-gemini --output-json .\predictions_real_local.json --print-evaluation --evaluation-output .\eval_real_local.json
```

評価まで一度に出したい場合は次です。

```powershell
python -m app.dataset_runner .\eval_cases.json --output-json .\predictions.json --print-evaluation --evaluation-output .\eval_report.json
```

`predictions.json` は `app.evaluation` がそのまま読める `records` 形式で保存されます。解析失敗ケースなどで `predicted.verdict` がない行は、評価時に既定でスキップされます。厳密にエラーにしたい場合だけ `app.evaluation` 側で `--strict` を付けてください。

評価 JSON を画像で見たい場合は、次の可視化スクリプトを使えます。

```powershell
python .\scripts\plot_evaluation.py .\eval_real.json
```

既定では `eval_real_plots` ディレクトリが作られ、次の PNG が保存されます。

- `evaluation_dashboard.png`
- `confusion_matrix.png`
- `per_class_metrics.png`

保存先を変えたい場合は `--output-dir` を使います。

```powershell
python .\scripts\plot_evaluation.py .\eval_real.json --output-dir .\plots
```

このスクリプトは `matplotlib` と `seaborn` を使います。未導入なら次を実行してください。

```powershell
pip install -r requirements.txt
```

## 注意

- このアプリは完全な真偽保証をするものではありません
- 書き振り評価は「煽りや断定の強さ」を見る補助情報で、真偽そのものとは別です
- 書き振り評価が低くても、それだけで真実や安全を保証するものではありません
- 速報性の高い話題や根拠不足の話題は `判断保留` になることがあります
- ログイン必須ページ、JavaScript依存ページ、PDF は本文抽出に失敗することがあります
- 規約や取得制限に触れる可能性があるサイトは自動取得せず、本文貼り付けのみ対応します
