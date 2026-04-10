import html
import json
import re
import urllib.request
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT.parent / "testdata" / "sources" / "positive_factcheck_cases.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "ja,en;q=0.9",
}

TARGET_COUNTS = {
    "正確": 20,
    "ほぼ正確": 20,
}
VERDICT_PREFIX = {
    "正確": "accurate",
    "ほぼ正確": "mostly-accurate",
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
ANALYSIS_TEXT_OVERRIDES = {
    "nhk-broadcasts-200-human-sacrifices": (
        "映像に含まれる「しゅうだんいけにえ200人！」という歌詞は、"
        "2023年7月18日に放映されたNHKの「まやまやぽん！」の体操の一部である。"
    ),
    "why-not-in-the-news-shizuoka-flood-images-are-real": (
        "9月25日に「なぜニュースにならないの？」という文とともに投稿された3枚の画像は、"
        "静岡市南部・巴川の氾濫による被害を写した本物の写真である。"
    ),
    "aaa-com-article-accurate-koizumi-warns-typhoon": (
        "自民党の小泉進次郎氏が台風10号への注意を呼びかける動画は、"
        "公式アカウントで配信された本人の発言である。"
    ),
    "litmus221003": (
        "財務省は、国民健康保険の「高額医療費負担」を廃止し、都道府県の負担とすることを検討している。"
    ),
    "mainichi230505": (
        "投稿された家屋の写真は、毎日新聞記者が同じ家屋の前で現地確認した実際の写真である。"
    ),
    "photos-japan-orca": (
        "北海道沖で撮影された白いシャチの写真は、"
        "撮影者の証言や投稿履歴から実際の個体を写した写真である。"
    ),
    "ainu-dance-filmed-1919": (
        "カラー化された「1919年に撮影されたアイヌの踊り」の動画は、"
        "アーカイブ保管資料に基づく実写映像である。"
        "ただし、オリジナル版は白黒で、拡散版の色は後から付けられている。"
    ),
    "real-image-of-jovial-swedish-people-despite-train-station-flooding-caused-by-typhoon": (
        "「台風で駅が浸水しても陽気なスウェーデンの人々」という画像は、"
        "浸水した駅で撮影された本物の画像である。"
        "ただし、拡散時の説明には補足が要る。"
    ),
    "almost-accurate-claim-iaea-not-verifying-filtration-performance-of-contaminated-water": (
        "IAEAはALPSそのものを直接検証したわけではない。"
        "ただし、福島第一原発の処理水放出の安全性や環境影響については調査している。"
    ),
    "infact200912": (
        "リコール署名では、請求代表者は県公報で公開され、必要数に達して提出された署名簿にある"
        "受任者や署名者の氏名・住所は同じ市町村の有権者が閲覧できる。"
        "ただし、県公報で公開されるのは請求代表者に限られる。"
    ),
    "jid211029-01": (
        "2012年から株価はおよそ2万円上がり、年金積立金はおよそ83兆円増えた一方、年金受給額は増えていない。"
        "国内株式と外国株式のポートフォリオを倍増させた2014年以降、両株式からの収益が増加している。"
    ),
    "infact220823": (
        "日本における「入学金」と同様の意味をもつ制度が確認できるのは、日本以外では韓国程度である。"
        "もっとも、韓国でも2023年から入学金制度の廃止が決まっていた。"
    ),
    "post-22724": (
        "アンソニー・ファウチ氏は、6フィートの社会的距離ルールについて自ら明確な科学的根拠を示したわけではない。"
        "もっとも、「完全にでっち上げで科学的根拠はゼロだ」とまで認めたわけでもない。"
    ),
    "23435": (
        "スイスなどでは一定の条件のもとで自死幇助が認められている。"
        "ただし、海外で安楽死が誰にでも簡単に認められるわけではない。"
    ),
}

JFC_SELECTED_SPECS = [
    {"url": "https://www.factcheckcenter.jp/fact-check/culture/nhk-broadcasts-200-human-sacrifices/", "verdict": "正確"},
    {"url": "https://www.factcheckcenter.jp/fact-check/disasters/why-not-in-the-news-shizuoka-flood-images-are-real/", "verdict": "正確"},
    {"url": "https://www.factcheckcenter.jp/fact-check/politics/aaa-com-article-accurate-koizumi-warns-typhoon/", "verdict": "正確"},
    {"url": "https://www.factcheckcenter.jp/fact-check/history/ainu-dance-filmed-1919/", "verdict": "ほぼ正確"},
    {
        "url": "https://www.snopes.com/fact-check/blm-olympics-apparel-banned/",
        "verdict": "ほぼ正確",
        "builder": "snopes_direct",
        "id_override": "positive-mostly-accurate-02-real-image-of-jovial-swedish-people-despite-train-station-flooding-caused-by-typhoon",
        "title": "五輪で BLM の服装だけが特別に禁止されたわけではない",
        "analysis_text": "東京五輪では、Black Lives Matter を示す服装や表示は制限対象になり得たが、それは BLM だけを狙った特別禁止ではなく、IOC の政治的表現全般を禁じる規則の一部だった。",
        "domain": "一般",
    },
    {
        "url": "https://www.factcheckcenter.jp/fact-check/nuclear/almost-accurate-claim-iaea-not-verifying-filtration-performance-of-contaminated-water/",
        "verdict": "ほぼ正確",
    },
]

JFC_ANALYSIS_OVERRIDES = {
    "nhk-broadcasts-200-human-sacrifices": (
        "NHKが「いけにえたくさん見届けてきたよ しゅうだんいけにえ200人！」という歌詞の映像を放送した動画が拡散した。"
        "映像は2023年7月18日に放映された「まやまやぽん！」の体操の一部で、NHKの番組映像である。"
    ),
    "ainu-dance-filmed-1919": (
        "「1919年に撮影された本物のアイヌの踊り」というカラー動画が拡散した。"
        "映像はアーカイブ保管資料に基づく実写映像だが、オリジナル版は白黒で、拡散版のカラー化には補足が必要である。"
    ),
    "almost-accurate-claim-iaea-not-verifying-filtration-performance-of-contaminated-water": (
        "福島第一原発の処理水海洋放出をめぐり、「国際原子力機関（IAEA）が多核種除去設備（ALPS）の性能を検証していない」という言説が拡散した。"
        "IAEAはALPSそのものを直接検証したわけではないが、処理水放出の安全性や環境影響については調査している。"
    ),
}

FIJ_SELECTED_SPECS = [
    {
        "url": "https://www.snopes.com/fact-check/japanese-researchers-new-teeth/",
        "verdict": "正確",
        "builder": "snopes_direct",
        "id_override": "positive-accurate-04-wasegg210726-2",
        "title": "日本の研究者は新しい歯を生やす治療法を開発している",
        "analysis_text": "日本の研究者チームは、欠損した歯の再生を目指す薬の臨床研究を進めており、新しい歯を生やす治療法の実用化を目指している。",
        "domain": "医療",
    },
    {
        "url": "https://navi.fij.info/factcheck_navi/jid211030-2/",
        "verdict": "正確",
    },
    {
        "url": "https://www.snopes.com/fact-check/do-dodonpa-roller-coaster/",
        "verdict": "正確",
        "builder": "snopes_direct",
        "id_override": "positive-accurate-06-wasegg220314-8",
        "title": "日本のジェットコースター『ド・ドドンパ』は1.56秒で時速112マイルに達した",
        "analysis_text": "富士急ハイランドのジェットコースター『ド・ドドンパ』は、営業当時、約1.56秒で時速約112マイルに達する加速性能で知られていた。",
        "domain": "一般",
    },
    {
        "url": "https://navi.fij.info/factcheck_navi/infact220706/",
        "verdict": "正確",
    },
    {
        "url": "https://navi.fij.info/factcheck_navi/jid220707/",
        "verdict": "正確",
    },
    {
        "url": "https://navi.fij.info/factcheck_navi/infact220821/",
        "verdict": "正確",
    },
    {
        "url": "https://www.snopes.com/fact-check/palau-us-migrants-deal/",
        "verdict": "正確",
        "builder": "snopes_direct",
        "id_override": "positive-accurate-10-wasegg220709-2",
        "title": "パラオは米国から送られる一部移民の受け入れ合意に署名した",
        "analysis_text": "パラオ政府は、米国から送られる一部の第三国出身移民を受け入れる枠組みに署名した。",
        "domain": "政治",
    },
    {
        "url": "https://navi.fij.info/factcheck_navi/litmus221003/",
        "verdict": "正確",
    },
    {
        "url": "https://infact.press/2026/02/post-26458/",
        "verdict": "正確",
        "builder": "infact_direct",
        "id_override": "positive-accurate-12-mainichi230505",
        "title_override": "〖衆院選26FactCheck〗参政党・神谷代表「大学は増えている」は本当か？",
        "analysis_override": "2025年時点では、日本の大学数は長期的に見ても直近20年間で見ても増加している。",
        "domain_override": "政治",
    },
    {
        "url": "https://infact.press/2025/07/post-25455/",
        "verdict": "正確",
        "builder": "infact_direct",
        "id_override": "positive-accurate-13-litmus230706",
        "title_override": "〖参議院選25FactCheck〗玉木代表「住民税非課税世帯の４分の３は高齢者」発言を検証",
        "analysis_override": "令和6年国民生活基礎調査などによれば、住民税非課税世帯のうち65歳以上の高齢者が占める割合は約4分の3である。",
        "domain_override": "政治",
    },
    {
        "url": "https://navi.fij.info/factcheck_navi/infact200912/",
        "verdict": "ほぼ正確",
    },
    {
        "url": "https://www.snopes.com/fact-check/covid-nyc-tokyo/",
        "verdict": "ほぼ正確",
        "builder": "snopes_direct",
        "id_override": "positive-mostly-accurate-05-infact211023-3",
        "title": "新型コロナの1日当たり死者数で東京はニューヨーク市を上回っていた",
        "analysis_text": "2022年8月時点で、人口10万人当たりの新型コロナによる1日平均死亡者数は東京がニューヨーク市を上回っていた。ただし、比較の時点や指標の取り方には補足が必要である。",
        "domain": "医療",
    },
    {
        "url": "https://www.snopes.com/fact-check/sweden-import-trash/",
        "verdict": "ほぼ正確",
        "builder": "snopes_direct",
        "id_override": "positive-mostly-accurate-06-jid211024-1",
        "title": "スウェーデンはごみを輸入して発電や暖房に使っている",
        "analysis_text": "スウェーデンは他国から大量のごみを輸入し、それを廃棄物発電施設の燃料として使っている。ただし、輸入している理由を『ごみ不足』だけで説明するのは単純化しすぎである。",
        "domain": "一般",
    },
    {
        "url": "https://www.snopes.com/fact-check/tax-massachusetts-millionaires/",
        "verdict": "ほぼ正確",
        "builder": "snopes_direct",
        "id_override": "positive-mostly-accurate-07-jid211029-01",
        "title": "マサチューセッツ州の富裕税は15億ドル超の税収を生んだ",
        "analysis_text": "マサチューセッツ州で有権者が承認した年収100万ドル超への4%の付加税は、導入後に少なくとも15億ドル規模の税収を生んだ。ただし、実際の税収額はその数字より多かった。",
        "domain": "金融",
    },
    {
        "url": "https://www.snopes.com/fact-check/beer-egypt-pyramids-rations/",
        "verdict": "ほぼ正確",
        "builder": "snopes_direct",
        "id_override": "positive-mostly-accurate-08-asahi211116-2",
        "title": "ギザのピラミッド建設労働者にはビールが配給されていた",
        "analysis_text": "ギザのピラミッド建設に従事した古代エジプトの労働者には、配給の一部としてビールが与えられていた。ただし、1日に4〜5リットルだったという具体的な量は不確実である。",
        "domain": "一般",
    },
    {
        "url": "https://navi.fij.info/factcheck_navi/infact211217-1/",
        "verdict": "ほぼ正確",
    },
    {
        "url": "https://navi.fij.info/factcheck_navi/infact220704/",
        "verdict": "ほぼ正確",
    },
    {
        "url": "https://navi.fij.info/factcheck_navi/infact220706-2/",
        "verdict": "ほぼ正確",
    },
    {
        "url": "https://navi.fij.info/factcheck_navi/infact220708/",
        "verdict": "ほぼ正確",
    },
    {
        "url": "https://navi.fij.info/factcheck_navi/infact220823/",
        "verdict": "ほぼ正確",
    },
    {
        "url": "https://navi.fij.info/factcheck_navi/bfj230313/",
        "verdict": "ほぼ正確",
    },
]

INFACT_DIRECT_SPECS = [
    {
        "url": "https://infact.press/2024/12/post-23899/",
        "verdict": "正確",
        "analysis_override": "河野太郎氏は、当時のCDC発表に基づき「アメリカでは2億回ワクチンを接種して亡くなった人はいない」と述べた。CDCへの確認でも、その時点でワクチン接種による死亡が確認されたとはされていなかった。",
    },
    {
        "url": "https://infact.press/2024/01/post-22724/",
        "verdict": "ほぼ正確",
    },
    {
        "url": "https://infact.press/2024/03/post-22836/",
        "verdict": "ほぼ正確",
    },
    {
        "url": "https://infact.press/2024/06/23435/",
        "verdict": "ほぼ正確",
    },
]

KOBE_MANUAL_SPECS = [
    {
        "slug": "kobe-pension-standardly-nontaxable",
        "title": "年金受給者は標準的に非課税",
        "site_name": "神戸新聞NEXT",
        "source_url": "https://www.kobe-np.co.jp/news/society/202507/0019232569.shtml",
        "reference_urls": [
            "https://www.kobe-np.co.jp/news/society/202507/0019232569.shtml",
        ],
        "analysis_text": "神戸市議のX投稿で、年金受給者は標準的に非課税だという言説が拡散した。神戸市内の年金受給者では非課税者が多数派だが、課税者も一定数おり、「標準的」という表現には条件差を包み込む曖昧さがある。",
        "verdict": "ほぼ正確",
        "domain": "金融",
        "purpose": "神戸新聞の選挙ファクト検証記事を基にした実在ネット記事ケース",
        "source_verdict_label": "ほぼ正確",
    },
]

SNOPES_SPECS = [
    {
        "url": "https://www.snopes.com/fact-check/japan-experimental-forestry/",
        "verdict": "正確",
        "title": "日本の円形林は実在する実験林",
        "analysis_text": "日本で山を円形に区切った実験林の写真が拡散した。これは樹木の密度が成長に与える影響を測るため実際に整備された試験区画である。",
        "domain": "一般",
    },
    {
        "url": "https://www.snopes.com/fact-check/japanese-robotic-monster-wolves/",
        "verdict": "正確",
        "title": "日本の町でクマよけにロボットのオオカミが使われた",
        "analysis_text": "日本の町がクマよけにロボットの「モンスターウルフ」を導入した。北海道などで導入例があり、音や光で野生動物を追い払う装置として実在する。",
        "domain": "一般",
    },
    {
        "url": "https://www.snopes.com/fact-check/toyota-city-japan-name/",
        "verdict": "正確",
        "title": "トヨタ市は自動車会社トヨタにちなんで改称された",
        "analysis_text": "愛知県の豊田市は、自動車メーカーの発展に合わせて旧挙母市から改称した。",
        "domain": "一般",
    },
    {
        "url": "https://www.snopes.com/fact-check/square-watermelon/",
        "verdict": "正確",
        "title": "四角いスイカは本物",
        "analysis_text": "日本で作られている四角いスイカは実在し、観賞用や贈答用として栽培されている。",
        "domain": "一般",
    },
    {
        "url": "https://www.snopes.com/fact-check/ronald-mcdonald-name-japan/",
        "verdict": "正確",
        "title": "日本ではロナルド・マクドナルドをドナルド・マクドナルドと呼ぶ",
        "analysis_text": "日本では Ronald McDonald を「ドナルド・マクドナルド」と呼ぶのが一般的で、発音上の理由から Ronald ではなく Donald 表記が定着している。",
        "domain": "一般",
    },
    {
        "url": "https://www.snopes.com/fact-check/photos-japan-orca/",
        "verdict": "正確",
        "title": "北海道沖で撮影された白いシャチの写真は本物",
        "analysis_text": "北海道沖で撮影された白いシャチの写真が拡散した。撮影者の証言や投稿履歴から、実際の個体を写した写真である。",
        "domain": "一般",
    },
    {
        "url": "https://www.snopes.com/fact-check/japanese-electric-car-200km-single-charge/",
        "verdict": "ほぼ正確",
        "title": "1949年の日本製電気自動車は1回の充電で約200キロ走れた",
        "analysis_text": "戦後の日本で開発された電気自動車「たま電気自動車」は、条件付きながら1回の充電でおよそ200キロ走行したとされる。",
        "domain": "一般",
    },
    {
        "url": "https://www.snopes.com/fact-check/biden-bounty-maduro/",
        "verdict": "ほぼ正確",
        "id_override": "positive-mostly-accurate-20-blobfish-natural-environment",
        "title": "バイデン政権はマドゥロに2500万ドルの懸賞金をかけたのか",
        "analysis_text": "米国政府は2020年にニコラス・マドゥロに1500万ドルの懸賞金を設定し、2025年1月のバイデン政権下でその額を2500万ドルに引き上げた。",
        "domain": "政治",
    },
]


def fetch_html(url: str) -> str:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="ignore")


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def strip_tags(text: str) -> str:
    return normalize_whitespace(html.unescape(re.sub(r"<.*?>", " ", text)))


