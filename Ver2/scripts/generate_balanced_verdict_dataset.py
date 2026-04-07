import json
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REAL_DATASET_PATH = ROOT / "testdata" / "real_article_dataset.json"

VERDICTS = [
    "正確",
    "ほぼ正確",
    "判断保留",
    "不正確",
    "誤り",
]
LEGACY_TO_CURRENT_VERDICT = {
    "信頼できる": "正確",
    "おおむね正確": "ほぼ正確",
    "どちらとも言えない": "判断保留",
    "未確認": "判断保留",
    "注意が必要": "不正確",
    "高確率でフェイク": "誤り",
}


def make_case(
    case_id: str,
    title: str,
    site_name: str,
    purpose: str,
    analysis_text: str,
    verdict: str,
    domain: str,
    source_url: str | None,
    snapshot_overrides: dict | None = None,
) -> dict:
    case = {
        "id": case_id,
        "title": title,
        "site_name": site_name,
        "purpose": purpose,
        "analysis_text": analysis_text,
        "expected": {
            "verdict": verdict,
            "domain": domain,
        },
    }
    if source_url:
        case["source_url"] = source_url
    if snapshot_overrides:
        case["snapshot_overrides"] = snapshot_overrides
    return case


def select_real_cases(real_cases: list[dict], verdict: str, count: int, prefix: str) -> list[dict]:
    selected = [
        case
        for case in real_cases
        if LEGACY_TO_CURRENT_VERDICT.get(case.get("expected", {}).get("verdict"), case.get("expected", {}).get("verdict"))
        == verdict
    ][:count]
    if len(selected) != count:
        raise ValueError(f"Expected {count} real cases for {verdict}, got {len(selected)}")

    cloned: list[dict] = []
    for index, case in enumerate(selected, start=1):
        item = deepcopy(case)
        item["id"] = f"balanced-{prefix}-{index:02d}-{case['id']}"
        item["expected"]["verdict"] = verdict
        cloned.append(item)
    return cloned


