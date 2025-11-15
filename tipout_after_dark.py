import os
import datetime
from square import Square
from dateutil import tz
from dateutil import parser as date_parser
from collections import defaultdict
from textwrap import shorten
import argparse

from square.types.time_range import TimeRange
from square.types.timecard_workday import TimecardWorkday
from square.types.timecard_filter import TimecardFilter
from square.types.timecard_query import TimecardQuery  # this is the wrapper type

LOCAL_TZ = tz.gettz("America/New_York")

def simulate_clockout_for_employee(timecards, target_tm_id, cutoff_hour=20):
    """
    Returns a modified *list of dicts* where only the target employee's
    shifts are truncated to cutoff_hour (local time).
    """
    simulated = []

    for tc in timecards:
        tm_id = getattr(tc, "team_member_id", None)

        try:
            start = date_parser.isoparse(tc.start_at).astimezone(LOCAL_TZ)
            end = date_parser.isoparse(tc.end_at).astimezone(LOCAL_TZ)

            # Convert frozen pydantic object to a mutable dict
            tc_data = tc.model_dump()

            if tm_id == target_tm_id and end.hour >= cutoff_hour:
                end = end.replace(hour=cutoff_hour, minute=0, second=0, microsecond=0)
                tc_data["end_at"] = end.astimezone(tz.UTC).isoformat()
                print(f"🕗 Simulated early clock-out for {tm_id} at {cutoff_hour}:00.")
            
            # Reconstruct as plain dict so downstream logic still works
            simulated.append(tc_data)

        except Exception as e:
            print(f"⚠️ Could not simulate clockout for {tm_id}: {e}")
            simulated.append(tc.model_dump())

    return simulated


def aggregate_tips_by_hour(payments, client: Square):
    """
    Groups all tip-like amounts (card tips + auto-gratuity) into hourly bins (local time).
    Returns dict[YYYY-MM-DD HH:00] = {"card_tips": cents, "auto_gratuity": cents}
    """
    hourly_data = defaultdict(lambda: {"card_tips": 0, "auto_gratuity": 0})

    for p in payments:
        if p.status != "COMPLETED":
            continue

        # Convert payment time to local
        created_at = getattr(p, "created_at", None)
        if not created_at:
            continue

        local_dt = date_parser.isoparse(created_at).astimezone(LOCAL_TZ)
        hour_bucket = local_dt.replace(minute=0, second=0, microsecond=0)

        # Card tip amount
        tip_amt = getattr(getattr(p, "tip_money", None), "amount", 0)

        # Include auto-gratuity (service charge)
        order_id = getattr(p, "order_id", None)
        auto_grat = fetch_order_service_charges(client, order_id) if order_id else 0

        hourly_data[hour_bucket]["card_tips"] += tip_amt
        hourly_data[hour_bucket]["auto_gratuity"] += auto_grat

    return hourly_data

def print_hourly_tip_summary(hourly_data):
    print("\n🕒 Tipouts by Hour (Local Time)")
    print("=" * 70)
    print(f"{'Hour Block':<25} {'Card Tips':>12} {'Auto Gratuity':>15} {'Total':>12}")
    print("-" * 70)
    for hour, vals in sorted(hourly_data.items()):
        card = vals["card_tips"] / 100
        grat = vals["auto_gratuity"] / 100
        total = card + grat
        print(f"{hour.strftime('%Y-%m-%d %H:%M'):<25} {card:12.2f} {grat:15.2f} {total:12.2f}")
    print("=" * 70)