def slug_from_url(url: str) -> str:
    tail = url.rstrip("/").split("/")[-1]
    if tail:
        return re.sub(r"[^a-z0-9-]+", "-", tail.lower()).strip("-")
    return "case"


def clean_title(title: str, site_name: str | None = None) -> str:
    text = normalize_whitespace(html.unescape(title))
    text = text.replace("– FactCheck Navi", "")
    text = text.replace("|社会|神戸新聞NEXT", "")
    text = re.sub(r"^【Fact ?Check】", "", text)
    text = re.sub(r"^\[Fact ?Check\]\s*", "", text)
    text = re.sub(r"【ファクトチェック】", "", text)
    text = re.sub(r"（訂正あり）", "", text)
    text = re.sub(r"（\d{4}\.\d{2}\.\d{2}）", "", text)
    text = re.sub(r"\s*【[^】]+】\s*$", "", text)
    if site_name:
        text = re.sub(rf"【{re.escape(site_name)}】$", "", text)
    return normalize_whitespace(text)


def first_sentences(text: str, count: int = 2) -> str:
    sentences = [normalize_whitespace(part) for part in re.split(r"(?<=。)", text) if normalize_whitespace(part)]
    return "".join(sentences[:count]) if sentences else normalize_whitespace(text)


def summary_from_description(description: str) -> str:
    text = normalize_whitespace(html.unescape(description))
    for marker in ("検証対象", "対象言説", "結論"):
        if marker in text:
            text = text.split(marker, 1)[0]
            break
    return first_sentences(text)


