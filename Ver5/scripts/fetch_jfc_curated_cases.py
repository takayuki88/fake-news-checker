import concurrent.futures
import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT.parent / "testdata" / "sources" / "jfc_curated_factcheck_cases.json"
SITEMAP_URL = "https://www.factcheckcenter.jp/sitemap-posts.xml"
SITE_NAME = "日本ファクトチェックセンター"
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
TITLE_RE = re.compile(r'<meta property="og:title" content="([^"]+)"')
DESC_RE = re.compile(r'<meta property="og:description" content="([^"]+)"')
VERDICT_RE = re.compile(r"(正確|ほぼ正確|根拠不明|不正確|誤り)です")
TARGET_VERDICTS = {
    "根拠不明": "判断保留",
    "不正確": "不正確",
    "誤り": "誤り",
}
TARGET_COUNT_PER_VERDICT = 20
DOMAIN_MAP = {
    "health": "医療",
    "economics": "金融",
    "disasters": "災害",
}
ANALYSIS_TEXT_OVERRIDES: dict[str, str] = {
    "yokohama-team-mirai-election-fraud-unfounded": (
        "横浜市でチームみらいが不正に得票したと裏づける公開根拠は確認できず、"
        "開票不正があったとまでは言えない。"
    ),
    "baseless-healthworkers-mynahokensho": (
        "医療従事者の大多数がマイナ保険証にしていないと断定できる公開データは確認できない。"
    ),
    "baseless-trump-said-all-hell-break-loose": (
        "米トランプ大統領が9月1日に「全てが大混乱に陥る」と発言したと裏づける公開情報は、"
        "日本時間9月1日17時時点で確認できない。"
    ),
    "baseless-jal123-fake-voice-recorder": (
        "日本航空123便事故の「完全版ボイスレコーダー」とされる動画が、"
        "実際の音声記録そのものだと示す根拠は確認できない。"
    ),
    "baseless-solar-panels-not-covered-by-fire-insurance": (
        "太陽光パネル付き住宅が火災保険の対象外になると一律に断定できる根拠は確認できない。"
    ),
    "baseless-ohtani-said-illegal-immigrants-should-leave": (
        "大谷翔平選手が「不法移民は出ていくべきだ」と発言したと裏づける確かな情報は確認できない。"
    ),
    "baseless-whale-sardine-beach-earthquake": (
        "イワシやクジラ、イルカの漂着が地震の前兆だと示す一貫した根拠は確認できない。"
    ),
    "false-claim-korean-massacre-6000-lie": (
        "関東大震災の朝鮮人虐殺の犠牲者数を「6000人は100%嘘」だと断定できる根拠はなく、"
        "人数は資料によって幅がある。"
    ),
    "baseless-uniqlo-china-factory-exit": (
        "ユニクロが中国の269工場を撤退させたと断定できる公開根拠は確認できない。"
    ),
    "kanagawa-10000-invalid-votes-fraud-claim": (
        "神奈川15区の約1万票の無効票が不正選挙の証拠だとまでは確認できない。"
    ),
    "baseless-exposition-pneumonia-class-closure": (
        "大阪万博会場でレジオネラ菌入り殺虫剤がまかれ、"
        "それが学級閉鎖の原因になったと裏づける根拠は確認できない。"
    ),
    "baseless-trump-said-he-will-save-japanese-citizens": (
        "トランプ大統領が「日本政府は助けないが日本国民は助ける」と発言したと裏づける公式情報は確認できない。"
    ),
    "baseless_nankai_trough_earthquake_aug14": (
        "2024年8月14日に南海トラフ地震が起こると、"
        "具体的な日時まで断定できる根拠は確認できない。"
    ),
    "saga-invalid-votes-fraud-claim-unfounded": (
        "佐賀1区で無効票5000票が不正選挙の証拠だと断定できる根拠は確認できない。"
    ),
    "baseless-fanta-orange-1970-additives": (
        "1976年のファンタオレンジの添加物が「たった3つ」だったと単純化して言い切れる根拠は確認できない。"
    ),
    "no-evidence-a-sign-made-by-chinese-people": (
        "「コノ先日本國憲法通用セズ」という看板を中国人が作ったと示す証拠は確認できない。"
    ),
    "baseless-koike-google-personal-data": (
        "小池百合子都知事がGoogleに個人情報を提供したと断定できる根拠は確認できない。"
    ),
    "mhlw-staff-vaccination-rate-uncertain": (
        "厚労省職員のワクチン接種率が10％だと裏づける公開データは確認できない。"
    ),
    "baseless-xi-jinping-fell-from-chair": (
        "習近平国家主席が会議中に椅子から転げ落ち、脳卒中を起こしたと裏づける確かな情報は確認できない。"
    ),
    "baseless-mynaportal-major-cut-in-administrative-costs-for-benefits": (
        "2万円給付の事務経費がマイナポータル活用で大幅に減ると断定できる根拠は、"
        "現時点の公開情報だけでは十分でない。"
    ),
    "politicians-zero-inheritance-tax": (
        "政治家に相続税上の特例があるかのように見せて「政治家だけ相続税0円」と一般化するのは、"
        "制度の範囲を広げすぎている。"
    ),
    "did-it-take-only-four-months-for-the-takaichi-administration-to-reach-the-mining-stage": (
        "レアアース確保に向けた取り組みは以前から進んでいたのに、"
        "「高市政権発足4ヶ月で一気に採掘までたどり着いた」と表現するのは時間軸を大きく省いている。"
    ),
    "japan-is-not-expanding-the-pakistani-intake-to-50thousands": (
        "日本がパキスタン人の受け入れ人数を2.5万人から5万人に拡大するという投稿は、"
        "制度の実態を単純化して人数枠の拡大が決まったかのように伝えている。"
    ),
    "inaccurate-kyoto-hotel-prices-collapse": (
        "中国人観光客のキャンセルが相次いだことを理由に「京都市内のホテル代が暴落している」とするのは、"
        "一部時期の下落を市内全体の急落のように広げている。"
    ),
    "inaccurate-gates-abondons-climate-action": (
        "ビル・ゲイツ氏は気候対策の優先順位の置き方を論じているが、"
        "「気候変動対策から撤退した」と受け取れる言い方は行き過ぎている。"
    ),
    "inaccurate-trump-administration-admits-covid-shots-are-crime-against-humanity": (
        "米政府が接種方針を見直したことをもって、"
        "新型コロナワクチンを「人類に対する犯罪」と認めたかのように結びつけるのは飛躍がある。"
    ),
    "inaccurate-favoratism-toward-chinese-students": (
        "一部の国費留学生の優遇を根拠に、「中国人留学生は学費がほぼ無料」と広く言うのは対象範囲を広げすぎている。"
    ),
    "inaccurate-foreigners-obtain-the-national-certification-for-care-workers": (
        "介護福祉士の国家資格で特例適用者がいることをもって、"
        "「外国人は不合格でも取得できる特例がある」と説明するのは制度の条件を落としている。"
    ),
    "inaccurate-claim-ministry-of-economy-trade-and-industry-did-not-state-they-did-not-measure-9-nuclides-other-than-tritium": (
        "担当者が「総量の推定は実施していない」と述べたことを、"
        "「トリチウム以外の9核種は測定していない」と受け取るのは発言の意味を広げすぎている。"
    ),
    "inaccurate-kurdish-group-tv-report": (
        "テレビ朝日の報道の一部だけを切り出し、"
        "「川口のクルド団体がテロ支援と報じられた」と受け取れる形にするのは文脈を欠いている。"
    ),
    "inaccurate-volunteer-recruitment-n-noto-peninsula-earthquake": (
        "能登半島地震の被災地で募集の形や受け入れ条件に制約があることを、"
        "「ボランティアを募集していない」と一般化するのは行き過ぎている。"
    ),
    "matsumoto-chief-cabinet-secretary-great-kanto-earthquake-korean-massacre-records-inaccurate": (
        "松野官房長官の「政府内に記録は見当たらない」という発言は、"
        "政府が朝鮮人虐殺の事実関係を整理した資料まで存在しないかのように受け取られかねない。"
    ),
    "ohio-train-derailment-disaster-hidden-reporter-arrested-false": (
        "オハイオ州の列車脱線事故で記者が逮捕された事実を、"
        "ただちに「隠ぺいのためだ」と結びつけるのは因果を飛ばしている。"
    ),
    "inaccurate-video-of-transgender-martial-artist-breaking-opponents-skull": (
        "ファロン・フォックス選手が拡散されたこの試合で相手の頭蓋骨を骨折させたかのように受け取るのは、"
        "動画の文脈をずらしている。"
    ),
    "inaccurate-claims-about-drone-delivery": (
        "ドローン配送が普及しない理由を、鳥に襲われるという映像だけで説明するのは一般化が過ぎる。"
    ),
    "inaccuracies-in-keio-baseball-cheering": (
        "一部授業で早慶戦観戦が出席扱いになることを、"
        "「慶応大学では野球の応援に行くと単位が取れる」と表現するのは制度を単純化しすぎている。"
    ),
    "japan-iran-visa-indefinite-extension": (
        "帰国困難者向けの在留措置を、「イラン国民のビザを無期限延長した」と説明するのは対象と内容を広げすぎている。"
    ),
    "ion-stores-atm-credit-card-inaccessibility-inaccurate": (
        "イオン銀行ATMなどの一時休止を、"
        "「イオンでATMやクレジットカードが使えなくなる」と受け取れる形で広げるのは範囲が広すぎる。"
    ),
    "factcheck-us-department-of-state-officially-declared-islam-a-threat": (
        "米国務省高官がイスラム過激派を脅威と述べたことを、"
        "「米国務省がイスラム教を脅威と宣言した」と広げるのは対象を取り違えている。"
    ),
    "inaccurate-9000yen-to-a-muslims-school-lunch": (
        "東京都の助成制度を、"
        "「ムスリムの園児1人につき毎月9000円を給食のために支給している」と説明するのは対象を狭く限定しすぎている。"
    ),
    "trump-im-the-last-to-use-nukes": (
        "トランプ氏が、現在の中東情勢を受けて「私は核兵器を使う最後の人間になるだろう」と発言した。"
    ),
    "did-noda-yoshihiko-said-spy-prevention-law-would-violate-spies-human-rights": (
        "野田佳彦氏が「スパイ防止法はスパイの人権を侵害してしまう」と発言した。"
    ),
    "chemtrail-government-airborne-dispersion-harmful-substances-false": (
        "飛行機雲は、政府などが危険な化学物質を散布している「ケムトレイル」である。"
    ),
    "japans-inflation-rate-is-not-the-highest": (
        "日本のインフレ率は世界で最も高い。"
    ),
    "japan-does-not-have-any-anti-islamic-legislation": (
        "日本はモスク建設やブルカの着用などを禁じる反イスラム法を制定した。"
    ),
    "pfizer-didnt-admit-covid-jab-causes-cancer": (
        "ファイザー社は新型コロナワクチンで大腸がんになると認めた。"
    ),
    "false-aomori-earthquake-artificial": (
        "2025年12月8日に青森県東方沖で起きた地震は人工地震である。"
    ),
    "kawaguchi-arrest-foreign-national-ratio": (
        "川口市の検挙人数178人のうち外国籍は135人で約76%を占め、"
        "検挙された人の約4人に3人が外国籍である。"
        "2024年に川口市内で刑法犯で検挙された外国人のうち、"
        "トルコ・中国・ベトナムの3国籍が7割を占める。"
    ),
    "false-dog-elevator-ai-video": (
        "子どもが犬とエレベーターに乗ろうとしたが犬が嫌がって見送り、"
        "その直後にエレベーターが落下して命が助かった。"
    ),
    "false-lee-jaemyung-setagaya-comment": (
        "世田谷区で韓国籍女性が殺害された事件について、"
        "韓国の李在明大統領が「日本は謝罪と賠償をするべきだ」と発言した。"
    ),
    "false-hometown-africa-nagai-visa": (
        "日本の4市がアフリカ諸国の「ホームタウン」に認定され、"
        "日本は山形県長井市をタンザニアに与え、移民定住のための特別ビザ制度も創設する。"
    ),
    "false-celebrity-death-hoaxes-youtube": (
        "浜崎あゆみ氏やビートたけし氏、友近氏などの著名人が亡くなった。"
    ),
    "false-koizumi-radiated-soil-video": (
        "小泉農水大臣が放射能汚染土を日本中にばらまいた。"
    ),
    "false-asahi-ceremony-flags": (
        "朝日新聞の入社式では、社旗の脇に韓国と中国の国旗を並べ、ハングル文字を掲げていた。"
    ),
    "false-100k-demo-osaka-yoon": (
        "大阪で10万人規模のデモ隊が、韓国の尹錫悦大統領の罷免や日本との断交を要求した。"
    ),
    "false-minimum-access-rice-harmful": (
        "アメリカ産のミニマムアクセス米は、除草剤や殺虫剤が頻繁に使われていて健康に影響がある。"
    ),
    "false-hokkaido-ainu-not-jomon": (
        "北海道の先住民族はアイヌではなく、縄文人である大和民族だ。"
    ),
    "false-planet-alignment-over-pyramid-every-2373": (
        "エジプトのピラミッド上空で水星・金星・土星が並ぶ現象は2373年に1度だけ起こり、"
        "その画像は実際の撮影写真だ。"
    ),
    "former-ukrainian-commander-zarzhinyi-53-million-dollar-retirement-bbc": (
        "ウクライナ軍の前司令官ヴァレリー・ザルジニー氏が5300万ドルの退職金を受け取ったとBBCが報じた。"
    ),
    "false-epstein-emperor-ai-photo": (
        "天皇陛下や上皇陛下がジェフリー・エプスタイン氏と一緒に写っている写真は本物だ。"
    ),
}
ANALYSIS_TEXT_GUIDELINES = [
    "analysis_text は記事本文の中心命題のうち、expected.verdict を直接決める判定対象文だけを書く",
    "正確です / 誤りです / ほぼ正確です / 根拠不明です などの判定文を入れない",
    "Snopes は True と判定 / JFC が誤りと判断 / 〜とされた などの評価メタ文を入れない",
    "主語・時点・数量・地域・比較対象など、真偽が変わる条件は落とさない",
    "1〜2文を目安に、読んだだけで expected.verdict に照らして判定できる形にする",
]
ANALYSIS_TEXT_META_PATTERNS = [
    r"(正確|ほぼ正確|根拠不明|不正確|誤り)です",
    r"と判定",
    r"と判断",
    r"とされた",
    r"と結論",
    r"True と判定",
    r"Mostly True",
]


