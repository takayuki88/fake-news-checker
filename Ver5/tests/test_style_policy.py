from app.analyzer import (
    apply_gemini_primary_review,
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
from app.evidence_search import build_evidence_links
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
    assert '"primary_review"' not in prompt
    assert "役割は次の1つ" in prompt


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


def test_build_prompt_mentions_quote_verification_guidance_for_claim_mode() -> None:
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

    assert "引用句そのもの、話者、発言時期、元の文脈" in prompt
    assert "英語原文や過去発言" in prompt


def test_build_evidence_links_add_quote_search_links_for_quoted_claim() -> None:
    links = build_evidence_links(
        ["トランプ氏が「私は核兵器を使う最後の人間になるだろう」と発言した。"],
        "一般",
    )

    assert links[0].kind == "外部根拠探索/引用検索"
    assert links[1].kind == "外部根拠探索/引用文脈"
    assert "私は核兵器を使う最後の人間になるだろう" in links[0].title


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


def test_apply_gemini_primary_review_blends_seed_scores_and_summary() -> None:
    seed = {
        "risk_score": 72,
        "confidence": "判定不能",
        "confidence_score": 40,
        "status": "自動判定",
        "summary": "heuristic summary",
        "labels": ["判定不能"],
        "reasons": ["heuristic reason"],
        "domain": "一般",
        "caution_level": "不正確",
        "signal_breakdown": [],
        "source_profile": {},
    }
    llm_output = {
        "primary_review": {
            "domain": "医療",
            "risk_score": 18,
            "confidence_score": 82,
            "summary": "Gemini の一次判定です。",
            "labels": ["反証情報あり", "unknown label"],
            "reasons": ["Gemini reason"],
        }
    }

    merged = apply_gemini_primary_review(seed, llm_output)

    assert merged["primary_review_raw_risk_score"] == 18
    assert merged["risk_score"] == 52
    assert merged["confidence_score"] == 56
    assert merged["status"] == "Gemini一次判定"
    assert merged["summary"] == "Gemini の一次判定です。"
    assert merged["domain"] == "医療"
    assert merged["labels"] == ["反証情報あり", "判定不能"]
    assert merged["reasons"] == ["Gemini reason", "heuristic reason"]


def test_apply_gemini_primary_review_keeps_seed_when_primary_review_missing() -> None:
    seed = {
        "risk_score": 35,
        "confidence": "モデルの確信度",
        "confidence_score": 60,
        "status": "自動判定",
        "summary": "heuristic summary",
        "labels": [],
        "reasons": ["heuristic reason"],
        "domain": "一般",
        "caution_level": "ほぼ正確",
        "signal_breakdown": [],
        "source_profile": {},
    }

    merged = apply_gemini_primary_review(seed, {})

    assert merged is seed


def test_apply_gemini_primary_review_skips_claim_mode_seed() -> None:
    seed = {
        "risk_score": 35,
        "confidence": "モデルの確信度",
        "confidence_score": 60,
        "status": "自動判定",
        "summary": "heuristic summary",
        "labels": [],
        "reasons": ["heuristic reason"],
        "domain": "一般",
        "caution_level": "ほぼ正確",
        "signal_breakdown": [],
        "source_profile": {"claim_mode": True},
    }
    llm_output = {
        "primary_review": {
            "domain": "医療",
            "risk_score": 90,
            "confidence_score": 90,
            "summary": "Gemini の一次判定です。",
            "labels": ["反証情報あり"],
            "reasons": ["Gemini reason"],
        }
    }

    merged = apply_gemini_primary_review(seed, llm_output)

    assert merged is seed


def test_false_claim_mode_helpers_accept_current_reason_wordings() -> None:
    cases = [
        (
            "5Gが新型コロナを引き起こす",
            "5Gの電磁波が新型コロナウイルスを引き起こしたり、ウイルスの拡散を助けたりするという科学的根拠は全くありません。WHOやCDCなどの専門機関がこの主張を否定しており、5Gが導入されていない地域でも新型コロナウイルスは蔓延しています。",
            16,
            81,
        ),
        (
            "1969年のアポロ月面着陸は捏造である",
            "アポロ計画による月面着陸は、月面から持ち帰られた岩石、月面に設置されたレーザー反射鏡、現代の月探査機による着陸地点の痕跡の撮影、および多数の関係者が関与しているにもかかわらず捏造を認める証言がないことなど、複数の科学的証拠と独立した検証によって事実であることが確認されています。旗がなびいているように見える、星が写っていない、影の異常といった陰謀論の主な根拠も、科学的に説明されています。",
            34,
            81,
        ),
        (
            "ミスタージャイアンツとはイチローのことである",
            "「ミスタージャイアンツ」は、読売ジャイアンツで活躍した長嶋茂雄氏の愛称として広く知られており、イチロー氏を指すという情報は見つかりませんでした。",
            16,
            81,
        ),
        (
            "工藤新一と江戸川コナンは同一人物でない",
            "漫画『名探偵コナン』の主人公である江戸川コナンの本名は工藤新一であり、黒の組織の薬によって体が小さくなった姿であると公式情報や関連情報で明記されているため、同一人物でないという主張は誤りである。",
            16,
            80,
        ),
        (
            "関東大震災で朝鮮人が井戸に毒を入れた",
            "関東大震災時に「朝鮮人が井戸に毒を入れた」という情報は、当時の混乱の中で広まった根拠のないデマ（流言）であり、事実ではないことが複数の資料で確認されています。このデマが朝鮮人虐殺を引き起こしました。",
            14,
            82,
        ),
        (
            "西郷隆盛は西南戦争で勝利した",
            "西南戦争は1877年に発生した日本最後の内戦であり、明治政府（新政府軍）が勝利し、西郷隆盛率いる私学校党は敗北しました。西郷隆盛は城山での最後の戦いで最期を遂げています。",
            16,
            80,
        ),
    ]

    for claim, reason, risk_score, confidence_score in cases:
        verdict = derive_public_verdict(
            risk_score=risk_score,
            confidence_score=confidence_score,
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
                        "claim": claim,
                        "verdict": "反証あり",
                        "reason": reason,
                    }
                ],
            },
            claim_mode=True,
        )
        assert verdict == "誤り"


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