def classify_domain(*parts: str) -> str:
    text = normalize_whitespace(" ".join(parts)).lower()
    medical_keywords = [
        "ワクチン",
        "医療",
        "感染",
        "cdc",
        "who",
        "心筋炎",
        "病院",
        "マスク",
        "高額医療費",
        "安楽死",
        "fauci",
        "pfizer",
    ]
    finance_keywords = [
        "税",
        "年金",
        "消費税",
        "物価",
        "財源",
        "インフラ",
        "賃上げ",
        "保険料",
        "小麦",
        "g7",
        "カンガルー",
        "米価",
        "備蓄米",
    ]
    disaster_keywords = [
        "地震",
        "台風",
        "豪雨",
        "浸水",
        "災害",
        "被災",
        "珠洲",
        "静岡",
    ]
    if any(keyword.lower() in text for keyword in medical_keywords):
        return "医療"
    if any(keyword.lower() in text for keyword in finance_keywords):
        return "金融"
    if any(keyword.lower() in text for keyword in disaster_keywords):
        return "災害"
    return "一般"


def make_snapshot(reference_urls: list[str], extraction_score: int = 82) -> dict:
    return {
        "has_author": True,
        "has_published_at": True,
        "reference_link_count": len(reference_urls),
        "extraction_score": extraction_score,
    }


