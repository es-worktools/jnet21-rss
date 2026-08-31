import json
import requests

URL = "https://www.jsps.go.jp/include/news/inform_ja.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
}

response = requests.get(
    URL,
    headers=HEADERS,
    timeout=60,
)

response.raise_for_status()
data = response.json()

print("status:", response.status_code)
print("count:", len(data))

for news_type in ["1", "2", "3"]:
    items = [
        item for item in data
        if item.get("news_type") == news_type
    ]

    print(f"\n=== news_type {news_type} ===")
    print("count:", len(items))

    for item in items[:10]:
        print(
            item.get("news_date"),
            "|",
            item.get("title"),
        )
