import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from zoneinfo import ZoneInfo
from xml.etree.ElementTree import Element, SubElement, ElementTree

BASE_URL = "https://www.sansokan.jp/events/"
OUTPUT_FILE = "sansokan-event.xml"

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


def detect_status(row_text):
    if "○" in row_text:
        return "受付中"

    if "△" in row_text:
        return "残席僅"

    if "×" in row_text:
        return "受付終了"

    return "不明"


now = datetime.now(ZoneInfo("Asia/Tokyo"))

events = {}

# 当月から6か月先まで確認
for offset in range(6):
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

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

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

        href = (
            link.get("href")
            or ""
        ).strip()

        match = re.search(
            r"/service/(\d+)/detail",
            href,
        )

        if not match or not title:
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

        status = detect_status(
            row_text
        )

        # 受付中・残席僅だけRSS対象
        if status not in (
            "受付中",
            "残席僅",
        ):
            continue

        # 同じイベントが複数月に出てもevent_noで1件化
        events[event_no] = {
            "event_no": event_no,
            "title": title,
            "url": href,
            "status": status,
            "row_text": row_text,
        }


if not events:
    raise RuntimeError(
        "受付中のイベントを1件も取得できませんでした"
    )


rss = Element(
    "rss",
    version="2.0",
)

channel = SubElement(
    rss,
    "channel",
)

SubElement(
    channel,
    "title",
).text = (
    "大阪産業創造館（サンソウカン） "
    "イベント・セミナー"
)

SubElement(
    channel,
    "link",
).text = BASE_URL

SubElement(
    channel,
    "description",
).text = (
    "大阪産業創造館（サンソウカン）の"
    "受付中・残席僅のイベント、セミナー、募集情報"
)

for event in events.values():
    item = SubElement(
        channel,
        "item",
    )

    SubElement(
        item,
        "title",
    ).text = event["title"]

    SubElement(
        item,
        "link",
    ).text = event["url"]

    guid = SubElement(
        item,
        "guid",
    )

    guid.set(
        "isPermaLink",
        "false",
    )

    guid.text = (
        "sansokan-event-"
        + event["event_no"]
    )

    SubElement(
        item,
        "description",
    ).text = event["row_text"]


ElementTree(rss).write(
    OUTPUT_FILE,
    encoding="utf-8",
    xml_declaration=True,
)

print(
    OUTPUT_FILE,
    len(events),
)
