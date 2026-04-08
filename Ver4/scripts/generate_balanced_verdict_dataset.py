import json
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REAL_DATASET_PATH = ROOT / "testdata" / "real_article_dataset.json"
POSITIVE_FACTCHECK_CASES_PATH = ROOT / "testdata" / "positive_factcheck_cases.json"
JFC_CURATED_CASES_PATH = ROOT / "testdata" / "jfc_curated_factcheck_cases.json"
DATASET_VERSION = 10
DATASET_CURATED_ON = "2026-03-31"

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
        expected_prefix = f"balanced-{prefix}-{index:02d}-"
        item["id"] = case["id"] if case["id"].startswith(expected_prefix) else f"{expected_prefix}{case['id']}"
        item["expected"]["verdict"] = verdict
        cloned.append(item)
    return cloned


def load_jfc_curated_cases() -> list[dict]:
    if not JFC_CURATED_CASES_PATH.exists():
        raise FileNotFoundError(
            f"JFC curated cases file not found: {JFC_CURATED_CASES_PATH}. "
            "Run scripts/fetch_jfc_curated_cases.py first."
        )

    payload = json.loads(JFC_CURATED_CASES_PATH.read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    distribution = {
        "判断保留": 0,
        "不正確": 0,
        "誤り": 0,
    }
    for case in cases:
        verdict = case.get("expected", {}).get("verdict")
        if verdict in distribution:
            distribution[verdict] += 1

    expected_distribution = {
        "判断保留": 20,
        "不正確": 20,
        "誤り": 20,
    }
    if distribution != expected_distribution:
        raise ValueError(f"Unexpected JFC curated distribution: {distribution}")

    return cases


def load_positive_factcheck_cases() -> list[dict]:
    if not POSITIVE_FACTCHECK_CASES_PATH.exists():
        raise FileNotFoundError(
            f"Positive fact-check cases file not found: {POSITIVE_FACTCHECK_CASES_PATH}. "
            "Run scripts/fetch_positive_factcheck_cases.py first."
        )

    payload = json.loads(POSITIVE_FACTCHECK_CASES_PATH.read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    distribution = {
        "正確": 0,
        "ほぼ正確": 0,
    }
    for case in cases:
        verdict = case.get("expected", {}).get("verdict")
        if verdict in distribution:
            distribution[verdict] += 1

    expected_distribution = {
        "正確": 20,
        "ほぼ正確": 20,
    }
    if distribution != expected_distribution:
        raise ValueError(f"Unexpected positive fact-check distribution: {distribution}")

    return cases


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
            "suffix": "limited-signal",
            "title": "{claim}という見方はあるが材料が細い",
            "text": "{site_name}では、{claim}という見方が紹介されている。ただ、支えになっているのは{basis}で、{gap}。現時点では裏付けが足りない。",
        },
        {
            "suffix": "hold-judgment",
            "title": "{claim}を裏づける決め手はまだ出ていない",
            "text": "{site_name}の記事は{claim}を示唆するが、確認できる材料は{basis}に寄っている。{gap}ため、今は判断を保留するのが妥当だ。",
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
            "suffix": "headline-gap",
            "title": "{claim}と受け取れる見出しだが説明が足りない",
            "text": "{site_name}の記事は{claim}と受け取れる見出しを付けているが、本文で示されるのは{partial_basis}までで、{missing}。言い切り方が先走っている。",
        },
        {
            "suffix": "local-to-general",
            "title": "限られた材料から{claim}へ話を広げている",
            "text": "{site_name}は{partial_basis}という限られた材料から、{claim}という広い結論に進んでいる。{missing}点を踏まえると、不正確さが残る。",
        },
        {
            "suffix": "causal-shortcut",
            "title": "因果関係を飛ばして{claim}と結びつけている",
            "text": "{site_name}の説明では、{partial_basis}と{claim}がそのまま結びつけられている。だが、{missing}ため、因果の扱いが粗い。",
        },
        {
            "suffix": "context-omitted",
            "title": "断片情報だけで{claim}が既成事実のように見える",
            "text": "{site_name}は断片的な材料として{partial_basis}を示しつつ、読者には{claim}が既成事実のように見える書き方をしている。{missing}。",
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
            "suffix": "image-assertion",
            "title": "{evidence}を並べて{claim}と断じる投稿",
            "text": "{site_name}は{evidence}を並べ、{claim}と断定している。検証可能な一次情報は示していない。",
        },
        {
            "suffix": "mechanism-story",
            "title": "{claim}の仕組みがあるかのように語る",
            "text": "{site_name}の内容は{claim}という筋書きを前提にしており、裏づけとして出てくるのは{evidence}だけだ。主張を支える事実が足りない。",
        },
        {
            "suffix": "share-warning",
            "title": "拡散を促しながら{claim}と訴える",
            "text": "{site_name}は危険を知らせるべき話だとして{claim}と訴えるが、根拠は{evidence}に限られる。確認可能な公的情報や信頼できる資料がない。",
        },
        {
            "suffix": "anonymous-source",
            "title": "匿名情報を重ねて{claim}を既成事実化している",
            "text": "{site_name}は匿名発言や断片資料を積み上げ、{claim}が既成事実であるかのように書いている。実際に示されるのは{evidence}程度で、主張は成り立たない。",
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
            "title": "{rumor}という情報が出回っているが裏が取れていない",
            "text": "{site_name}は{rumor}という情報が広がっていると紹介しているが、{missing}は確認できていない。真偽はまだ固まらない。",
        },
        {
            "suffix": "rumor-roundup",
            "title": "{rumor}という話題をまとめているが確認材料が薄い",
            "text": "{site_name}の中心は{rumor}という話題だが、よりどころは転送文や匿名発言レベルで、{missing}がない。現時点では確認不足だ。",
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
    cases = []
    cases.extend(load_positive_factcheck_cases())
    cases.extend(load_jfc_curated_cases())

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
            "version": DATASET_VERSION,
            "curated_on": DATASET_CURATED_ON,
            "language": "ja",
            "description": "公開 verdict 5区分を評価するための 100 件データセットです。analysis_text は人手要約または評価用の中心命題で、元記事の全文転載ではありません。",
            "notes": [
                "この dataset は 5区分で合計100件です。内訳は 正確20 / ほぼ正確20 / 判断保留20 / 不正確20 / 誤り20 です。",
                "正確 / ほぼ正確 は、日本ファクトチェックセンター(JFC)、FactCheck Navi が集約した日本系ファクトチェック記事、InFact、神戸新聞、Snopes の日本関連記事を基にした実在ネット記事ケースです。",
                "判断保留 / 不正確 / 誤り は、日本ファクトチェックセンター(JFC)の公開ファクトチェック記事を基にした実在ネット記事ケースです。",
                "analysis_text は全ケースで日本語要約にそろえています。",
                "判定対象は analysis_text の中心命題です。",
                "analysis_text は、記事本文の中心命題のうち expected.verdict を直接決める判定対象文だけを書く方針です。",
                "analysis_text には 正確です / 誤りです / ほぼ正確です などの判定文や、Snopes は True と判定 などの評価メタ文を入れません。",
                "analysis_text には、主語・時点・数量・地域・比較対象など、真偽が変わる条件を残します。",
                "analysis_text は 1〜2文を目安にし、読んだだけで expected.verdict に照らして判定できる形を目指します。",
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