def get_week_bounds(reference_date=None, start_of_week=0):
    """
    Returns (start_iso, end_iso) for the week (Monday–Sunday by default)
    containing the given reference_date (or today if None).
    
    Args:
        reference_date: datetime or None → defaults to now in local time.
        start_of_week: int (0=Monday, 6=Sunday)
    """
    if reference_date:
        target = datetime.datetime.strptime(reference_date, "%Y-%m-%d")
    else:
        target = datetime.now()

    # Normalize to local time zone
    reference_date = target.astimezone(LOCAL_TZ)

    # Compute start (Monday by default)
    weekday = reference_date.weekday()
    start_delta = (weekday - start_of_week) % 7
    start = (reference_date - datetime.timedelta(days=start_delta)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    # End of Sunday (23:59:59.999)
    end = (start + datetime.timedelta(days=7)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    # Return in ISO UTC format (Square expects UTC)
    return start.astimezone(tz.UTC).isoformat(), end.astimezone(tz.UTC).isoformat()


def fetch_timecards(client: "Square", location_id: str, start_iso: str, end_iso: str, print_total_hours: bool = True):
    """
    Returns list of timecard objects in the interval.
    Optionally prints total hours worked for the period.
    """
    try:
        # Construct the filter
        filter_obj = TimecardFilter(
            location_ids=[location_id],
            start=TimeRange(start_at=start_iso),
            end=TimeRange(end_at=end_iso),
            workday=TimecardWorkday(start_at=start_iso, end_at=end_iso)
        )

        # Wrap in a query object
        query_obj = TimecardQuery(filter=filter_obj)
        # print(query_obj)

        # Use the typed object, not a dict
        resp = client.labor.search_timecards(query=query_obj)

        # resp = client.labor.search_timecards(query=query)

        if hasattr(resp, "timecards") and resp.timecards:
            timecards = resp.timecards

            if print_total_hours:
                total_seconds = 0
                for tc in timecards:
                    # If the timecard has worked_hours directly (in seconds)
                    if hasattr(tc, "worked_hours"):
                        total_seconds += tc.worked_hours * 3600  # if worked_hours is in hours
                    # Or compute from clock_in_time / clock_out_time
                    elif hasattr(tc, "clock_in_time") and hasattr(tc, "clock_out_time"):
                        fmt = "%Y-%m-%dT%H:%M:%S%z"
                        try:
                            start = datetime.fromisoformat(tc.clock_in_time)
                            end = datetime.fromisoformat(tc.clock_out_time)
                            total_seconds += (end - start).total_seconds()
                        except Exception:
                            continue

                total_hours = total_seconds / 3600
                # print(f"Total hours worked in period: {total_hours:.2f} hours")
            # print(timecards)
            return timecards

        else:
            print("⚠️ No timecards found or error returned:", getattr(resp, "errors", None))
            return []

    except Exception as e:
        print("❌ Exception fetching timecards:", e)
        return []



def fetch_payments(client: Square, location_id: str, start_iso: str, end_iso: str):
    """
    Returns a list of payments in the interval for a given location.
    """
    try:
        # list() returns a SyncPager[Payment]
        pager = client.payments.list(
            begin_time=start_iso,
            end_time=end_iso,
            location_id=location_id,
            limit=100  # optional, max per page
        )
        payments = list(pager)  # iterates through all pages automatically
        if payments:
            #for payment in payments:
            #    print(payment)
            return payments
        else:
            print("⚠️ No payments found in the interval")
            return []
    except Exception as e:
        print("⚠️ Error fetching payments:", e)
        return []

def fetch_order_service_charges(client: Square, order_id: str):
    """
    Fetches service charges for a given order, returning total gratuity amount in cents.
    """
    try:
        # Some SDK versions use retrieve(), others retrieve_order()
        # print(dir(client.orders))
        if hasattr(client.orders, "get"):
            resp = client.orders.get(order_id=order_id)
        elif hasattr(client.orders, "retrieve"):
            resp = client.orders.retrieve(order_id=order_id)
        else:
            resp = client.orders.retrieve_order(order_id=order_id)
        order = getattr(resp, "order", None)
        # print(f"Response Dictionary: {dir(resp)} \n")
        # print(f"Order Dictionary: {dir(order)} \n")
        if not order or not getattr(order, "service_charges", None):
            return 0

        total = 0
        # print(f"Order Service Charges: {order.service_charges}\n")
        for sc in order.service_charges:
            # Detect Square auto-gratuity type
            if getattr(sc, "type", "") == "AUTO_GRATUITY":
                total += getattr(getattr(sc, "applied_money", None), "amount", 0)
        return total

    except Exception as e:
        print(f"⚠️ Could not fetch order {order_id}: {e}")
        return 0


def aggregate_hours_and_tips(timecards, payments):
    """
    Returns dict mapping team_member_id -> {hours, declared_cash_tips, card_tips}
    """
    data = {}

    # Process timecards: hours and declared cash tips
    for tc in timecards:
        tm_id = tc.team_member_id
        if not tm_id:
            continue

        start = date_parser.isoparse(tc.start_at)
        end = date_parser.isoparse(tc.end_at)
        total_seconds = (end - start).total_seconds()

        # Subtract breaks
        for b in getattr(tc, "breaks", []) or []:
            bstart = date_parser.isoparse(b.start_at)
            bend = date_parser.isoparse(b.end_at)
            total_seconds -= (bend - bstart).total_seconds()

        hours = total_seconds / 3600.0
        declared_cash = 0
        if getattr(tc, "declared_cash_tip_money", None):
            declared_cash = tc.declared_cash_tip_money.amount  # in cents

        rec = data.setdefault(tm_id, {"hours": 0.0, "declared_cash_tips": 0, "card_tips": 0})
        rec["hours"] += hours
        rec["declared_cash_tips"] += declared_cash
        # Determine eligibility from team member info
        eligible = getattr(tc, "team_member", None)
        eligible = getattr(eligible, "eligible_for_tip", False) if eligible else False
        rec["eligible"] = eligible

    # Process payments: card tips
    for p in payments:
        if p.status != "COMPLETED":
            continue
        tip = getattr(p.tip_money, "amount", 0)
        tm_id = getattr(p, "team_member_id", None)
        if not tm_id or tip == 0:
            continue

        rec = data.setdefault(tm_id, {"hours": 0.0, "declared_cash_tips": 0, "card_tips": 0})
        rec["card_tips"] += tip

    return data


def distribute_pooled_tips(data):
    """
    Pools tips from all employees and distributes them by hours worked,
    respecting tip eligibility. Employees marked as ineligible contribute
    their tips to the pool but do not receive a share.
    
    Args:
        data: dict mapping team_member_id -> {
            hours, declared_cash_tips, card_tips, eligible (bool)
        }

    Returns:
        data with 'tip_out_allocated' added per team member
    """
    total_pool = 0
    # First, collect tips from ineligible employees and initialize eligible employees
    for tm_id, rec in data.items():
        if not rec.get("eligible", True):
            # Ineligible employees contribute their tips to the pool
            total_pool += rec.get("declared_cash_tips", 0) + rec.get("card_tips", 0)
            rec["tip_out_allocated"] = 0
        else:
            # Eligible employees start with their own tips
            rec["tip_out_allocated"] = rec.get("declared_cash_tips", 0) + rec.get("card_tips", 0)

    # Compute total hours of eligible employees
    eligible_hours = sum(rec["hours"] for rec in data.values() if rec.get("eligible", True))

    if eligible_hours > 0 and total_pool > 0:
        # Distribute the pooled tips proportionally by hours worked
        for tm_id, rec in data.items():
            if rec.get("eligible", True):
                rec["tip_out_allocated"] += total_pool * (rec["hours"] / eligible_hours)

    return data

def aggregate_hours_and_tips_by_day(timecards, payments, client: Square):
    """
    Returns a nested dict:
    data[date][team_member_id] = {hours, declared_cash_tips, card_tips, eligible}
    """
    data = defaultdict(lambda: defaultdict(lambda: {
        "hours": 0.0, "declared_cash_tips": 0, "card_tips": 0, "eligible": False
    }))

    # --- Process timecards ---
    for tc in timecards:
        tm_id = tc.team_member_id
        if not tm_id or not getattr(tc, "start_at", None):
            continue

        start = date_parser.isoparse(tc.start_at)
        end = date_parser.isoparse(tc.end_at)
        work_date = start.date().isoformat()

        total_seconds = (end - start).total_seconds()

        # Subtract breaks if present
        for b in getattr(tc, "breaks", []) or []:
            try:
                bstart = date_parser.isoparse(b.start_at)
                bend = date_parser.isoparse(b.end_at)
                total_seconds -= (bend - bstart).total_seconds()
            except Exception:
                continue

        hours = total_seconds / 3600.0
        declared_cash = 0
        if getattr(tc, "declared_cash_tip_money", None):
            declared_cash = tc.declared_cash_tip_money.amount  # in cents

        rec = data[work_date][tm_id]
        rec["hours"] += hours
        rec["declared_cash_tips"] += declared_cash
        # print(tc)
        eligible = getattr(tc, "wage", None)
        # print(dir(eligible))
        # print(dir(tc))
        rec["eligible"] = getattr(eligible, "tip_eligible", False)

    # --- Process payments (assign to payment date) ---
    for p in payments:
        if p.status != "COMPLETED" or not getattr(p, "created_at", None):
            continue

        pay_date = date_parser.isoparse(p.created_at).astimezone(LOCAL_TZ).date().isoformat()
        tm_id = getattr(p, "team_member_id", None)
        if not tm_id:
            continue

        # Card tips
        card_tip_amount = getattr(getattr(p, "tip_money", None), "amount", 0)

        # Include auto-gratuity / service charges if applicable
        # Fetch any auto-gratuity (service charge marked as gratuity)
        service_charge_total = 0
        order_id = getattr(p, "order_id", None)
        if order_id:
            service_charge_total = fetch_order_service_charges(client, order_id)

        total_tip_like_amount = card_tip_amount + service_charge_total

        if total_tip_like_amount == 0:
            continue

        rec = data[pay_date][tm_id]
        rec["card_tips"] += total_tip_like_amount
        # print("Payment:", pay_date, tm_id, tip)
    # print("Aggregated data by day:", dict(data))
    return data

def utc_to_local(utc_str):
    """
    Convert Square UTC timestamp (ISO8601 string) to local date string (YYYY-MM-DD).
    """
    if not utc_str:
        return None
    try:
        # dateutil.parser.isoparse handles "2025-11-07T01:47:57.978Z" and offsets
        utc_dt = date_parser.isoparse(utc_str)
        # ensure we convert to the local timezone you set earlier
        local_dt = utc_dt.astimezone(LOCAL_TZ)
        return local_dt.date().isoformat()
    except Exception as e:
        print(f"⚠️ utc_to_local failed for {utc_str!r}: {e}")
        return None

def distribute_daily_tips_old(data_by_day):
    """
    Distributes tips for each day only among eligible employees who worked that day.
    Returns a flat dict[team_member_id] with total allocations.
    """
    totals = defaultdict(lambda: {
        "hours": 0.0,
        "declared_cash_tips": 0,
        "card_tips": 0,
        "tip_out_allocated": 0,
        "tip_out_allocated_after_card_processing": 0
    })

    for date_str, members in data_by_day.items():
        total_pool = 0
        eligible_hours = 0

        # Step 1: gather pool and hours for eligible
        for tm_id, rec in members.items():
            if rec.get("eligible", True):
                eligible_hours += rec["hours"]
            else:
                total_pool += rec["declared_cash_tips"] + rec["card_tips"]
        # print(f"Date {date_str}: total_pool={total_pool}, eligible_hours={eligible_hours}")
        # Step 2: add eligible employees' own tips to the pool
        total_pool += sum(
            rec["declared_cash_tips"] + rec["card_tips"]
            for rec in members.values() if rec.get("eligible", True)
        )
        # print(f"Date {date_str}: total_pool after adding eligible tips={total_pool}")
        # Step 3: distribute to eligible employees by hours
        for tm_id, rec in members.items():
            totals[tm_id]["hours"] += rec["hours"]
            totals[tm_id]["declared_cash_tips"] += rec["declared_cash_tips"]
            totals[tm_id]["card_tips"] += rec["card_tips"]

            if rec.get("eligible", True) and eligible_hours > 0:
                share = total_pool * (rec["hours"] / eligible_hours)
                totals[tm_id]["tip_out_allocated"] += share
                totals[tm_id]["tip_out_allocated_after_card_processing"] += share * 0.975  # assuming 2.5% card processing fee

    return totals

from collections import defaultdict

def distribute_daily_tips(data_by_day):
    """
    Distribute daily tip pools evenly among all eligible employees who worked that day.
    Each day’s total tips (cash + card) are combined and split evenly.
    Returns a dict[team_member_id] with total allocations.
    """
    totals = defaultdict(lambda: {
        "hours": 0.0,
        "declared_cash_tips": 0,
        "card_tips": 0,
        "tip_out_allocated": 0,
        "tip_out_allocated_after_card_processing": 0
    })

    for date_str, members in data_by_day.items():
        # Total tips for the day (cash + card)
        total_pool = sum(
            rec.get("declared_cash_tips", 0) + rec.get("card_tips", 0)
            for rec in members.values()
        )

        # Eligible employees = anyone with hours > 0 and marked eligible
        eligible_members = [
            tm_id for tm_id, rec in members.items()
            if rec.get("eligible", True) and rec.get("hours", 0) > 0
        ]
        num_eligible = len(eligible_members)

        # First: always accumulate hours/tip fields so they show up in report even if no allocation
        for tm_id, rec in members.items():
            totals[tm_id]["hours"] += rec.get("hours", 0.0)
            totals[tm_id]["declared_cash_tips"] += rec.get("declared_cash_tips", 0)
            totals[tm_id]["card_tips"] += rec.get("card_tips", 0)

        # If nobody eligible, skip allocation but keep hours recorded
        if num_eligible == 0:
            # Optionally, you can log this
            # print(f"Date {date_str}: no eligible employees to allocate ${total_pool/100:.2f}")
            continue

        # Even share per eligible employee
        equal_share = total_pool / num_eligible

        # Apply allocations to eligible employees
        for tm_id in eligible_members:
            totals[tm_id]["tip_out_allocated"] += equal_share
            totals[tm_id]["tip_out_allocated_after_card_processing"] += equal_share * 0.975  # adjust for card fee

    return totals

def distribute_tips_by_clockin(payments, timecards, client: Square, simulate_tm_id=None, simulate_cutoff=None):
    """
    Splits each tip (card + auto-gratuity) evenly among all *eligible* employees
    who were clocked in at the time the payment occurred.
    If simulate_tm_id and simulate_cutoff are provided, only that employee’s
    shifts are truncated to the cutoff time (local).
    """
    totals = defaultdict(lambda: {
        "hours": 0.0,
        "declared_cash_tips": 0,
        "card_tips": 0,
        "tip_out_allocated": 0,
        "tip_out_allocated_after_card_processing": 0
    })

    # Preprocess timecards into local spans
    clock_spans = []
    for tc in timecards:
        tm_id = getattr(tc, "team_member_id", None)
        if not tm_id or not getattr(tc, "start_at", None) or not getattr(tc, "end_at", None):
            continue

        eligible = False
        wage = getattr(tc, "wage", None)
        if wage and hasattr(wage, "tip_eligible"):
            eligible = wage.tip_eligible

        start = date_parser.isoparse(tc.start_at).astimezone(LOCAL_TZ)
        end = date_parser.isoparse(tc.end_at).astimezone(LOCAL_TZ)

        # --- simulate early clock-out if requested ---
        if simulate_tm_id and simulate_cutoff and tm_id == simulate_tm_id:
            if end.hour > simulate_cutoff:
                end = end.replace(hour=simulate_cutoff, minute=0, second=0, microsecond=0)
                print(f"🕗 Simulated early clock-out for {tm_id} at {simulate_cutoff}:00")

        clock_spans.append((tm_id, start, end, eligible))

        # Track hours for reporting (use simulated end if applicable)
        totals[tm_id]["hours"] += (end - start).total_seconds() / 3600.0

    # --- process payments ---
    for p in payments:
        if p.status != "COMPLETED":
            continue

        pay_time = date_parser.isoparse(p.created_at).astimezone(LOCAL_TZ)
        card_tip = getattr(getattr(p, "tip_money", None), "amount", 0)
        order_id = getattr(p, "order_id", None)
        auto_grat = fetch_order_service_charges(client, order_id) if order_id else 0
        total_tip_amt = card_tip + auto_grat
        if total_tip_amt == 0:
            continue

        # Find eligible employees clocked in at that moment
        eligible_employees = [
            tm_id for (tm_id, start, end, eligible) in clock_spans
            if eligible and start <= pay_time <= end
        ]
        if not eligible_employees:
            continue

        # Split evenly among eligible clocked-in employees
        share = total_tip_amt / len(eligible_employees)
        for tm_id in eligible_employees:
            rec = totals[tm_id]
            rec["card_tips"] += card_tip / len(eligible_employees)
            rec["tip_out_allocated"] += share
            rec["tip_out_allocated_after_card_processing"] += share * 0.975  # 2.5% card fee
            if auto_grat > 0:
                rec["card_tips"] += auto_grat / len(eligible_employees)

    return totals



def main(target_date=None, ignore_dates=None, start_of_week=0):
    token = os.getenv("SQUARE_ACCESS_TOKEN") or "EAAAly8mEyanb9A8n_mDWkIXvzMj74XtZOM6gDTChMPpyBSro1CSFTqtw9uNF80D"
    location_id = os.getenv("SQUARE_LOCATION_ID") or "LRJKGMZV2MY77"
    run_tipout_hourly_report = False
    run_tipout_report = True

    client = Square(token=token)
    location_list = client.locations.list()
    # location_list = location_list.locations()
    for location in location_list.locations or []:
        print(f"Found location: {location.name} (ID: {location.id})")
        location_id = location.id  # use the last one found

        if not token or not location_id:
            raise RuntimeError("Set SQUARE_ACCESS_TOKEN and SQUARE_LOCATION_ID env vars or edit script.")
        start_iso, end_iso = get_week_bounds(target_date, start_of_week=start_of_week)
        print(f"📅 Reporting period: {start_iso} → {end_iso}")

        timecards = fetch_timecards(client, location_id, start_iso, end_iso)
        payments = fetch_payments(client, location_id, start_iso, end_iso)

        if ignore_dates:
            filtered_payments = []
            for p in payments:
                payment_date = getattr(p, "created_at", "")
                # print("Payment created_at:", payment_date)
                local_date = utc_to_local(payment_date)
                # print(f"Payment date: {local_date}")
                if local_date not in ignore_dates:
                    filtered_payments.append(p)
            payments = filtered_payments

        simulated_tm = "TM9FuJdbMUXRz-KA"
        simulated_tm = None
        simulated_cutoff = 20
        simulated_cutoff = None
        # if simulated_tm is not None:
        #     timecards = simulate_clockout_for_employee(timecards, simulated_tm)

        data_by_day = aggregate_hours_and_tips_by_day(timecards, payments, client)
        agg = distribute_daily_tips(data_by_day)
        allocations = distribute_tips_by_clockin(payments, timecards, client, simulated_tm, simulate_cutoff=simulated_cutoff)
        agg1 = allocations
        if run_tipout_hourly_report:
            hourly_tips = aggregate_tips_by_hour(payments, client)
            print_hourly_tip_summary(hourly_tips)
        
        aggs = [agg, agg1]
        if run_tipout_report:
            for agg in aggs:
                # Get team member names
                team_map = {}
                tm_resp = client.team_members.search(query={"filter":{"location_ids":[location_id], "status":"ACTIVE"}})
                for tm in getattr(tm_resp, "team_members", []) or []:
                    name = f"{tm.given_name or ''} {tm.family_name or ''}".strip()
                    team_map[tm.id] = name

                # Print report
                print("\n👥 Employee Weekly Tip Report")
                print("=" * 105)
                header = f"{'Name':<25} {'Hours':>7} {'Cash Tips':>12} {'Card Tips':>12} {'Allocated':>14} {'Allocated (after Fee)':>28}"
                print(header)
                print("-" * 105)

                for tm_id, rec in sorted(agg.items(), key=lambda x: x[1]["tip_out_allocated"], reverse=True):
                    name = shorten(team_map.get(tm_id, "Unknown"), width=25, placeholder="…")
                    hours = rec["hours"]
                    cash = rec["declared_cash_tips"] / 100  # convert cents → dollars
                    card = rec["card_tips"] / 100
                    allocated = rec.get("tip_out_allocated", 0) / 100
                    allocated_after_fee = rec.get("tip_out_allocated_after_card_processing", 0) / 100
                    print(f"{name:<25} {hours:7.2f} {cash:12.2f} {card:12.2f} {allocated:14.2f} {allocated_after_fee:28.2f}")

                print("-" * 105)

                total_cash_tips = sum(tm["declared_cash_tips"] for tm in agg.values()) / 100
                total_card_tips = sum(tm["card_tips"] for tm in agg.values()) / 100
                total_allocated = sum(tm.get("tip_out_allocated", 0) for tm in agg.values()) / 100
                total_allocated_after_fee = sum(tm.get("tip_out_allocated_after_card_processing", 0) for tm in agg.values()) / 100

                print(f"{'TOTALS':<25} {'':7} {total_cash_tips:12.2f} {total_card_tips:12.2f} {total_allocated:14.2f} {total_allocated_after_fee:28.2f}")
                print("=" * 105)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate weekly payroll/tip report from Square data.")
    parser.add_argument(
        "--date",
        type=str,
        help="Target date (YYYY-MM-DD) within the week to report on. Default: today.",
    )
    parser.add_argument(
        "--ignore",
        nargs="*",
        default=[],
        help="List of specific dates (YYYY-MM-DD) to ignore (e.g. cleaning shifts).",
    )

    args = parser.parse_args()
    main(target_date=args.date, ignore_dates=args.ignore)
