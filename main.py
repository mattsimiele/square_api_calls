import os
import datetime
from square import Square
from square.exceptions import ApiError
from dateutil import parser, tz

def get_week_bounds(reference_date=None):
    """
    Returns (start_iso, end_iso) for a 7-day window ending at `reference_date` (inclusive).
    E.g. if reference_date is today, returns last 7 days (UTC).
    """
    if reference_date is None:
        reference_date = datetime.datetime.now(tz=tz.UTC)
    # You might want Monday → Sunday windows; adapt as needed.
    end = reference_date
    start = end - datetime.timedelta(days=7)
    # Format as RFC3339 / ISO 8601 strings
    # SDK expects e.g. "2025-10-01T00:00:00Z"
    return start.isoformat(), end.isoformat()

def fetch_timecards(client: Square, location_id: str, start_iso: str, end_iso: str):
    """
    Returns list of timecard objects in the interval.
    """
    try:
        body = {
            "location_ids": [location_id],
            "start_at": start_iso,
            "end_at": end_iso
        }
        resp = client.labor.search_timecards(body)
        if resp.is_success():
            return resp.body.get("timecards", [])
        else:
            print("Error fetching timecards:", resp.errors)
            return []
    except ApiError as e:
        print("API error fetching timecards:", e)
        return []

def fetch_payments(client: Square, location_id: str, start_iso: str, end_iso: str):
    """
    Returns list of payments in the interval.
    """
    try:
        resp = client.payments.list_payments(
            begin_time=start_iso,
            end_time=end_iso,
            location_id=location_id
        )
        if resp.is_success():
            return resp.body.get("payments", [])
        else:
            print("Error fetching payments:", resp.errors)
            return []
    except ApiError as e:
        print("API error fetching payments:", e)
        return []

def aggregate_hours_and_tips(timecards, payments):
    """
    Returns dict mapping team_member_id -> {hours, declared_cash_tips, card_tips}
    """
    data = {}
    # Process timecards: hours and declared cash tips
    for tc in timecards:
        tm_id = tc.get("team_member_id")
        if tm_id is None:
            continue
        # Duration: end_at - start_at minus breaks
        start = parser.isoparse(tc["start_at"])
        end = parser.isoparse(tc["end_at"])
        total_seconds = (end - start).total_seconds()
        # Subtract break durations (if present)
        for b in tc.get("breaks", []):
            bstart = parser.isoparse(b["start_at"])
            bend = parser.isoparse(b["end_at"])
            total_seconds -= (bend - bstart).total_seconds()
        hours = total_seconds / 3600.0

        declared_cash = 0
        if "declared_cash_tip_money" in tc:
            declared_cash = tc["declared_cash_tip_money"]["amount"]  # in cents (or minor currency unit)

        rec = data.setdefault(tm_id, {"hours": 0.0, "declared_cash_tips": 0, "card_tips": 0})
        rec["hours"] += hours
        rec["declared_cash_tips"] += declared_cash

    # Process payments: card tips, assign to team_member_id
    for p in payments:
        if p.get("status") != "COMPLETED":
            continue
        tip = p.get("tip_money", {}).get("amount", 0)
        tm_id = p.get("team_member_id")
        if tm_id is None or tip == 0:
            continue
        rec = data.setdefault(tm_id, {"hours": 0.0, "declared_cash_tips": 0, "card_tips": 0})
        rec["card_tips"] += tip

    return data

def distribute_pooled_tips(data):
    """
    Example tip-out logic: for those employees, you can pool card + cash tips,
    then allocate by hours.
    This function can return a new dict with final tip allocations,
    or augment `data`.
    """
    # Sum total hours among people who have hours
    total_hours = sum(v["hours"] for v in data.values() if v["hours"] > 0)
    if total_hours == 0:
        return data

    # Sum all tips (cash declared + card)
    total_tips = sum(v["declared_cash_tips"] + v["card_tips"] for v in data.values())

    # Tip per hour
    tip_per_hour = total_tips / total_hours

    for tm_id, rec in data.items():
        rec["tip_out_allocated"] = tip_per_hour * rec["hours"]
    return data

def main():
    # Load config / env
    token = os.getenv("SQUARE_TOKEN")
    location_id = os.getenv("SQUARE_LOCATION_ID")
    if not token or not location_id:
        raise RuntimeError("Set SQUARE_TOKEN and SQUARE_LOCATION_ID env variables")
    client = Square(token=token)

    start_iso, end_iso = get_week_bounds()
    print("Reporting period:", start_iso, "→", end_iso)

    timecards = fetch_timecards(client, location_id, start_iso, end_iso)
    payments = fetch_payments(client, location_id, start_iso, end_iso)

    agg = aggregate_hours_and_tips(timecards, payments)
    agg = distribute_pooled_tips(agg)

    # Optionally: fetch team member names for nicer output
    team_map = {}
    try:
        tm_resp = client.team.list_team_members(location_id=location_id)
        if tm_resp.is_success():
            for tm in tm_resp.body.get("team_members", []):
                team_map[tm["id"]] = tm.get("given_name", "") + " " + tm.get("family_name", "")
    except ApiError:
        pass

    # Print report
    print("Employee Weekly Report")
    print("TM_ID, Name, Hours, DeclaredCashTips (cents), CardTips (cents), TipOutAllocated (cents)")
    for tm_id, rec in agg.items():
        name = team_map.get(tm_id, "")
        print(f"{tm_id}, {name}, {rec['hours']:.2f}, {rec['declared_cash_tips']}, {rec['card_tips']}, {rec.get('tip_out_allocated', 0):.0f}")

if __name__ == "__main__":
    main()
