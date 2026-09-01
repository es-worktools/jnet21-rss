import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from zoneinfo import ZoneInfo

BASE_URL = "https://www.sansokan.jp/events/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
}


def add_months(year, month, offset):
    month += offset

    while month > 12:
        month -= 12
        year += 1

    return year, month


now = datetime.now(ZoneInfo("Asia/Tokyo"))

all_items = []

for offset in range(3):
    year, month = add_months(
        now.year,
        now.month,
        offset,
    )

    ym = f"{year:04d}-{month:02d}"

    response = requests.get(
        BASE_URL,
        headers=HEADERS,
        params={"ym": ym},
        timeout=60,
    )
    response.raise_for_status()

    print()
    print("=" * 70)
    print("MONTH:", ym)
    print("status:", response.status_code)
    print("length:", len(response.text))

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    count = 0

    for link in soup.find_all(
        "a",
        href=re.compile(
            r"ebis\.obda\.or\.jp/service/\d+/detail"
        ),
    ):
        title = link.get_text(
            " ",
            strip=True,
        )

        if not title:
            continue

        href = link.get("href", "").strip()

        match = re.search(
            r"/service/(\d+)/detail",
            href,
        )

        if not match:
            continue

        event_no = match.group(1)

        row = link.find_parent("tr")

        if row:
            row_text = row.get_text(
                " ",
                strip=True,
            )
        else:
            row_text = title

        if "○" in row_text:
            status = "受付中"
        elif "△" in row_text:
            status = "残席僅"
        elif "×" in row_text:
            status = "受付終了"
        else:
            status = "不明"

        print()
        print("event_no:", event_no)
        print("status  :", status)
        print("title   :", title)
        print("url     :", href)
        print("row     :", row_text)

        all_items.append(
            (
                event_no,
                status,
                title,
                href,
            )
        )

        count += 1

    print()
    print("MONTH ITEMS:", count)


print()
print("=" * 70)
print("TOTAL:", len(all_items))

open_items = [
    item
    for item in all_items
    if item[1] in (
        "受付中",
        "残席僅",
    )
]

print(
    "OPEN / FEW LEFT:",
    len(open_items),
)

unique = {}

for item in open_items:
    unique[item[0]] = item

print(
    "UNIQUE OPEN / FEW LEFT:",
    len(unique),
)

print()
print("--- RSS CANDIDATES ---")

for event_no, status, title, href in unique.values():
    print(
        event_no,
        status,
        title,
        href,
        sep=" | ",
    )
