import json
import pandas as pd
from datetime import datetime

def save_results(results):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = f"orders_{timestamp}.json"
    xlsx_path = f"orders_{timestamp}.xlsx"

    # Save JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Save Excel
    df = pd.DataFrame(results)
    df.to_excel(xlsx_path, index=False)

    print(f"Saved {len(results)} results:")
    print(f" - JSON:  {json_path}")
    print(f" - Excel: {xlsx_path}")
