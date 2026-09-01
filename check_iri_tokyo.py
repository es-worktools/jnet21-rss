import html
import re
import requests
from urllib.parse import urljoin

PAGE_URL = "https://www.iri-tokyo.jp/seminar-event/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
}

KEYWORDS = [
    "seminar-event",
    "seminar",
    "kuroco",
    "rcms-api",
    "entryStartDate",
    "entryEndDate",
    "openStartDate",
    "openEndDate",
]

response = requests.get(
    PAGE_URL,
    headers=HEADERS,
    timeout=60,
)
response.raise_for_status()

page_html = html.unescape(response.text)

# HTMLから読み込まれているNuxt JSをすべて取得
paths = re.findall(
    r'(?:src|href)=["\']([^"\']+\.js(?:\?[^"\']*)?)',
    page_html,
)

js_urls = sorted({
    urljoin(PAGE_URL, path)
    for path in paths
})

print("page status:", response.status_code)
print("JavaScript files:", len(js_urls))

for js_url in js_urls:
    try:
        js_response = requests.get(
            js_url,
            headers=HEADERS,
            timeout=60,
        )
        js_response.raise_for_status()
    except Exception as e:
        print("\nFAILED:", js_url)
        print(e)
        continue

    text = js_response.content.decode(
        "utf-8",
        errors="replace",
    )

    lower_text = text.lower()

    matched_keywords = [
        keyword
        for keyword in KEYWORDS
        if keyword.lower() in lower_text
    ]

    # /rcms-api/... のようなAPIパスも探す
    api_paths = sorted(set(
        re.findall(
            r'/?rcms-api/[A-Za-z0-9_./?=&%-]+',
            text,
        )
    ))

    if not matched_keywords and not api_paths:
        continue

    print("\n========================================")
    print("CANDIDATE:", js_url)
    print("length:", len(text))
    print("keywords:", ", ".join(matched_keywords))

    if api_paths:
        print("\n--- API PATHS ---")
        for path in api_paths[:30]:
            print(path)

    print("\n--- CONTEXT ---")

    shown = 0

    for keyword in matched_keywords:
        start = 0

        while shown < 20:
            pos = lower_text.find(
                keyword.lower(),
                start,
            )

            if pos == -1:
                break

            left = max(0, pos - 350)
            right = min(
                len(text),
                pos + len(keyword) + 500,
            )

            context = text[left:right]

            print(
                f"\n[{keyword}]"
            )
            print(context)

            shown += 1
            start = pos + len(keyword)

            if shown >= 20:
                break
