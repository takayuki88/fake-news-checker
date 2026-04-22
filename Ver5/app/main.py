"""FastAPI の入口。

ブラウザ画面と API の両方から入力を受け取り、
本文抽出(content_extractor) -> 判定(analyzer) -> 画面/API返却の順に処理します。
"""

from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .analyzer import analyze_page
from .config import get_settings
from .content_extractor import resolve_page_input
from .models import AnalysisResult, AnalyzeForm
from .time_utils import build_analysis_timestamp_fields

BASE_DIR = Path(__file__).resolve().parent

# `app` は FastAPI アプリそのものです。uvicorn はこの変数を探して起動します。
app = FastAPI(title="Fake News Checker Ver5", version="5.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def format_duration_seconds(duration_ms: int | None) -> str:
    """ミリ秒を、画面表示しやすい秒数の文字列に変換する。"""
    if duration_ms is None:
        return "0.0"
    seconds = (Decimal(duration_ms) / Decimal("1000")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{seconds:.1f}"


templates.env.filters["duration_seconds"] = format_duration_seconds


def base_context() -> dict:
    """テンプレートに毎回渡す共通データを作る。"""
    settings = get_settings()
    timestamp_fields = build_analysis_timestamp_fields(settings)
    return {
        "result": None,
        "error": None,
        "form_data": {"page_url": "", "page_text": "", "skip_policy_check": False},
        "gemini_enabled": bool(settings.gemini_api_key),
        "today_date": timestamp_fields["analysis_date"],
        "today_datetime": timestamp_fields["analysis_datetime"],
        "min_text_chars": settings.min_text_chars,
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """トップページを表示するだけの GET ルート。"""
    context = base_context()
    context["request"] = request
    return templates.TemplateResponse(request, "index.html", context)


@app.post("/analyze", response_class=HTMLResponse)
async def analyze(
    request: Request,
    page_url: str = Form(default=""),
    page_text: str = Form(default=""),
    skip_policy_check: bool = Form(default=False),
) -> HTMLResponse:
    """ブラウザのフォーム送信を受け取り、判定結果つきの画面を返す。"""
    form_data = {
        "page_url": page_url,
        "page_text": page_text,
        "skip_policy_check": skip_policy_check,
    }
    context = base_context()
    settings = get_settings()
    # URL入力でも本文貼り付けでも、ここで共通の `ResolvedPage` 形式にそろえる。
    page, error = await resolve_page_input(
        page_text,
        page_url,
        settings,
        skip_policy_check=skip_policy_check,
    )
    if error or not page:
        context.update(
            {
                "request": request,
                "result": None,
                "error": error or "解析対象を確定できませんでした。",
                "form_data": form_data,
            }
        )
        return templates.TemplateResponse(request, "index.html", context, status_code=400)

    # 判定の中心処理は analyzer.py に集約している。
    result = await analyze_page(page, settings)
    context.update(
        {
            "request": request,
            "result": result.model_dump(),
            "error": None,
            "form_data": form_data,
        }
    )
    return templates.TemplateResponse(request, "index.html", context)


@app.post("/api/analyze", response_model=AnalysisResult)
async def analyze_api(payload: AnalyzeForm) -> AnalysisResult:
    """外部プログラムから JSON で使うための API ルート。"""
    settings = get_settings()
    page_url = str(payload.page_url) if payload.page_url else None
    page, error = await resolve_page_input(
        payload.page_text,
        page_url,
        settings,
        skip_policy_check=payload.skip_policy_check,
    )
    if error or not page:
        raise HTTPException(status_code=400, detail=error or "解析対象を確定できませんでした。")
    return await analyze_page(page, settings)


@app.get("/api/health")
async def healthcheck() -> dict[str, str]:
    """起動確認用の軽いエンドポイント。"""
    return {"status": "ok"}
