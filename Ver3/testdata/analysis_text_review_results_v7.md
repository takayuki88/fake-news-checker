# analysis_text Review Results (v7)

- Reviewer: Codex
- Date: 2026-03-31
- Dataset version: 7
- Scope: `real_article_dataset.json` 100件を [analysis_text_review_checklist.md](./analysis_text_review_checklist.md) に沿って順番に点検

## Summary

- `OK`: 27件
- `軽微修正`: 13件
- `要修正`: 60件
- 所感: `正確` / `ほぼ正確` は中心命題に近いケースが比較的多い。一方で `判断保留` / `不正確` / `誤り` は「主張 + 反証説明」が混ざっており、`analysis_text` 単体で期待ラベルを引きやすい文になっていないケースが多い。

## 001-025

- `[001]` `positive-accurate-01-nhk-broadcasts-200-human-sacrifices` | `正確` | `軽微修正` | 前半の「拡散した」が背景。後半の「NHK番組映像である」に絞ると中心命題が明確。
- `[002]` `positive-accurate-02-why-not-in-the-news-shizuoka-flood-images-are-real` | `正確` | `軽微修正` | 「AI画像など真偽不明情報も混じる」が周辺説明。3枚の画像が実際の浸水被害だという命題に寄せたい。
- `[003]` `positive-accurate-03-aaa-com-article-accurate-koizumi-warns-typhoon` | `正確` | `軽微修正` | 「偽物ではないかという指摘が広がった」が背景。公式配信の実動画という核命題に絞れる。
- `[004]` `positive-accurate-04-wasegg210726-2` | `正確` | `OK` | 条件付きの事実命題としてまとまっている。
- `[005]` `positive-accurate-05-jid211030-2` | `正確` | `OK` | 数値と時系列が残っており、文単体で判定しやすい。
- `[006]` `positive-accurate-06-wasegg220314-8` | `正確` | `OK` | 対象時点と対象ページが明確で、中心命題として十分。
- `[007]` `positive-accurate-07-infact220706` | `正確` | `OK` | 主語・条件・母数が残っていて判定対象文としてよい。
- `[008]` `positive-accurate-08-jid220707` | `正確` | `OK` | ユーザー想定どおり、中心命題と必要条件が揃っている。
- `[009]` `positive-accurate-09-infact220821` | `正確` | `OK` | 法令の何が事実かが直接書かれている。
- `[010]` `positive-accurate-10-wasegg220709-2` | `正確` | `OK` | 比較対象を含むシンプルな事実命題になっている。
- `[011]` `positive-accurate-11-litmus221003` | `正確` | `軽微修正` | 後半の「ネット上では混同」が周辺説明。前半の財務省検討の事実に絞るほうがよい。
- `[012]` `positive-accurate-12-mainichi230505` | `正確` | `軽微修正` | 「この写真」がやや曖昧。対象写真を明示すると判定しやすい。
- `[013]` `positive-accurate-13-litmus230706` | `正確` | `OK` | 企業確認という事実命題にまとまっている。
- `[014]` `positive-accurate-14-post-23899` | `正確` | `OK` | 発言内容と確認結果が直接つながっている。
- `[015]` `positive-accurate-15-japan-experimental-forestry` | `正確` | `OK` | 拡散対象と実在確認が短くまとまっている。
- `[016]` `positive-accurate-16-japanese-robotic-monster-wolves` | `正確` | `OK` | 実在性の中心命題として十分。
- `[017]` `positive-accurate-17-toyota-city-japan-name` | `正確` | `OK` | 主語と因果が簡潔で明確。
- `[018]` `positive-accurate-18-square-watermelon` | `正確` | `OK` | 単体で正確判定しやすい。
- `[019]` `positive-accurate-19-ronald-mcdonald-name-japan` | `正確` | `OK` | 主張と理由が短くまとまっている。
- `[020]` `positive-accurate-20-photos-japan-orca` | `正確` | `軽微修正` | 前半の「写真が拡散した」は背景。実写真である点を主文にしたい。
- `[021]` `positive-mostly-accurate-01-ainu-dance-filmed-1919` | `ほぼ正確` | `軽微修正` | 1文目の「拡散した」は背景。実写だがカラー化に補足が要る、に寄せたい。
- `[022]` `positive-mostly-accurate-02-real-image-of-jovial-swedish-people-despite-train-station-flooding-caused-by-typhoon` | `ほぼ正確` | `軽微修正` | 背景説明が長い。本物画像だが前提補足が要る、に絞れる。
- `[023]` `positive-mostly-accurate-03-almost-accurate-claim-iaea-not-verifying-filtration-performance-of-contaminated-water` | `ほぼ正確` | `軽微修正` | 「言説が拡散した」が背景。IAEAが直接検証していない点と安全性調査はした点の対比に絞りたい。
- `[024]` `positive-mostly-accurate-04-infact200912` | `ほぼ正確` | `要修正` | 「その点は不正確」が判定文そのもの。対象命題をメタ評価抜きで書き直す必要がある。
- `[025]` `positive-mostly-accurate-05-infact211023-3` | `ほぼ正確` | `OK` | 相違点と不確定部分が残っており、ほぼ正確の命題として機能する。

