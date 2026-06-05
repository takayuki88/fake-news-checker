# Ver3 コード読み方ガイド

このガイドは、Ver3 のコードを初めて読む人向けの短い地図です。
細かい実装を追う前に、まず「どのファイルが何を担当しているか」をつかむために使ってください。

## 全体の流れ

1. `app/main.py`
   - Web画面とAPIの入口です。
   - 入力されたURLまたは本文を受け取り、抽出処理と判定処理へ渡します。

2. `app/content_extractor.py`
   - URLや貼り付け本文を、判定しやすい `ResolvedPage` に変換します。
   - URLの場合は、取得可否の確認、HTML取得、本文抽出、タイトルや公開日時の推定を行います。

3. `app/analyzer.py`
   - 判定ロジックの中心です。
   - まずローカルルールで一次判定を作り、Gemini が使える場合は根拠確認を重ね、最後に5区分の判定へ整えます。

4. `app/models.py`
   - 入力、抽出済みページ、判定結果などのデータ構造を定義しています。
   - コードを読むときに「この変数には何が入るのか」が分からなくなったら、このファイルを見ると整理できます。

5. `app/dataset_runner.py`
   - 100件などのデータセットをまとめて実行するためのコマンドライン用コードです。
   - 予測JSON、評価JSON、CSV、グラフを保存できます。

6. `app/evaluation.py`
   - 予測ラベルと正解ラベルを比べ、accuracy、precision、recall、F1、混同行列を計算します。

7. `app/evidence_search.py`
   - 本文から確認すべき主張を抜き出し、公的機関やファクトチェックサイトを検索するためのリンクを作ります。

8. `app/config.py` と `app/time_utils.py`
   - `.env` や環境変数から設定を読み込み、判定日時を日本時間などで扱います。

## 初心者におすすめの読み順

1. `app/main.py` の `analyze`
2. `app/content_extractor.py` の `resolve_page_input`
3. `app/analyzer.py` の `analyze_page`
4. `app/analyzer.py` の `heuristic_analysis`
5. `app/analyzer.py` の `combine_result`
6. `app/models.py` の `ResolvedPage` と `AnalysisResult`

この順番で読むと、「入力が来る」「本文を整える」「判定する」「結果を返す」という流れを追いやすいです。

## データセット評価の読み方

データセット評価だけ見たい場合は、次の順番がおすすめです。

1. `app/dataset_runner.py` の `main`
2. `app/dataset_runner.py` の `run_dataset`
3. `app/dataset_runner.py` の `analyze_case`
4. `app/evaluation.py` の `build_evaluation_report`

実行例:

```powershell
python -m app.dataset_runner ..\testdata\shared\real_article_dataset_v2.json --save-evaluation-bundle --print-evaluation
```

## コメントの読み方

コード内のコメントや docstring は、すべての行を説明するためではなく、迷いやすい場所に道しるべを置くために追加しています。
細かい文法よりも、まずは「この関数は何を受け取り、何を返すのか」を追うと読みやすくなります。
