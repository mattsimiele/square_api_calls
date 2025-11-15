from .base import BaseExtractor
from parsers.item_parser import ItemParser
from parsers.buyer_parser import extract_buyer_info

class ThanksgivingBoardExtractor(BaseExtractor):
    KEYWORD = "thanksgiving cheese board"

    def extract(self, order, client):
        results = []

        buyer_name, buyer_email, buyer_phone = extract_buyer_info(order, client)
        if getattr(order, "line_items", []) is None:
            return results

        for item in getattr(order, "line_items", []):
            # match Thanksgiving board exactly or startswith
            if item.name is None:
                continue
            if self.KEYWORD in item.name.lower():
                parser = ItemParser(item)

                results.append({
                    "order_id": order.id,
                    "order_state": order.state,
                    "buyer_name": buyer_name,
                    "email": buyer_email,
                    "phone": buyer_phone,
                    "item_name": item.name,
                    "variation": getattr(item, "variation_name", None),
                    "qty": float(item.quantity),
                    "total": item.total_money.amount / 100.0,
                    **parser.as_dict(),
                })

        return results