def test_supported_claim_with_numeric_phrase_is_not_mistaken_for_name_correction_and_can_be_accurate() -> None:
    verdict = derive_public_verdict(
        risk_score=35,
        confidence_score=62,
        labels=["大筋で整合"],
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
                {"title": "factcheckcenter.jp", "url": "https://example.com/a"},
                {"title": "factcheckcenter.jp", "url": "https://example.com/b"},
            ],
            "claim_reviews": [
                {
                    "claim": "NHKが「集団生贄200人」という歌詞の歌を放映した",
                    "verdict": "概ね整合",
                    "reason": "NHKは2023年7月18日に放送された番組「まやまやぽん！」において、「いけにえたくさん見届けてきたよ しゅうだんいけにえ200人！」などの歌詞を含む歌を放映したことが、日本ファクトチェックセンターや週刊女性PRIMEなどの報道機関によって確認されています。",
                },
            ],
        },
        claim_mode=True,
    )
    assert verdict == "正確"


def test_supported_negative_fact_claim_is_not_mistaken_for_name_correction_and_can_be_accurate() -> None:
    verdict = derive_public_verdict(
        risk_score=35,
        confidence_score=63,
        labels=["大筋で整合"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "概ね整合",
            "claim_reviews": [
                {
                    "claim": "日本人最初のメジャーリーガーは野茂英雄ではない。",
                    "verdict": "概ね整合",
                    "reason": "多くの情報源が、1964年にメジャーリーグでプレーした村上雅則が日本人初のメジャーリーガーであると報じているため。野茂英雄は1995年にメジャーデビューしたが、彼が最初ではない。",
                },
            ],
        },
        claim_mode=True,
    )
    assert verdict == "正確"


def test_supported_claim_with_honorific_suffix_is_not_mistaken_for_name_correction_and_can_be_accurate() -> None:
    verdict = derive_public_verdict(
        risk_score=23,
        confidence_score=69,
        labels=["大筋で整合"],
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
                {"title": "edogawa-u.ac.jp", "url": "https://example.com/a"},
            ],
            "claim_reviews": [
                {
                    "claim": "大谷翔平は、メジャーリーグ史上初めてシーズン50本塁打50盗塁を達成した。",
                    "verdict": "概ね整合",
                    "reason": "大谷翔平選手は2024年9月19日（日本時間20日）にメジャーリーグ史上初のシーズン50本塁打50盗塁を達成したと複数の主要報道機関や情報源が報じています。",
                },
            ],
        },
        claim_mode=True,
    )
    assert verdict == "正確"


def test_temporal_follow_up_without_caveat_can_still_be_accurate() -> None:
    verdict = derive_public_verdict(
        risk_score=44,
        confidence_score=60,
        labels=["大筋で整合"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "概ね整合",
            "claim_reviews": [
                {
                    "claim": "アベノマスクには全部で500億円ほどの税金が使われた",
                    "verdict": "概ね整合",
                    "reason": "政府が発表した当初の契約額は260億円でしたが、その後の報道や会計検査院の報告では、調達費や事務費、保管費などを含め、総額が約486億円から543.5億円に上るとされています。このため、「500億円ほど」という主張は概ね整合しています。",
                },
            ],
        },
        claim_mode=True,
    )
    assert verdict == "正確"


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


