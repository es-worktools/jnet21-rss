import json
import requests

URL = (
    "https://www.chuokai-nara.or.jp/"
    "chuokai/contents/kumiai/search_kumiai_news"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.chuokai-nara.or.jp/chuokai/",
}

response = requests.post(
    URL,
    headers=HEADERS,
    data={"data": "news"},
    timeout=60,
)

response.raise_for_status()

print("status:", response.status_code)
print("content-type:", response.headers.get("content-type"))
print("length:", len(response.text))

data = response.json()

print("type:", type(data).__name__)
print("count:", len(data))

print("\n--- first 20 records ---")

for item in data[:20]:
    print(
        json.dumps(
            item,
            ensure_ascii=False,
            indent=2,
        )
    )