## 026-050

- `[026]` `positive-mostly-accurate-06-jid211024-1` | `ほぼ正確` | `OK` | 最新データとの差を示す中心命題として読める。
- `[027]` `positive-mostly-accurate-07-jid211029-01` | `ほぼ正確` | `OK` | 複数要素はあるが、どこが大筋正しくどこに補足が要るかが読める。
- `[028]` `positive-mostly-accurate-08-asahi211116-2` | `ほぼ正確` | `OK` | 賞の対象と人物関係が明確。
- `[029]` `positive-mostly-accurate-09-infact211217-1` | `ほぼ正確` | `OK` | 数値と比較対象が具体的で、判定対象文として十分。
- `[030]` `positive-mostly-accurate-10-infact220704` | `ほぼ正確` | `OK` | 言い間違いと実数値の関係が整理されている。
- `[031]` `positive-mostly-accurate-11-infact220706-2` | `ほぼ正確` | `OK` | 発言内容の確認命題としてシンプル。
- `[032]` `positive-mostly-accurate-12-infact220708` | `ほぼ正確` | `OK` | 可能性付きの法的評価として妥当。
- `[033]` `positive-mostly-accurate-13-infact220823` | `ほぼ正確` | `要修正` | 末尾の「ほぼ正確だ」が判定文。制度比較の命題だけに整理したい。
- `[034]` `positive-mostly-accurate-14-bfj230313` | `ほぼ正確` | `OK` | 数と呼称の中心命題としてそのまま使える。
- `[035]` `positive-mostly-accurate-15-post-22724` | `ほぼ正確` | `要修正` | 「拡散している」「確認した」が記事説明。ファウチ発言の中身を判定対象文にすべき。
- `[036]` `positive-mostly-accurate-16-post-22836` | `ほぼ正確` | `OK` | 発言命題として単体で読める。
- `[037]` `positive-mostly-accurate-17-23435` | `ほぼ正確` | `要修正` | 「情報が拡散」「その内容をファクトチェック」が説明文。安楽死可否の中心命題に絞る必要がある。
- `[038]` `positive-mostly-accurate-18-kobe-pension-standardly-nontaxable` | `ほぼ正確` | `OK` | 多数派だが全員ではない、というほぼ正確の核が書けている。
- `[039]` `positive-mostly-accurate-19-japanese-electric-car-200km-single-charge` | `ほぼ正確` | `OK` | 条件付きの真を適切に表現できている。
- `[040]` `positive-mostly-accurate-20-blobfish-natural-environment` | `ほぼ正確` | `OK` | 条件差を含む命題として素直。
- `[041]` `jfc-hold-01-yokohama-team-mirai-election-fraud-unfounded` | `判断保留` | `要修正` | 後半が反証説明に寄っており、文単体では `誤り/不正確` に見えやすい。保留理由中心に直したい。
- `[042]` `jfc-hold-02-baseless-healthworkers-mynahokensho` | `判断保留` | `要修正` | 「根拠資料で示されていない」に加えて反対方向のアンケート結果まで入っており、保留より反証に寄る。
- `[043]` `jfc-hold-03-baseless-trump-said-all-hell-break-loose` | `判断保留` | `軽微修正` | 日時付きで未確認という保留理由はある。前半の「拡散している」を省くとよりよい。
- `[044]` `jfc-hold-04-baseless-jal123-fake-voice-recorder` | `判断保留` | `要修正` | 主張紹介だけで保留理由が弱い。何が確認不能かを中心命題にしたい。
- `[045]` `jfc-hold-05-baseless-solar-panels-not-covered-by-fire-insurance` | `判断保留` | `要修正` | 大手3社の説明まで入ると保留ではなく反証寄り。保留ラベルと自然判定がズレる。
- `[046]` `jfc-hold-06-baseless-ohtani-said-illegal-immigrants-should-leave` | `判断保留` | `要修正` | パロディアカウントと未確認情報が入り、単体では `誤り` に見えやすい。
- `[047]` `jfc-hold-07-baseless-whale-sardine-beach-earthquake` | `判断保留` | `要修正` | 「データはありません」まで入ると保留より否定に寄る。保留の中心命題にし直したい。
- `[048]` `jfc-hold-08-false-claim-korean-massacre-6000-lie` | `判断保留` | `要修正` | 被害者数には幅がある、という保留論点よりも、反証説明が前に出ている。
- `[049]` `jfc-hold-09-baseless-uniqlo-china-factory-exit` | `判断保留` | `要修正` | 後半がかなり具体的な反証で、自然には `不正確/誤り` に見える。
- `[050]` `jfc-hold-10-kanagawa-10000-invalid-votes-fraud-claim` | `判断保留` | `要修正` | 選管コメントまで入ると保留より否定に寄る。

