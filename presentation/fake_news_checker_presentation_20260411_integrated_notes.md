# Fake News Checker Integrated Presentation Notes

- generated_on: 2026-04-11
- dataset: testdata\shared\real_article_dataset_v2.json
- legacy_ver2_eval: Ver2\evaluation_outputs\20260401-1213\eval_real_v2_use_gemini_after_rule_tune4.json
- current_ver2_eval: Ver2\evaluation_outputs\20260411-0509\eval_real_article_dataset_v2_use_gemini.json

## Slide 1
- 20260401 本編資料の統合版であることを表紙で明示する。

## Slide 2
- 社会背景と個人的動機は元の本編資料を維持し、課題意識を先に共有する。

## Slide 3
- dataset v2 は 100件、5区分は各20件で balanced。
- ドメイン分布は 一般75 / 医療5 / 金融2 / 災害2 / 政治16。

## Slide 4
- 初期仮説・分析アプローチは元資料の構成を保ち、ローカル一次判定と Gemini 比較の流れを説明する。

## Slide 5
- UI の実行例として、入力 -> 判定中 -> 結果表示 の 3 ステップをスクリーンショットで示す。

## Slide 6
- 出力例では、要注意度・判定・理由がどのように返るかを説明する。

## Slide 7
- 初期版は accuracy 0.370 / macro F1 0.266 / 誤り recall 0.000。
- 最新版は accuracy 0.840 / macro F1 0.837 / 誤り recall 0.800。
- 改善が大きかったことをこのスライドで強く伝える。

## Slide 8
- 最新版の主な誤分類は ほぼ正確 -> 正確: 6件, 正確 -> ほぼ正確: 4件, 誤り -> 不正確: 4件, ほぼ正確 -> 不正確: 2件。
- ほぼ正確の境界と、誤りを不正確へ落とすケースが残課題。

## Slide 9
- 精度 84% まで来たことで、説明付き確認支援ツールとしての実用性が高まったと話す。

## Slide 10
- shared dataset 集約、5 plots、CSV/XLSX bundle 化など運用面の工夫を説明する。

## Slide 11
- 次の改善テーマは 誤り -> 不正確 の圧縮と、ほぼ正確の境界調整。

## Slide 12
- summary_metrics.png では Accuracy 0.840、Binary F1 0.889 を確認する。

## Slide 13
- per_class_metrics.png では ほぼ正確 recall 0.600 が弱点であることを確認する。

## Slide 14
- confusion_matrix.png では ほぼ正確 -> 正確 6件、誤り -> 不正確 4件に注目する。

## Slide 15
- evaluation_overview.png では mismatches 16件、sample_count 100、skipped 0 を確認する。

## Slide 16-19
- 最後は参考資料として図を単独表示し、質疑応答で使えるようにする。
