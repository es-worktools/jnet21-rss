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
print("type:", type(data).__name__)

if isinstance(data, list):
    print("count:", len(data))

    for i, item in enumerate(data[:5], start=1):
        print(f"\n--- item {i} ---")
        print(json.dumps(
            item,
            ensure_ascii=False,
            indent=2,
        ))

elif isinstance(data, dict):
    print("top-level keys:", list(data.keys()))

    for key, value in data.items():
        print(f"\n--- key: {key} ---")
        print("type:", type(value).__name__)

        if isinstance(value, list):
            print("count:", len(value))

            for i, item in enumerate(value[:5], start=1):
                print(f"\nitem {i}")
                print(json.dumps(
                    item,
                    ensure_ascii=False,
                    indent=2,
                ))

            break
