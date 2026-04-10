from app.analyzer import (
    build_prompt,
    build_fallback_style_overview,
    build_result_status,
    derive_public_verdict,
    merge_style_overview,
    publicize_result,
    style_key_for_score,
    style_label_for_score,
    style_score_display,
)
from app.config import Settings
from app.models import AnalysisSignal, ResolvedPage


def make_page() -> ResolvedPage:
    return ResolvedPage(
        title="検証用ページ",
        site_name="Example News",
        input_source="manual_text",
        extraction_note="manual input",
        text_preview="検証用の本文プレビューです。",
        extracted_chars=120,
        analysis_text="これは検証用の本文です。十分な長さがあり、解析対象として扱えます。",
    )


def make_style_overview(score: int) -> dict:
    return {
        "status": "テスト用",
        "summary": "書き振り評価のテストです。",
        "score": score,
        "score_display": style_score_display(score),
        "label": style_label_for_score(score),
        "key": style_key_for_score(score),
        "note": None,
        "model": "test-style",
        "highlights": [],
        "signals": [],
    }


def test_fallback_style_overview_ignores_non_style_signals() -> None:
    style_signal = AnalysisSignal(title="強い見出し", score_delta=10, tone="リスク上昇", detail="断定的です。")
    non_style_signal = AnalysisSignal(title="引用リンクなし", score_delta=18, tone="リスク上昇", detail="出典不足です。")

    style_only = build_fallback_style_overview([style_signal])
    mixed = build_fallback_style_overview([style_signal, non_style_signal])

    assert style_only.score == mixed.score
    assert [signal.title for signal in mixed.signals] == ["強い見出し"]


def test_build_result_status_escalates_only_at_style_score_80_or_above() -> None:
    assert build_result_status("自動判定", "概ね整合", 70, {}, {"score": 79}) == "自動判定"
    assert build_result_status("自動判定", "概ね整合", 70, {}, {"score": 80}) == "要人手確認"


def test_gemini_style_review_is_disabled_by_default_in_settings() -> None:
    assert Settings().gemini_style_review_enabled is False


def test_build_prompt_omits_style_review_when_disabled() -> None:
    page = make_page()
    prompt = build_prompt(
        page,
        {
            "domain": "一般",
            "labels": [],
            "reasons": [],
            "source_snapshot": page,
            "evidence_overview": {"claims": [], "links": []},
            "source_profile": {},
        },
        Settings(gemini_style_review_enabled=False),
    )
    assert '"style_review"' not in prompt


def test_build_prompt_mentions_short_claim_guidance_for_short_input() -> None:
    page = make_page()
    prompt = build_prompt(
        page,
        {
            "domain": "一般",
            "labels": [],
            "reasons": [],
            "source_snapshot": page,
            "evidence_overview": {"claims": [], "links": []},
            "source_profile": {},
        },
        Settings(gemini_style_review_enabled=False),
    )

    assert "短文claim評価" in prompt
    assert "それだけで「出典不明」や「信頼できる一次ソース未確認」を付けないでください。" in prompt


def test_merge_style_overview_stays_local_when_gemini_style_review_disabled() -> None:
    overview = merge_style_overview(
        {"signal_breakdown": [], "style_overview": build_fallback_style_overview([]).model_dump()},
        {"output": {"style_review": {"style_score": 90}}},
        Settings(gemini_style_review_enabled=False),
    )
    assert overview["status"] == "ローカル補助判定"


def test_public_verdict_is_not_changed_by_style_score_but_status_is() -> None:
    page = make_page()
    payload = {
        "risk_score": 35,
        "confidence": "中程度",
        "confidence_score": 60,
        "status": "自動判定",
        "summary": "整合しています。",
        "labels": [],
        "reasons": ["テスト理由"],
        "domain": "一般",
        "verification_links": [],
        "caution_level": "ほぼ正確",
        "model_used": "heuristic+gemini-evidence+gemini-style",
        "signal_breakdown": [],
        "evidence_overview": {
            "status": "Gemini根拠比較済み",
            "summary": "外部根拠は大筋で整合しています。",
            "assessment_status": "概ね整合",
            "assessment_summary": "外部根拠は大筋で整合しています。",
            "links": [],
            "grounding_sources": [],
            "claim_reviews": [],
            "grounding_queries": [],
            "retrieved_urls": [],
        },
    }

    low_style = publicize_result(page, {**payload, "style_overview": make_style_overview(30)}, {})
    high_style = publicize_result(page, {**payload, "style_overview": make_style_overview(95)}, {})

    assert low_style.verdict == "ほぼ正確"
    assert high_style.verdict == "ほぼ正確"
    assert low_style.status == "自動判定"
    assert high_style.status == "人による確認推奨"


