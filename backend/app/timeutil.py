from datetime import datetime, timedelta, timezone

CST = timezone(timedelta(hours=8))


def now_iso() -> str:
    """当前时间的 ISO8601 字符串，带 +08:00 时区。"""
    return datetime.now(CST).isoformat(timespec="seconds")


def parse_dt(value: str) -> datetime:
    """解析 ISO8601 字符串，无时区时按东八区处理。"""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=CST)
    return dt.astimezone(CST)


def local_date(now: datetime | None = None, day_start_hour: int = 4) -> str:
    """按日界换算当前应归属的复盘日期。"""
    now = (now or datetime.now(CST)).astimezone(CST)
    return (now - timedelta(hours=day_start_hour)).date().isoformat()


def fmt_minutes(minutes: int) -> str:
    hours, mins = divmod(max(minutes, 0), 60)
    if hours and mins:
        return f"{hours}小时{mins}分钟"
    if hours:
        return f"{hours}小时"
    return f"{mins}分钟"
