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
