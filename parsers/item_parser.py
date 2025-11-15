import re

DATE_PATTERNS = [
    r'\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b',                    # 11/26 or 11/26/2025
    r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}\b',  # Nov 26
    r'\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+\w+\s+\d{1,2}\b',  # Friday Nov 8
]

TIME_PATTERNS = [
    r'\b\d{1,2}(:\d{2})?\s*(am|pm)\b',          # 2pm, 2:00 pm
    r'\b\d{1,2}\s*(am|pm)\b',                   # 3 pm
    r'\b(?:noon|midnight)\b',                   # noon, midnight
    r'\b\d{1,2}:\d{2}\b',                       # 14:00
]

class ItemParser:
    def __init__(self, item):
        self.item = item
        self.pickup_date = None
        self.pickup_time = None
        self.allergies = None
        self.extra_modifiers = []
        self.parse_modifiers()

    def parse_modifiers(self):
        if getattr(self.item, "modifiers", []) is None:
            return
        for mod in getattr(self.item, "modifiers", []):
            text = mod.name.strip().lower()

            # Find date first
            for pattern in DATE_PATTERNS:
                m = re.search(pattern, text, flags=re.IGNORECASE)
                if m:
                    self.pickup_date = m.group(0)
                    break

            # Find time
            for pattern in TIME_PATTERNS:
                m = re.search(pattern, text, flags=re.IGNORECASE)
                if m:
                    t = m.group(0)
                    if t == "noon":
                        t = "12:00 pm"
                    elif t == "midnight":
                        t = "12:00 am"
                    self.pickup_time = t
                    break

            if "allerg" in text:
                self.allergies = text.split(":", 1)[-1].strip()
                continue    

            # If neither date nor time was captured, keep as extra
            if (self.pickup_date is None) and (self.pickup_time is None) and (self.allergies is None):
                self.extra_modifiers.append(mod.name)

    def as_dict(self):
        return {
            "pickup_date": self.pickup_date,
            "pickup_time": self.pickup_time,
            "allergies": self.allergies,
            "extra_modifiers": self.extra_modifiers,
        }
