"""判定日時をアプリのタイムゾーンで扱うための小さな補助関数群。"""

from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import Settings

DEFAULT_TIMEZONE = "Asia/Tokyo"
FIXED_OFFSET_FALLBACKS: dict[str, tzinfo] = {
    "Asia/Tokyo": timezone(timedelta(hours=9), "JST"),
    "UTC": timezone.utc,
}


def get_app_timezone_name(settings: Settings) -> str:
    """設定からタイムゾーン名を取り出す。未設定なら日本時間にする。"""
    return settings.app_timezone or DEFAULT_TIMEZONE


def get_app_timezone(settings: Settings) -> tzinfo:
    """タイムゾーン名を Python の tzinfo に変換する。"""
    timezone_name = get_app_timezone_name(settings)
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        pass

    try:
        return ZoneInfo(DEFAULT_TIMEZONE)
    except ZoneInfoNotFoundError:
        # Windows + venv では tzdata 未導入だと ZoneInfo が失敗するため、
        # よく使うタイムゾーンだけ固定オフセットで継続動作させる。
        return FIXED_OFFSET_FALLBACKS.get(timezone_name, FIXED_OFFSET_FALLBACKS[DEFAULT_TIMEZONE])


def get_current_app_datetime(settings: Settings) -> datetime:
    """アプリ設定のタイムゾーンで現在時刻を返す。"""
    return datetime.now(get_app_timezone(settings))


def format_app_date(now: datetime) -> str:
    """日付だけを `YYYY-MM-DD` 形式にする。"""
    return now.strftime("%Y-%m-%d")


def format_app_datetime(now: datetime) -> str:
    """日時を画面やJSONに出しやすい文字列にする。"""
    return now.strftime("%Y-%m-%d %H:%M:%S %Z")


def build_analysis_timestamp_fields(settings: Settings) -> dict[str, str]:
    """判定結果に保存する日付・日時・タイムゾーンをまとめて作る。"""
    now = get_current_app_datetime(settings)
    timezone_name = getattr(now.tzinfo, "key", None) or now.tzname() or get_app_timezone_name(settings)
    return {
        "analysis_date": format_app_date(now),
        "analysis_datetime": format_app_datetime(now),
        "analysis_timezone": timezone_name,
    }
