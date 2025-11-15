from square.types.search_orders_query import SearchOrdersQuery
from square.types.search_orders_filter import SearchOrdersFilter
from square.types.search_orders_date_time_filter import SearchOrdersDateTimeFilter
from square.types.search_orders_sort import SearchOrdersSort

class SquareOrderFinder:
    def __init__(self, client):
        self.client = client

    def search_orders(self, start_iso, end_iso, location_ids):
        query = SearchOrdersQuery(
            filter=SearchOrdersFilter(
                date_time_filter=SearchOrdersDateTimeFilter(
                    created_at={"start_at": start_iso, "end_at": end_iso}
                )
            ),
            sort=SearchOrdersSort(sort_field="CREATED_AT", sort_order="DESC")
        )

        resp = self.client.orders.search(
            location_ids=location_ids,
            query=query,
            limit=1000,
            return_entries=False
        )

        return getattr(resp, "orders", []) or []
