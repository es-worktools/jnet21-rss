import requests

URLS = {
    "main": "https://www.chuokai-nara.or.jp/chuokai/js/main.js",
    "scroll": "https://www.chuokai-nara.or.jp/chuokai/js/scroll.js",
    "libs": "https://www.chuokai-nara.or.jp/chuokai/js/libs.js",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.chuokai-nara.or.jp/chuokai/",
}

for name, url in URLS.items():
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=60,
    )

    response.raise_for_status()
    response.encoding = response.apparent_encoding

    filename = f"chuokai-nara-{name}.js"

    with open(
        filename,
        "w",
        encoding="utf-8",
    ) as f:
        f.write(response.text)

    print(f"\n===== {name} =====")
    print("status:", response.status_code)
    print("length:", len(response.text))
    print("saved:", filename)
