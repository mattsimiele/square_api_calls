import argparse
import os
from square import Square

from tipout.timecards import fetch_timecards
from tipout.payments import fetch_payments
from tipout.aggregation import aggregate_hours_and_tips_by_day, aggregate_tips_by_hour
from tipout.distribution import distribute_daily_tips, distribute_tips_by_clockin
from tipout.reporting import print_weekly_report, print_hourly_tip_summary, print_combined_report
from tipout.utils import get_week_bounds, utc_to_local

def main():
    parser = argparse.ArgumentParser(description="Weekly Square Tipout Report")
    parser.add_argument("--date", help="Date inside the target week (YYYY-MM-DD)")
    parser.add_argument("--ignore", nargs="*", default=[], help="Dates to ignore")
    parser.add_argument("--location", nargs="*", help="Specific location IDs to include")
    args = parser.parse_args()

    token = os.getenv("SQUARE_ACCESS_TOKEN") or "EAAAly8mEyanb9A8n_mDWkIXvzMj74XtZOM6gDTChMPpyBSro1CSFTqtw9uNF80D"
    if not token:
        raise RuntimeError("Missing SQUARE_ACCESS_TOKEN environment variable.")

    client = Square(token=token)

    # --- Fetch all locations ---
    loc_resp = client.locations.list()
    all_locations = {loc.id: loc for loc in (loc_resp.locations or [])}

    # --- Filter locations if --location flag is given ---
    if args.location:
        target_locations = [all_locations[loc_id] for loc_id in args.location if loc_id in all_locations]
        if not target_locations:
            print("⚠️ No valid location IDs were provided.")
            return
    else:
        target_locations = list(all_locations.values())

    # --- Date range ---
    start_iso, end_iso = get_week_bounds(args.date)
    print(f"📅 Reporting period: {start_iso} → {end_iso}")

    all_location_results = {}
    all_location_clockin_results = {}

    # --- Process each location ---
    for loc in target_locations:
        location_id = loc.id
        print(f"\n📍 Processing Location: {loc.name} (ID: {location_id})")

        timecards = fetch_timecards(client, location_id, start_iso, end_iso)
        payments  = fetch_payments(client, location_id, start_iso, end_iso)

        if args.ignore:
            filtered = []
            for p in payments:
                local_date = utc_to_local(getattr(p, "created_at", None))
                if local_date not in args.ignore:
                    filtered.append(p)
            payments = filtered

        # --- Aggregation ---
        daily = aggregate_hours_and_tips_by_day(timecards, payments, client)

        # --- Distribute ---
        daily_alloc   = distribute_daily_tips(daily)
        clockin_alloc = distribute_tips_by_clockin(
            payments, timecards, client,
            simulate_tm_id=None,
            simulate_cutoff=None
        )

        # --- Reporting ---
        # print_weekly_report(client, location_id, daily_alloc, title=f"{loc.name} • Daily Pool Tip Report")
        # print_weekly_report(client, location_id, clockin_alloc, title=f"{loc.name} • Clock-In Tip Report")
        
        all_location_results[location_id] = daily_alloc
        all_location_clockin_results[location_id] = clockin_alloc
        # hourly = aggregate_tips_by_hour(payments, client)
        # print_hourly_tip_summary(hourly)
    print_combined_report(client, all_location_results, title="Combined Tip + Payroll Summary Across All Locations")
    print_combined_report(client, all_location_clockin_results, title="Combined Clock-In Tip Summary Across All Locations")



if __name__ == "__main__":
    main()
