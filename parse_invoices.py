#!/usr/bin/env python3
"""
Parse a Food Matters Again invoice into structured tabular data.

Usage:
    python parse_invoice.py --file "Invoice_9140577_from_Food_Matters_Again.pdf" --output "parsed_invoice.csv"
"""

import pdfplumber
import pandas as pd
import re
import argparse
import sys


def parse_food_matters_invoice(pdf_path: str) -> pd.DataFrame:
    """
    Parse a Food Matters Again invoice PDF into a structured DataFrame.
    Returns columns: ['description', 'pack', 'qty', 'unit_price', 'total']
    """
    rows = []
    line_pattern = re.compile(
        r"^(?P<desc>.+?)\s+(?P<qty>\d+(?:\.\d+)?)\s+(?P<rate>\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s+(?P<total>\d{1,3}(?:,\d{3})*(?:\.\d+)?)$"
    )

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for raw in text.splitlines():
                line = raw.strip()
                if not line:
                    continue

                # ignore headers/footers and irrelevant lines
                if any(keyword in line.upper() for keyword in [
                    "DESCRIPTION", "RATE", "AMOUNT", "DATE", "INVOICE",
                    "BALANCE DUE", "THANK YOU", "CLAIMS", "PLEASE", "TERMS"
                ]):
                    continue

                # match pattern ending in 3 numeric fields
                m = line_pattern.search(line)
                if not m:
                    continue

                desc = m.group("desc").strip()
                qty = float(m.group("qty"))
                rate = float(m.group("rate").replace(",", ""))
                total = float(m.group("total").replace(",", ""))

                # detect optional pack info
                pack_match = re.search(r"(\d+\/[0-9.\sA-Za-z]+)", desc)
                pack = pack_match.group(1).strip() if pack_match else ""
                desc_clean = desc.replace(pack, "").strip()

                rows.append({
                    "description": desc_clean,
                    "pack": pack,
                    "qty": qty,
                    "unit_price": rate,
                    "total": total
                })

    df = pd.DataFrame(rows)
    return df


def main():
    parser = argparse.ArgumentParser(
        description="Parse Food Matters Again invoice PDF into structured data."
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Path to the invoice PDF file."
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional CSV output path (e.g., parsed_invoice.csv)."
    )

    args = parser.parse_args()

    print(f"📄 Parsing invoice: {args.file}")
    try:
        df = parse_food_matters_invoice(args.file)
        if df.empty:
            print("⚠️ No line items were detected. Check PDF formatting.")
            sys.exit(1)

        print(f"✅ Parsed {len(df)} items from invoice.")
        print(df)

        if args.output:
            df.to_csv(args.output, index=False)
            print(f"💾 Saved parsed data to {args.output}")

    except Exception as e:
        print(f"❌ Error parsing invoice: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