def test_fact_check_source_is_capped_at_mostly_accurate_without_official_source() -> None:
    verdict = derive_public_verdict(
        risk_score=8,
        confidence_score=90,
        labels=[],
        source_profile={
            "official_source": False,
            "fact_check_source": True,
            "trusted_source": True,
            "correction_article": True,
        },
        evidence_overview={},
    )
    assert verdict == "ほぼ正確"


def test_strong_grounded_alignment_can_be_accurate_without_official_source() -> None:
    verdict = derive_public_verdict(
        risk_score=68,
        confidence_score=44,
        labels=["出典不明", "信頼できる一次ソース未確認", "大筋で整合"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
        },
        evidence_overview={
            "assessment_status": "概ね整合",
            "grounding_sources": [
                {"title": "factcheckcenter.jp", "url": "https://vertexaisearch.cloud.google.com/example-1"},
                {"title": "factcheckcenter.jp", "url": "https://vertexaisearch.cloud.google.com/example-2"},
                {"title": "note.com", "url": "https://vertexaisearch.cloud.google.com/example-3"},
            ],
            "claim_reviews": [
                {"claim": "claim", "verdict": "概ね整合", "reason": "supported"},
            ],
        },
    )
    assert verdict == "正確"


def test_single_official_grounding_source_can_make_supported_research_claim_accurate() -> None:
    verdict = derive_public_verdict(
        risk_score=68,
        confidence_score=42,
        labels=["出典不明", "信頼できる一次ソース未確認", "大筋で整合"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
        },
        evidence_overview={
            "assessment_status": "概ね整合",
            "grounding_sources": [
                {"title": "hokudai.ac.jp", "url": "https://vertexaisearch.cloud.google.com/example-1"},
                {"title": "kidsport.jp", "url": "https://vertexaisearch.cloud.google.com/example-2"},
            ],
            "claim_reviews": [
                {"claim": "claim", "verdict": "概ね整合", "reason": "supported"},
            ],
        },
    )
    assert verdict == "正確"


def test_report_backed_claim_review_can_promote_supported_case_to_accurate() -> None:
    verdict = derive_public_verdict(
        risk_score=52,
        confidence_score=44,
        labels=["出典不明", "信頼できる一次ソース未確認", "大筋で整合"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
        },
        evidence_overview={
            "assessment_status": "概ね整合",
            "grounding_sources": [],
            "claim_reviews": [
                {
                    "claim": "小泉氏の動画は本人の発言である",
                    "verdict": "概ね整合",
                    "reason": "日本ファクトチェックセンターが公式アカウント上の本人発言だと確認している。",
                },
            ],
        },
    )
    assert verdict == "正確"


def test_contextual_caveat_in_claim_review_keeps_case_mostly_accurate() -> None:
    verdict = derive_public_verdict(
        risk_score=52,
        confidence_score=46,
        labels=["出典不明", "信頼できる一次ソース未確認", "大筋で整合"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
        },
        evidence_overview={
            "assessment_status": "概ね整合",
            "grounding_sources": [],
            "claim_reviews": [
                {
                    "claim": "CDCが死亡者はいないと発表した",
                    "verdict": "概ね整合",
                    "reason": "公式見解とは整合するが、接種後死亡と因果関係ありの死亡は区別する必要がある。ただし表現には注意が必要。",
                },
            ],
        },
    )
    assert verdict == "ほぼ正確"


