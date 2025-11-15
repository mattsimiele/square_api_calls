from datetime import datetime, timedelta
from dateutil import tz, parser as date_parser

LOCAL_TZ = tz.gettz("America/New_York")


def get_week_bounds(date_str=None):
    if date_str:
        target = datetime.strptime(date_str, "%Y-%m-%d")
    else:
        target = datetime.now()

    local_dt = target.astimezone(LOCAL_TZ)
    start = local_dt - timedelta(days=local_dt.weekday())
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)

    end = start + timedelta(days=7)

    return (
        start.astimezone(tz.UTC).isoformat(),
        end.astimezone(tz.UTC).isoformat(),
    )


def utc_to_local(utc_str):
    if not utc_str:
        return None
    try:
        dt = date_parser.isoparse(utc_str)
        return dt.astimezone(LOCAL_TZ).date().isoformat()
    except Exception:
        return None