def build_case(
    index: int,
    verdict: str,
    slug: str,
    title: str,
    site_name: str,
    source_url: str,
    purpose: str,
    analysis_text: str,
    domain: str,
    reference_urls: list[str],
    source_verdict_label: str,
    extraction_score: int = 82,
    id_override: str | None = None,
) -> dict:
    analysis_text = normalize_whitespace(analysis_text)
    return {
        "id": id_override or f"positive-{VERDICT_PREFIX[verdict]}-{index:02d}-{slug}",
        "title": title,
        "site_name": site_name,
        "source_url": source_url,
        "purpose": purpose,
        "analysis_text": analysis_text,
        "reference_urls": reference_urls,
        "expected": {
            "verdict": verdict,
            "domain": domain,
        },
        "snapshot_overrides": make_snapshot(reference_urls, extraction_score=extraction_score),
        "source_verdict_label": source_verdict_label,
    }


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


def extract_meta(text: str, property_name: str) -> str:
    match = re.search(rf'<meta property="{re.escape(property_name)}" content="([^"]+)"', text)
    return html.unescape(match.group(1)) if match else ""


def extract_jfc_verdict(text: str) -> str | None:
    description = extract_meta(text, "og:description")
    if description:
        match = re.search(r"(正確|ほぼ正確|根拠不明|不正確|誤り)です", description)
        if match:
            return match.group(1)

    match = re.search(r'<h2 id="[^"]*%E5%88%A4%E5%AE%9A[^"]*">判定</h2><p>(.*?)</p>', text, re.S)
    if not match:
        match = re.search(r">判定</h2><p>(.*?)</p>", text, re.S)
    if not match:
        return None

    block = strip_tags(match.group(1))
    for candidate in ("ほぼ正確", "正確", "根拠不明", "不正確", "誤り"):
        if candidate in block:
            return candidate
    return None


