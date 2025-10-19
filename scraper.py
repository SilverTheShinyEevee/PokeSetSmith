import requests
from bs4 import BeautifulSoup
import json
import re

URL = "https://www.serebii.net/games/ribbons.shtml"

CATEGORIES = {
    "Champion Ribbons": ["Champion", "Hall of Fame", "League"],
    "Battle & Achievement Ribbons": ["Battle", "Victory", "Tournament", "Arena", "Mastery", "Elite"],
    "Contest & Event Ribbons": ["Contest", "Artist", "Festival", "World", "Premier", "Performance", "Stage"],
    "Friendship & Common Ribbons": ["Effort", "Classic", "Best Friends", "Partner", "Friend", "Commemorative"],
    "Marks (Weather / Size)": ["Mark", "Cloudy", "Rainy", "Stormy", "Snowy", "Sunny", "Jumbo", "Teeny", "Huge", "Tiny"],
    "Special / Distribution Ribbons": ["Distribution", "Anniversary", "Promo", "Developer", "Special"]
}

def categorize_ribbon(name: str) -> str:
    for category, keywords in CATEGORIES.items():
        for kw in keywords:
            if kw.lower() in name.lower():
                return category
    return "Uncategorized Ribbons"

def scrape_ribbons():
    response = requests.get(URL)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    ribbons = set()
    for td in soup.find_all("td"):
        text = td.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()

        # Ignore descriptions (too long or sentences)
        if len(text.split()) > 8:
            continue
        if "." in text or "," in text:
            continue

        # Match name format (must end in Ribbon or Mark)
        if re.search(r"(Ribbon|Mark)$", text, re.IGNORECASE):
            # Normalize capitalization and spacing
            cleaned = text.strip()
            ribbons.add(cleaned)

    categorized = {}
    for ribbon in sorted(ribbons, key=lambda x: x.lower()):
        cat = categorize_ribbon(ribbon)
        categorized.setdefault(cat, []).append(ribbon)

    for cat in categorized:
        categorized[cat].sort(key=lambda x: x.lower())

    with open("ribbons.json", "w", encoding="utf-8") as f:
        json.dump(categorized, f, indent=2, ensure_ascii=False)

    total = sum(len(v) for v in categorized.values())
    print(f"? Extracted {total} ribbons/marks across {len(categorized)} categories")
    print("?? Saved to ribbons.json")

if __name__ == "__main__":
    scrape_ribbons()