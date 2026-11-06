"""SQLite CURRENT_TIMESTAMP is UTC; display local civil time consistently."""
from datetime import datetime, timezone


def local_time(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone()
    except (ValueError, TypeError, AttributeError):
        return None


def timestamp(value, full=False):
    parsed = local_time(value)
    return parsed.strftime('%Y-%m-%d %H:%M' if full else '%H:%M') if parsed else '时间未知'
