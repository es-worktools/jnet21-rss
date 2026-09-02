import re
from collections import Counter
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


FACILITY_LIST_URL = (
    "https://www.jeed.go.jp/location/poly/index.html"
)

JST = timezone(timedelta(hours=9))
CURRENT_YEAR = datetime.now(JST).year

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
}

TIMEOUT = 25

DISCOVERY_WORDS = (
    "開催月別",
    "コース一覧",
    "能力開発セミナー",
    "在職者",
    "セミナー",
)

STATUS_HINTS = (
    "受付",
    "残り",
    "残席",
    "キャンセル",
    "中止",
    "電話",
    "終了",
    "満席",
    "空き",
    "申込",
    "募集",
    "相談",
)

session = requests.Session()
session.headers.update(HEADERS)


def normalize(text):
    return re.sub(
        r"\s+",
        " ",
        text or "",
    ).strip()


def get_soup(url):
    response = session.get(
        url,
        timeout=TIMEOUT,
        allow_redirects=True,
    )

    response.raise_for_status()

    return (
        response.url,
        BeautifulSoup(
            response.content,
            "html.parser",
        ),
    )


def short_facility_name(text):
    text = normalize(text)

    match = re.search(
        r"（(ポリテクセンター[^）]+)）",
        text,
    )

    if match:
        return match.group(1)

    match = re.search(
        r"(ポリテクセンター[^\s（]+)",
        text,
    )

    if match:
        return match.group(1)

    return text


def get_facilities():
    _, soup = get_soup(
        FACILITY_LIST_URL
    )

    facilities = []
    seen = set()

    for link in soup.find_all(
        "a",
        href=True,
    ):
        text = normalize(
            link.get_text(
                " ",
                strip=True,
            )
        )

        if "ポリテクセンター" not in text:
            continue

        # 高度ポリテクセンターは
        # 0146のお知らせで別途対応済み
        if "高度ポリテクセンター" in text:
            continue

        url = urljoin(
            FACILITY_LIST_URL,
            link["href"],
        )

        parsed = urlparse(url)

        if (
            parsed.hostname
            != "www3.jeed.go.jp"
        ):
            continue

        if url in seen:
            continue

        seen.add(url)

        facilities.append(
            {
                "name": short_facility_name(
                    text
                ),
                "full_name": text,
                "url": url,
            }
        )

    return facilities


def same_host(url1, url2):
    return (
        urlparse(url1).hostname
        == urlparse(url2).hostname
    )


def discovery_link_score(
    text,
    href,
):
    text = normalize(text)
    href_lower = href.lower()

    score = 0

    if "開催月別" in text:
        score += 100

    if "コース一覧" in text:
        score += 80

    if "能力開発セミナー" in text:
        score += 60

    if "在職者" in text:
        score += 40

    if "セミナー" in text:
        score += 20

    if "index3" in href_lower:
        score += 80

    if "index2" in href_lower:
        score += 40

    if "zaishoku" in href_lower:
        score += 30

    if "zaisyoku" in href_lower:
        score += 30

    if str(CURRENT_YEAR) in href_lower:
        score += 20

    return score


def page_score(soup):
    text = normalize(
        soup.get_text(
            " ",
            strip=True,
        )
    )

    score = 0

    if "コース番号" in text:
        score += 6

    if "開催月別" in text:
        score += 5

    if "受付中" in text:
        score += 4

    if "訓練日程" in text:
        score += 3

    if "キャンセル待ち" in text:
        score += 2

    table_rows = len(
        soup.find_all("tr")
    )

    if table_rows >= 10:
        score += 2

    if table_rows >= 30:
        score += 2

    return score


def cell_text(cell):
    parts = []

    visible = normalize(
        cell.get_text(
            " ",
            strip=True,
        )
    )

    if visible:
        parts.append(visible)

    for image in cell.find_all("img"):
        for attr in (
            "alt",
            "title",
        ):
            value = normalize(
                image.get(attr, "")
            )

            if (
                value
                and value not in parts
            ):
                parts.append(value)

    return normalize(
        " ".join(parts)
    )


