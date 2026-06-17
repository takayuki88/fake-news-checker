# 評価サマリー

## 評価条件

Ver4の評価では、5ラベル各20件、合計100件のbalanced datasetを使用しました。

- dataset: `testdata/shared/real_article_dataset_v2.json`
- evaluation result: `evaluation_outputs/20260427-0304/eval_real_article_dataset_v2_use_gpt_gemini.json`
- model setting: GPT一次レビュー + Gemini外部根拠確認

## 主要指標

| 指標 | 結果 |
| --- | ---: |
| sample count | 100 |
| accuracy | 0.9000 |
| macro F1 | 0.8989 |
| weighted F1 | 0.8989 |
| mismatches | 10 |

## ラベル別の傾向

| ラベル | Precision | Recall | F1 | Support |
| --- | ---: | ---: | ---: | ---: |
| 正確 | 0.8333 | 1.0000 | 0.9091 | 20 |
| ほぼ正確 | 0.8824 | 0.7500 | 0.8108 | 20 |
| 判断保留 | 1.0000 | 0.9500 | 0.9744 | 20 |
| 不正確 | 0.8500 | 0.8500 | 0.8500 | 20 |
| 誤り | 0.9500 | 0.9500 | 0.9500 | 20 |

## 考察

明確な正誤や判断保留は比較的安定しました。
一方で、誤分類は「正確」「ほぼ正確」「不正確」の境界に集中しました。

この結果から、今後は固有名詞ごとの個別パッチではなく、どの差分を「ほぼ正確」とし、どの差分を「不正確」とするかを構造化することが重要だと考えています。

## 次の検証方針

- 既存100件はdevデータとして、改善による既存性能の変化を見る
- 新規blind test 100件を作成し、未知データでの性能を見る
- Ver2 / Ver3 / Ver4を同じblind setで比較する
