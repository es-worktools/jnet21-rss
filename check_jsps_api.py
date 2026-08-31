import re
import requests

URL = "https://www.jsps.go.jp/assets/a/main.js?ver=20260422"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
}

response = requests.get(
    URL,
    headers=HEADERS,
    timeout=60,
)

response.raise_for_status()
response.encoding = response.apparent_encoding

text = response.text

print("status:", response.status_code)
print("length:", len(text))

patterns = [
    r"https?://[^\"'\s]+",
    r"fetch\([^)]*\)",
    r"\$\.ajax\([^)]*\)",
    r"\$\.get\([^)]*\)",
    r"\$\.post\([^)]*\)",
    r"XMLHttpRequest",
    r"newsList",
    r"data-id",
    r"10300",
    r"api",
    r"json",
]

for pattern in patterns:
    print("\n---", pattern, "---")

    matches = re.findall(
        pattern,
        text,
        flags=re.IGNORECASE,
    )

    for match in matches[:50]:
        print(match)

with open(
    "jsps-main-debug.js",
    "w",
    encoding="utf-8",
) as f:
    f.write(text)

print("\njsps-main-debug.js を保存しました")
