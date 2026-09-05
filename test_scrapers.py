import os
from scrapers import search_all_stores

API_KEY = os.getenv("GEMINI_API_KEY", "")

print("Searching for noise canceling headphones under Rs.5000...")
print()

result = search_all_stores(
    query="noise canceling headphones",
    max_budget_inr=5000,
    limit_per_store=5,
    api_key=API_KEY,
)

total = result["total_found"]
stores = result["stores_responded"]
print(f"Total found: {total}")
print(f"Stores responded: {stores}")
print()

for i, p in enumerate(result["products"][:15], 1):
    store = p["store"]
    price = p["price_inr"]
    name = p["name"][:60]
    rating = p.get("rating", "N/A")
    reviews = p.get("reviews", "N/A")
    print(f"  #{i:2d} {store:10} | Rs.{price:>6,} | Rating: {rating} | Reviews: {reviews}")
    print(f"       {name}")
    url = p.get("url", "")
    if url:
        print(f"       {url[:80]}")
    print()
