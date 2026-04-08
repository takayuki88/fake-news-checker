from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


def current_min_text_chars() -> int:
    try:
        from .config import get_settings

        return max(int(get_settings().min_text_chars), 1)
    except Exception:
        return 10


class AnalyzeForm(BaseModel):
    page_text: str | None = Field(default=None, max_length=12000)
    page_url: HttpUrl | None = None
    skip_policy_check: bool = False

    @field_validator("page_text")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @model_validator(mode="after")
    def validate_input(self) -> "AnalyzeForm":
        min_chars = current_min_text_chars()
        if not self.page_text and not self.page_url:
            raise ValueError("ページURLまたはページ本文のどちらかを入力してください。")
        if self.page_text and len(self.page_text) < min_chars:
            raise ValueError(f"ページ本文は{min_chars}文字以上入力してください。")
        return self


class VerificationLink(BaseModel):
    title: str
    url: str
    kind: str


class AnalysisSignal(BaseModel):
    title: str
    score_delta: int
    tone: str
    detail: str


class StyleSignal(BaseModel):
    title: str
    severity: str
    detail: str


class EvidenceClaimReview(BaseModel):
    claim: str
    verdict: str
    reason: str


class RetrievedUrl(BaseModel):
    url: str
    status: str


class TimingStage(BaseModel):
    key: str
    label: str
    duration_ms: int = Field(ge=0)
    note: str | None = None


class TimingOverview(BaseModel):
    total_ms: int = Field(ge=0)
    stages: list[TimingStage] = Field(default_factory=list)


class EvidenceOverview(BaseModel):
    status: str
    summary: str
    claims: list[str] = Field(default_factory=list)
    links: list["VerificationLink"] = Field(default_factory=list)
    assessment_status: str | None = None
    assessment_summary: str | None = None
    assessment_note: str | None = None
    assessment_model: str | None = None
    claim_reviews: list[EvidenceClaimReview] = Field(default_factory=list)
    grounding_queries: list[str] = Field(default_factory=list)
    grounding_sources: list["VerificationLink"] = Field(default_factory=list)
    retrieved_urls: list[RetrievedUrl] = Field(default_factory=list)


class StyleOverview(BaseModel):
    status: str
    summary: str
    score: int | None = Field(default=None, ge=0, le=100)
    score_display: str
    label: str
    key: str
    note: str | None = None
    model: str | None = None
    highlights: list[str] = Field(default_factory=list)
    signals: list[StyleSignal] = Field(default_factory=list)


class ScoreCalculationStep(BaseModel):
    label: str
    expression: str
    result: str
    note: str | None = None


class ScoreCalculation(BaseModel):
    attention_steps: list[ScoreCalculationStep] = Field(default_factory=list)


class SourceSnapshot(BaseModel):
    title: str
    site_name: str
    source_url: str | None = None
    input_source: str
    analysis_mode: str = "article"
    extraction_note: str
    analysis_date: str | None = None
    analysis_datetime: str | None = None
    analysis_timezone: str | None = None
    policy_check_status: str | None = None
    policy_check_note: str | None = None
    policy_check_url: str | None = None
    policy_checked_urls: list[str] = Field(default_factory=list)
    text_preview: str
    extracted_chars: int = Field(ge=0)
    has_author: bool = False
    has_published_at: bool = False
    author_name: str | None = None
    published_at: str | None = None
    reference_link_count: int = Field(default=0, ge=0)
    paragraph_count: int = Field(default=0, ge=0)
    heading_count: int = Field(default=0, ge=0)
    extraction_score: int = Field(default=0, ge=0, le=100)


class ResolvedPage(SourceSnapshot):
    analysis_text: str = Field(min_length=10)
    timing_overview: TimingOverview | None = None


class AnalysisResult(BaseModel):
    verdict: str
    verdict_key: str
    verdict_display: str
    attention_score: int | None = Field(default=None, ge=0, le=100)
    attention_display: str
    attention_band_display: str
    risk_score: int | None = Field(default=None, ge=0, le=100)
    caution_level: str | None = None
    confidence: str
    confidence_label: str
    confidence_score: int = Field(ge=0, le=100)
    status: str
    summary: str
    reasons: list[str]
    supplement: str | None = None
    labels: list[str]
    domain: str
    evidence_sources: list[VerificationLink]
    verification_links: list[VerificationLink]
    model_used: str
    source_snapshot: SourceSnapshot
    signal_breakdown: list[AnalysisSignal]
    evidence_overview: EvidenceOverview
    style_overview: StyleOverview
    score_calculation: ScoreCalculation | None = None
    timing_overview: TimingOverview | None = None