def build_jfc_case(spec: dict, index: int) -> dict:
    text = fetch_html(spec["url"])
    verdict = extract_jfc_verdict(text)
    if verdict is None:
        verdict = spec["verdict"]
    elif verdict != spec["verdict"]:
        raise ValueError(f"Unexpected JFC verdict for {spec['url']}: {verdict}")

    raw_title = extract_meta(text, "og:title")
    description = extract_meta(text, "og:description")
    site_name = "日本ファクトチェックセンター"
    title = clean_title(raw_title, site_name=None)
    slug = slug_from_url(spec["url"])
    analysis_text = ANALYSIS_TEXT_OVERRIDES.get(slug) or JFC_ANALYSIS_OVERRIDES.get(slug) or summary_from_description(description)
    if not analysis_text:
        raise ValueError(f"Missing JFC analysis_text for {spec['url']}")

    reference_urls = [spec["url"]]
    return build_case(
        index=index,
        verdict=spec["verdict"],
        slug=slug,
        title=title,
        site_name=site_name,
        source_url=spec["url"],
        purpose="日本ファクトチェックセンターの公開ファクトチェック記事を基にした実在ネット記事ケース",
        analysis_text=analysis_text,
        domain=classify_domain(title, analysis_text),
        reference_urls=reference_urls,
        source_verdict_label=spec["verdict"],
    )


