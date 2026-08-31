import requests

URLS = [
    "https://www.icnet.or.jp/infoicnet.html",
    "https://www.icnet.or.jp/infoinsti.html",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
}

for index, url in enumerate(URLS, start=1):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=60,
    )

    response.raise_for_status()
    response.encoding = response.apparent_encoding

    print(f"\n===== PAGE {index} =====")
    print("url:", url)
    print("status:", response.status_code)
    print("length:", len(response.text))

    filename = f"ishikawa-debug-{index}.html"

    with open(
        filename,
        "w",
        encoding="utf-8",
    ) as f:
        f.write(response.text)

    print("saved:", filename)
