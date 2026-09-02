import re
from collections import Counter, defaultdict
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

    # 一部施設の文字コード警告対策
    if (
        not response.encoding
        or response.encoding.lower()
        in ("iso-8859-1", "ascii")
    ):
        response.encoding = (
            response.apparent_encoding
            or "utf-8"
        )

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    return response.url, soup


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
                "url": url,
            }
        )

    return facilities


def same_host(url1, url2):
    return (
        urlparse(url1).hostname
        == urlparse(url2).hostname
    )


def discovery_link_score(text, href):
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

    if "状況" in text:
        score += 4

    if "訓練日程" in text:
        score += 3

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

    # 状況を画像で表示している施設対策
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


def normalize_status(raw_status):
    status = normalize(raw_status)

    if not status:
        return "（空欄）"

    # 中止を最優先
    if "中止" in status:
        return "中止"

    if "キャンセル" in status:
        return "キャンセル待ち"

    if (
        "受付未定" in status
        or "受付予定" in status
    ):
        return "受付未定"

    if (
        "受付終了" in status
        or "受付は終了" in status
        or "受付修了" in status
        or status == "終了"
        or "終了しました" in status
        or "実施済" in status
        or status == "締切"
    ):
        return "受付終了"

    if (
        "残りわずか" in status
        or "残席わずか" in status
        or "残席僅" in status
    ):
        return "残りわずか"

    if "受付中" in status:
        return "受付中"

    if "電話相談" in status:
        return "電話相談"

    if (
        "お問い合わせ" in status
        or "お問合せ" in status
        or "問合せ" in status
        or "問い合わせ" in status
    ):
        return "お問い合わせ"

    if (
        "申込締切日" in status
        or "申込期限" in status
        or "締切日" in status
    ):
        return "申込締切日"

    if (
        "満席" in status
        or "定員に達" in status
        or "定員到達" in status
    ):
        return "満席"

    return "その他"


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

    has_course_code = bool(
        re.search(
            r"\b[A-Z0-9]{4,}\b",
            row_text,
            re.I,
        )
    )

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

    for table in soup.find_all("table"):
        status_index = None

        # この表の「状況」列を特定
        for header_row in table.find_all(
            "tr"
        ):
            header_cells = (
                header_row.find_all(
                    [
                        "th",
                        "td",
                    ]
                )
            )

            header_texts = [
                cell_text(cell)
                for cell
                in header_cells
            ]

            for index, text in enumerate(
                header_texts
            ):
                if (
                    text == "状況"
                    or "空席状況" in text
                    or "受付状況" in text
                    or "申込状況" in text
                ):
                    status_index = index
                    break

            if status_index is not None:
                break

        for row in table.find_all("tr"):
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

            # 「状況」「空席状況」「受付状況」「申込状況」
            # の列が確認できた場合だけ使用する
            use_index = status_index

            raw_status = ""

            if (
                use_index is not None
                and use_index < len(texts)
            ):
                raw_status = texts[
                    use_index
                ]

            category = normalize_status(
                raw_status
            )

            rows.append(
                {
                    "facility": (
                        facility_name
                    ),
                    "list_url": list_url,
                    "raw_status": (
                        raw_status
                    ),
                    "category": category,
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


def discover_course_list(home_url):
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

        if score > 0:
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

success = []
failed = []
all_rows = []

for facility in facilities:
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
            continue

        rows = inspect_course_list(
            name,
            list_url,
            list_soup,
        )

        success.append(
            (
                name,
                list_url,
                len(rows),
            )
        )

        all_rows.extend(rows)

    except Exception as e:
        failed.append(
            (
                name,
                home_url,
                repr(e),
            )
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


category_counter = Counter(
    row["category"]
    for row in all_rows
)

print()
print("=" * 80)
print("NORMALIZED STATUS")
print("=" * 80)

for category, count in (
    category_counter.most_common()
):
    print(
        f"{category}: {count}"
    )


raw_statuses = defaultdict(Counter)

for row in all_rows:
    raw = (
        row["raw_status"]
        or "（空欄）"
    )

    raw_statuses[
        row["category"]
    ][raw] += 1


print()
print("=" * 80)
print("RAW STATUS")
print("=" * 80)

for category in sorted(
    raw_statuses.keys()
):
    print()
    print(
        f"[{category}]"
    )

    for raw, count in (
        raw_statuses[
            category
        ].most_common()
    ):
        print(
            f"{raw}: {count}"
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
print("OTHER STATUS SAMPLE")
print("=" * 80)

other_rows = [
    row
    for row in all_rows
    if row["category"]
    == "その他"
]

if not other_rows:
    print("なし")
else:
    for row in other_rows[:20]:
        print()
        print(
            row["facility"]
        )
        print(
            "status:",
            row["raw_status"],
        )
        print(
            row["row"]
        )


print()
print("=" * 80)
print("BLANK STATUS BY FACILITY")
print("=" * 80)

blank_counter = Counter(
    row["facility"]
    for row in all_rows
    if row["category"]
    == "（空欄）"
)

if not blank_counter:
    print("なし")
else:
    for facility, count in (
        blank_counter.most_common()
    ):
        print(
            facility,
            ":",
            count,
        )