def test_three_grounding_sources_can_promote_supported_case_to_accurate() -> None:
    verdict = derive_public_verdict(
        risk_score=68,
        confidence_score=45,
        labels=["出典不明", "信頼できる一次ソース未確認", "大筋で整合"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
        },
        evidence_overview={
            "assessment_status": "概ね整合",
            "grounding_sources": [
                {"title": "news-a.example", "url": "https://example.com/a"},
                {"title": "news-b.example", "url": "https://example.com/b"},
                {"title": "news-c.example", "url": "https://example.com/c"},
            ],
            "claim_reviews": [
                {
                    "claim": "claim",
                    "verdict": "概ね整合",
                    "reason": "複数の情報源で確認されています。",
                },
            ],
        },
    )
    assert verdict == "正確"


def test_two_generic_grounding_sources_are_not_enough_for_accurate() -> None:
    verdict = derive_public_verdict(
        risk_score=68,
        confidence_score=45,
        labels=["出典不明", "信頼できる一次ソース未確認", "大筋で整合"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
        },
        evidence_overview={
            "assessment_status": "概ね整合",
            "grounding_sources": [
                {"title": "news-a.example", "url": "https://example.com/a"},
                {"title": "news-b.example", "url": "https://example.com/b"},
            ],
            "claim_reviews": [
                {
                    "claim": "claim",
                    "verdict": "概ね整合",
                    "reason": "確認されています。",
                },
            ],
        },
    )
    assert verdict == "ほぼ正確"


def test_non_core_caveat_with_supported_fact_can_still_be_accurate() -> None:
    verdict = derive_public_verdict(
        risk_score=60,
        confidence_score=47,
        labels=["出典不明", "信頼できる一次ソース未確認", "大筋で整合"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
        },
        evidence_overview={
            "assessment_status": "概ね整合",
            "grounding_sources": [
                {"title": "site-a.example", "url": "https://example.com/a"},
                {"title": "site-b.example", "url": "https://example.com/b"},
                {"title": "site-c.example", "url": "https://example.com/c"},
            ],
            "claim_reviews": [
                {
                    "claim": "square watermelon",
                    "verdict": "概ね整合",
                    "reason": "複数の情報源で実在が確認されました。ただし、食用には適さないとされています。",
                },
            ],
        },
    )
    assert verdict == "正確"


def test_value_judgment_claim_review_does_not_promote_to_accurate() -> None:
    verdict = derive_public_verdict(
        risk_score=50,
        confidence_score=50,
        labels=["出典不明", "信頼できる一次ソース未確認", "大筋で整合"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
        },
        evidence_overview={
            "assessment_status": "概ね整合",
            "grounding_sources": [],
            "claim_reviews": [
                {
                    "claim": "115億円分余剰とは全くの無駄遣いです",
                    "verdict": "概ね整合",
                    "reason": "会計検査院の報告で余剰在庫は確認できるが、無駄遣いという評価表現は残る。",
                },
            ],
        },
    )
    assert verdict == "ほぼ正確"


def test_partial_detail_error_claim_review_keeps_case_mostly_accurate_and_mid_band_attention() -> None:
    result = publicize_result(
        make_page(),
        {
            "risk_score": 64,
            "confidence": "中程度",
            "confidence_score": 54,
            "status": "自動判定",
            "summary": "1919年に撮影されたアイヌの踊りの映像は存在するが、オリジナルは白黒である。",
            "labels": ["反証情報あり", "出典不明", "信頼できる一次ソース未確認"],
            "reasons": [
                "1919年にアイヌの踊りが撮影された映像は存在する。",
                "カラー映像はAIによる着色であり、オリジナルは白黒である。",
            ],
            "domain": "一般",
            "verification_links": [],
            "caution_level": "正確",
            "model_used": "heuristic+gemini-evidence+gemini-style",
            "signal_breakdown": [],
            "evidence_overview": {
                "status": "Gemini根拠比較済み",
                "summary": "外部根拠は大筋で整合しています。",
                "assessment_status": "概ね整合",
                "assessment_summary": "外部根拠は大筋で整合しています。",
                "links": [],
                "grounding_sources": [
                    {"title": "factcheckcenter.jp", "url": "https://example.com/1", "kind": "Gemini参照ソース"},
                    {"title": "nibutani-ainu-museum.com", "url": "https://example.com/2", "kind": "Gemini参照ソース"},
                    {"title": "nii.ac.jp", "url": "https://example.com/3", "kind": "Gemini参照ソース"},
                ],
                "claim_reviews": [
                    {
                        "claim": "アイヌの踊りが1919年に撮影され、カラー映像で保存されていた",
                        "verdict": "概ね整合",
                        "reason": "1919年にアイヌの踊りが撮影された映像は存在するが、オリジナルは白黒であり、カラー映像はAIによって着色されたものであるため、「カラー映像で保存されていた」という主張は不正確である。",
                    }
                ],
                "grounding_queries": [],
                "retrieved_urls": [],
            },
        },
        {
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
        },
    )

    assert result.verdict == "ほぼ正確"
    assert result.attention_score is not None
    assert 21 <= result.attention_score <= 40