def build_gray_cases() -> list[dict]:
    topics = [
        {
            "prefix": "gray-health-supplement",
            "site_name": "健康トレンド通信",
            "domain": "医療",
            "source_url": "https://claims.example/gray/health-supplement",
            "claim": "新しい睡眠サプリが慢性的な不眠を改善する",
            "basis": "小規模モニターと利用者アンケート",
            "gap": "対照群付き試験や長期追跡データはそろっていない",
        },
        {
            "prefix": "gray-rates-next-meeting",
            "site_name": "マーケット観測ノート",
            "domain": "金融",
            "source_url": "https://claims.example/gray/rates-next-meeting",
            "claim": "次回会合で追加利上げが見送られる",
            "basis": "市場関係者の聞き取りと一部アナリスト予想",
            "gap": "公表資料や決定文はまだ出ていない",
        },
        {
            "prefix": "gray-rent-redevelopment",
            "site_name": "都市生活レビュー",
            "domain": "一般",
            "source_url": "https://claims.example/gray/rent-redevelopment",
            "claim": "駅前再開発で周辺家賃が下がる",
            "basis": "一部不動産会社の見通しと限定的な募集事例",
            "gap": "地域全体の統計と他要因の切り分けは不十分だ",
        },
        {
            "prefix": "gray-school-tablet-score",
            "site_name": "教育データ観測",
            "domain": "一般",
            "source_url": "https://claims.example/gray/school-tablet-score",
            "claim": "学校のタブレット導入で学力が上がった",
            "basis": "一部自治体の速報値と担当者コメント",
            "gap": "学年差や補習施策など他の要因が整理されていない",
        },
        {
            "prefix": "gray-rainwater-bacteria",
            "site_name": "地域ニュース検証メモ",
            "domain": "災害",
            "source_url": "https://claims.example/gray/rainwater-bacteria",
            "claim": "豪雨後の断水地域で体調不良が増えたのは給水タンク由来の細菌が原因だ",
            "basis": "住民報告と一部検査メモ",
            "gap": "保健所の確定公表や因果関係の整理はまだ出ていない",
        },
    ]
    patterns = [
        {
            "suffix": "survey-signal",
            "title": "{claim}とする小規模データが出ている",
            "text": "{site_name}は、{claim}と伝えるが、根拠は{basis}にとどまり、{gap}。現時点では結論を急げない。",
        },
        {
            "suffix": "experts-split",
            "title": "{claim}との見方はあるが専門家評価は割れている",
            "text": "{site_name}は、{claim}との見方を紹介している。ただし材料は{basis}が中心で、{gap}ため、評価は分かれている。",
        },
        {
            "suffix": "preliminary-only",
            "title": "{claim}という速報はあるが確定材料が足りない",
            "text": "{site_name}によれば、{claim}可能性が示唆されているが、現段階の材料は{basis}に偏っている。{gap}ため、追加確認が必要だ。",
        },
        {
            "suffix": "mixed-signals",
            "title": "{claim}を示す材料と否定材料が混在している",
            "text": "{site_name}は、{claim}と見る材料を挙げる一方で、反対の材料も残っている。主な根拠は{basis}で、{gap}。",
        },
        {
            "suffix": "causation-unclear",
            "title": "{claim}と言い切るには因果関係が不明確",
            "text": "{site_name}は、{claim}と示唆するが、今のところ確認できるのは{basis}までだ。{gap}ため、断定は難しい。",
        },
    ]
    cases: list[dict] = []
    for topic in topics:
        for index, pattern in enumerate(patterns, start=1):
            cases.append(
                make_case(
                    case_id=f"{topic['prefix']}-{index:02d}",
                    title=pattern["title"].format(**topic),
                    site_name=topic["site_name"],
                    purpose="5区分評価用の追加確認ケース",
                    analysis_text=pattern["text"].format(**topic),
                    verdict="判断保留",
                    domain=topic["domain"],
                    source_url=topic["source_url"],
                    snapshot_overrides={
                        "has_author": index % 2 == 1,
                        "has_published_at": True,
                        "reference_link_count": 1,
                        "extraction_score": 67,
                    },
                )
            )
    return cases


