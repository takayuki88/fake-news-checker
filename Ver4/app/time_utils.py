from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import Settings

DEFAULT_TIMEZONE = "Asia/Tokyo"
FIXED_OFFSET_FALLBACKS: dict[str, tzinfo] = {
    "Asia/Tokyo": timezone(timedelta(hours=9), "JST"),
    "UTC": timezone.utc,
}


def get_app_timezone_name(settings: Settings) -> str:
    return settings.app_timezone or DEFAULT_TIMEZONE


def get_app_timezone(settings: Settings) -> tzinfo:
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
    return datetime.now(get_app_timezone(settings))


def format_app_date(now: datetime) -> str:
    return now.strftime("%Y-%m-%d")


def format_app_datetime(now: datetime) -> str:
    return now.strftime("%Y-%m-%d %H:%M:%S %Z")


def build_analysis_timestamp_fields(settings: Settings) -> dict[str, str]:
    now = get_current_app_datetime(settings)
    timezone_name = getattr(now.tzinfo, "key", None) or now.tzname() or get_app_timezone_name(settings)
    return {
        "analysis_date": format_app_date(now),
        "analysis_datetime": format_app_datetime(now),
        "analysis_timezone": timezone_name,
    }
