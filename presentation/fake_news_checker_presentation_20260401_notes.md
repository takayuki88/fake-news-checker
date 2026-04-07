# Fake News Checker Presentation Notes

- generated_on: 2026-04-01
- dataset: Ver3\testdata\real_article_dataset_v2.json
- ver2_eval: Ver2\evaluation_outputs\20260401-1213\eval_real_v2_use_gemini_after_rule_tune4.json
- ver3_eval: Ver3\evaluation_outputs\20260401-1155\eval_real_v2_use_gemini_after_rule_tune3.json

## Slide 1
- 表紙は datamix 卒業発表の見本に合わせたレイアウト。
- タイトルは『フェイクニュースチェッカー』、副題はプレゼン資料であることを明示する。

## Slide 2
- 課題と選んだ理由では、オールドメディア不信、SNSの台頭、兵庫県知事の騒動、個人的な苦い経験を背景として話す。
- 正確な情報へ近づくための支援ツールを作りたい、という動機にまとめる。

## Slide 3
- dataset v2 は 100件、5区分は各20件で balanced。
- スキーマは id, expected_verdict, analysis_text, expected_domain。
- ドメイン分布は 一般67 / 医療13 / 金融10 / 災害6 / 政治4。

## Slide 4
- 初期仮説は、ローカル一次判定と Gemini の外部根拠比較を組み合わせれば境界ケースを改善できる、というもの。
- 書き振り評価は真偽判定と分離する設計を説明する。

## Slide 5
- Ver2 tune4: accuracy 0.370, macro F1 0.266, 誤り recall 0.000。
- Ver3 tune3: accuracy 0.330, macro F1 0.206, 誤り recall 0.000。
- Ver2 の方が全体指標は少し上だが、誤り recall 0.000 が共通課題であることを話す。

## Slide 6
- Ver2 の主な誤判定は 正確 -> ほぼ正確: 20件, 判断保留 -> 不正確: 12件, 誤り -> 不正確: 11件。
- 誤りを『判断保留』や『不正確』へ逃がしている点がボトルネック。

## Slide 7
- 現状の最適ポジションは自動ジャッジではなく、説明付き確認支援ツール。
- 個人の投稿前チェック、自治体や学校の一次仕分け、教育用途に価値がある。

## Slide 8
- 工夫点として、真偽判定と書き振り評価の分離、5 plots 運用、CSV/XLSX 出力まで含めた bundle 化を挙げる。
- まとめ出力は Ver2\scripts\export_evaluation_bundle.ps1 を使う。

## Slide 9
- 今後は Ver2 を中心に、誤り経路の強化、正確ラベル復帰、ケースレビューの継続を行う。

## Slide 10
- summary_metrics.png を使って、全体指標と binary 指標の弱さを説明する。

## Slide 11
- per_class_metrics.png を使って、クラスごとの偏りを説明する。

## Slide 12
- confusion_matrix.png を使って、どのラベルへ誤って流れているかを説明する。

## Slide 13
- evaluation_overview.png を使って、mismatch 数と集計値を説明する。

## Slide 14
- 参考資料として confusion_matrix.png を単独スライドで追加。

## Slide 15
- 参考資料として evaluation_overview.png を単独スライドで追加。

## Slide 16
- 参考資料として per_class_metrics.png を単独スライドで追加。

## Slide 17
- 参考資料として summary_metrics.png を単独スライドで追加。