def test_generic_supported_claim_with_slight_numeric_gap_stays_mostly_accurate() -> None:
    verdict = derive_public_verdict(
        risk_score=68,
        confidence_score=51,
        labels=["出典不明", "信頼できる一次ソース未確認", "大筋で整合"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
        },
        evidence_overview={
            "assessment_status": "概ね整合",
            "grounding_sources": [
                {"title": "site-a.example", "url": "https://example.com/a"},
                {"title": "site-b.example", "url": "https://example.com/b"},
                {"title": "site-c.example", "url": "https://example.com/c"},
            ],
            "claim_reviews": [
                {
                    "claim": "claim",
                    "verdict": "概ね整合",
                    "reason": "数値自体は概ね整合しているが、わずかな差異がある。",
                },
            ],
        },
    )
    assert verdict == "ほぼ正確"


def test_name_correction_in_supported_claim_stays_mostly_accurate() -> None:
    verdict = derive_public_verdict(
        risk_score=68,
        confidence_score=53,
        labels=["出典不明", "信頼できる一次ソース未確認", "大筋で整合"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
        },
        evidence_overview={
            "assessment_status": "概ね整合",
            "grounding_sources": [
                {"title": "wikipedia.org", "url": "https://example.com/a"},
                {"title": "gaga.ne.jp", "url": "https://example.com/b"},
                {"title": "naxos.jp", "url": "https://example.com/c"},
            ],
            "claim_reviews": [
                {
                    "claim": "三大テノールとは、ルチアーノ・パヴァロッティ、プラシド・ドミンゴ、ホセ・カレーライスの3名である",
                    "verdict": "概ね整合",
                    "reason": "三大テノールは、ルチアーノ・パヴァロッティ、プラシド・ドミンゴ、ホセ・カレーラスの3名のテノール歌手を指す名称である。",
                },
            ],
        },
    )
    assert verdict == "ほぼ正確"


def test_kanji_name_correction_in_supported_claim_stays_mostly_accurate() -> None:
    verdict = derive_public_verdict(
        risk_score=44,
        confidence_score=59,
        labels=["大筋で整合"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
        },
        evidence_overview={
            "assessment_status": "概ね整合",
            "grounding_sources": [
                {"title": "wikipedia.org", "url": "https://example.com/a"},
                {"title": "natalie.mu", "url": "https://example.com/b"},
            ],
            "claim_reviews": [
                {
                    "claim": "玉置浩二は、日本のシンガーソングライター、ロックバンド完全地帯のボーカリストで、北海道旭川市出身である",
                    "verdict": "概ね整合",
                    "reason": "玉置浩二は日本のシンガーソングライターであり、ロックバンド安全地帯のボーカリストで、北海道旭川市出身である。",
                },
            ],
        },
    )
    assert verdict == "ほぼ正確"


def test_split_supported_claim_with_one_name_correction_stays_mostly_accurate() -> None:
    verdict = derive_public_verdict(
        risk_score=48,
        confidence_score=71,
        labels=["反証情報あり", "文脈不足に注意"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "反証あり",
            "grounding_sources": [
                {"title": "columbia.jp", "url": "https://example.com/a"},
                {"title": "natalie.mu", "url": "https://example.com/b"},
            ],
            "claim_reviews": [
                {
                    "claim": "玉置浩二は、日本のシンガーソングライターである。",
                    "verdict": "概ね整合",
                    "reason": "玉置浩二は日本のシンガーソングライターである。",
                },
                {
                    "claim": "玉置浩二は、ロックバンド完全地帯のボーカリストである。",
                    "verdict": "反証あり",
                    "reason": "玉置浩二がボーカリストを務めるロックバンドは「安全地帯」であり、「完全地帯」は誤りです。",
                },
                {
                    "claim": "玉置浩二は、北海道旭川市出身である。",
                    "verdict": "概ね整合",
                    "reason": "玉置浩二は北海道旭川市出身である。",
                },
            ],
        },
        claim_mode=True,
    )
    assert verdict == "ほぼ正確"


