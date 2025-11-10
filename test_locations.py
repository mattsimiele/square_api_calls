from square import Square
from square.environment import SquareEnvironment

# Initialize the Square client
client = Square(
    token="EAAAly8mEyanb9A8n_mDWkIXvzMj74XtZOM6gDTChMPpyBSro1CSFTqtw9uNF80D",
    environment=SquareEnvironment.PRODUCTION  # or Environment.SANDBOX
)

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
