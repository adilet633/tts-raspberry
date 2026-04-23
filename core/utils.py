from datetime import datetime


def now_time_str() -> str:
    return datetime.now().strftime("%H:%M")


def today_date_str() -> str:
    return datetime.now().strftime("%d.%m.%Y")


def safe_int(x, default=0) -> int:
    try:
        return int(x)
    except Exception:
        return default