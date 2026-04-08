from __future__ import annotations

import json
from typing import Any


PRIMARY_REVIEW_SCHEMA = {
    "primary_review": {
        "domain": "医療 | 災害 | 政治 | 金融 | 一般",
        "risk_score": "0-100",
        "confidence_score": "0-100",
        "summary": "120字以内",
        "labels": ["最大4件"],
        "reasons": ["最大4件"],
    }
}


def build_gpt_primary_prompt(page: Any, seed: dict[str, Any]) -> str:
    prompt_seed = {
        "local_domain": seed.get("domain"),
        "local_labels": seed.get("labels", []),
        "local_reasons": seed.get("reasons", []),
        "source_snapshot": getattr(seed.get("source_snapshot"), "model_dump", lambda: seed.get("source_snapshot", {}))(),
    }
    return f"""
あなたは日本語のニュース検証支援AIです。
役割は、ページ本文とメタ情報だけを使って一次判定を返すことです。
外部検索結果や外部根拠は使わないでください。
出力は JSON のみとしてください。

期待する JSON:
{json.dumps(PRIMARY_REVIEW_SCHEMA, ensure_ascii=False, indent=2)}

対象URL: {getattr(page, "source_url", "") or "未入力"}
ページ名: {getattr(page, "title", "") or "未取得"}
サイト名: {getattr(page, "site_name", "") or "未取得"}
判定日: {getattr(page, "analysis_date", "") or "未設定"}
判定日時: {getattr(page, "analysis_datetime", "") or "未設定"}

著者名: {getattr(page, "author_name", "") or "未取得"}
公開日時: {getattr(page, "published_at", "") or "未取得"}
引用リンク数: {getattr(page, "reference_link_count", 0)}
抽出品質: {getattr(page, "extraction_score", 0)}/100

本文抜粋:
\"\"\"
{getattr(page, "analysis_text", "")[:2400]}
\"\"\"

ローカル一次判定の補助情報:
{json.dumps(prompt_seed, ensure_ascii=False)}
""".strip()


def normalize_openai_primary_review(raw_output: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(raw_output, dict):
        return None

    primary_review = raw_output.get("primary_review")
    if not isinstance(primary_review, dict):
        return None

    labels = primary_review.get("labels")
    reasons = primary_review.get("reasons")
    return {
        "primary_review": {
            "domain": str(primary_review.get("domain") or "").strip(),
            "risk_score": primary_review.get("risk_score"),
            "confidence_score": primary_review.get("confidence_score"),
            "summary": str(primary_review.get("summary") or "").strip(),
            "labels": labels if isinstance(labels, list) else [],
            "reasons": reasons if isinstance(reasons, list) else [],
        }
    }


async def run_openai_primary_review(page: Any, seed: dict[str, Any], settings: Any) -> dict[str, Any] | None:
    if not getattr(settings, "openai_api_key", ""):
        return None
    if not getattr(settings, "openai_primary_model", ""):
        return None

    prompt = build_gpt_primary_prompt(page, seed)

    # The first Ver4 scaffold commit fixes the prompt and response shape first.
    # Wiring the actual OpenAI request will follow in the next commit.
    _ = prompt
    return None
