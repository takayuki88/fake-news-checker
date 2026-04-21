# Ver1 コード読み方ガイド

このガイドは、Ver1 のコードを初めて読む人向けの短い地図です。
細かい実装を追う前に、まず「入力から判定結果までの流れ」をつかむために使ってください。

## 全体の流れ

1. `app/main.py`
   - Web画面とAPIの入口です。
   - 入力されたURLまたは本文を受け取り、抽出処理と判定処理へ渡します。

2. `app/content_extractor.py`
   - URLや貼り付け本文を、判定しやすい `ResolvedPage` に変換します。
   - URLの場合は、取得可否の確認、HTML取得、本文抽出、タイトルや公開日時の推定を行います。

3. `app/analyzer.py`
   - 判定ロジックの中心です。
   - ローカルルールで一次判定を作り、Gemini が使える場合は根拠確認を重ね、最後に5区分の判定へ整えます。

4. `app/models.py`
   - 入力、抽出済みページ、判定結果などのデータ構造を定義しています。
   - 「この変数には何が入るのか」が分からなくなったら、このファイルを見ると整理できます。

5. `app/dataset_runner.py`
   - データセットを1件ずつ判定するための補助コードです。
   - Ver1では、後続バージョンよりも評価保存まわりはシンプルです。

6. `app/evidence_search.py`
   - 本文から確認すべき主張を抜き出し、公的機関やファクトチェックサイトを検索するためのリンクを作ります。

7. `app/config.py` と `app/time_utils.py`
   - `.env` や環境変数から設定を読み込み、判定日時を日本時間などで扱います。

## 初心者におすすめの読み順

1. `app/main.py` の `analyze`
2. `app/content_extractor.py` の `resolve_page_input`
3. `app/analyzer.py` の `analyze_page`
4. `app/analyzer.py` の `heuristic_analysis`
5. `app/analyzer.py` の `combine_result`
6. `app/models.py` の `ResolvedPage` と `AnalysisResult`

## コメントの読み方

コード内のコメントや docstring は、すべての行を説明するためではなく、迷いやすい場所に道しるべを置くために追加しています。
まずは「この関数は何を受け取り、何を返すのか」を追うと読みやすいです。