def fetch_sitemap_urls() -> list[str]:
    with urllib.request.urlopen(SITEMAP_URL, timeout=30) as response:
        root = ET.fromstring(response.read())
    urls = [node.text for node in root.findall(".//sm:url/sm:loc", NS)]
    return [
        url
        for url in urls
        if url
        and "/fact-check/" in url
        and "/fact-check/others/fact-check-weekly-" not in url
    ]


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def clean_title(title: str) -> str:
    title = re.sub(r"【[^】]+】", "", title)
    title = re.sub(r"（[^）]*）", "", title)
    return normalize_whitespace(title)


def clean_sentence(sentence: str) -> str:
    sentence = normalize_whitespace(sentence)
    sentence = re.sub(r"、?(?:ミスリードで)?(?:正確|ほぼ正確|根拠不明|不正確|誤り)です", "", sentence)
    sentence = sentence.replace("がXで拡散しましたが、", "がXで拡散しており、")
    sentence = sentence.replace("が拡散しましたが、", "が拡散しており、")
    sentence = sentence.replace("が拡散していますが、", "が拡散しており、")
    sentence = sentence.replace("が話題になりましたが、", "が話題になっており、")
    sentence = sentence.replace("が話題になっていますが、", "が話題になっており、")
    sentence = sentence.replace("がXで拡散しましたが", "がXで拡散している")
    sentence = sentence.replace("が拡散しましたが", "が拡散している")
    sentence = sentence.replace("が拡散していますが", "が拡散している")
    sentence = sentence.replace("が話題になりましたが", "が話題になっている")
    sentence = sentence.replace("が話題になっていますが", "が話題になっている")
    sentence = sentence.replace("拡散している、", "拡散しており、")
    sentence = sentence.replace("話題になっている、", "話題になっており、")
    sentence = sentence.strip(" 、")
    if sentence.endswith("が"):
        sentence = sentence[:-1].rstrip()
    return sentence


