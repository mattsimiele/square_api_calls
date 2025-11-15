#!/usr/bin/env python3
import os
import argparse
import pandas as pd
from datetime import datetime, timezone
from square import Square
import json
import re
from square.types.search_orders_query import SearchOrdersQuery
from square.types.search_orders_filter import SearchOrdersFilter
from square.types.search_orders_date_time_filter import SearchOrdersDateTimeFilter
from square.types.search_orders_sort import SearchOrdersSort
# from square.types.sort_order import SortOrder

def extract_cheese_board_info(order, client):
    """
    Extracts key info (pickup date, size, allergy info, and buyer name)
    from a Thanksgiving Cheese Board order.
    """
    time_pattern = re.compile(
        r'^\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*$',
        re.IGNORECASE
    )
    results = []

    buyer_name = None
    #print(dir(order))
    #print(order.fulfillments)
    #print(order.customer_id)
    #print("----")
    buyer_name = None
    buyer_email = None
    buyer_phone = None
    if getattr(order, "fulfillments", None):
        for f in order.fulfillments:
            # print(dir(f))
            if getattr(f, "pickup_details", None):
                rec = getattr(f.pickup_details, "recipient", None)
                # print(dir(rec))
                if rec:
                    buyer_name = getattr(rec, "display_name", None) or (
                        f"{getattr(rec, 'first_name', '')} {getattr(rec, 'last_name', '')}".strip()
                    )
                    buyer_email = getattr(rec, "email_address", None)
                    buyer_phone = getattr(rec, "phone_number", None)
                    break  # we only need the first recipient
    # print(f"Buyer name from fulfillment: {buyer_name}, email: {buyer_email}, phone: {buyer_phone}")
    # --- If no fulfillment info, try customer_id lookup ---
    if buyer_name in (None, "Unknown") and getattr(order, "customer_id", None):
        try:
            cust_resp = client.customers.retrieve_customer(order.customer_id)
            cust = getattr(cust_resp, "customer", None)
            if cust:
                given = getattr(cust, "given_name", "") or ""
                family = getattr(cust, "family_name", "") or ""
                company = getattr(cust, "company_name", "") or ""
                buyer_name = " ".join([n for n in [given, family] if n]).strip() or company or "Unknown"
                buyer_email = getattr(cust, "email_address", buyer_email)
                buyer_phone = getattr(cust, "phone_number", buyer_phone)
        except Exception as e:
            print(f"⚠️ Could not retrieve customer info for {order.customer_id}: {e}")

    for item in getattr(order, "line_items", []):
        if "cheese board" not in item.name.lower():
            continue

        pickup_date = None
        allergy_info = None
        size = getattr(item, "variation_name", None)

        for mod in getattr(item, "modifiers", []):
            # print(mod.name)
            n = mod.name.lower()
            if re.search(r"\d{1,2}/\d{1,2}", n):
                pickup_date = mod.name
            elif time_pattern.match(n.strip()):
                pickup_time = mod.name
            elif "allerg" in n:
                allergy_info = mod.name.split(":", 1)[-1].strip()

        results.append({
            "order_id": order.id,
            "order_state": order.state,
            "buyer_name": buyer_name,
            "email": buyer_email,
            "phone": buyer_phone,
            "item_name": item.name,
            "size": size,
            "qty": float(item.quantity),
            "pickup_time": pickup_time,
            "pickup_date": pickup_date,
            "allergies": allergy_info,
            "total": item.total_money.amount / 100.0,
        })

    return results


def find_item_sales(client, item_name, start_iso, end_iso, location_ids):
    """
    Search orders in Square and return any line items that match a partial item name.
    """
    matches = []

    query = SearchOrdersQuery(
        filter=SearchOrdersFilter(
            # state_filter={"states": ["COMPLETED"]},
            date_time_filter=SearchOrdersDateTimeFilter(
                created_at={"start_at": start_iso, "end_at": end_iso}
            )
        ),
        sort=SearchOrdersSort(sort_field="CREATED_AT", sort_order="DESC")
    )

    resp = client.orders.search(
        location_ids=location_ids,
        query=query,
        limit=1000,
        return_entries=False
    )

    if hasattr(resp, "errors") and resp.errors:
        print("⚠️ Error:", resp.errors)
        return matches
    matches2 = []
    orders = getattr(resp, "orders", []) or []
    for order in orders:
        order_id = order.id
        location_id = order.location_id
        created_at = order.created_at

        for item in getattr(order, "line_items", []) or []:
            if item is not None and hasattr(item, "name") and item.name:
                if item_name.lower() in item.name.lower():
                    # print(f"🔍 Match found: Order {order_id}, Item: {item}")
                    matches.append({
                        "order_id": order_id,
                        "created_at": created_at,
                        "item_name": item.name,
                        "quantity": float(item.quantity),
                        "unit_price": int(item.base_price_money.amount) / 100 if item.base_price_money else None,
                        "total": int(item.total_money.amount) / 100 if item.total_money else None,
                        "location_id": location_id
                    })
                    board_info = extract_cheese_board_info(order, client)
                    if board_info:
                        matches2.extend(board_info)
    return matches2


def main():
    parser = argparse.ArgumentParser(
        description="Find all Square transactions containing a specific item."
    )
    parser.add_argument("--item", required=True, help="Partial name of the item to search for")
    parser.add_argument("--start", help="Start date (YYYY-MM-DD)", required=False)
    parser.add_argument("--end", help="End date (YYYY-MM-DD)", required=False)
    parser.add_argument("--output", help="CSV output filename", default="item_sales.csv")
    args = parser.parse_args()

    token = os.getenv("SQUARE_ACCESS_TOKEN") or "EAAAly8mEyanb9A8n_mDWkIXvzMj74XtZOM6gDTChMPpyBSro1CSFTqtw9uNF80D"
    if not token:
        raise RuntimeError("Missing SQUARE_ACCESS_TOKEN environment variable.")

    client = Square(token=token)
    locations = client.locations.list()

    location_ids = [loc.id for loc in locations.locations] 
    print(f"📍 Found {len(location_ids)} locations: {', '.join(location_ids)}")

    # Handle date range
    start_dt = (
        datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if args.start else datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
    )
    end_dt = (
        datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if args.end else datetime.now(timezone.utc)
    )

    matches = find_item_sales(client, args.item, start_dt.isoformat(), end_dt.isoformat(), location_ids)
    if not matches:
        print("❌ No matching transactions found.")
        return
    
    # Save JSON
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = f"thanksgiving_orders_{timestamp}.json"
    xlsx_path = f"thanksgiving_orders_{timestamp}.xlsx"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(matches, f, indent=2, ensure_ascii=False)

    # Convert to DataFrame and export to Excel
    df = pd.DataFrame(matches)
    df.to_excel(xlsx_path, index=False)

    print(f"\n💾 Saved {len(matches)} cheese board orders:")
    print(f" - JSON:  {json_path}")
    print(f" - Excel: {xlsx_path}")


if __name__ == "__main__":
    main()