def test_single_counterevidence_review_with_supported_core_and_name_correction_stays_mostly_accurate() -> None:
    verdict = derive_public_verdict(
        risk_score=54,
        confidence_score=69,
        labels=["反証情報あり", "文脈不足に注意"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "反証あり",
            "grounding_sources": [
                {"title": "columbia.jp", "url": "https://example.com/a"},
                {"title": "wikipedia.org", "url": "https://example.com/b"},
            ],
            "claim_reviews": [
                {
                    "claim": "玉置浩二は、日本のシンガーソングライター、ロックバンド完全地帯のボーカリストで、北海道旭川市出身である",
                    "verdict": "反証あり",
                    "reason": "玉置浩二は日本のシンガーソングライターであり、北海道旭川市出身であることは複数の情報源で確認できる。しかし、所属するロックバンドの名称は「安全地帯」であり、「完全地帯」ではないため、主張は一部誤りである。",
                },
            ],
        },
        claim_mode=True,
    )
    assert verdict == "ほぼ正確"


def test_self_inflicted_death_correction_in_supported_claim_stays_mostly_accurate() -> None:
    verdict = derive_public_verdict(
        risk_score=34,
        confidence_score=71,
        labels=["一次ソースと整合"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "概ね整合",
            "grounding_sources": [
                {"title": "city.kameoka.kyoto.jp", "url": "https://example.com/a"},
                {"title": "wikipedia.org", "url": "https://example.com/b"},
            ],
            "claim_reviews": [
                {
                    "claim": "織田信長は本能寺の変で明智光秀に殺された。",
                    "verdict": "概ね整合",
                    "reason": "複数の歴史資料や報道機関の記事が、織田信長が本能寺の変において明智光秀の謀反により死亡したことを示しています。信長は本能寺で襲撃され、自害したとされています。",
                },
            ],
        },
        claim_mode=True,
    )
    assert verdict == "ほぼ正確"