def build_analysis_text(description: str) -> str:
    head = normalize_whitespace(description.split("検証対象")[0])
    sentences = [clean_sentence(part) for part in head.split("。") if clean_sentence(part)]
    return "".join(f"{sentence}。" for sentence in sentences[:2])


def collect_analysis_text_warnings(case_id: str, analysis_text: str) -> list[str]:
    warnings: list[str] = []
    normalized = normalize_whitespace(analysis_text)
    if not normalized:
        warnings.append("analysis_text is empty")
    if normalized.count("。") > 2:
        warnings.append("analysis_text is longer than 2 sentences")
    for pattern in ANALYSIS_TEXT_META_PATTERNS:
        if re.search(pattern, normalized):
            warnings.append(f"analysis_text may include meta phrasing: {pattern}")
    return warnings


def map_domain(raw_domain: str) -> str:
    return DOMAIN_MAP.get(raw_domain, "一般")


def fetch_article(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as response:
        html_text = response.read().decode("utf-8", errors="ignore")

    title_match = TITLE_RE.search(html_text)
    desc_match = DESC_RE.search(html_text)
    if not title_match or not desc_match:
        raise ValueError(f"missing meta tags: {url}")

    title = html.unescape(title_match.group(1))
    description = html.unescape(desc_match.group(1))
    verdict_match = VERDICT_RE.search(description)
    verdict = verdict_match.group(1) if verdict_match else None

    path = url.replace("https://www.factcheckcenter.jp/", "")
    parts = path.split("/")
    raw_domain = parts[1] if len(parts) > 2 else "others"
    slug = path.rstrip("/").split("/")[-1]

    return {
        "url": url,
        "title": clean_title(title),
        "description": description,
        "source_verdict": verdict,
        "domain": map_domain(raw_domain),
        "raw_domain": raw_domain,
        "slug": slug,
    }


def select_diverse(items: list[dict], count: int) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    domain_order: list[str] = []
    for item in items:
        if item["raw_domain"] not in grouped:
            domain_order.append(item["raw_domain"])
        grouped[item["raw_domain"]].append(item)

    selected: list[dict] = []
    while len(selected) < count and any(grouped[domain] for domain in domain_order):
        for domain in domain_order:
            if grouped[domain]:
                selected.append(grouped[domain].pop(0))
                if len(selected) == count:
                    break
    return selected


def build_case(item: dict, case_index: int) -> dict:
    expected_verdict = TARGET_VERDICTS[item["source_verdict"]]
    case_prefix = {
        "判断保留": "jfc-hold",
        "不正確": "jfc-inaccurate",
        "誤り": "jfc-false",
    }[expected_verdict]
    analysis_text = ANALYSIS_TEXT_OVERRIDES.get(item["slug"]) or build_analysis_text(item["description"])
    return {
        "id": f"{case_prefix}-{case_index:02d}-{item['slug']}",
        "title": item["title"],
        "site_name": SITE_NAME,
        "source_url": item["url"],
        "purpose": "JFC の公開ファクトチェック記事を基にした実在ネット記事ケース",
        "analysis_text": analysis_text,
        "reference_urls": [item["url"]],
        "expected": {
            "verdict": expected_verdict,
            "domain": item["domain"],
        },
        "snapshot_overrides": {
            "has_author": True,
            "has_published_at": True,
            "reference_link_count": 1,
            "extraction_score": 82,
        },
        "source_verdict_label": item["source_verdict"],
        "source_domain": item["raw_domain"],
    }


def build_payload() -> dict:
    urls = fetch_sitemap_urls()
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        articles = list(executor.map(fetch_article, urls))

    selected_cases: list[dict] = []
    summary: dict[str, dict[str, int]] = {}
    analysis_text_warnings: dict[str, list[str]] = {}
    for source_verdict, expected_verdict in TARGET_VERDICTS.items():
        candidates = [article for article in articles if article["source_verdict"] == source_verdict]
        selected = select_diverse(candidates, TARGET_COUNT_PER_VERDICT)
        if len(selected) != TARGET_COUNT_PER_VERDICT:
            raise ValueError(
                f"Expected {TARGET_COUNT_PER_VERDICT} JFC cases for {source_verdict}, got {len(selected)}"
            )
        summary[expected_verdict] = dict(Counter(article["raw_domain"] for article in selected))
        for index, item in enumerate(selected, start=1):
            case = build_case(item, index)
            warnings = collect_analysis_text_warnings(case["id"], case["analysis_text"])
            if warnings:
                analysis_text_warnings[case["id"]] = warnings
            selected_cases.append(case)

    return {
        "meta": {
            "source_site": SITE_NAME,
            "source_sitemap": SITEMAP_URL,
            "selection_strategy": "latest-first with round-robin across JFC raw domains",
            "case_count": len(selected_cases),
            "verdict_summary": summary,
            "analysis_text_guidelines": ANALYSIS_TEXT_GUIDELINES,
            "analysis_text_warning_count": len(analysis_text_warnings),
            "analysis_text_warning_examples": dict(list(analysis_text_warnings.items())[:10]),
        },
        "cases": selected_cases,
    }


def main() -> int:
    payload = build_payload()
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