def test_staged_historical_transition_stays_mostly_accurate() -> None:
    verdict = derive_public_verdict(
        risk_score=34,
        confidence_score=70,
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
            "claim_reviews": [
                {
                    "claim": "大政奉還で江戸幕府は終焉を迎え、明治時代に移った",
                    "verdict": "概ね整合",
                    "reason": "大政奉還は1867年に徳川慶喜が政権を朝廷に返上した出来事であり、これにより江戸幕府の武家政治が終焉を迎えました。その後、王政復古の大号令が発令され、明治時代へと移行しました。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "ほぼ正確"


def test_supported_claim_with_understated_numeric_result_stays_mostly_accurate() -> None:
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
            "claim_reviews": [
                {
                    "claim": "マサチューセッツ州の有権者は、100万ドルを超える所得に対する4％の追加税を承認し、これにより2024年度に15億ドルの歳入が得られた",
                    "verdict": "概ね整合",
                    "reason": "マサチューセッツ州の有権者は、2023年1月1日発効の憲法改正（フェアシェア修正案）により、100万ドルを超える所得に4%の追加税を承認しました。2024会計年度の歳入は、複数の情報源によると18億ドルから24.6億ドルの範囲であり、主張の15億ドルを上回っています。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "ほぼ正確"


def test_reported_precise_historical_quantity_stays_mostly_accurate() -> None:
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
            "claim_reviews": [
                {
                    "claim": "ギザのピラミッドを建設した古代エジプトの労働者たちは、毎日4～5リットルのビールを配給されていた",
                    "verdict": "概ね整合",
                    "reason": "複数の記事で、古代エジプトのピラミッド建設労働者には毎日4～5リットルのビールが配給されていたと記述されているためです。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "ほぼ正確"


def test_supported_claim_with_small_numeric_drift_stays_mostly_accurate() -> None:
    verdict = derive_public_verdict(
        risk_score=34,
        confidence_score=70,
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
            "claim_reviews": [
                {
                    "claim": "岸田首相の発言「今年の春闘の賃上げ率2.08%は、過去20年で2番目に高い」",
                    "verdict": "概ね整合",
                    "reason": "岸田首相の発言は2022年6月21日の党首討論会で行われたもので、連合が発表した2022年春闘の賃上げ率2.09%を指していると考えられます。2.08%という数値はわずかに異なりますが、2.09%は過去20年間で2番目に高い賃上げ率であるため、発言の根幹は概ね正確です。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "ほぼ正確"


def test_shared_authorship_claim_stays_mostly_accurate() -> None:
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
            "claim_reviews": [
                {
                    "claim": "日本国憲法はアメリカが作った憲法である",
                    "verdict": "概ね整合",
                    "reason": "日本国憲法の草案はアメリカ占領軍総司令部（GHQ）の民政局によって作成され、その後日本政府が修正を加えて制定されたため、アメリカの強い影響下にあったと言える。",
                }
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


def test_multi_sentence_near_miss_count_correction_can_be_mostly_accurate() -> None:
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
                    "claim": "イチローは28年のプロ野球選手生活の中でシーズン200安打以上を11回記録した。日本より試合数の多いメージャーリーグであったからこそ、11回もそれをメジャーリーグで記録することができたと考えられる。",
                    "verdict": "反証あり",
                    "reason": "イチローのシーズン200安打以上は日米通算で11回ですが、メジャーリーグでの達成は10回、日本プロ野球での達成は1回です。したがって、「11回もそれをメジャーリーグで記録することができた」という部分は事実と異なります。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "ほぼ正確"


def test_release_month_correction_can_be_mostly_accurate() -> None:
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
                    "claim": "X JAPANは1989年5月にアルバム『BLUE BLOOD』でメジャー・デビューした",
                    "verdict": "反証あり",
                    "reason": "X JAPANのメジャーデビューアルバム『BLUE BLOOD』は1989年4月21日にリリースされた。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "ほぼ正確"


def test_ratio_rounding_correction_can_be_mostly_accurate() -> None:
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
                    "claim": "アメリカの国土面積は日本の24倍である",
                    "verdict": "反証あり",
                    "reason": "外務省のデータによると、アメリカの国土面積は約983万平方キロメートル、日本の国土面積は約37.8万平方キロメートルであり、アメリカは日本の約26倍の広さです。他の情報源でも約25倍から26倍とされています。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "ほぼ正確"


def test_one_off_record_count_correction_can_be_mostly_accurate() -> None:
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
                    "claim": "通算本塁打数の世界記録は王貞治の869本である",
                    "verdict": "反証あり",
                    "reason": "王貞治の通算本塁打数は868本であり、869本ではありません。NPB.jp日本野球機構や野球殿堂博物館の公式記録で確認できます。",
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


def test_false_claim_mode_geocentrism_counterevidence_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=14,
        confidence_score=82,
        labels=["反証情報あり"],
        source_profile={
            "official_source": False,
            "fact_check_source": True,
            "trusted_source": True,
            "correction_article": True,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "反証あり",
            "claim_reviews": [
                {
                    "claim": "地球は宇宙の中心にあり、地球の回りを太陽やその他の星々が回っている。",
                    "verdict": "反証あり",
                    "reason": "この主張は天動説であり、コペルニクス、ガリレオ、ケプラー、ニュートンらの研究により、地球が太陽の周りを公転する地動説が科学的に確立されています。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_5g_covid_counterevidence_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=16,
        confidence_score=73,
        labels=["反証情報あり"],
        source_profile={
            "official_source": False,
            "fact_check_source": True,
            "trusted_source": True,
            "correction_article": True,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "反証あり",
            "claim_reviews": [
                {
                    "claim": "5Gが新型コロナを引き起こす。",
                    "verdict": "反証あり",
                    "reason": "世界保健機関（WHO）は、ウイルスは電波やモバイルネットワーク上を移動できず、5Gがない多くの国でも新型コロナウイルス感染症が拡大していると明言しています。また、科学的専門家も5Gがウイルスを生成することはないと述べています。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_vaccine_cancer_counterevidence_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=19,
        confidence_score=82,
        labels=["反証情報あり"],
        source_profile={
            "official_source": False,
            "fact_check_source": True,
            "trusted_source": True,
            "correction_article": True,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "反証あり",
            "claim_reviews": [
                {
                    "claim": "新型コロナワクチンを接種すると大腸がんになる。",
                    "verdict": "反証あり",
                    "reason": "ファイザー社が新型コロナワクチンと大腸がんの因果関係を認めたという主張は誤りであり、関連性を示す発表や報道もありません。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_birther_counterevidence_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=16,
        confidence_score=81,
        labels=["反証情報あり"],
        source_profile={
            "official_source": False,
            "fact_check_source": True,
            "trusted_source": True,
            "correction_article": True,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "反証あり",
            "claim_reviews": [
                {
                    "claim": "バラク・オバマはアメリカ生まれではない。",
                    "verdict": "反証あり",
                    "reason": "バラク・オバマは1961年8月4日にハワイ州ホノルルで生まれ、2011年には出生証明書の長式版が公開されています。アメリカ生まれではないという主張は「バーサー運動」と呼ばれる陰謀論であり、複数のファクトチェック機関や公的機関によって否定されています。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_mmr_autism_counterevidence_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=22,
        confidence_score=73,
        labels=["反証情報あり"],
        source_profile={
            "official_source": False,
            "fact_check_source": True,
            "trusted_source": True,
            "correction_article": True,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "反証あり",
            "claim_reviews": [
                {
                    "claim": "MMRワクチンで自閉症になる。",
                    "verdict": "反証あり",
                    "reason": "MMRワクチンと自閉症の関連性を示唆した1998年の論文は、データ不正により撤回され、著者の医師免許も剥奪されました。その後の大規模な疫学研究でも、MMRワクチンと自閉症の関連性は確認されていません。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_fake_quote_absence_and_misattribution_escalates_to_false() -> None:
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
                    "reason": "李在明大統領がこの事件に言及したという直接的な報道や公的発表は確認できませんでした。この主張はまとめサイト由来の誤情報であり、過去の別発言をこの事件に紐づけたものではありません。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_modified_image_with_confidence_59_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=51,
        confidence_score=59,
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
                    "reason": "この主張の根拠画像は、入社式写真を第三者が意図的に加工したもので、加工された痕跡も確認されています。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_5g_covid_variation_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=52,
        confidence_score=74,
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
                    "claim": "5Gが新型コロナを引き起こす。",
                    "verdict": "反証あり",
                    "reason": "世界保健機関（WHO）や各国の公的機関、ファクトチェック機関が、5Gと新型コロナウイルスの間に科学的な因果関係がないことを明確に否定しています。ウイルスは電波に乗って移動せず、5Gが導入されていない地域でも感染拡大は起きています。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_synthetic_image_variation_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=52,
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
                    "claim": "ギザのピラミッド上空に水星、金星、土星が見える。これは2373年に1度起こる現象である。",
                    "verdict": "反証あり",
                    "reason": "この画像は合成であり実際のものではありません。NASAの説明でも、このような惑星の並びは数千年に一度の現象ではないとされています。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_5g_covid_brief_denial_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=16,
        confidence_score=80,
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
                    "claim": "5Gが新型コロナを引き起こす。",
                    "verdict": "反証あり",
                    "reason": "科学的根拠がなく、WHOなどの専門機関が明確に否定しているため。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_vaccine_cancer_authority_denial_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=20,
        confidence_score=84,
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
                    "claim": "新型コロナワクチンを接種すると大腸がんになる。",
                    "verdict": "反証あり",
                    "reason": "ファイザー社は新型コロナワクチンと大腸がんの因果関係を認めておらず、厚生労働省や国立がん研究センターもワクチンががんを誘発する根拠はないと発表しています。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_birther_birthplace_confirmation_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=14,
        confidence_score=82,
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
                    "claim": "バラク・オバマはアメリカ生まれではない。",
                    "verdict": "反証あり",
                    "reason": "バラク・オバマは1961年8月4日にアメリカ合衆国ハワイ州ホノルルで誕生したことが、複数の信頼できる情報源によって確認されています。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_nickname_alias_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=16,
        confidence_score=81,
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
                    "claim": "ミスタージャイアンツとはイチローのことである。",
                    "verdict": "反証あり",
                    "reason": "「ミスタージャイアンツ」は、読売ジャイアンツの元選手・監督である長嶋茂雄氏の愛称として広く知られています。イチロー氏がこの愛称で呼ばれるという情報は見当たりません。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_record_holder_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=16,
        confidence_score=81,
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
                    "claim": "バロンドールの最多受賞者は中田英寿である。",
                    "verdict": "反証あり",
                    "reason": "バロンドールの最多受賞者はリオネル・メッシ選手（8回）であり、中田英寿選手ではありません。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_first_winner_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=16,
        confidence_score=78,
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
                    "claim": "バロンドールの最初の受賞者は中村俊輔である。",
                    "verdict": "反証あり",
                    "reason": "バロンドールは1956年に創設され、記念すべき第1回の受賞者はイングランドのスタンリー・マシューズである。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_recontextualized_quote_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=54,
        confidence_score=66,
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
                    "claim": "トランプ氏が、現在の中東情勢を受けて「私は核兵器を使う最後の人間になるだろう」と発言した",
                    "verdict": "反証あり",
                    "reason": "トランプ氏の「私は核兵器を使う最後の人間になるだろう」という発言は、2016年8月6日にニューハンプシャー州ウィンダム高校での選挙集会で行われたものであり、2026年の現在の中東情勢を受けての発言ではありません。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_mmr_autism_wording_variation_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=19,
        confidence_score=83,
        labels=["反証情報あり"],
        source_profile={
            "official_source": False,
            "fact_check_source": True,
            "trusted_source": True,
            "correction_article": True,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "反証あり",
            "claim_reviews": [
                {
                    "claim": "MMRワクチンで自閉症になる。",
                    "verdict": "反証あり",
                    "reason": "MMRワクチンと自閉症の関連性については、多数の疫学研究で否定されており、関連性を示す証拠はありません。この主張の根拠となった論文は、データ改ざんが発覚し撤回されています。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_unconfirmed_quote_wording_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=54,
        confidence_score=61,
        labels=["反証情報あり", "文脈不足に注意"],
        source_profile={
            "official_source": False,
            "fact_check_source": True,
            "trusted_source": True,
            "correction_article": True,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "反証あり",
            "claim_reviews": [
                {
                    "claim": "世田谷区で韓国籍女性が殺害された事件について、韓国の李在明大統領が「日本は謝罪と賠償をするべきだ」と発言した。",
                    "verdict": "反証あり",
                    "reason": "日本ファクトチェックセンターの検証により、李在明大統領がこの事件に関して「日本は謝罪と賠償をするべきだ」と発言したという事実は確認されておらず、誤りであるとされています。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_same_person_negation_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=16,
        confidence_score=80,
        labels=["反証情報あり"],
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
                    "claim": "工藤新一と江戸川コナンは同一人物でない。",
                    "verdict": "反証あり",
                    "reason": "『名探偵コナン』の主人公である江戸川コナンは、毒薬によって体が小さくなった工藤新一の仮の姿であり、同一人物であると公式情報や関連サイトで明記されています。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_japan_northernmost_point_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=14,
        confidence_score=82,
        labels=["反証情報あり"],
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
                    "claim": "日本の最北端は知床岬である。",
                    "verdict": "反証あり",
                    "reason": "日本の最北端は択捉島であり、一般人が到達できる最北端は北海道の宗谷岬である。知床岬は日本の最北端ではない。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_historical_poison_rumor_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=14,
        confidence_score=82,
        labels=["反証情報あり"],
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
                    "claim": "関東大震災で朝鮮人が井戸に毒を入れた。",
                    "verdict": "反証あり",
                    "reason": "関東大震災時に「朝鮮人が井戸に毒を入れた」という流言が広まったが、警視庁の資料や内閣府の報告書など複数の公的資料で、朝鮮人による暴動や投毒の噂は誤りであったと確認されている。このデマが朝鮮人虐殺の背景となった。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_recontextualized_quote_current_situation_variation_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=54,
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
                    "claim": "トランプ氏が、現在の中東情勢を受けて「私は核兵器を使う最後の人間になるだろう」と発言した",
                    "verdict": "反証あり",
                    "reason": "トランプ氏が「私は核兵器を使う最後の人間になるだろう」と発言したのは2016年8月6日の選挙集会であり、現在の情勢を受けたものではないため、主張の前提が誤っています。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_5g_covid_generation_denial_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=16,
        confidence_score=80,
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
                    "claim": "5Gが新型コロナを引き起こす。",
                    "verdict": "反証あり",
                    "reason": "世界保健機関（WHO）は、5Gが新型コロナウイルス感染症（COVID-19）を広めないこと、ウイルスは電波やモバイルネットワーク上を移動できないことを明確に述べています。また、専門家も5Gがウイルスを生成しないと指摘しています。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_mmr_autism_fabrication_variation_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=20,
        confidence_score=82,
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
                    "claim": "MMRワクチンで自閉症になる。",
                    "verdict": "反証あり",
                    "reason": "MMRワクチンと自閉症の関連を示唆した論文は、データ捏造などの不正が発覚し撤回されました。その後の大規模な疫学研究では、MMRワクチンと自閉症の間に因果関係がないことが一貫して示されています。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_apollo_moon_landing_hoax_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=34,
        confidence_score=80,
        labels=["反証情報あり", "既知のデマ類型に類似", "文脈不足に注意"],
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
                    "claim": "1969年のアポロ月面着陸は捏造である",
                    "verdict": "反証あり",
                    "reason": "アポロ計画の月面着陸は、日本の月周回衛星「かぐや」による着陸地点のクレーター撮影や、NASAのルナリコネッサンスオービターによる高解像度画像によって確認されています。また、ソビエト連邦を含む複数の国がアポロミッションを独立して監視しており、陰謀論の主な根拠も科学的に説明されています。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_geocentrism_established_wording_variation_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=14,
        confidence_score=82,
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
                    "claim": "地球は宇宙の中心にあり、地球の回りを太陽やその他の星々が回っている",
                    "verdict": "反証あり",
                    "reason": "地球が宇宙の中心にあり、太陽や他の天体がその周りを回るという天動説は、コペルニクス、ガリレオ、ケプラー、ニュートンらの研究により科学的に反証され、太陽が中心の地動説が確立されています。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_mmr_autism_unreliable_data_wording_variation_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=20,
        confidence_score=82,
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
                    "claim": "MMRワクチンで自閉症になる。",
                    "verdict": "反証あり",
                    "reason": "MMRワクチンと自閉症の関連性を示唆した1998年の論文は、不正なデータと倫理的違反により撤回されました。その後の多数の大規模疫学研究では、MMRワクチン接種と自閉症リスクの増加との関連性は認められていません。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_japan_northernmost_claim_is_wrong_wording_variation_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=14,
        confidence_score=82,
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
                    "claim": "日本の最北端は知床岬である。",
                    "verdict": "反証あり",
                    "reason": "日本の最北端は択捉島であり、一般人が到達できる最北端は宗谷岬であるため、知床岬であるという主張は誤りです。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_trump_current_mideast_quote_wording_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=54,
        confidence_score=66,
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
                    "reason": "トランプ氏の「私は核兵器を使う最後の人間になるだろう」という発言は、2016年8月6日にニューハンプシャー州のウィンダム高校で行われた大統領選集会でのものであり、現在の中東情勢を受けてのものではありません。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_5g_covid_scientific_knowledge_wording_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=16,
        confidence_score=81,
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
                    "claim": "5Gが新型コロナを引き起こす。",
                    "verdict": "反証あり",
                    "reason": "科学的知見や実験確認例は全くなく、WHOなどの専門機関が5Gと新型コロナウイルス感染症の関連性を否定しているため。ウイルスは電波やモバイルネットワーク上を移動できない。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_mmr_autism_no_scientific_evidence_wording_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=20,
        confidence_score=82,
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
                    "claim": "MMRワクチンで自閉症になる。",
                    "verdict": "反証あり",
                    "reason": "MMRワクチンと自閉症の関連性を示す科学的証拠はなく、関連性を主張した元の論文は不正行為により撤回され、著者の医師免許も剥奪されています。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_lee_fake_quote_jfc_wording_escalates_to_false() -> None:
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
                    "reason": "日本ファクトチェックセンター（JFC）がこの主張を検証し、李在明大統領がそのような発言をしたという事実はないと結論付けています。この情報はまとめサイトによって拡散された誤りです。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_claim_mode_counterevidence_review_prevents_almost_accurate_for_compound_claim() -> None:
    verdict = derive_public_verdict(
        risk_score=41,
        confidence_score=78,
        labels=["反証情報あり", "文脈不足に注意"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "概ね整合",
            "claim_reviews": [
                {
                    "claim": "スタジオジブリ制作のアニメ映画「となりのトトロ」と「火垂るの墓」は1988年4月に同時上映された。「となりのトトロ」は高畑勲、「火垂るの墓」は宮崎駿の監督作品である。",
                    "verdict": "反証あり",
                    "reason": "「となりのトトロ」の監督は宮崎駿、「火垂るの墓」の監督は高畑勲であり、主張と逆です。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "不正確"


def test_claim_mode_unsettled_future_constitutional_revision_prediction_holds() -> None:
    verdict = derive_public_verdict(
        risk_score=34,
        confidence_score=70,
        labels=["文脈不足に注意"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "概ね整合",
            "claim_reviews": [
                {
                    "claim": "近い将来、日本は憲法を改正する。",
                    "verdict": "概ね整合",
                    "reason": "主要政党が憲法改正を目指しているため政治的目標としては整合するが、最終的には国民投票による承認が必要で、現時点で確定していない。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "判断保留"


def test_claim_mode_unsettled_future_nato_accession_prediction_holds() -> None:
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
                    "claim": "近い将来、日本はNATOに加盟する。",
                    "verdict": "反証あり",
                    "reason": "日本がNATOに加盟するという事実は確認されていません。加盟の予定や具体的な動きに関する情報はありません。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "判断保留"


def test_claim_mode_future_sports_record_prediction_holds() -> None:
    verdict = derive_public_verdict(
        risk_score=34,
        confidence_score=69,
        labels=["大筋で整合"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "概ね整合",
            "claim_reviews": [
                {
                    "claim": "落合博満のように三冠王を三度獲得するバッターは今後現れないだろう。",
                    "verdict": "概ね整合",
                    "reason": "落合博満は唯一の三冠王3度達成者だが、今後同様の達成者が現れる可能性は極めて低いと推測される。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "判断保留"


def test_claim_mode_future_sports_record_prediction_with_general_view_wording_holds() -> None:
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
            "claim_reviews": [
                {
                    "claim": "落合博満のように三冠王を三度獲得するバッターは今後現れないだろう。",
                    "verdict": "概ね整合",
                    "reason": "落合博満は唯一の三冠王3度達成者であり、その偉業の再現は極めて困難であるという見方が一般的であるため。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "判断保留"


def test_claim_mode_future_sports_record_messi_prediction_holds() -> None:
    verdict = derive_public_verdict(
        risk_score=35,
        confidence_score=69,
        labels=["大筋で整合"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "概ね整合",
            "claim_reviews": [
                {
                    "claim": "リオネル・メッシのようにバロンドールを8回獲得するサッカー選手は今後現れないだろう。",
                    "verdict": "概ね整合",
                    "reason": "メッシの8回受賞は記録的だが、今後破られにくいという専門家や報道機関の見解にとどまる。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "判断保留"


def test_claim_mode_future_sports_award_prediction_holds() -> None:
    verdict = derive_public_verdict(
        risk_score=34,
        confidence_score=69,
        labels=["大筋で整合"],
        source_profile={
            "official_source": False,
            "fact_check_source": False,
            "trusted_source": False,
            "correction_article": False,
            "claim_mode": True,
        },
        evidence_overview={
            "assessment_status": "概ね整合",
            "claim_reviews": [
                {
                    "claim": "大谷翔平は近い将来サイヤング賞を獲得するだろう。",
                    "verdict": "概ね整合",
                    "reason": "将来の予測であり現時点で断定できないが、獲得の可能性はスポーツメディアで議論されている。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "判断保留"


def test_claim_mode_disputed_historical_existence_yamatotakeru_holds() -> None:
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
                    "claim": "ヤマトタケルは実在した。",
                    "verdict": "反証あり",
                    "reason": "ヤマトタケルは伝説上の人物とされるが、実在性をめぐっては議論があり、明確な歴史的根拠は確認されていません。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "判断保留"


def test_claim_mode_disputed_historical_existence_arthur_holds() -> None:
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
                    "claim": "アーサー王は実在した王である。",
                    "verdict": "反証あり",
                    "reason": "歴史家の間ではアーサー王の実在性について議論が続いているが、実在の王であったという確固たる証拠はない。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "判断保留"


def test_claim_mode_disputed_historical_existence_arthur_backed_wording_holds() -> None:
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
                    "claim": "アーサー王は実在した王である。",
                    "verdict": "反証あり",
                    "reason": "アーサー王の歴史上の実在性については歴史家の間で議論が続いており、伝説的な要素が強いとされているため、実在した王であるという断定的な主張は裏付けられていません。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "判断保留"


def test_claim_mode_future_earthquake_deadline_prediction_holds() -> None:
    verdict = derive_public_verdict(
        risk_score=66,
        confidence_score=69,
        labels=["反証情報あり", "反証根拠あり"],
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
                    "claim": "南海トラフ地震は2035年までに起こる。",
                    "verdict": "反証あり",
                    "reason": "政府機関は南海トラフ地震の30年以内の発生確率を公表しているが、発生年月を特定して予知することは現在の地震学では不可能としている。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "判断保留"


def test_claim_mode_disputed_authenticity_shroud_holds() -> None:
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
                    "claim": "トリノの聖骸布は本当にキリストの遺体を包んだ布である。",
                    "verdict": "反証あり",
                    "reason": "1988年の放射性炭素年代測定では中世の布とされたが、一部に年代測定への異論もあり、主流の科学的見解は中世起源を示している。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "判断保留"


def test_claim_mode_disputed_authenticity_shroud_radiocarbon_wording_holds() -> None:
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
                    "claim": "トリノの聖骸布は本当にキリストの遺体を包んだ布である。",
                    "verdict": "反証あり",
                    "reason": "1988年の放射性炭素年代測定により、トリノの聖骸布は1260年から1390年の間に作られた中世の布であると科学的に結論付けられている。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "判断保留"


def test_claim_mode_disputed_historical_identity_or_role_naotora_holds() -> None:
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
            "claim_reviews": [
                {
                    "claim": "井伊直虎という女城主は実在した。",
                    "verdict": "概ね整合",
                    "reason": "井伊直虎は女領主として紹介されるが、次郎法師との同一性については史料が少ないため断定を控えるべきとの見解もあります。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "判断保留"


def test_false_claim_mode_nonexistent_law_sonzai_sezu_wording_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=18,
        confidence_score=82,
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
                    "reason": "日本にそのような反イスラム法は存在せず、憲法や文化庁の方針にも反します。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_context_mismatch_quote_wording_escalates_to_false() -> None:
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
                    "reason": "そのような報道は確認できないうえ、過去の歴史問題に関する談話が本件とは異なる文脈で流用されています。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_first_ballon_dor_winner_plain_desu_wording_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=16,
        confidence_score=81,
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
                    "claim": "バロンドールの最初の受賞者は中村俊輔である。",
                    "verdict": "反証あり",
                    "reason": "バロンドールは1956年に創設され、最初の受賞者はスタンリー・マシューズです。中村俊輔は2007年にバロンドールの候補者にはなりましたが、受賞はしていません。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_mmr_autism_denied_relatedness_wording_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=19,
        confidence_score=83,
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
                    "claim": "MMRワクチンで自閉症になる。",
                    "verdict": "反証あり",
                    "reason": "1998年の論文が不正なデータにより撤回され、その後の大規模な疫学研究でMMRワクチンと自閉症の関連性は否定されているため。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_apollo_hoax_flag_and_witness_wording_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=34,
        confidence_score=81,
        labels=["反証情報あり", "既知のデマ類型に類似", "文脈不足に注意"],
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
                    "claim": "1969年のアポロ月面着陸は捏造である",
                    "verdict": "反証あり",
                    "reason": "アポロ月面着陸はNASAによって複数回成功しており、捏造説の主な根拠（旗の揺れ、星の不在など）は科学的に反証されている。また、40万人もの関係者から捏造を認める証言は出ていない。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_saigo_boshin_death_claim_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=13,
        confidence_score=81,
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
                    "claim": "西郷隆盛は戊辰戦争で戦死した。",
                    "verdict": "反証あり",
                    "reason": "西郷隆盛は戊辰戦争で新政府軍の参謀として活躍しましたが、戦死したのは1877年の西南戦争です。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"


def test_false_claim_mode_saigo_seinan_victory_claim_escalates_to_false() -> None:
    verdict = derive_public_verdict(
        risk_score=13,
        confidence_score=81,
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
                    "claim": "西郷隆盛は西南戦争で勝利した。",
                    "verdict": "反証あり",
                    "reason": "西南戦争は明治政府軍の勝利で終結し、西郷隆盛は敗北し自刃しました。",
                }
            ],
        },
        claim_mode=True,
    )
    assert verdict == "誤り"