## 051-075

- `[051]` `jfc-hold-11-baseless-exposition-pneumonia-class-closure` | `判断保留` | `要修正` | 「殺虫剤にレジオネラ菌は含まれていない」は強い反証。保留ラベルと噛み合っていない。
- `[052]` `jfc-hold-12-baseless-trump-said-he-will-save-japanese-citizens` | `判断保留` | `要修正` | 「発表はありません」まで入ると保留より否定に寄る。
- `[053]` `jfc-hold-13-baseless_nankai_trough_earthquake_aug14` | `判断保留` | `要修正` | 地震発生と投稿拡散の説明で終わっており、保留理由が `analysis_text` に出ていない。
- `[054]` `jfc-hold-14-saga-invalid-votes-fraud-claim-unfounded` | `判断保留` | `要修正` | 選管の否定コメントが入っており、単体では保留より否定判定に寄る。
- `[055]` `jfc-hold-15-baseless-fanta-orange-1970-additives` | `判断保留` | `要修正` | 表示ルールの説明まで入ると、保留よりも主張の不正確さを説明する文になっている。
- `[056]` `jfc-hold-16-no-evidence-a-sign-made-by-chinese-people` | `判断保留` | `軽微修正` | 「証拠はありません」が保留理由になっている。前半の背景を削れば基準に近づく。
- `[057]` `jfc-hold-17-baseless-koike-google-personal-data` | `判断保留` | `要修正` | 後半で都の説明まで入っており、自然には反証寄り。
- `[058]` `jfc-hold-18-mhlw-staff-vaccination-rate-uncertain` | `判断保留` | `要修正` | 厚労省が「事実ではない」と答えており、保留より否定文になっている。
- `[059]` `jfc-hold-19-baseless-xi-jinping-fell-from-chair` | `判断保留` | `要修正` | 主張紹介だけで保留理由がなく、単体判定できない。
- `[060]` `jfc-hold-20-baseless-mynaportal-major-cut-in-administrative-costs-for-benefits` | `判断保留` | `要修正` | 自治体コメントまで入ると不正確寄りの文になる。
- `[061]` `jfc-inaccurate-01-politicians-zero-inheritance-tax` | `不正確` | `要修正` | 「一般と同じように相続税がかかる」と言い切っており、中心命題ではなく訂正文が混ざる。
- `[062]` `jfc-inaccurate-02-did-it-take-only-four-months-for-the-takaichi-administration-to-reach-the-mining-stage` | `不正確` | `要修正` | 投稿紹介 + 研究経緯説明になっている。誇張されている元主張だけを残したい。
- `[063]` `jfc-inaccurate-03-japan-is-not-expanding-the-pakistani-intake-to-50thousands` | `不正確` | `要修正` | 現文は「発信も報道もない」と強く否定しており、自然には `誤り` に寄る。
- `[064]` `jfc-inaccurate-04-inaccurate-kyoto-hotel-prices-collapse` | `不正確` | `要修正` | 暴落主張と価格推移説明が混ざる。中心命題を「暴落している」に寄せるべき。
- `[065]` `jfc-inaccurate-05-inaccurate-gates-abondons-climate-action` | `不正確` | `要修正` | 訂正文が長く、単体では `誤り` と読みやすい。撤退したかのような主張に絞りたい。
- `[066]` `jfc-inaccurate-06-inaccurate-trump-administration-admits-covid-shots-are-crime-against-humanity` | `不正確` | `要修正` | 一部事実 + 否定の構成で、記事説明のまま。
- `[067]` `jfc-inaccurate-07-inaccurate-favoratism-toward-chinese-students` | `不正確` | `要修正` | 誇張主張に対し統計反証が混ざる。主張そのものへ寄せたい。
- `[068]` `jfc-inaccurate-08-inaccurate-foreigners-obtain-the-national-certification-for-care-workers` | `不正確` | `要修正` | 「日本人にも適用」が説明文。対象命題は特例が外国人だけにあるという誤解。
- `[069]` `jfc-inaccurate-09-inaccurate-claim-ministry-of-economy-trade-and-industry-did-not-state-they-did-not-measure-9-nuclides-other-than-tritium` | `不正確` | `要修正` | 長い説明文で、どの部分が不正確かが主張文として抽出されていない。
- `[070]` `jfc-inaccurate-10-inaccurate-kurdish-group-tv-report` | `不正確` | `要修正` | 「反論部分がカット」が説明文。元の切り取り主張を中心にしたい。
- `[071]` `jfc-inaccurate-11-inaccurate-volunteer-recruitment-n-noto-peninsula-earthquake` | `不正確` | `要修正` | 主張紹介だけで、どこが不正確かが `analysis_text` に出ていない。
- `[072]` `jfc-inaccurate-12-matsumoto-chief-cabinet-secretary-great-kanto-earthquake-korean-massacre-records-inaccurate` | `不正確` | `要修正` | 官房長官発言と政府資料説明が混ざる。中心命題を発言内容側に寄せるべき。
- `[073]` `jfc-inaccurate-13-ohio-train-derailment-disaster-hidden-reporter-arrested-false` | `不正確` | `要修正` | 「事故が起きて記者が逮捕された。隠ぺいか」という流れで、判定対象文として未整理。
- `[074]` `jfc-inaccurate-14-inaccurate-video-of-transgender-martial-artist-breaking-opponents-skull` | `不正確` | `軽微修正` | 不正確な部分は読み取れるが、動画説明を少し削って「この試合で頭蓋骨骨折」は不正確に寄せたい。
- `[075]` `jfc-inaccurate-15-inaccurate-claims-about-drone-delivery` | `不正確` | `要修正` | 文法が崩れているうえ、訂正説明が混ざっている。

