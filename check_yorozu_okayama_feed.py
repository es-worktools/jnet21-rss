import requests
import xml.etree.ElementTree as ET

URLS = [
    "https://yorozu-okayama.go.jp/feed/",
    "https://yorozu-okayama.go.jp/category/news/feed/",
    "https://yorozu-okayama.go.jp/seminar-all/feed/",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    )
}

for url in URLS:
    print()
    print("=" * 70)
    print("URL:", url)

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=60,
            allow_redirects=True,
        )

        print("status:", response.status_code)
        print("final :", response.url)
        print(
            "content-type:",
            response.headers.get("content-type"),
        )
        print("length:", len(response.content))

        print(
            "history:",
            [
                (r.status_code, r.url)
                for r in response.history
            ],
        )

        if response.status_code != 200:
            continue

        try:
            root = ET.fromstring(
                response.content
            )
        except Exception as e:
            print("XML ERROR:", repr(e))
            print(
                response.text[:500]
            )
            continue

        items = root.findall(".//item")

        print("items:", len(items))

        for i, item in enumerate(
            items[:10],
            1,
        ):
            title = (
                item.findtext("title", "")
                or ""
            ).strip()

            link = (
                item.findtext("link", "")
                or ""
            ).strip()

            print(
                f"{i:02d}: {title}"
            )
            print(
                "    ",
                link,
            )

    except Exception as e:
        print(
            "ERROR:",
            repr(e),
        )