def build_caution_cases() -> list[dict]:
    topics = [
        {
            "prefix": "caution-fever-event",
            "site_name": "速報まとめライン",
            "domain": "医療",
            "source_url": "https://claims.example/caution/fever-event",
            "claim": "市内の発熱患者増加は週末イベントが原因だ",
            "partial_basis": "一部病院の混雑とSNS上の参加報告",
            "missing": "検査結果や保健所の因果確認がない",
        },
        {
            "prefix": "caution-old-flood-photo",
            "site_name": "災害共有ネット",
            "domain": "災害",
            "source_url": "https://claims.example/caution/old-flood-photo",
            "claim": "古い浸水写真を今回の洪水被害だとして使い、被害が全域に広がったと示す",
            "partial_basis": "写真自体は実在する災害記録",
            "missing": "撮影時期と今回の地域との対応づけが欠けている",
        },
        {
            "prefix": "caution-price-double",
            "site_name": "家計ウォッチ速報",
            "domain": "一般",
            "source_url": "https://claims.example/caution/price-double",
            "claim": "一部商品の値上がりを根拠に来月は生活費が全国で倍になると断定する",
            "partial_basis": "特定店舗の価格改定と家計アンケートの一部回答",
            "missing": "全国統計や品目別の差を無視している",
        },
        {
            "prefix": "caution-company-default",
            "site_name": "企業噂レポート",
            "domain": "金融",
            "source_url": "https://claims.example/caution/company-default",
            "claim": "単年度赤字だけで大手企業の破綻が確定したかのように伝える",
            "partial_basis": "決算短信の一部数値",
            "missing": "資金繰りや支援策など継続企業情報の文脈が抜けている",
        },
        {
            "prefix": "caution-small-study-cure",
            "site_name": "ヘルス話題便",
            "domain": "医療",
            "source_url": "https://claims.example/caution/small-study-cure",
            "claim": "小規模研究を根拠に特定食品が感染症を予防すると広く言い切る",
            "partial_basis": "対象数の少ない観察研究",
            "missing": "再現研究や公的ガイドラインとの整合が確認されていない",
        },
    ]
    patterns = [
        {
            "suffix": "overclaim",
            "title": "{claim}",
            "text": "{site_name}は、{claim}。ただし根拠は{partial_basis}に偏っており、{missing}。",
        },
        {
            "suffix": "context-drop",
            "title": "文脈を落として{claim}",
            "text": "{site_name}は、{partial_basis}をもとに{claim}と示すが、{missing}ため受け取りに注意がいる。",
        },
        {
            "suffix": "causal-leap",
            "title": "{partial_basis}だけで{claim}と結論づけている",
            "text": "{site_name}では、{partial_basis}を主な根拠として{claim}と結びつけている。しかし{missing}。",
        },
        {
            "suffix": "headline-push",
            "title": "見出しでは{claim}と強く押し出している",
            "text": "{site_name}のまとめは{claim}と強く打ち出すが、本文で示される材料は{partial_basis}程度で、{missing}。",
        },
        {
            "suffix": "selective-facts",
            "title": "限定的な事実だけを拾って{claim}",
            "text": "{site_name}は、{partial_basis}のような限定的事実を拾い、{claim}と読める形で伝える。{missing}。",
        },
    ]
    cases: list[dict] = []
    for topic in topics:
        for index, pattern in enumerate(patterns, start=1):
            cases.append(
                make_case(
                    case_id=f"{topic['prefix']}-{index:02d}",
                    title=pattern["title"].format(**topic),
                    site_name=topic["site_name"],
                    purpose="5区分評価用の文脈不足ケース",
                    analysis_text=pattern["text"].format(**topic),
                    verdict="不正確",
                    domain=topic["domain"],
                    source_url=topic["source_url"],
                    snapshot_overrides={
                        "has_author": index in {1, 3},
                        "has_published_at": True,
                        "reference_link_count": 0,
                        "extraction_score": 63,
                    },
                )
            )
    return cases


def build_fake_cases() -> list[dict]:
    topics = [
        {
            "prefix": "fake-vaccine-chip",
            "site_name": "匿名SNS投稿",
            "domain": "医療",
            "source_url": "https://claims.example/fake/vaccine-chip",
            "claim": "新型コロナワクチンには追跡用のマイクロチップが入っている",
            "evidence": "接種券の番号とぼやけた拡大画像",
        },
        {
            "prefix": "fake-bleach-cure",
            "site_name": "民間療法チャンネル",
            "domain": "医療",
            "source_url": "https://claims.example/fake/bleach-cure",
            "claim": "漂白剤を薄めて飲めば感染症を治療できる",
            "evidence": "個人の体験談と正体不明の表",
        },
        {
            "prefix": "fake-5g-virus",
            "site_name": "陰謀解説ブログ",
            "domain": "一般",
            "source_url": "https://claims.example/fake/5g-virus",
            "claim": "5G基地局がウイルスを発生させている",
            "evidence": "地図の重ね合わせ画像と匿名証言",
        },
        {
            "prefix": "fake-earthquake-cloud",
            "site_name": "予言観測クラブ",
            "domain": "災害",
            "source_url": "https://claims.example/fake/earthquake-cloud",
            "claim": "雲の形を見れば明日の大地震を正確に予測できる",
            "evidence": "過去写真のこじつけ比較",
        },
        {
            "prefix": "fake-secret-deposit-order",
            "site_name": "裏政治メモ",
            "domain": "金融",
            "source_url": "https://claims.example/fake/secret-deposit-order",
            "claim": "政府が来週から預金を強制没収する秘密命令を出した",
            "evidence": "出所不明の文書画像",
        },
    ]
    patterns = [
        {
            "suffix": "image-proof",
            "title": "{evidence}を根拠に{claim}",
            "text": "{site_name}は、{evidence}を証拠として、{claim}と断定している。",
        },
        {
            "suffix": "insider-proof",
            "title": "内部情報があるとして{claim}",
            "text": "{site_name}は、内部情報を知る人物がいるとして{claim}と主張している。示される材料は{evidence}だけだ。",
        },
        {
            "suffix": "video-proof",
            "title": "短い動画だけで{claim}",
            "text": "{site_name}は、短い動画と{evidence}をもとに、{claim}と広めている。",
        },
        {
            "suffix": "secret-plan",
            "title": "秘密計画が進んでいるとして{claim}",
            "text": "{site_name}は、秘密計画が進んでいるという前提で{claim}と書いている。根拠として並ぶのは{evidence}だ。",
        },
        {
            "suffix": "must-share",
            "title": "すぐ拡散すべきだとして{claim}",
            "text": "{site_name}は、周囲に知らせるべき重要情報だとして{claim}と訴える。裏付けとして示されるのは{evidence}に限られる。",
        },
    ]
    cases: list[dict] = []
    for topic in topics:
        for index, pattern in enumerate(patterns, start=1):
            cases.append(
                make_case(
                    case_id=f"{topic['prefix']}-{index:02d}",
                    title=pattern["title"].format(**topic),
                    site_name=topic["site_name"],
                    purpose="5区分評価用の高リスク誤情報ケース",
                    analysis_text=pattern["text"].format(**topic),
                    verdict="誤り",
                    domain=topic["domain"],
                    source_url=topic["source_url"],
                    snapshot_overrides={
                        "has_author": False,
                        "has_published_at": False,
                        "reference_link_count": 0,
                        "extraction_score": 55,
                    },
                )
            )
    return cases