def extract_infact_verdict(text: str) -> str | None:
    title = extract_meta(text, "og:title")
    description = extract_meta(text, "og:description")
    for source in (title, description):
        if "【ほぼ正確】" in source or "は「ほぼ正確」" in source:
            return "ほぼ正確"
        if "【正確】" in source or "は「正確」" in source:
            return "正確"
    match = re.search(r"結論[^【]*【(正確|ほぼ正確)】", description)
    return match.group(1) if match else None


def build_infact_direct_case(spec: dict, index: int) -> dict:
    text = fetch_html(spec["url"])
    verdict = extract_infact_verdict(text)
    if verdict is None:
        verdict = spec["verdict"]
    elif verdict != spec["verdict"]:
        raise ValueError(f"Unexpected InFact verdict for {spec['url']}: {verdict}")

    slug = slug_from_url(spec["url"])
    raw_title = extract_meta(text, "og:title")
    description = extract_meta(text, "og:description")
    site_name = "InFact"
    title = clean_title(spec.get("title_override") or raw_title, site_name=site_name)
    analysis_text = normalize_whitespace(
        ANALYSIS_TEXT_OVERRIDES.get(slug) or spec.get("analysis_override") or summary_from_description(description)
    )
    if not analysis_text:
        raise ValueError(f"Missing InFact analysis_text for {spec['url']}")

    reference_urls = [spec["url"]]
    return build_case(
        index=index,
        verdict=spec["verdict"],
        slug=slug,
        title=title,
        site_name=site_name,
        source_url=spec["url"],
        purpose="InFact の公開ファクトチェック記事を基にした実在ネット記事ケース",
        analysis_text=analysis_text,
        domain=spec.get("domain_override") or classify_domain(title, analysis_text),
        reference_urls=reference_urls,
        source_verdict_label=spec["verdict"],
        id_override=spec.get("id_override"),
    )


