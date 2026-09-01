import requests
import xml.etree.ElementTree as ET

URL = "https://www.maff.go.jp/rss.xml"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    )
}

response = requests.get(
    URL,
    headers=HEADERS,
    timeout=60,
)

response.raise_for_status()

print("status:", response.status_code)
print("content-type:", response.headers.get("content-type"))
print("length:", len(response.content))

root = ET.fromstring(response.content)

items = root.findall(".//item")

print("items:", len(items))
print()

for i, item in enumerate(items[:50], 1):
    title = item.findtext("title", "").strip()
    link = item.findtext("link", "").strip()
    category = item.findtext("category", "").strip()

    is_kanbo = "/j/press/kanbo/" in link

    print(
        f"{i:02d}",
        "KANBO" if is_kanbo else "-----",
        f"category={category!r}",
    )
    print(" title:", title)
    print(" link :", link)
    print()
