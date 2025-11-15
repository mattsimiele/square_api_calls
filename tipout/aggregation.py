from collections import defaultdict
from dateutil import parser as date_parser
from dateutil import tz
from .payments import fetch_order_service_charges

LOCAL_TZ = tz.gettz("America/New_York")


def aggregate_tips_by_hour(payments, client):
    hourly = defaultdict(lambda: {"card_tips": 0, "auto_gratuity": 0})

    for p in payments:
        if p.status != "COMPLETED":
            continue

        dt = date_parser.isoparse(p.created_at).astimezone(LOCAL_TZ)
        bucket = dt.replace(minute=0, second=0, microsecond=0)

        card = getattr(getattr(p, "tip_money", None), "amount", 0)
        auto = fetch_order_service_charges(client, getattr(p, "order_id", None))

        hourly[bucket]["card_tips"] += card
        hourly[bucket]["auto_gratuity"] += auto

    return hourly


def aggregate_hours_and_tips_by_day(timecards, payments, client):
    data = defaultdict(lambda: defaultdict(lambda: {
        "hours": 0.0,
        "declared_cash_tips": 0,
        "card_tips": 0,
        "eligible": False
    }))

    # Timecards
    for tc in timecards:
        tm_id = tc.team_member_id
        if not tm_id or not getattr(tc, "start_at", None):
            continue

        # Convert BOTH timestamps to local timezone
        start = date_parser.isoparse(tc.start_at).astimezone(LOCAL_TZ)
        end = date_parser.isoparse(tc.end_at).astimezone(LOCAL_TZ)

        # Date key MUST match the date the shift started IN LOCAL TIME
        date_key = start.date().isoformat()

        hours = (end - start).total_seconds() / 3600
        cash = getattr(getattr(tc, "declared_cash_tip_money", None), "amount", 0)

        data[date_key][tm_id]["hours"] += hours
        data[date_key][tm_id]["declared_cash_tips"] += cash

        wage = getattr(tc, "wage", None)
        data[date_key][tm_id]["eligible"] = getattr(wage, "tip_eligible", False)

    # Payments
    for p in payments:
        if p.status != "COMPLETED":
            continue
        dt = date_parser.isoparse(p.created_at).astimezone(LOCAL_TZ)
        date_key = dt.date().isoformat()

        tm_id = getattr(p, "team_member_id", None)
        if not tm_id:
            continue

        card = getattr(getattr(p, "tip_money", None), "amount", 0)
        auto = fetch_order_service_charges(client, getattr(p, "order_id", None))

        data[date_key][tm_id]["card_tips"] += (card + auto)

    return data
