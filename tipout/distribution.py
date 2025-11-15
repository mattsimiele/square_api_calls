from collections import defaultdict
from dateutil import parser as date_parser
from dateutil import tz

from .payments import fetch_order_service_charges
LOCAL_TZ = tz.gettz("America/New_York")


def distribute_daily_tips(data_by_day):
    totals = defaultdict(lambda: {
        "hours": 0.0,
        "declared_cash_tips": 0,
        "card_tips": 0,
        "tip_out_allocated": 0,
        "tip_out_allocated_after_card_processing": 0
    })

    for day, members in data_by_day.items():
        pool = sum(
            rec["declared_cash_tips"] + rec["card_tips"]
            for rec in members.values()
        )

        eligible = [tm for tm, rec in members.items()
                    if rec["eligible"] and rec["hours"] > 0]

        # accumulate hours + totals across whole week
        for tm_id, rec in members.items():
            totals[tm_id]["hours"] += rec["hours"]
            totals[tm_id]["declared_cash_tips"] += rec["declared_cash_tips"]
            totals[tm_id]["card_tips"] += rec["card_tips"]

        if not eligible:
            continue

        share = pool / len(eligible)
        for tm_id in eligible:
            totals[tm_id]["tip_out_allocated"] += share
            totals[tm_id]["tip_out_allocated_after_card_processing"] += share * 0.975

    return totals


def distribute_tips_by_clockin(payments, timecards, client, simulate_tm_id=None, simulate_cutoff=None):
    totals = defaultdict(lambda: {
        "hours": 0.0,
        "declared_cash_tips": 0,
        "card_tips": 0,
        "tip_out_allocated": 0,
        "tip_out_allocated_after_card_processing": 0
    })

    clock_spans = []
    for tc in timecards:
        tm_id = tc.team_member_id
        if not tm_id or not getattr(tc, "start_at", None):
            continue

        start = date_parser.isoparse(tc.start_at).astimezone(LOCAL_TZ)
        end = date_parser.isoparse(tc.end_at).astimezone(LOCAL_TZ)

        eligible = getattr(getattr(tc, "wage", None), "tip_eligible", False)

        clock_spans.append((tm_id, start, end, eligible))

        totals[tm_id]["hours"] += (end - start).total_seconds() / 3600

    for p in payments:
        if p.status != "COMPLETED":
            continue

        pay_time = date_parser.isoparse(p.created_at).astimezone(LOCAL_TZ)
        card = getattr(getattr(p, "tip_money", None), "amount", 0)
        auto = fetch_order_service_charges(client, getattr(p, "order_id", None))
        
        tip_amt = card + auto

        eligible_tms = [
            tm for (tm, start, end, elig) in clock_spans
            if elig and start <= pay_time <= end
        ]

        if not eligible_tms or tip_amt == 0:
            continue

        share = tip_amt / len(eligible_tms)
        for tm in eligible_tms:
            totals[tm]["card_tips"] += share
            totals[tm]["tip_out_allocated"] += share
            totals[tm]["tip_out_allocated_after_card_processing"] += share * 0.975

    return totals