def build_unconfirmed_cases() -> list[dict]:
    topics = [
        {
            "prefix": "unconfirmed-bank-atm",
            "site_name": "地域掲示板速報",
            "domain": "金融",
            "source_url": "https://claims.example/unconfirmed/bank-atm",
            "rumor": "明日から主要銀行のATMが全国停止する",
            "missing": "銀行の正式告知やシステム障害報告",
        },
        {
            "prefix": "unconfirmed-school-closure",
            "site_name": "保護者チャット共有",
            "domain": "一般",
            "source_url": "https://claims.example/unconfirmed/school-closure",
            "rumor": "市内全校が来週から一斉休校になる",
            "missing": "教育委員会の正式発表",
        },
        {
            "prefix": "unconfirmed-celebrity-death",
            "site_name": "トレンド速報板",
            "domain": "一般",
            "source_url": "https://claims.example/unconfirmed/celebrity-death",
            "rumor": "著名人が事故で死亡した",
            "missing": "本人事務所や主要報道機関の確認",
        },
        {
            "prefix": "unconfirmed-earthquake-warning",
            "site_name": "予兆ウォッチ速報",
            "domain": "災害",
            "source_url": "https://claims.example/unconfirmed/earthquake-warning",
            "rumor": "今夜中に特定地域で大地震が起きる",
            "missing": "気象庁など公的機関の確認",
        },
        {
            "prefix": "unconfirmed-hospital-cluster",
            "site_name": "医療メモ速報",
            "domain": "医療",
            "source_url": "https://claims.example/unconfirmed/hospital-cluster",
            "rumor": "県内病院で未知の感染クラスターが発生した",
            "missing": "保健所や病院の正式公表",
        },
    ]
    patterns = [
        {
            "suffix": "sns-spread",
            "title": "{rumor}という情報がSNSで広がっている",
            "text": "{site_name}では、{rumor}という情報がSNSで広がっていると紹介しているが、{missing}は確認できない。",
        },
        {
            "suffix": "chat-capture",
            "title": "チャット画像を根拠に{rumor}との話が出ている",
            "text": "{site_name}は、チャットのスクリーンショットをもとに{rumor}との話を載せている。ただし{missing}が見当たらない。",
        },
        {
            "suffix": "unnamed-source",
            "title": "匿名の関係者情報として{rumor}が語られている",
            "text": "{site_name}は、匿名の関係者談として{rumor}と伝えるが、{missing}が出ていない段階だ。",
        },
        {
            "suffix": "forwarded-message",
            "title": "転送メッセージ経由で{rumor}が拡散している",
            "text": "{site_name}では、転送メッセージを引用して{rumor}とする情報をまとめている。しかし{missing}はまだ確認できない。",
        },
        {
            "suffix": "voice-note",
            "title": "音声メモを根拠に{rumor}とささやかれている",
            "text": "{site_name}は、音声メモの内容から{rumor}との情報が出回っていると書いているが、{missing}が不足している。",
        },
    ]
    cases: list[dict] = []
    for topic in topics:
        for index, pattern in enumerate(patterns, start=1):
            cases.append(
                make_case(
                    case_id=f"{topic['prefix']}-{index:02d}",
                    title=pattern["title"].format(**topic),
                    site_name=topic["site_name"],
                    purpose="5区分評価用の根拠不足ケース",
                    analysis_text=pattern["text"].format(**topic),
                    verdict="判断保留",
                    domain=topic["domain"],
                    source_url=topic["source_url"],
                    snapshot_overrides={
                        "has_author": False,
                        "has_published_at": index in {1, 2},
                        "reference_link_count": 0,
                        "extraction_score": 58,
                    },
                )
            )
    return cases


