#!/usr/bin/env python3
import argparse
from datetime import datetime, timezone
import os
import pandas as pd
from square import Square

from square_client import SquareOrderFinder
from utils.square_file_output import save_results

from extractors.cheese_board import CheeseBoardExtractor
from extractors.thanksgiving_board import ThanksgivingBoardExtractor
from extractors.charcuterie_board import CharcuterieBoardExtractor
from extractors.countdown import HolidayCountdown

EXTRACTORS = [
    ThanksgivingBoardExtractor(),
    CharcuterieBoardExtractor(),
    # CheeseBoardExtractor(),
    HolidayCountdown(),
]

def get_extractors(item, run_all=False):
    if run_all:
        return EXTRACTORS

    # Otherwise choose one based on item name
    item_lower = item.lower()

    for extractor in EXTRACTORS:
        if extractor.KEYWORD in item_lower:
            return [extractor]

    raise ValueError(f"No extractor matches item '{item}'")



def main():
    parser = argparse.ArgumentParser(description="Search Square item sales.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--item", help="Single item name")
    group.add_argument("--all", action="store_true", help="Run ALL extractors")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--output", default="orders.xlsx")
    args = parser.parse_args()

    token = os.getenv("SQUARE_ACCESS_TOKEN") or "EAAAly8mEyanb9A8n_mDWkIXvzMj74XtZOM6gDTChMPpyBSro1CSFTqtw9uNF80D"
    if not token:
        raise RuntimeError("Missing SQUARE_ACCESS_TOKEN environment variable.")

    client = Square(token=token)
    finder = SquareOrderFinder(client)

    # Determine extractor
    extractors = get_extractors(args.item, run_all=args.all)


    # Date handling
    start_dt = (
        datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if args.start else datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
    )
    end_dt = (
        datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if args.end else datetime.now(timezone.utc)
    )

    # Location IDs
    locations = client.locations.list()
    location_ids = [loc.id for loc in locations.locations]

    # Search Orders
    orders = finder.search_orders(start_dt.isoformat(), end_dt.isoformat(), location_ids)

    # Extract structured info
    all_results = []

    for extractor in extractors:
        for order in orders:
            results = extractor.extract(order, client)
            all_results.extend(results)


    if not all_results:
        print("No matching items found.")
        return

    # Output file writing
    save_results(all_results)

    print(f"Done. Extracted {len(all_results)} records.")


if __name__ == "__main__":
    main()
