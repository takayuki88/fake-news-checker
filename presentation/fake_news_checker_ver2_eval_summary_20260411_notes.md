# Fake News Checker Ver2 Evaluation Summary Notes

- source_pptx: fake_news_checker_presentation_20260401.pptx
- dataset: testdata\shared\real_article_dataset_v2.json
- evaluation: Ver2\evaluation_outputs\20260411-0509\eval_real_article_dataset_v2_use_gemini.json
- predictions_csv: Ver2\evaluation_outputs\20260411-0509\Ver2_real_article_dataset_v2_with_predicted_verdict_attention_score.csv

## Slide 1
- 表紙。既存資料の続編として、Ver2 の最新評価を短く説明する。Accuracy 84.0%、Macro F1 0.837、Binary F1 0.889 を最初に示す。

## Slide 2
- 2枚目は目的と条件。100件 balanced dataset を Gemini 付きで再評価したこと、実運用では確認支援ツールとして位置づけていることを説明する。

## Slide 3
- 3枚目は全体結果。Accuracy 84.0%、Macro F1 0.837、誤り binary F1 0.889。以前より改善したが、境界ラベルの揺れが残る点を添える。

## Slide 4
- 4枚目はクラス別。判断保留と不正確は安定している一方、ほぼ正確 recall 0.600 がボトルネック。誤り recall 0.800 もまだ伸ばしたい。

## Slide 5
- 5枚目は混同行列。ほぼ正確→正確が6件、誤り→不正確が4件。境界を安全側に倒した結果だが、今後は誤り recall の改善が重要。

## Slide 6
- 6枚目は代表誤分類。正確→ほぼ正確、ほぼ正確→正確、ほぼ正確→不正確、誤り→不正確を1件ずつ見せて、境界条件の調整が中心課題だと示す。

## Slide 7
- 7枚目は改善方針。短期は誤り recall、中期はほぼ正確の境界設計。最終的な位置づけは自動断定ではなく説明付き確認支援ツールとする。

## Slide 8
- 最後はダッシュボード全体図。質疑ではこのスライドを開いて、混同行列・summary・per-class を一枚で見せられるようにする。