def extract_status(cell_texts):
    for text in cell_texts:
        if not text:
            continue

        # ステータス欄は通常短い
        if len(text) > 40:
            continue

        if any(
            hint in text
            for hint in STATUS_HINTS
        ):
            return text

    return ""


def looks_like_course_row(
    row,
    cell_texts,
):
    links = row.find_all(
        "a",
        href=True,
    )

    if not links:
        return False

    row_text = normalize(
        " ".join(cell_texts)
    )

    # コース番号らしき表記
    has_course_code = bool(
        re.search(
            r"\b[A-Z0-9]{4,}\b",
            row_text,
            re.I,
        )
    )

    # 個別HTMLへのリンク
    has_detail_link = False

    for link in links:
        href = (
            link.get("href")
            or ""
        ).lower()

        if not href.endswith(
            (
                ".html",
                ".htm",
            )
        ):
            continue

        if re.search(
            r"(?:index|menu|top)"
            r"\d*\.html?$",
            href,
        ):
            continue

        has_detail_link = True
        break

    return (
        has_course_code
        or has_detail_link
    )


def inspect_course_list(
    facility_name,
    list_url,
    soup,
):
    rows = []

    for row in soup.find_all("tr"):
        cells = row.find_all(
            [
                "td",
                "th",
            ]
        )

        if len(cells) < 2:
            continue

        texts = [
            cell_text(cell)
            for cell in cells
        ]

        if not looks_like_course_row(
            row,
            texts,
        ):
            continue

        status = extract_status(
            texts
        )

        rows.append(
            {
                "facility": facility_name,
                "list_url": list_url,
                "status": (
                    status
                    or "【判定できず】"
                ),
                "row": normalize(
                    " | ".join(texts)
                ),
            }
        )

    return rows


def direct_candidate_urls(
    home_url,
):
    paths = [
        (
            f"zaishoku/{CURRENT_YEAR}"
            "/index3.html"
        ),
        (
            f"zaisyoku/{CURRENT_YEAR}"
            "/index3.html"
        ),
        (
            f"zaishoku/{CURRENT_YEAR}"
            "/index2.html"
        ),
        (
            f"zaisyoku/{CURRENT_YEAR}"
            "/index2.html"
        ),
        "zaishoku/index3.html",
        "zaisyoku/index3.html",
    ]

    return [
        urljoin(
            home_url,
            path,
        )
        for path in paths
    ]


def discover_course_list(
    home_url,
):
    final_home_url, home_soup = (
        get_soup(home_url)
    )

    initial = []

    for link in home_soup.find_all(
        "a",
        href=True,
    ):
        text = normalize(
            link.get_text(
                " ",
                strip=True,
            )
        )

        href = urljoin(
            final_home_url,
            link["href"],
        )

        if not same_host(
            final_home_url,
            href,
        ):
            continue

        if href.lower().endswith(
            (
                ".pdf",
                ".doc",
                ".docx",
                ".xls",
                ".xlsx",
            )
        ):
            continue

        score = discovery_link_score(
            text,
            href,
        )

        if score <= 0:
            continue

        initial.append(
            (
                score,
                href,
            )
        )

    initial.sort(
        reverse=True,
        key=lambda x: x[0],
    )

    queue = []

    for _, url in initial[:6]:
        queue.append(
            (
                url,
                1,
            )
        )

    for url in direct_candidate_urls(
        final_home_url
    ):
        queue.append(
            (
                url,
                1,
            )
        )

    visited = set()

    best_url = None
    best_soup = None
    best_score = -1

    # 1施設につき最大14ページまで
    while (
        queue
        and len(visited) < 14
    ):
        url, depth = queue.pop(0)

        if url in visited:
            continue

        visited.add(url)

        try:
            final_url, soup = get_soup(
                url
            )
        except Exception:
            continue

        score = page_score(soup)

        if score > best_score:
            best_score = score
            best_url = final_url
            best_soup = soup

        # 「在職者向け」ページから
        # 「開催月別一覧」へもう1段辿る
        if depth >= 2:
            continue

        child_links = []

        for link in soup.find_all(
            "a",
            href=True,
        ):
            text = normalize(
                link.get_text(
                    " ",
                    strip=True,
                )
            )

            href = urljoin(
                final_url,
                link["href"],
            )

            if not same_host(
                final_url,
                href,
            ):
                continue

            if href.lower().endswith(
                ".pdf"
            ):
                continue

            child_score = (
                discovery_link_score(
                    text,
                    href,
                )
            )

            if child_score <= 0:
                continue

            child_links.append(
                (
                    child_score,
                    href,
                )
            )

        child_links.sort(
            reverse=True,
            key=lambda x: x[0],
        )

        for _, child_url in (
            child_links[:6]
        ):
            if child_url not in visited:
                queue.append(
                    (
                        child_url,
                        depth + 1,
                    )
                )

    # 一覧らしさが低すぎる場合は失敗扱い
    if (
        best_url is None
        or best_soup is None
        or best_score < 5
    ):
        return None, None, best_score

    return (
        best_url,
        best_soup,
        best_score,
    )