## 076-100

- `[076]` `jfc-inaccurate-16-inaccuracies-in-keio-baseball-cheering` | `不正確` | `要修正` | 「単位が取得できる」という主張と実際の運用説明が混在している。
- `[077]` `jfc-inaccurate-17-japan-iran-visa-indefinite-extension` | `不正確` | `要修正` | 「無期限延長ではない」と説明しており、中心命題抽出になっていない。
- `[078]` `jfc-inaccurate-18-ion-stores-atm-credit-card-inaccessibility-inaccurate` | `不正確` | `要修正` | 「内容。」で文が崩れている。加えて説明文が混ざる。
- `[079]` `jfc-inaccurate-19-factcheck-us-department-of-state-officially-declared-islam-a-threat` | `不正確` | `要修正` | 「イスラム過激派」と「イスラム教全体」の違いを説明する文で、中心命題は別にある。
- `[080]` `jfc-inaccurate-20-inaccurate-9000yen-to-a-muslims-school-lunch` | `不正確` | `要修正` | 対象限定の誤りを説明しており、誤解を招く元主張に絞りたい。
- `[081]` `jfc-false-01-trump-im-the-last-to-use-nukes` | `誤り` | `要修正` | 誤訳説明まで混ざる。偽の発言主張そのものを `analysis_text` にすべき。
- `[082]` `jfc-false-02-did-noda-yoshihiko-said-spy-prevention-law-would-violate-spies-human-rights` | `誤り` | `要修正` | 後半の「記録は確認できず」が訂正文。誤発言主張だけに絞る必要がある。
- `[083]` `jfc-false-03-chemtrail-government-airborne-dispersion-harmful-substances-false` | `誤り` | `要修正` | 説明と反証が混ざり、文末も崩れている。ケムトレイル主張そのものに寄せたい。
- `[084]` `jfc-false-04-japans-inflation-rate-is-not-the-highest` | `誤り` | `要修正` | IMF/OECD説明が入っており、単体では反証付き文章になっている。
- `[085]` `jfc-false-05-japan-does-not-have-any-anti-islamic-legislation` | `誤り` | `要修正` | 法制度説明が訂正文として混ざる。反イスラム法が制定されたという主張に絞るべき。
- `[086]` `jfc-false-06-pfizer-didnt-admit-covid-jab-causes-cancer` | `誤り` | `要修正` | インタビュー内容の説明が混ざる。誤主張そのものへ寄せたい。
- `[087]` `jfc-false-07-false-aomori-earthquake-artificial` | `誤り` | `軽微修正` | 人工地震示唆という偽主張は読める。地震発生の背景を少し削るとより明確。
- `[088]` `jfc-false-08-kawaguchi-arrest-foreign-national-ratio` | `誤り` | `要修正` | 後半の「誤って解釈しています」が訂正文。ユーザーが指摘した通り、誤主張だけを残したい。
- `[089]` `jfc-false-09-false-dog-elevator-ai-video` | `誤り` | `要修正` | 「現実の映像ではなく。」で文が途切れており、反証も混ざる。
- `[090]` `jfc-false-10-false-lee-jaemyung-setagaya-comment` | `誤り` | `要修正` | 末尾の「そのような発言はありません」が訂正文。偽発言主張に絞るべき。
- `[091]` `jfc-false-11-false-hometown-africa-nagai-visa` | `誤り` | `要修正` | 「交流強化を目指すものですが...」が訂正文。偽主張部分だけにしたい。
- `[092]` `jfc-false-12-false-celebrity-death-hoaxes-youtube` | `誤り` | `要修正` | 「死亡したという情報は。」で文が途切れているうえ、訂正文が混ざる。
- `[093]` `jfc-false-13-false-koizumi-radiated-soil-video` | `誤り` | `要修正` | 閣議決定の説明が混ざる。動画題名の主張を中心命題に寄せる必要がある。
- `[094]` `jfc-false-14-false-asahi-ceremony-flags` | `誤り` | `要修正` | 「実際の画像を改変」が訂正文。改変前の偽主張を単体化したい。
- `[095]` `jfc-false-15-false-100k-demo-osaka-yoon` | `誤り` | `要修正` | 実参加者数などの反証説明が混ざる。主張だけに絞るべき。
- `[096]` `jfc-false-16-false-minimum-access-rice-harmful` | `誤り` | `要修正` | 安全検査説明が混ざる。危険だという主張を判定対象文にしたい。
- `[097]` `jfc-false-17-false-hokkaido-ainu-not-jomon` | `誤り` | `要修正` | 政府や国連の認定説明が訂正文。誤主張そのものへ寄せたい。
- `[098]` `jfc-false-18-false-planet-alignment-over-pyramid-every-2373` | `誤り` | `要修正` | 合成画像説明と文末の途切れがある。元の偽主張に絞るべき。
- `[099]` `jfc-false-19-former-ukrainian-commander-zarzhinyi-53-million-dollar-retirement-bbc` | `誤り` | `要修正` | BBC否定説明が混ざる。退職金報道主張だけに寄せたい。
- `[100]` `jfc-false-20-false-epstein-emperor-ai-photo` | `誤り` | `要修正` | 「捏造されたもので。」が訂正文かつ文末が崩れている。誤画像主張だけを残したい。

## Next Focus

- まずは `要修正` 60件を直す
- 次に `軽微修正` 13件をトリミングして、背景文を落とす
- 特に `判断保留` / `不正確` / `誤り` は、`主張 + 訂正文` の混在を解消する
