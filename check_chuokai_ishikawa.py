import requests

URLS = {
    "infoicnet": (
        "https://www.icnet.or.jp/"
        "iensystem/iendbjs.cgi"
        "?mode=jss&cate=infoicnet&opt=nosty"
    ),
    "infoinsti": (
        "https://www.icnet.or.jp/"
        "iensystem/iendbjs.cgi"
        "?mode=jss&cate=infoinsti&opt=nosty"
    ),
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.icnet.or.jp/",
}

for name, url in URLS.items():
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=60,
    )

    response.raise_for_status()
    response.encoding = response.apparent_encoding

    print(f"\n===== {name} =====")
    print("status:", response.status_code)
    print("content-type:", response.headers.get("content-type"))
    print("length:", len(response.text))

    print("\n--- first 120 lines ---")

    lines = response.text.splitlines()

    for line in lines[:120]:
        print(line)

    filename = f"ishikawa-{name}.js"

    with open(
        filename,
        "w",
        encoding="utf-8",
    ) as f:
        f.write(response.text)

    print("\nsaved:", filename)
