import hashlib
import re
import requests
from urllib.parse import urljoin
from xml.etree.ElementTree import Element, SubElement, ElementTree

BASE_URL = "https://www.iri-tokyo.jp/"
LIST_URL = "https://www.iri-tokyo.jp/seminar-event/"
OUTPUT_FILE = "iri-tokyo-seminar.xml"
MAX_ITEMS = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
}


def get_api_config():
    response = requests.get(
        LIST_URL,
        headers=HEADERS,
        timeout=60,
    )
    response.raise_for_status()

    text = response.text

    domain_match = re.search(
        r'kurocoApiDomain:"([^"]+)"',
        text,
    )

    token_match = re.search(
        r'apiAccessToken:"([^"]+)"',
        text,
    )

    if not domain_match:
        raise RuntimeError(
            "Kuroco APIドメインを取得できませんでした"
        )

    if not token_match:
        raise RuntimeError(
            "Kuroco APIアクセストークンを取得できませんでした"
        )

    return (
        domain_match.group(1),
        token_match.group(1),
    )


def get_items():
    api_domain, api_token = get_api_config()

    api_url = (
        api_domain
        + "/rcms-api/36/seminar_event_list_open"
    )

    headers = {
        **HEADERS,
        "Accept": "application/json",
        "x-rcms-api-access-token": api_token,
        "Referer": LIST_URL,
    }

    response = requests.get(
        api_url,
        headers=headers,
        params={"cnt": 0},
        timeout=60,
    )

    response.raise_for_status()

    data = response.json()
    items = data.get("list", [])

    if not items:
        raise RuntimeError(
            "受付中のセミナー・講習会を1件も取得できませんでした"
        )

    return items


source_items = get_items()

items = []
seen = set()

for entry in source_items:
    title = str(
        entry.get("subject") or ""
    ).strip()

    topics_id = str(
        entry.get("topics_id") or ""
    ).strip()

    slug = str(
        entry.get("slug") or ""
    ).strip()

    if not title:
        continue

    if slug:
        url = urljoin(
            BASE_URL,
            f"seminar-event/{slug}/",
        )
    elif topics_id:
        url = urljoin(
            BASE_URL,
            f"seminar-event/{topics_id}/",
        )
    else:
        continue

    key = (
        title,
        url,
    )

    if key in seen:
        continue

    seen.add(key)

    items.append({
        "title": title,
        "url": url,
        "topics_id": topics_id,
    })

    if len(items) >= MAX_ITEMS:
        break


if not items:
    raise RuntimeError(
        "RSS対象を1件も生成できませんでした"
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
    "東京都立産業技術研究センター "
    "募集中の技術セミナー・講習会"
)

SubElement(
    channel,
    "link",
).text = LIST_URL

SubElement(
    channel,
    "description",
).text = (
    "東京都立産業技術研究センターの"
    "申込受付中の技術セミナー・講習会"
)

for entry in items:
    item = SubElement(
        channel,
        "item",
    )

    SubElement(
        item,
        "title",
    ).text = entry["title"]

    SubElement(
        item,
        "link",
    ).text = entry["url"]

    unique_id = hashlib.sha256(
        (
            entry["topics_id"]
            + "|"
            + entry["title"]
            + "|"
            + entry["url"]
        ).encode("utf-8")
    ).hexdigest()

    SubElement(
        item,
        "guid",
    ).text = (
        f"urn:iri-tokyo-seminar:{unique_id}"
    )


ElementTree(rss).write(
    OUTPUT_FILE,
    encoding="utf-8",
    xml_declaration=True,
)

print(
    OUTPUT_FILE,
    len(items),
)
