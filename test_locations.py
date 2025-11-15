from square import Square
from square.environment import SquareEnvironment

# Initialize the Square client
client = Square(
    token="EAAAly8mEyanb9A8n_mDWkIXvzMj74XtZOM6gDTChMPpyBSro1CSFTqtw9uNF80D",
    environment=SquareEnvironment.PRODUCTION  # or Environment.SANDBOX
)

def find_team_member_id(client, name_query):
    """
    Searches active team members and returns the ID for the name that matches or partially matches.
    """
    resp = client.team_members.search(query={"filter": {"status": "ACTIVE"}})
    matches = []

    for tm in getattr(resp, "team_members", []) or []:
        full_name = f"{tm.given_name or ''} {tm.family_name or ''}".strip()
        if name_query.lower() in full_name.lower():
            matches.append((tm.id, full_name))

    if not matches:
        print(f"⚠️ No matches found for '{name_query}'.")
        return None

    print("✅ Found matches:")
    for tid, name in matches:
        print(f"  - {name} → {tid}")

    if len(matches) > 1:
        print("⚠️ Multiple matches found; pick the correct ID above.")
    return matches[0][0]

find_team_member_id(client, "Steve")

# Fetch locations
result = client.locations.list()

# Handle result (Pydantic model)
if result.locations:
    print("✅ Locations:")
    for loc in result.locations:
        print(f"Name: {loc.name}")
        print(f"ID: {loc.id}")
        if loc.address:
            city = loc.address.locality or ""
            state = loc.address.administrative_district_level1 or ""
            print(f"Address: {city}, {state}")
        print("------")
elif result.errors:
    print("❌ Errors occurred:")
    for err in result.errors:
        print(f"{err.category}: {err.detail}")
else:
    print("⚠️ No locations found.")
