# 2026-04-10 Rerun Comparison

対象データセット:
- `Ver4/testdata/real_article_dataset_v2.json`

注記:
- 下記の `latest` は 2026-04-10 にローカル作業ツリー上で再実行した bundle
- この時点では未 push のローカル変更を含む

## Summary

| Version | Previous run | Accuracy | Macro F1 | False recall | Latest run | Accuracy | Macro F1 | False recall | Accuracy diff | Macro F1 diff | False recall diff |
| --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Ver2 | `20260410-1016` | 0.6300 | 0.6314 | 0.3500 | `20260410-1126` | 0.6300 | 0.6256 | 0.4500 | +0.0000 | -0.0058 | +0.1000 |
| Ver3 | `20260410-1043` | 0.4900 | 0.5003 | 0.4000 | `20260410-1130` | 0.5500 | 0.5605 | 0.5000 | +0.0600 | +0.0602 | +0.1000 |
| Ver4 | `20260410-1050` | 0.5300 | 0.5433 | 0.3000 | `20260410-1138` | 0.5000 | 0.5104 | 0.4500 | -0.0300 | -0.0329 | +0.1500 |

## Latest Cross-Version View

| Version | Run | Accuracy | Macro F1 | False precision | False recall | False row |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Ver2 | `20260410-1126` | 0.6300 | 0.6256 | 0.8182 | 0.4500 | `[0, 0, 0, 11, 9]` |
| Ver3 | `20260410-1130` | 0.5500 | 0.5605 | 0.4000 | 0.5000 | `[0, 0, 0, 10, 10]` |
| Ver4 | `20260410-1138` | 0.5000 | 0.5104 | 0.4091 | 0.4500 | `[0, 0, 0, 11, 9]` |

## False-Class Changes

### Ver2: `20260410-1016` -> `20260410-1126`

- `不正確 -> 誤り`
  - `jfc-false-02-did-noda-yoshihiko-said-spy-prevention-law-would-violate-spies-human-rights`
  - `jfc-false-09-false-dog-elevator-ai-video`
  - `jfc-false-11-false-hometown-africa-nagai-visa`
  - `jfc-false-18-false-planet-alignment-over-pyramid-every-2373`
- `誤り -> 不正確`
  - `jfc-false-01-trump-im-the-last-to-use-nukes`
  - `jfc-false-04-japans-inflation-rate-is-not-the-highest`

### Ver3: `20260410-1043` -> `20260410-1130`

- `不正確 -> 誤り`
  - `jfc-false-02-did-noda-yoshihiko-said-spy-prevention-law-would-violate-spies-human-rights`
  - `jfc-false-08-kawaguchi-arrest-foreign-national-ratio`
  - `jfc-false-11-false-hometown-africa-nagai-visa`
- `誤り -> 不正確`
  - `jfc-false-14-false-asahi-ceremony-flags`

### Ver4: `20260410-1050` -> `20260410-1138`

- `不正確 -> 誤り`
  - `jfc-false-02-did-noda-yoshihiko-said-spy-prevention-law-would-violate-spies-human-rights`
  - `jfc-false-14-false-asahi-ceremony-flags`
  - `jfc-false-18-false-planet-alignment-over-pyramid-every-2373`
- `判断保留 -> 不正確`
  - `jfc-false-10-false-lee-jaemyung-setagaya-comment`

## Current Takeaway

- 総合指標では引き続き `Ver2` が最良
- `誤り` recall は `Ver3` が 0.5000 で最良
- `Ver4` は総合指標を落とした一方で、`誤り` recall は 0.3000 -> 0.4500 まで改善
- 直近の helper 調整は、`誤り` 取りこぼし改善には効いている
- 次の主戦場は、`Ver2` の総合維持を保ちながら `Ver3` / `Ver4` の `ほぼ正確` と `不正確` の境界を崩さずに底上げすること