facilities = get_facilities()

print(
    "FACILITIES:",
    len(facilities),
)
print()

success = []
failed = []
all_rows = []

for index, facility in enumerate(
    facilities,
    1,
):
    name = facility["name"]
    home_url = facility["url"]

    try:
        (
            list_url,
            list_soup,
            score,
        ) = discover_course_list(
            home_url
        )

        if not list_url:
            failed.append(
                (
                    name,
                    home_url,
                    f"一覧未発見 score={score}",
                )
            )

            print(
                f"NG {index:02d} | "
                f"{name} | "
                "開催月別一覧を特定できず"
            )

            continue

        rows = inspect_course_list(
            name,
            list_url,
            list_soup,
        )

        statuses = Counter(
            row["status"]
            for row in rows
        )

        success.append(
            (
                name,
                list_url,
                len(rows),
                statuses,
            )
        )

        all_rows.extend(rows)

        status_text = ", ".join(
            f"{key}={value}"
            for key, value
            in statuses.items()
        )

        print(
            f"OK {index:02d} | "
            f"{name} | "
            f"rows={len(rows)} | "
            f"{status_text}"
        )

        print(
            "   ",
            list_url,
        )

    except Exception as e:
        failed.append(
            (
                name,
                home_url,
                repr(e),
            )
        )

        print(
            f"ERROR {index:02d} | "
            f"{name} | "
            f"{repr(e)}"
        )


print()
print("=" * 80)
print("SUMMARY")
print("=" * 80)

print(
    "施設総数:",
    len(facilities),
)

print(
    "一覧発見:",
    len(success),
)

print(
    "失敗:",
    len(failed),
)

print(
    "コース行総数:",
    len(all_rows),
)


status_counter = Counter(
    row["status"]
    for row in all_rows
)

print()
print("=" * 80)
print("STATUS SUMMARY")
print("=" * 80)

for status, count in (
    status_counter.most_common()
):
    print(
        f"{status}: {count}"
    )


print()
print("=" * 80)
print("FAILED FACILITIES")
print("=" * 80)

if not failed:
    print("なし")
else:
    for (
        name,
        url,
        reason,
    ) in failed:
        print(
            name,
            "|",
            reason,
            "|",
            url,
        )


print()
print("=" * 80)
print("UNCLASSIFIED STATUS SAMPLE")
print("=" * 80)

unknown_rows = [
    row
    for row in all_rows
    if row["status"]
    == "【判定できず】"
]

if not unknown_rows:
    print("なし")
else:
    for row in unknown_rows[:30]:
        print()
        print(
            row["facility"]
        )
        print(
            row["list_url"]
        )
        print(
            row["row"]
        )