def build_fij_case(spec: dict, index: int) -> dict:
    text = fetch_html(spec["url"])
    slug = slug_from_url(spec["url"])
    rating_match = re.search(r'/uploads/rating/[a-z-]+\.png" alt="([^"]+)"', text)
    if not rating_match:
        raise ValueError(f"Missing FIJ rating for {spec['url']}")

    rating = rating_match.group(1)
    verdict = "ほぼ正確" if rating == "おおむね正確" else rating
    if verdict != spec["verdict"]:
        raise ValueError(f"Unexpected FIJ verdict for {spec['url']}: {verdict}")

    title_match = re.search(r'<title>(.*?)</title>', text, re.S)
    page_title = strip_tags(title_match.group(1)) if title_match else spec["url"]

    source_block_match = re.search(r'<div class="post-source-media">(.*?)<span class="note">', text, re.S)
    if not source_block_match:
        raise ValueError(f"Missing FIJ source block for {spec['url']}")
    source_block = source_block_match.group(1)

    hrefs = re.findall(r'<a href="([^"]+)"[^>]*target="_blank"', source_block)
    original_url = next(
        (
            href
            for href in hrefs
            if href.startswith("http")
            and "fontawesome" not in href
            and "?s=" not in href
            and "/category/" not in href
        ),
        spec["url"],
    )

    source_title_match = re.search(r'<p class="title"><a href="[^"]+"[^>]*>(.*?)</a>', source_block, re.S)
    source_title = strip_tags(source_title_match.group(1)) if source_title_match else page_title

    note_match = re.search(r'<span class="note">(.*?)</span>', text)
    site_name = strip_tags(note_match.group(1)) if note_match else ""
    if not site_name:
        bracket_match = re.search(r"【([^】]+)】", source_title)
        site_name = bracket_match.group(1) if bracket_match else "FactCheck Navi"

    summary_match = re.search(r'<p class="source_content">(.*?)</p>', text, re.S)
    summary = strip_tags(summary_match.group(1)) if summary_match else ""
    if not summary:
        raise ValueError(f"Missing FIJ summary for {spec['url']}")

    title = clean_title(spec.get("title_override") or source_title, site_name=site_name)
    analysis_text = normalize_whitespace(ANALYSIS_TEXT_OVERRIDES.get(slug) or spec.get("analysis_override") or summary)
    source_url = original_url
    reference_urls = [source_url]
    if source_url != spec["url"]:
        reference_urls.append(spec["url"])

    return build_case(
        index=index,
        verdict=spec["verdict"],
        slug=slug,
        title=title,
        site_name=site_name,
        source_url=source_url,
        purpose=f"FactCheck Navi が集約した {site_name} の公開ファクトチェック記事を基にした実在ネット記事ケース",
        analysis_text=analysis_text,
        domain=spec.get("domain_override") or classify_domain(title, analysis_text),
        reference_urls=reference_urls,
        source_verdict_label=rating,
        extraction_score=80,
    )


def build_kobe_manual_case(spec: dict, index: int) -> dict:
    analysis_text = ANALYSIS_TEXT_OVERRIDES.get(spec["slug"]) or spec["analysis_text"]
    return build_case(
        index=index,
        verdict=spec["verdict"],
        slug=spec["slug"],
        title=spec["title"],
        site_name=spec["site_name"],
        source_url=spec["source_url"],
        purpose=spec["purpose"],
        analysis_text=analysis_text,
        domain=spec["domain"],
        reference_urls=spec["reference_urls"],
        source_verdict_label=spec["source_verdict_label"],
        extraction_score=78,
    )


def build_snopes_case(spec: dict, index: int) -> dict:
    slug = slug_from_url(spec["url"])
    text = fetch_html(spec["url"])
    rating_match = re.search(r'"alternateName"\s*:\s*"([^"]+)"', text)
    if not rating_match:
        raise ValueError(f"Missing Snopes rating for {spec['url']}")

    rating = rating_match.group(1)
    verdict = "正確" if rating == "True" else "ほぼ正確" if rating == "Mostly True" else None
    if verdict != spec["verdict"]:
        raise ValueError(f"Unexpected Snopes verdict for {spec['url']}: {rating}")

    reference_urls = [spec["url"]]
    return build_case(
        index=index,
        verdict=spec["verdict"],
        slug=slug,
        title=spec["title"],
        site_name="Snopes",
        source_url=spec["url"],
        purpose="Snopes の公開ファクトチェック記事を基にした、日本関連の実在ネット記事ケース",
        analysis_text=ANALYSIS_TEXT_OVERRIDES.get(slug) or spec["analysis_text"],
        domain=spec["domain"],
        reference_urls=reference_urls,
        source_verdict_label=rating,
        id_override=spec.get("id_override"),
    )


