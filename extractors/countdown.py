from .base import BaseExtractor
from parsers.buyer_parser import extract_buyer_info

def is_holiday_calendar(name: str) -> bool:
    """
    Classify an item as a holiday countdown calendar.
    Must contain 'countdown' and either 'holiday' or 'advent'.
    """
    if not name:
        return False
    name = name.lower()
    return "countdown" in name and ("holiday" in name or "advent" in name)


class HolidayCountdown(BaseExtractor):
    KEYWORD = "holiday countdown"
    def extract(self, order, client):
        results = []

        buyer_name, buyer_email, buyer_phone = extract_buyer_info(order, client)
        line_items = getattr(order, "line_items", [])
        if not line_items:
            return results

        for item in line_items:
            if not item or not item.name:
                continue

            if not is_holiday_calendar(item.name):
                continue

            if not getattr(order, "tenders", None):
                continue  # skip unpaid / abandoned 

            results.append({
                "order_id": order.id,
                # "date_closed": getattr(order, "closed_at", None),
                # "order_source": source_name,
                "order_state": order.state,
                "buyer_name": buyer_name,
                "email": buyer_email,
                "phone": buyer_phone,
                "item_name": item.name,
                "variation": getattr(item, "variation_name", None),
                "qty": float(item.quantity),
                "total": item.total_money.amount / 100.0,
            })

        return results