def build_dataset() -> dict:
    current_payload = json.loads(REAL_DATASET_PATH.read_text(encoding="utf-8"))
    current_cases = current_payload.get("cases", [])

    current_distribution = {verdict: 0 for verdict in VERDICTS}
    for case in current_cases:
        verdict = case.get("expected", {}).get("verdict")
        if verdict in current_distribution:
            current_distribution[verdict] += 1

    expected_existing_distribution = {
        "正確": 20,
        "ほぼ正確": 20,
        "判断保留": 20,
        "不正確": 20,
        "誤り": 20,
    }
    if len(current_cases) == 100 and current_distribution == expected_existing_distribution:
        return current_payload

    real_cases = current_cases

    cases = []
    cases.extend(select_real_cases(real_cases, "正確", 20, "accurate"))
    cases.extend(select_real_cases(real_cases, "ほぼ正確", 20, "mostly"))
    cases.extend(build_gray_cases()[:20])
    cases.extend(build_caution_cases()[:20])
    cases.extend(build_fake_cases()[:20])

    if len(cases) != 100:
        raise ValueError(f"Expected 100 cases, got {len(cases)}")

    distribution = {verdict: 0 for verdict in VERDICTS}
    for case in cases:
        verdict = case["expected"]["verdict"]
        distribution[verdict] += 1

    expected_distribution = {
        "正確": 20,
        "ほぼ正確": 20,
        "判断保留": 20,
        "不正確": 20,
        "誤り": 20,
    }
    for verdict, count in distribution.items():
        if count != expected_distribution[verdict]:
            raise ValueError(f"Expected {expected_distribution[verdict]} cases for {verdict}, got {count}")

    return {
        "meta": {
            "name": "real_article_dataset_balanced100",
            "version": 1,
            "curated_on": "2026-03-29",
            "language": "ja",
            "description": "公開 verdict 5区分を評価するための 100 件データセットです。analysis_text は人手要約または評価用の中心命題で、元記事の全文転載ではありません。",
            "notes": [
                "この dataset は 5区分で合計100件です。内訳は 正確20 / ほぼ正確20 / 判断保留20 / 不正確20 / 誤り20 です。",
                "正確 / ほぼ正確 は既存の実在記事ベース要約から選抜したケースです。",
                "判断保留 / 不正確 / 誤り は verdict 境界の評価用に整えた curated case です。",
                "判定対象は analysis_text の中心命題です。",
            ],
            "verdict_distribution": distribution,
        },
        "cases": cases,
    }


def main() -> int:
    payload = build_dataset()
    REAL_DATASET_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