def test_single_counterevidence_review_with_numeric_detail_correction_can_be_mostly_accurate() -> None:
    verdict = derive_public_verdict(
        risk_score=54,
        confidence_score=69,
        labels=["反証情報あり", "文脈不足に注意"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "反証あり",
            "claim_reviews": [
                {
                    "claim": "イチローは29年間のプロ野球選手生活で日米通算4367安打を記録した。",
                    "verdict": "反証あり",
                    "reason": "イチローの日米通算安打数は4367本で複数の情報源と整合しますが、プロ野球選手生活は28年間であり、29年間ではありません。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "ほぼ正確"


def test_single_counterevidence_review_with_scope_correction_can_be_mostly_accurate() -> None:
    verdict = derive_public_verdict(
        risk_score=50,
        confidence_score=71,
        labels=["反証情報あり", "文脈不足に注意"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "反証あり",
            "claim_reviews": [
                {
                    "claim": "ペンギンはみんな南極に住んでいる。",
                    "verdict": "反証あり",
                    "reason": "ペンギンは南極大陸だけでなく、亜南極圏の島々、オーストラリア、南米、アフリカの各大陸南部、赤道直下のガラパゴス諸島など、南半球の幅広い地域に生息しています。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "ほぼ正確"


def test_single_counterevidence_review_with_same_group_omission_can_be_mostly_accurate() -> None:
    verdict = derive_public_verdict(
        risk_score=54,
        confidence_score=68,
        labels=["反証情報あり", "文脈不足に注意"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "反証あり",
            "claim_reviews": [
                {
                    "claim": "大谷翔平と同学年の日本人メージャーリーガーは鈴木誠也である。",
                    "verdict": "反証あり",
                    "reason": "大谷翔平選手と鈴木誠也選手は共に1994年生まれで同学年ですが、同じく1994年生まれの日本人メジャーリーガーには藤浪晋太郎選手もいます。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "ほぼ正確"


def test_counterevidence_with_supported_core_and_corrective_detail_can_be_mostly_accurate() -> None:
    verdict = derive_public_verdict(
        risk_score=79,
        confidence_score=48,
        labels=["信頼できる一次ソース未確認", "判定不能", "出典不明", "文脈不足に注意"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
        },
        evidence_overview={
            "assessment_status": "要追加確認",
            "claim_reviews": [
                {
                    "claim": "claim",
                    "verdict": "要追加確認",
                    "reason": "有権者による承認、税率、対象は確認できた。しかし本文の歳入額の一次ソースは確認できない。",
                }
            ],
        },
    )
    assert verdict == "ほぼ正確"


def test_non_trusted_low_risk_without_evidence_stays_unknown() -> None:
    verdict = derive_public_verdict(
        risk_score=36,
        confidence_score=69,
        labels=[],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
        },
        evidence_overview={},
    )
    assert verdict == "判断保留"


def test_non_trusted_low_risk_with_stronger_confidence_can_remain_mostly_accurate() -> None:
    verdict = derive_public_verdict(
        risk_score=32,
        confidence_score=72,
        labels=[],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
        },
        evidence_overview={},
    )
    assert verdict == "ほぼ正確"


def test_high_risk_source_gap_escalates_to_false_when_no_evidence_status() -> None:
    verdict = derive_public_verdict(
        risk_score=80,
        confidence_score=45,
        labels=["出典不明", "信頼できる一次ソース未確認"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
        },
        evidence_overview={},
    )
    assert verdict == "誤り"


def test_fact_check_source_can_remain_mostly_accurate_in_mid_risk_band() -> None:
    verdict = derive_public_verdict(
        risk_score=46,
        confidence_score=58,
        labels=["信頼できる一次ソース未確認", "追加確認が必要"],
        source_profile={
            "official_source": False,
            "fact_check_source": True,
            "trusted_source": True,
            "correction_article": False,
        },
        evidence_overview={},
    )
    assert verdict == "ほぼ正確"


def test_non_trusted_mid_risk_low_confidence_escalates_to_inaccurate() -> None:
    verdict = derive_public_verdict(
        risk_score=46,
        confidence_score=59,
        labels=["判定不能", "追加確認が必要"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
        },
        evidence_overview={},
    )
    assert verdict == "不正確"


def test_non_trusted_high_confidence_near_unknown_boundary_can_stay_mostly_accurate() -> None:
    verdict = derive_public_verdict(
        risk_score=44,
        confidence_score=73,
        labels=["追加確認が必要"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
        },
        evidence_overview={},
    )
    assert verdict == "ほぼ正確"


def test_counterevidence_with_source_gap_can_move_to_inaccurate() -> None:
    verdict = derive_public_verdict(
        risk_score=92,
        confidence_score=53,
        labels=["反証情報あり", "出典不明", "信頼できる一次ソース未確認"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
        },
        evidence_overview={"assessment_status": "反証あり"},
    )
    assert verdict == "不正確"


def test_counterevidence_with_source_gap_can_be_false_when_refutation_is_strong() -> None:
    verdict = derive_public_verdict(
        risk_score=88,
        confidence_score=51,
        labels=["反証情報あり", "出典不明", "信頼できる一次ソース未確認", "文脈不足に注意"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
        },
        evidence_overview={"assessment_status": "反証あり"},
    )
    assert verdict == "誤り"


def test_counterevidence_with_source_gap_and_extra_check_stays_non_false() -> None:
    verdict = derive_public_verdict(
        risk_score=88,
        confidence_score=51,
        labels=["反証情報あり", "出典不明", "信頼できる一次ソース未確認", "追加確認が必要"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
        },
        evidence_overview={"assessment_status": "反証あり"},
    )
    assert verdict == "不正確"


def test_counterevidence_without_source_gap_can_be_inaccurate_before_false() -> None:
    verdict = derive_public_verdict(
        risk_score=77,
        confidence_score=60,
        labels=["反証情報あり"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
        },
        evidence_overview={"assessment_status": "反証あり"},
    )
    assert verdict == "不正確"


def test_counterevidence_without_source_gap_can_be_false_with_slightly_lower_threshold() -> None:
    verdict = derive_public_verdict(
        risk_score=78,
        confidence_score=50,
        labels=["反証情報あり"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
        },
        evidence_overview={"assessment_status": "反証あり"},
    )
    assert verdict == "誤り"


def test_split_claim_with_supported_core_but_wrong_manager_stays_inaccurate() -> None:
    verdict = derive_public_verdict(
        risk_score=51,
        confidence_score=70,
        labels=["反証情報あり", "大筋で整合"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "反証あり",
            "claim_reviews": [
                {
                    "claim": "2023年のWBCで大谷翔平の活躍もあり、野球日本代表は優勝した。",
                    "verdict": "概ね整合",
                    "reason": "2023年のWBCで野球日本代表は優勝し、大谷翔平選手はMVPに輝くなど活躍しました。",
                },
                {
                    "claim": "その時の監督は王貞治だった。",
                    "verdict": "反証あり",
                    "reason": "2023年のWBCにおける野球日本代表の監督は栗山英樹氏でした。王貞治氏は2006年のWBCで監督を務めました。",
                },
            ],
        },
        claim_mode=True,
    )
    assert verdict == "不正確"


def test_multi_error_counterevidence_review_stays_inaccurate() -> None:
    verdict = derive_public_verdict(
        risk_score=54,
        confidence_score=69,
        labels=["反証情報あり", "大筋で整合"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "反証あり",
            "claim_reviews": [
                {
                    "claim": "スタジオジブリ制作のアニメ映画「となりのトトロ」と「火垂るの墓」は1988年4月に同時上映された。「となりのトトロ」は高畑勲、「火垂るの墓」は宮崎駿の監督作品で、プロデューサーは庵野秀明だった。",
                    "verdict": "反証あり",
                    "reason": "スタジオジブリ制作の「となりのトトロ」と「火垂るの墓」は1988年4月16日に同時上映されたことは概ね整合する。しかし、「となりのトトロ」の監督は宮崎駿、「火垂るの墓」の監督は高畑勲であり、主張とは逆である。また、両作品のプロデューサーは原徹であり、庵野秀明ではない。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "不正確"


def test_pairwise_all_members_claim_stays_inaccurate_when_one_member_fails() -> None:
    verdict = derive_public_verdict(
        risk_score=54,
        confidence_score=69,
        labels=["反証情報あり", "大筋で整合"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "反証あり",
            "claim_reviews": [
                {
                    "claim": "新選組の土方歳三・斎藤一は戊辰戦争を戦い抜いたが、最後は函館で二人とも戦死した。",
                    "verdict": "反証あり",
                    "reason": "土方歳三は函館戦争で戦死したが、斎藤一は戊辰戦争を生き延び、明治時代に東京で病死したことが複数の情報源で確認できるため、二人とも函館で戦死したという主張は誤りである。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "不正確"


def test_type_noun_swap_stays_inaccurate_even_when_entity_frame_matches() -> None:
    verdict = derive_public_verdict(
        risk_score=54,
        confidence_score=68,
        labels=["反証情報あり", "大筋で整合"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "反証あり",
            "claim_reviews": [
                {
                    "claim": "ドラえもんは22世紀の未来の日本から来た犬型ロボットである。",
                    "verdict": "反証あり",
                    "reason": "ドラえもんは22世紀の未来から来たネコ型ロボットであり、犬型ロボットではありません。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "不正確"


def test_multi_sentence_claim_with_correct_date_but_wrong_penalty_stays_inaccurate() -> None:
    verdict = derive_public_verdict(
        risk_score=50,
        confidence_score=71,
        labels=["反証情報あり", "大筋で整合"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "反証あり",
            "claim_reviews": [
                {
                    "claim": "2025年10月1日豊明市スマートフォン等の適正使用の推進に関する条例が施行された。違反すると罰金などの罰則がある。",
                    "verdict": "反証あり",
                    "reason": "豊明市スマートフォン等の適正使用の推進に関する条例は2025年10月1日に施行されましたが、複数の情報源によると、この条例には罰則規定がありません。この条例は理念条例であり、市民の権利を制限したり、義務を課したりするものではないとされています。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "不正確"


def test_causal_multi_clause_numeric_claim_stays_inaccurate() -> None:
    verdict = derive_public_verdict(
        risk_score=52,
        confidence_score=70,
        labels=["反証情報あり", "大筋で整合"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "反証あり",
            "claim_reviews": [
                {
                    "claim": "9.11テロを起こしたウサマ・ビンラディンをイラクのサダム・フセインが匿ったため、2003年アメリカはイラクを攻撃し、イラク戦争が始まった。",
                    "verdict": "反証あり",
                    "reason": "9.11テロの首謀者ウサマ・ビンラディンはアフガニスタンのタリバン政権に匿われており、イラクのサダム・フセインが匿ったという事実は確認されていません。イラク戦争の開戦理由とされた大量破壊兵器の存在やテロ組織との関連性も後に否定されています。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "不正確"


def test_single_numeric_attribute_without_supported_core_can_stay_inaccurate() -> None:
    verdict = derive_public_verdict(
        risk_score=54,
        confidence_score=67,
        labels=["反証情報あり", "大筋で整合"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "反証あり",
            "claim_reviews": [
                {
                    "claim": "世界最高のテノールの一人とされるルチアーノ・パヴァロッティだが、身長は160cmと小柄だった。",
                    "verdict": "反証あり",
                    "reason": "複数の情報源によると、ルチアーノ・パヴァロッティの身長は180cmまたは188cmであり、160cmという主張は事実と異なります。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "不正確"


def test_false_claim_mode_conspiracy_counterevidence_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=52,
        confidence_score=68,
        labels=["反証情報あり", "文脈不足に注意"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "反証あり",
            "claim_reviews": [
                {
                    "claim": "飛行機雲は、政府などが危険な化学物質を散布している「ケムトレイル」である。",
                    "verdict": "反証あり",
                    "reason": "「ケムトレイル」説は陰謀論であり、科学的根拠がなく、公的機関やファクトチェック機関によって誤りであると繰り返し否定されています。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_nonexistent_law_counterevidence_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=52,
        confidence_score=68,
        labels=["反証情報あり", "文脈不足に注意"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "反証あり",
            "claim_reviews": [
                {
                    "claim": "日本はモスク建設やブルカの着用などを禁じる反イスラム法を制定した。",
                    "verdict": "反証あり",
                    "reason": "日本国憲法は信教の自由を保障しており、そのような法律は制定されていません。文化庁宗務課もそのような法律の存在を否定しています。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_fake_quote_counterevidence_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=52,
        confidence_score=68,
        labels=["反証情報あり", "文脈不足に注意"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "反証あり",
            "claim_reviews": [
                {
                    "claim": "世田谷区で韓国籍女性が殺害された事件について、韓国の李在明大統領が「日本は謝罪と賠償をするべきだ」と発言した。",
                    "verdict": "反証あり",
                    "reason": "日本ファクトチェックセンターによると、そのような発言をしたという事実はなく、拡散された情報はまとめサイトによる誤りであるとされています。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_fake_or_modified_image_counterevidence_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=52,
        confidence_score=67,
        labels=["反証情報あり", "文脈不足に注意"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "反証あり",
            "claim_reviews": [
                {
                    "claim": "朝日新聞の入社式では、社旗の脇に韓国と中国の国旗を並べ、ハングル文字を掲げていた。",
                    "verdict": "反証あり",
                    "reason": "この画像は2013年度入社式の写真が第三者によって意図的に加工されたものであると確認されています。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_generated_ai_image_counterevidence_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=52,
        confidence_score=67,
        labels=["反証情報あり", "文脈不足に注意"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "反証あり",
            "claim_reviews": [
                {
                    "claim": "天皇陛下や上皇陛下がジェフリー・エプスタイン氏と一緒に写っている写真は本物だ。",
                    "verdict": "反証あり",
                    "reason": "この写真は生成AIによるフェイク画像であり、実際には存在しません。ディープフェイク検知でも生成AI由来と判定されています。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_mistranslated_quote_counterevidence_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=52,
        confidence_score=67,
        labels=["反証情報あり", "文脈不足に注意"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "反証あり",
            "claim_reviews": [
                {
                    "claim": "トランプ氏が、現在の中東情勢を受けて「私は核兵器を使う最後の人間になるだろう」と発言した。",
                    "verdict": "反証あり",
                    "reason": "この発言は2016年のものであり、現在の中東情勢を受けたものではなく、英語の原文の解釈も誤っていることがファクトチェック記事で指摘されています。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"
