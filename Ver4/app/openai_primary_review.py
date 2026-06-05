"""OpenAI による Ver4 の一次レビューを担当する補助モジュール。"""

from __future__ import annotations

import json
from typing import Any

import httpx


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

PRIMARY_REVIEW_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "primary_review": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "domain": {
                    "type": "string",
                    "enum": ["医療", "災害", "政治", "金融", "一般"],
                },
                "risk_score": {"type": "integer", "minimum": 0, "maximum": 100},
                "confidence_score": {"type": "integer", "minimum": 0, "maximum": 100},
                "summary": {"type": "string"},
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 4,
                },
                "reasons": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 4,
                },
            },
            "required": [
                "domain",
                "risk_score",
                "confidence_score",
                "summary",
                "labels",
                "reasons",
            ],
        }
    },
    "required": ["primary_review"],
}

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


def normalize_analysis_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    return "claim" if mode == "claim" else "article"


def is_claim_mode(page: Any) -> bool:
    analysis_mode = normalize_analysis_mode(getattr(page, "analysis_mode", None))
    if analysis_mode == "claim":
        return True
    input_source = str(getattr(page, "input_source", "") or "").strip()
    source_url = str(getattr(page, "source_url", "") or "").strip()
    extracted_chars = int(getattr(page, "extracted_chars", 0) or 0)
    paragraph_count = int(getattr(page, "paragraph_count", 0) or 0)
    reference_link_count = int(getattr(page, "reference_link_count", 0) or 0)
    has_author = bool(getattr(page, "has_author", False))
    has_published_at = bool(getattr(page, "has_published_at", False))
    return (
        input_source in {"manual_text", "test_fixture"}
        and not source_url
        and not has_author
        and not has_published_at
        and reference_link_count == 0
        and extracted_chars <= 280
        and paragraph_count <= 2
    )


def supports_temperature(model_name: str) -> bool:
    cleaned = str(model_name or "").strip().lower()
    return not cleaned.startswith("gpt-5")


def build_openai_primary_payload(prompt: str, model_name: str) -> dict[str, Any]:
    """Responses API に送るリクエスト本文を作る。"""
    payload = {
        "model": model_name,
        "input": prompt,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "primary_review_response",
                "strict": True,
                "schema": PRIMARY_REVIEW_JSON_SCHEMA,
            }
        },
    }
    if supports_temperature(model_name):
        payload["temperature"] = 0.1
    return payload


def build_gpt_primary_prompt(page: Any, seed: dict[str, Any]) -> str:
    """ページ本文とローカル一次判定から、OpenAI 用プロンプトを組み立てる。"""
    prompt_seed = {
        "local_domain": seed.get("domain"),
        "local_labels": seed.get("labels", []),
        "local_reasons": seed.get("reasons", []),
        "source_snapshot": getattr(seed.get("source_snapshot"), "model_dump", lambda: seed.get("source_snapshot", {}))(),
    }
    claim_mode = is_claim_mode(page)
    mode_label = "短文claim評価" if claim_mode else "記事評価"
    mode_instruction = ""
    if claim_mode:
        mode_instruction = (
            "今回の入力は記事本文ではなく短文の主張です。入力に URL・著者名・公開日時・引用リンクが無いこと自体は通常なので、"
            "それだけで「出典不明」や「信頼できる一次ソース未確認」を強く付けないでください。"
            "メタデータ不足ではなく、主張の具体性・内部整合性・検証可能性に注目して一次判定してください。"
            "複数の有力学説が併存し定説が確立していない歴史論争・所在地論争・歴史人物の性別や同一性の論争は、"
            "誤りや正確と断定せず保留寄りの一次評価にしてください。"
        )
    return f"""
あなたは日本語のニュース検証支援AIです。
役割は、ページ本文とメタ情報だけを使って一次判定を返すことです。
外部検索結果や外部根拠は使わないでください。
{mode_instruction}
この一次判定は最終判定ではなく、後段の Gemini 外部根拠確認に渡す仮説です。
本文とメタ情報だけでは外部事実を確認できない場合、risk_score や confidence_score を極端に振らず、
主張の具体性、内部矛盾、煽りの強さ、検証可能性を中心に中間的なスコアで表現してください。
小さな日付・数字・固有名詞・範囲の差分が疑われる場合は、全面的な虚偽よりも「細部確認が必要」な一次評価に寄せてください。
明確な内部矛盾、なりすまし、存在しない制度・発言の断定、既知の陰謀論テンプレなどが本文内から強く読める場合だけ高リスクにしてください。
出力は JSON のみとしてください。

期待する JSON:
{json.dumps(PRIMARY_REVIEW_SCHEMA, ensure_ascii=False, indent=2)}

対象URL: {getattr(page, "source_url", "") or "未入力"}
ページ名: {getattr(page, "title", "") or "未取得"}
サイト名: {getattr(page, "site_name", "") or "未取得"}
判定日: {getattr(page, "analysis_date", "") or "未設定"}
判定日時: {getattr(page, "analysis_datetime", "") or "未設定"}
解析モード: {mode_label}

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
    """OpenAI のJSON出力を、後続処理が使いやすい形に整える。"""
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


def extract_openai_output_text(payload: dict[str, Any]) -> str:
    output = payload.get("output")
    if not isinstance(output, list):
        return ""

    texts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            text = str(part.get("text") or part.get("output_text") or "").strip()
            if text:
                texts.append(text)
    return "\n".join(texts).strip()


def format_openai_error(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        try:
            payload = exc.response.json()
        except ValueError:
            payload = {}
        error_message = ""
        if isinstance(payload, dict):
            raw_error = payload.get("error")
            if isinstance(raw_error, dict):
                error_message = str(raw_error.get("message") or "").strip()
        return f"OpenAI API error {status_code}: {error_message or exc.response.text.strip()}"
    if isinstance(exc, httpx.HTTPError):
        return f"OpenAI HTTP error: {exc}"
    return f"{type(exc).__name__}: {exc}"


async def run_openai_primary_review(page: Any, seed: dict[str, Any], settings: Any) -> dict[str, Any] | None:
    """OpenAI API を呼び出し、一次レビュー結果を返す。失敗時はエラー情報を返す。"""
    if not getattr(settings, "openai_api_key", ""):
        return None
    if not getattr(settings, "openai_primary_model", ""):
        return None

    prompt = build_gpt_primary_prompt(page, seed)
    payload = build_openai_primary_payload(prompt, settings.openai_primary_model)
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    timeout = httpx.Timeout(connect=15.0, read=70.0, write=20.0, pool=20.0)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(OPENAI_RESPONSES_URL, headers=headers, json=payload)
            response.raise_for_status()
        data = response.json()
        raw_text = extract_openai_output_text(data)
        if not raw_text:
            return {
                "output": None,
                "error": "OpenAI primary review did not return text output.",
            }
        normalized = normalize_openai_primary_review(json.loads(raw_text))
        if not normalized:
            return {
                "output": None,
                "error": "OpenAI primary review did not match the expected schema.",
            }
        return {
            "output": normalized,
            "response_id": data.get("id"),
        }
    except (httpx.HTTPError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return {
            "output": None,
            "error": format_openai_error(exc),
        }
