from textwrap import shorten
from collections import defaultdict


def print_weekly_report(client, location_id, agg, title="Tip Report"):
    team_map = {}
    tm_search = client.team_members.search(
        query={"filter": {"location_ids": [location_id], "status": "ACTIVE"}}
    )
    for tm in getattr(tm_search, "team_members", []) or []:
        name = f"{tm.given_name or ''} {tm.family_name or ''}".strip()
        team_map[tm.id] = name

    print("\n" + title)
    print("=" * 105)
    print(f"{'Name':<25} {'Hours':>7} {'Cash':>12} {'Card':>12} {'Allocated':>14} {'After Fee':>15}")
    print("-" * 105)

    total_hours = 0
    total_cash = 0
    total_card = 0
    total_alloc = 0
    total_alloc_after = 0

    for tm_id, rec in sorted(agg.items(), key=lambda x: x[1]["tip_out_allocated"], reverse=True):
        name = shorten(team_map.get(tm_id, "Unknown"), width=25, placeholder="…")
        hours = rec["hours"]
        cash = rec["declared_cash_tips"] / 100
        card = rec["card_tips"] / 100
        alloc = rec["tip_out_allocated"] / 100
        alloc_after = rec["tip_out_allocated_after_card_processing"] / 100

        # Print row
        print(f"{name:<25} {hours:7.2f} {cash:12.2f} {card:12.2f} {alloc:14.2f} {alloc_after:15.2f}")

        # Accumulate totals
        total_hours += hours
        total_cash += cash
        total_card += card
        total_alloc += rec["tip_out_allocated"] / 100
        total_alloc_after += rec["tip_out_allocated_after_card_processing"] / 100

    print("-" * 105)

    # Totals row
    print(
        f"{'TOTALS':<25} "
        f"{total_hours:7.2f} "
        f"{total_cash:12.2f} "
        f"{total_card:12.2f} "
        f"{total_alloc:14.2f} "
        f"{total_alloc_after:15.2f}"
    )

    print("=" * 105)


def print_hourly_tip_summary(hourly_data):
    print("\n🕒 Hourly Tip Summary")
    print("=" * 70)
    print(f"{'Hour':<25} {'Card Tips':>12} {'Auto Grat':>12} {'Total':>12}")
    print("-" * 70)
    for hour, v in sorted(hourly_data.items()):
        card = v["card_tips"] / 100
        auto = v["auto_gratuity"] / 100
        print(f"{hour:<25} {card:12.2f} {auto:12.2f} {card + auto:12.2f}")


def print_combined_report(client, all_location_data, title="Combined Payroll Summary"):
    """
    all_location_data = {
        location_id: agg_dict_for_that_location,
        ...
    }
    """

    # Build team member name map across ALL locations
    team_map = {}
    for location_id in all_location_data.keys():
        tm_search = client.team_members.search(
            query={"filter": {"location_ids": [location_id], "status": "ACTIVE"}}
        )
        for tm in getattr(tm_search, "team_members", []) or []:
            name = f"{tm.given_name or ''} {tm.family_name or ''}".strip()
            team_map[tm.id] = name

    # Combine totals from all locations
    combined = defaultdict(lambda: {
        "hours": 0,
        "declared_cash_tips": 0,
        "card_tips": 0,
        "tip_out_allocated": 0,
        "tip_out_allocated_after_card_processing": 0
    })

    for location_id, agg in all_location_data.items():
        for tm_id, rec in agg.items():
            combined[tm_id]["hours"] += rec["hours"]
            combined[tm_id]["declared_cash_tips"] += rec["declared_cash_tips"]
            combined[tm_id]["card_tips"] += rec["card_tips"]
            combined[tm_id]["tip_out_allocated"] += rec["tip_out_allocated"]
            combined[tm_id]["tip_out_allocated_after_card_processing"] += rec["tip_out_allocated_after_card_processing"]

    # --- Print Report ---
    print("\n" + title)
    print("=" * 105)
    print(f"{'Name':<25} {'Hours':>7} {'Cash':>12} {'Card':>12} {'Allocated':>14} {'After Fee':>15}")
    print("-" * 105)

    # Sort alphabetically by name, not Square ID
    for tm_id, rec in sorted(combined.items(), key=lambda x: team_map.get(x[0], "zzz").lower()):
        name = team_map.get(tm_id, "Unknown")
        hours = rec["hours"]
        cash = rec["declared_cash_tips"] / 100
        card = rec["card_tips"] / 100
        alloc = rec["tip_out_allocated"] / 100
        alloc_after = rec["tip_out_allocated_after_card_processing"] / 100

        print(f"{name:<25} {hours:7.2f} {cash:12.2f} {card:12.2f} {alloc:14.2f} {alloc_after:15.2f}")

    print("=" * 105)
