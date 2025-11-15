from datetime import datetime
from dateutil import parser as date_parser
from dateutil import tz
from square.types.time_range import TimeRange
from square.types.timecard_workday import TimecardWorkday
from square.types.timecard_filter import TimecardFilter
from square.types.timecard_query import TimecardQuery

LOCAL_TZ = tz.gettz("America/New_York")


def fetch_timecards(client, location_id, start_iso, end_iso):
    """
    Returns list of timecard objects in the window.
    """
    try:
        filter_obj = TimecardFilter(
            location_ids=[location_id],
            start=TimeRange(start_at=start_iso),
            end=TimeRange(end_at=end_iso),
            workday=TimecardWorkday(start_at=start_iso, end_at=end_iso)
        )

        query_obj = TimecardQuery(filter=filter_obj)
        resp = client.labor.search_timecards(query=query_obj)

        return getattr(resp, "timecards", []) or []

    except Exception as e:
        print("❌ Error fetching timecards:", e)
        return []
