def extract_buyer_info(order, client):
    buyer_name = None
    buyer_email = None
    buyer_phone = None

    # Try fulfillments first
    if getattr(order, "fulfillments", None):
        for f in order.fulfillments:
            details = getattr(f, "pickup_details", None)
            if details and getattr(details, "recipient", None):
                rec = details.recipient
                buyer_name = getattr(rec, "display_name", None)
                buyer_email = getattr(rec, "email_address", None)
                buyer_phone = getattr(rec, "phone_number", None)
                break

    # Fallback to customer object
    if not buyer_name and getattr(order, "customer_id", None):
        try:
            resp = client.customers.retrieve_customer(order.customer_id)
            cust = getattr(resp, "customer", None)
            if cust:
                given = getattr(cust, "given_name", "") or ""
                family = getattr(cust, "family_name", "") or ""
                company = getattr(cust, "company_name", "") or ""
                buyer_name = " ".join([given, family]).strip() or company
                buyer_email = getattr(cust, "email_address", buyer_email)
                buyer_phone = getattr(cust, "phone_number", buyer_phone)
        except:
            pass

    return buyer_name, buyer_email, buyer_phone
