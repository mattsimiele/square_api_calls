from dateutil import parser as date_parser
from dateutil import tz

LOCAL_TZ = tz.gettz("America/New_York")


def fetch_payments(client, location_id, start_iso, end_iso):
    """
    Fetch all payments for the given date window.
    """
    try:
        pager = client.payments.list(
            begin_time=start_iso,
            end_time=end_iso,
            location_id=location_id,
            limit=100
        )
        return list(pager)
    except Exception as e:
        print("⚠️ Error fetching payments:", e)
        return []


def fetch_order_service_charges(client, order_id):
    """
    Fetch auto-gratuity from the Order object.
    """
    try:
        if hasattr(client.orders, "get"):
            resp = client.orders.get(order_id=order_id)
        else:
            resp = client.orders.retrieve_order(order_id=order_id)

        order = getattr(resp, "order", None)
        if not order or not getattr(order, "service_charges", None):
            return 0

        total = 0
        for sc in order.service_charges:
            if getattr(sc, "type", "") == "AUTO_GRATUITY":
                total += getattr(getattr(sc, "applied_money", None), "amount", 0)

        return total

    except Exception as e:
        print(f"⚠️ Could not fetch service charges for order {order_id}: {e}")
        return 0