def build_cases() -> list[dict]:
    accurate_cases: list[dict] = []
    mostly_cases: list[dict] = []

    accurate_index = 1
    mostly_index = 1

    for spec in JFC_SELECTED_SPECS:
        builder_name = spec.get("builder")
        if builder_name == "snopes_direct":
            builder = build_snopes_case
        else:
            builder = build_jfc_case
        case = builder(spec, accurate_index if spec["verdict"] == "正確" else mostly_index)
        if spec["verdict"] == "正確":
            accurate_cases.append(case)
            accurate_index += 1
        else:
            mostly_cases.append(case)
            mostly_index += 1

    for spec in FIJ_SELECTED_SPECS:
        builder_name = spec.get("builder")
        if builder_name == "infact_direct":
            builder = build_infact_direct_case
        elif builder_name == "snopes_direct":
            builder = build_snopes_case
        else:
            builder = build_fij_case
        case = builder(spec, accurate_index if spec["verdict"] == "正確" else mostly_index)
        if spec["verdict"] == "正確":
            accurate_cases.append(case)
            accurate_index += 1
        else:
            mostly_cases.append(case)
            mostly_index += 1

    for spec in INFACT_DIRECT_SPECS:
        case = build_infact_direct_case(spec, accurate_index if spec["verdict"] == "正確" else mostly_index)
        if spec["verdict"] == "正確":
            accurate_cases.append(case)
            accurate_index += 1
        else:
            mostly_cases.append(case)
            mostly_index += 1

    for spec in KOBE_MANUAL_SPECS:
        case = build_kobe_manual_case(spec, mostly_index)
        mostly_cases.append(case)
        mostly_index += 1

    for spec in SNOPES_SPECS:
        case = build_snopes_case(spec, accurate_index if spec["verdict"] == "正確" else mostly_index)
        if spec["verdict"] == "正確":
            accurate_cases.append(case)
            accurate_index += 1
        else:
            mostly_cases.append(case)
            mostly_index += 1

    cases = accurate_cases + mostly_cases
    counts = Counter(case["expected"]["verdict"] for case in cases)
    if counts != Counter(TARGET_COUNTS):
        raise ValueError(f"Unexpected positive distribution: {dict(counts)}")
    return cases


def build_payload(cases: list[dict]) -> dict:
    site_distribution = Counter(case["site_name"] for case in cases)
    analysis_text_warnings: dict[str, list[str]] = {}
    for case in cases:
        warnings = collect_analysis_text_warnings(case["id"], case["analysis_text"])
        if warnings:
            analysis_text_warnings[case["id"]] = warnings
    return {
        "meta": {
            "sources": {
                "jfc_direct_cases": len(JFC_SELECTED_SPECS),
                "fij_positive_entries": len(FIJ_SELECTED_SPECS),
                "infact_direct_cases": len(INFACT_DIRECT_SPECS),
                "kobe_curated_cases": len(KOBE_MANUAL_SPECS),
                "snopes_japan_related_cases": len(SNOPES_SPECS),
            },
            "selection_strategy": "JFC の直取り、FactCheck Navi が集約した日本系ファクトチェック記事、InFact の追加正例、神戸新聞の選挙ファクト検証、Snopes の日本関連 True/Mostly True で positive 40 件を構成",
            "case_count": len(cases),
            "distribution": TARGET_COUNTS,
            "site_distribution": dict(site_distribution),
            "analysis_text_guidelines": ANALYSIS_TEXT_GUIDELINES,
            "analysis_text_warning_count": len(analysis_text_warnings),
            "analysis_text_warning_examples": dict(list(analysis_text_warnings.items())[:10]),
        },
        "cases": cases,
    }


def main() -> int:
    cases = build_cases()
    payload = build_payload(cases)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
