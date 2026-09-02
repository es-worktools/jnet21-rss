import csv
import hashlib
import json
import os
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from email.utils import format_datetime
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree

import requests
from bs4 import BeautifulSoup, NavigableString, Tag


FACILITY_LIST_URL = (
    "https://www.jeed.go.jp/location/poly/index.html"
)

NAGOYA_SPECIAL_URL = (
    "https://www3.jeed.go.jp/aichi/poly/zaishoku/index.html"
)

OUTPUT_FILE = "polytech-nationwide.xml"
STATE_FILE = "polytech-nationwide-state.json"
CURRENT_CSV_FILE = "polytech-nationwide-current.csv"

MAX_RSS_ITEMS = 200
INITIAL_SEED_LIMIT = 0

JST = timezone(timedelta(hours=9))
NOW = datetime.now(JST)
TODAY = NOW.date()

# 1～3月は前年度ページが中心
if TODAY.month >= 4:
    FISCAL_YEAR = TODAY.year
else:
    FISCAL_YEAR = TODAY.year - 1

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
}

TIMEOUT = 30

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

    if len(facilities) < 60:
        raise RuntimeError(
            f"施設一覧の取得件数が少なすぎます: "
            f"{len(facilities)}"
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

    if "index_month" in href_lower:
        score += 100

    if "index3" in href_lower:
        score += 80

    if "index2" in href_lower:
        score += 40

    if "zaishoku" in href_lower:
        score += 30

    if "zaisyoku" in href_lower:
        score += 30

    if str(FISCAL_YEAR) in href_lower:
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

    if "空席" in text:
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

    # 実際にコース番号らしい行が多いページを
    # 強く優先する
    course_rows = 0

    for row in soup.find_all("tr"):
        cells = row.find_all(
            [
                "td",
                "th",
            ]
        )

        if len(cells) < 2:
            continue

        row_text = normalize(
            row.get_text(
                " ",
                strip=True,
            )
        )

        if re.search(
            r"\b(?:"
            r"[A-Z0-9]{4,9}"
            r"|"
            r"[A-Z0-9]{1,6}"
            r"-"
            r"[A-Z0-9]{1,6}"
            r")\b",
            row_text,
            re.I,
        ):
            course_rows += 1

    score += min(
        course_rows,
        100,
    )

    return score


def direct_candidate_urls(
    home_url,
):
    years = []

    for year in (
        FISCAL_YEAR,
        TODAY.year,
        FISCAL_YEAR + 1,
    ):
        if year not in years:
            years.append(year)

    paths = []

    for year in years:
        paths.extend(
            [
                f"zaishoku/{year}/index3.html",
                f"zaisyoku/{year}/index3.html",
                f"zaishoku/{year}/index2.html",
                f"zaisyoku/{year}/index2.html",
                f"zaishoku/{year}/index_month.html",
                f"zaisyoku/{year}/index_month.html",
            ]
        )

    paths.extend(
        [
            "zaishoku/index3.html",
            "zaisyoku/index3.html",
            "zaishoku/index2.html",
            "zaisyoku/index2.html",
            "zaishoku/index_month.html",
            "zaisyoku/index_month.html",
        ]
    )

    return [
        urljoin(
            home_url,
            path,
        )
        for path in paths
    ]


def discover_course_list(
    home_url,
    cached_url=None,
):
    # 前回成功したURLを最優先
    if cached_url:
        try:
            final_url, soup = get_soup(
                cached_url
            )

            if page_score(soup) >= 5:
                return (
                    final_url,
                    soup,
                    page_score(soup),
                )
        except Exception:
            pass

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

    for _, url in initial[:8]:
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
        and len(visited) < 40
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
                (
                    ".pdf",
                    ".doc",
                    ".docx",
                    ".xls",
                    ".xlsx",
                )
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

        for _, child_url in reversed(
            child_links[:8]
        ):
            if child_url not in visited:
                queue.insert(
                    0,
                    (
                        child_url,
                        depth + 1,
                    ),
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

    # 画像でステータス表示している施設
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


def find_header_index(
    header_texts,
    keywords,
):
    for index, text in enumerate(
        header_texts
    ):
        if any(
            keyword in text
            for keyword in keywords
        ):
            return index

    return None


def table_indices(table):
    result = {
        "code": None,
        "title": None,
        "date": None,
        "status": None,
    }

    for header_row in table.find_all(
        "tr"
    ):
        cells = header_row.find_all(
            [
                "th",
                "td",
            ]
        )

        if len(cells) < 2:
            continue

        texts = [
            cell_text(cell)
            for cell in cells
        ]

        code_index = find_header_index(
            texts,
            (
                "コース番号",
                "コースNo",
                "コースＮｏ",
            ),
        )

        title_index = find_header_index(
            texts,
            (
                "コース名",
                "セミナー名",
                "訓練コース",
            ),
        )

        date_index = find_header_index(
            texts,
            (
                "訓練日程",
                "開催日",
                "実施日",
                "日程",
            ),
        )

        status_index = find_header_index(
            texts,
            (
                "空席状況",
                "受付状況",
                "申込状況",
                "状況",
            ),
        )

        if code_index is not None:
            result["code"] = code_index

        if title_index is not None:
            result["title"] = title_index

        if date_index is not None:
            result["date"] = date_index

        if status_index is not None:
            result["status"] = status_index

        if (
            result["code"] is not None
            or result["title"] is not None
            or result["date"] is not None
            or result["status"] is not None
        ):
            # ヘッダーらしい行が見つかれば十分
            if (
                result["title"] is not None
                and result["date"] is not None
            ):
                break

    return result


def find_detail_link(
    row,
    list_url,
):
    candidates = []

    list_host = urlparse(
        list_url
    ).hostname

    for link in row.find_all(
        "a",
        href=True,
    ):
        href = (
            link.get("href")
            or ""
        ).strip()

        if not href:
            continue

        lower = href.lower()

        if lower.startswith(
            (
                "mailto:",
                "javascript:",
                "#",
            )
        ):
            continue

        absolute = urljoin(
            list_url,
            href,
        )

        parsed = urlparse(
            absolute
        )

        if (
            parsed.hostname
            != list_host
        ):
            continue

        path = parsed.path.lower()

        if path.endswith(
            (
                ".pdf",
                ".doc",
                ".docx",
                ".xls",
                ".xlsx",
                ".zip",
            )
        ):
            continue

        basename = path.rstrip(
            "/"
        ).split("/")[-1]

        if basename in {
            "",
            "index.html",
            "index.htm",
            "index2.html",
            "index3.html",
            "index_month.html",
        }:
            continue

        text = normalize(
            link.get_text(
                " ",
                strip=True,
            )
        )

        score = len(text)

        if path.endswith(
            (
                ".html",
                ".htm",
            )
        ):
            score += 100

        candidates.append(
            (
                score,
                absolute,
                text,
            )
        )

    if not candidates:
        return None, ""

    candidates.sort(
        reverse=True,
        key=lambda x: x[0],
    )

    _, url, text = candidates[0]

    return url, text


def extract_course_code(
    texts,
    code_index=None,
):
    def valid_code(value):
        value = normalize(value)

        if not value:
            return ""

        # 同じセルに複数コードがある場合は
        # 先頭コードを代表として使用
        candidate = value.split()[0]

        if len(candidate) < 4:
            return ""

        if not re.fullmatch(
            r"[A-Z0-9]+"
            r"(?:-[A-Z0-9]+)*",
            candidate,
            re.I,
        ):
            return ""

        # 年だけの数字などを除外
        if (
            candidate.isdigit()
            and "-" not in candidate
        ):
            return ""

        return candidate

    if (
        code_index is not None
        and code_index < len(texts)
    ):
        code = valid_code(
            texts[code_index]
        )

        if code:
            return code

    whole = normalize(
        " ".join(texts)
    )

    candidates = re.findall(
        r"\b[A-Z0-9]+"
        r"(?:-[A-Z0-9]+)*\b",
        whole,
        re.I,
    )

    for candidate in candidates:
        if len(candidate) < 4:
            continue

        if (
            candidate.isdigit()
            and "-" not in candidate
        ):
            continue

        # 英字を含むか、
        # 200-1 のようなハイフン付き数字
        if (
            re.search(
                r"[A-Z]",
                candidate,
                re.I,
            )
            or "-" in candidate
        ):
            return candidate

    return ""


def extract_title(
    texts,
    title_index,
    link_text,
    code,
):
    if (
        title_index is not None
        and title_index < len(texts)
    ):
        title = normalize(
            texts[title_index]
        )

        if title:
            return title

    if link_text:
        if (
            code
            and normalize(link_text) != code
        ):
            return normalize(link_text)

    candidates = []

    for text in texts:
        text = normalize(text)

        if not text:
            continue

        if text == code:
            continue

        if len(text) < 5:
            continue

        if re.fullmatch(
            r"\d{1,2}名",
            text,
        ):
            continue

        candidates.append(text)

    if not candidates:
        return ""

    return max(
        candidates,
        key=len,
    )


def extract_schedule(
    texts,
    date_index,
):
    if (
        date_index is not None
        and date_index < len(texts)
    ):
        value = normalize(
            texts[date_index]
        )

        if value:
            return value

    whole = normalize(
        " | ".join(texts)
    )

    # 日付らしい部分が無ければ
    # 行全体を返す
    return whole


def parse_full_japanese_date(text):
    text = normalize(text)

    # 令和8年9月15日
    match = re.search(
        r"令和\s*(元|\d+)\s*年"
        r"\s*(\d{1,2})\s*月"
        r"\s*(\d{1,2})\s*日",
        text,
    )

    if match:
        era_year = match.group(1)

        if era_year == "元":
            reiwa_year = 1
        else:
            reiwa_year = int(
                era_year
            )

        return date(
            2018 + reiwa_year,
            int(match.group(2)),
            int(match.group(3)),
        )

    # R9/2/12、R9.2/3、R9年2月12日
    match = re.search(
        r"\bR\s*(\d{1,2})"
        r"\s*(?:[./]|年)\s*"
        r"(\d{1,2})"
        r"\s*(?:[./]|月)\s*"
        r"(\d{1,2})\s*日?",
        text,
        re.I,
    )

    if match:
        return date(
            2018 + int(
                match.group(1)
            ),
            int(match.group(2)),
            int(match.group(3)),
        )

    # 2026年9月15日
    match = re.search(
        r"\b(20\d{2})\s*年"
        r"\s*(\d{1,2})\s*月"
        r"\s*(\d{1,2})\s*日",
        text,
    )

    if match:
        return date(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
        )

    return None


def infer_fiscal_date(
    month,
    day,
):
    if month >= 4:
        year = FISCAL_YEAR
    else:
        year = FISCAL_YEAR + 1

    try:
        return date(
            year,
            month,
            day,
        )
    except ValueError:
        return None


def parse_start_date(text):
    full = parse_full_japanese_date(
        text
    )

    if full:
        return full

    # 9月15日
    match = re.search(
        r"(?<!\d)"
        r"(\d{1,2})\s*月"
        r"\s*(\d{1,2})\s*日",
        text,
    )

    if match:
        return infer_fiscal_date(
            int(match.group(1)),
            int(match.group(2)),
        )

    # 9/15
    match = re.search(
        r"(?<!\d)"
        r"(\d{1,2})\s*/"
        r"\s*(\d{1,2})",
        text,
    )

    if match:
        return infer_fiscal_date(
            int(match.group(1)),
            int(match.group(2)),
        )

    return None


def parse_deadline(text):
    return parse_full_japanese_date(
        text
    )


def normalize_status(raw_status):
    status = normalize(raw_status)

    if status in (
        "",
        "─",
        "-",
        "－",
        "―",
        "—",
    ):
        return "（空欄）"

    if "中止" in status:
        return "中止"

    if "キャンセル" in status:
        return "キャンセル待ち"

    if (
        "日程調整中" in status
        or "受付未定" in status
        or "受付予定" in status
    ):
        return "受付未定"

    # 締切日の記載は
    # 「締切」より先に判定
    if (
        "申込締切日" in status
        or "申込期限" in status
        or "締切日" in status
    ):
        return "申込締切日"

    if (
        "受付終了" in status
        or "受付は終了" in status
        or "受付修了" in status
        or status == "終了"
        or "終了しました" in status
        or "実施済" in status
        or status == "完了"
        or status == "締切"
    ):
        return "受付終了"

    if (
        "満席" in status
        or "定員に達" in status
        or "定員到達" in status
    ):
        return "満席"

    if (
        "残りわずか" in status
        or "残り僅か" in status
        or "残席わずか" in status
        or "残席僅" in status
        or "定員間近" in status
    ):
        return "残りわずか"

    if (
        "受付中" in status
        or status == "募集中"
        or "空きがあります" in status
    ):
        return "受付中"

    if "電話相談" in status:
        return "お問い合わせ"

    if (
        "お問い合わせ" in status
        or "お問合せ" in status
        or "問合せ" in status
        or "問い合わせ" in status
        or "要問合せ" in status
    ):
        return "お問い合わせ"

    return "その他"


def is_eligible(
    category,
    raw_status,
    start_date,
):
    # 明確に受付可能
    if category in (
        "受付中",
        "残りわずか",
        "お問い合わせ",
    ):
        # 過去開催なら除外
        if (
            start_date is not None
            and start_date < TODAY
        ):
            return False

        return True

    # 締切日方式
    if category == "申込締切日":
        deadline = parse_deadline(
            raw_status
        )

        if deadline is None:
            return False

        if deadline < TODAY:
            return False

        if (
            start_date is not None
            and start_date < TODAY
        ):
            return False

        return True

    # 状況記載なし。
    # 開催日が未来なら残す
    if category == "（空欄）":
        return (
            start_date is not None
            and start_date >= TODAY
        )

    return False


def make_course_key(
    facility,
    code,
    detail_url,
    title,
):
    base = "|".join(
        [
            facility,
            code,
            detail_url,
            title,
        ]
    )

    return hashlib.sha256(
        base.encode("utf-8")
    ).hexdigest()


def inspect_course_list(
    facility_name,
    list_url,
    soup,
):
    courses = []

    for table in soup.find_all("table"):
        indices = table_indices(
            table
        )

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

            detail_url, link_text = (
                find_detail_link(
                    row,
                    list_url,
                )
            )

            code = extract_course_code(
                texts,
                indices["code"],
            )

            if not detail_url:
                if (
                    facility_name
                    == "ポリテクセンター中部"
                ):
                    detail_url = list_url
                    link_text = ""
                else:
                    continue

            if not code:
                continue

            title = extract_title(
                texts,
                indices["title"],
                link_text,
                code,
            )

            if not title:
                continue

            raw_status = ""

            status_index = (
                indices["status"]
            )

            if (
                status_index is not None
                and status_index
                < len(texts)
            ):
                raw_status = texts[
                    status_index
                ]

            # 表のヘッダー行はコースとして扱わない
            if raw_status in (
                "空き状況等",
                "空席状況",
                "受付状況",
                "申込状況",
                "状況",
            ):
                continue

            schedule = extract_schedule(
                texts,
                indices["date"],
            )

            start_date = parse_start_date(
                schedule
            )

            category = normalize_status(
                raw_status
            )

            eligible = is_eligible(
                category,
                raw_status,
                start_date,
            )

            key = make_course_key(
                facility_name,
                code,
                detail_url,
                title,
            )

            courses.append(
                {
                    "key": key,
                    "facility": (
                        facility_name
                    ),
                    "code": code,
                    "title": title,
                    "url": detail_url,
                    "list_url": list_url,
                    "schedule": schedule,
                    "start_date": (
                        start_date.isoformat()
                        if start_date
                        else ""
                    ),
                    "raw_status": raw_status,
                    "status_category": (
                        category
                    ),
                    "eligible": eligible,
                }
            )

    # 同一コース重複除去
    unique = {}

    for course in courses:
        unique[
            course["key"]
        ] = course

    return list(
        unique.values()
    )


def scan_nagoya_special():
    final_url, soup = get_soup(
        NAGOYA_SPECIAL_URL
    )

    target_heading = None

    for heading in soup.find_all(
        [
            "h3",
            "h4",
            "h5",
        ]
    ):
        text = normalize(
            heading.get_text(
                " ",
                strip=True,
            )
        )

        if (
            "名古屋港湾主催セミナー"
            in text
        ):
            target_heading = heading
            break

    if target_heading is None:
        return []

    parts = []
    detail_url = final_url

    for element in (
        target_heading.next_elements
    ):
        if (
            isinstance(element, Tag)
            and element is not target_heading
            and element.name
            in ("h3", "h4", "h5")
        ):
            break

        if isinstance(
            element,
            NavigableString,
        ):
            text = normalize(
                str(element)
            )

            if text:
                parts.append(text)

        if (
            isinstance(element, Tag)
            and element.name == "a"
        ):
            link_text = normalize(
                element.get_text(
                    " ",
                    strip=True,
                )
            )

            href = (
                element.get("href")
                or ""
            ).strip()

            if (
                href
                and "コース内容"
                in link_text
            ):
                detail_url = urljoin(
                    final_url,
                    href,
                )

    section_text = normalize(
        " ".join(parts)
    )

    courses = []
    seen_codes = set()

    for match in re.finditer(
        r"\b([A-Z]\d{3,4}[A-Z]?)\b",
        section_text,
        re.I,
    ):
        code = match.group(1)

        if code in seen_codes:
            continue

        snippet = section_text[
            match.end():
            match.end() + 220
        ]

        title_match = re.search(
            r"[『「](.+?)[』」]",
            snippet,
        )

        if not title_match:
            continue

        title = normalize(
            title_match.group(1)
        )

        before_title = snippet[
            :title_match.start()
        ]

        schedule_match = re.search(
            r"(\d{1,2}/\d{1,2}"
            r".*?)$",
            before_title,
        )

        if schedule_match:
            schedule = normalize(
                schedule_match.group(1)
            )
        else:
            schedule = before_title

        start_date = parse_start_date(
            schedule
        )

        category = "（空欄）"

        eligible = (
            start_date is not None
            and start_date >= TODAY
        )

        key = make_course_key(
            "ポリテクセンター名古屋港",
            code,
            detail_url,
            title,
        )

        courses.append(
            {
                "key": key,
                "facility": (
                    "ポリテクセンター名古屋港"
                ),
                "code": code,
                "title": title,
                "url": detail_url,
                "list_url": final_url,
                "schedule": schedule,
                "start_date": (
                    start_date.isoformat()
                    if start_date
                    else ""
                ),
                "raw_status": (
                    "名古屋港湾主催・"
                    "受付状況個別表記なし"
                ),
                "status_category": (
                    category
                ),
                "eligible": eligible,
            }
        )

        seen_codes.add(code)

    return courses


def load_state():
    if not os.path.exists(
        STATE_FILE
    ):
        return None

    with open(
        STATE_FILE,
        "r",
        encoding="utf-8",
    ) as f:
        state = json.load(f)

    if state.get("version") != 1:
        raise RuntimeError(
            "state version が不正です"
        )

    return state


def save_state(state):
    with open(
        STATE_FILE,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            state,
            f,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )


def make_notification(
    course,
    reason,
):
    detected_at = NOW.isoformat()

    guid_source = "|".join(
        [
            course["key"],
            reason,
            detected_at,
        ]
    )

    guid = hashlib.sha256(
        guid_source.encode("utf-8")
    ).hexdigest()

    title = (
        f"【{course['facility']}】"
        f"{course['title']}"
    )

    description_parts = [
        f"検知：{reason}",
        f"施設：{course['facility']}",
    ]

    if course["code"]:
        description_parts.append(
            f"コース番号："
            f"{course['code']}"
        )

    if course["schedule"]:
        description_parts.append(
            f"日程："
            f"{course['schedule']}"
        )

    if course["raw_status"]:
        description_parts.append(
            f"状況："
            f"{course['raw_status']}"
        )
    else:
        description_parts.append(
            "状況：記載なし"
        )

    return {
        "guid": guid,
        "title": title,
        "url": course["url"],
        "description": " / ".join(
            description_parts
        ),
        "pub_date": detected_at,
        "facility": course[
            "facility"
        ],
        "course_key": course[
            "key"
        ],
    }


def generate_rss(
    notifications,
):
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
        "全国ポリテクセンター｜"
        "能力開発セミナー"
    )

    SubElement(
        channel,
        "link",
    ).text = FACILITY_LIST_URL

    SubElement(
        channel,
        "description",
    ).text = (
        "全国のポリテクセンターの"
        "能力開発セミナーの新規掲載・"
        "受付対象への変更を通知します。"
    )

    for notification in notifications[
        :MAX_RSS_ITEMS
    ]:
        item = SubElement(
            channel,
            "item",
        )

        SubElement(
            item,
            "title",
        ).text = notification["title"]

        SubElement(
            item,
            "link",
        ).text = notification["url"]

        guid = SubElement(
            item,
            "guid",
        )

        guid.set(
            "isPermaLink",
            "false",
        )

        guid.text = (
            "polytech-"
            + notification["guid"]
        )

        pub_date = datetime.fromisoformat(
            notification["pub_date"]
        )

        SubElement(
            item,
            "pubDate",
        ).text = format_datetime(
            pub_date
        )

        SubElement(
            item,
            "description",
        ).text = notification[
            "description"
        ]

    ElementTree(rss).write(
        OUTPUT_FILE,
        encoding="utf-8",
        xml_declaration=True,
    )

def generate_current_csv(courses):
    current_courses_list = [
        course
        for course in courses.values()
        if course["eligible"]
    ]

    # 開催開始日の近い順
    current_courses_list.sort(
        key=lambda course: (
            course["start_date"]
            or "9999-12-31",
            course["facility"],
            course["title"],
        )
    )

    fieldnames = [
        "施設名",
        "コース番号",
        "セミナー名",
        "開催開始日",
        "日程",
        "受付状況",
        "受付判定",
        "URL",
    ]

    with open(
        CURRENT_CSV_FILE,
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        for course in current_courses_list:
            writer.writerow(
                {
                    "施設名": course[
                        "facility"
                    ],
                    "コース番号": course[
                        "code"
                    ],
                    "セミナー名": course[
                        "title"
                    ],
                    "開催開始日": course[
                        "start_date"
                    ],
                    "日程": course[
                        "schedule"
                    ],
                    "受付状況": (
                        course["raw_status"]
                        or "記載なし"
                    ),
                    "受付判定": course[
                        "status_category"
                    ],
                    "URL": course[
                        "url"
                    ],
                }
            )

    return len(
        current_courses_list
    )


state = load_state()

first_run = state is None

if first_run:
    state = {
        "version": 1,
        "facility_lists": {},
        "courses": {},
        "notifications": [],
    }


previous_courses = state.get(
    "courses",
    {},
)

previous_lists = state.get(
    "facility_lists",
    {},
)

notifications = state.get(
    "notifications",
    [],
)


facilities = get_facilities()

current_courses = {}
current_lists = dict(
    previous_lists
)

successful_facilities = set()
failed_facilities = []

unknown_counter = Counter()
category_counter = Counter()


for facility in facilities:
    name = facility["name"]
    home_url = facility["url"]

    # 名古屋港は特殊補完
    if "名古屋港" in name:
        continue

    # 大阪港は在職者向け能力開発セミナーの
    # 全国監視対象外
    if "大阪港" in name:
        continue

    try:
        (
            list_url,
            list_soup,
            score,
        ) = discover_course_list(
            home_url,
            previous_lists.get(name),
        )

        if not list_url:
            raise RuntimeError(
                f"一覧未発見 score={score}"
            )

        courses = inspect_course_list(
            name,
            list_url,
            list_soup,
        )

        if not courses:
            page_title = ""

            if list_soup.title:
                page_title = normalize(
                    list_soup.title.get_text(
                        " ",
                        strip=True,
                    )
                )

            table_count = len(
                list_soup.find_all("table")
            )

            row_count = len(
                list_soup.find_all("tr")
            )

            html_links = []

            for link in list_soup.find_all(
                "a",
                href=True,
            ):
                href = (
                    link.get("href")
                    or ""
                ).strip()

                if re.search(
                    r"\.html?(?:$|[?#])",
                    href,
                    re.I,
                ):
                    html_links.append(href)

            sample_links = html_links[:5]

            raise RuntimeError(
                "コースを1件も取得できません"
                f" | list_url={list_url}"
                f" | title={page_title}"
                f" | tables={table_count}"
                f" | rows={row_count}"
                f" | html_links={len(html_links)}"
                f" | sample={sample_links}"
            )

        current_lists[name] = (
            list_url
        )

        successful_facilities.add(
            name
        )

        for course in courses:
            current_courses[
                course["key"]
            ] = course

            category_counter[
                course[
                    "status_category"
                ]
            ] += 1

            if (
                course[
                    "status_category"
                ]
                == "その他"
            ):
                unknown_counter[
                    course["raw_status"]
                    or "（空欄）"
                ] += 1

    except Exception as e:
        failed_facilities.append(
            (
                name,
                repr(e),
            )
        )


# 名古屋港の特殊補完
try:
    nagoya_courses = (
        scan_nagoya_special()
    )

    if not nagoya_courses:
        raise RuntimeError(
            "名古屋港湾主催セミナー"
            "を取得できません"
        )

    successful_facilities.add(
        "ポリテクセンター名古屋港"
    )

    for course in nagoya_courses:
        current_courses[
            course["key"]
        ] = course

        category_counter[
            course[
                "status_category"
            ]
        ] += 1

except Exception as e:
    failed_facilities.append(
        (
            "ポリテクセンター名古屋港",
            repr(e),
        )
    )


# 取得失敗施設は前回状態を保持。
# 一時エラー後の復旧時に
# 全件新着扱いになるのを防ぐ。
failed_names = {
    name
    for name, _
    in failed_facilities
}

for key, old_course in (
    previous_courses.items()
):
    if (
        old_course["facility"]
        in failed_names
    ):
        current_courses[
            key
        ] = old_course


new_notifications = []


if first_run:
    # 初回は全件通知せず、
    # 現在受付対象のうち
    # 開催日の近い30件だけ初期表示。
    eligible_courses = [
        course
        for course
        in current_courses.values()
        if course["eligible"]
    ]

    eligible_courses.sort(
        key=lambda course: (
            course["start_date"]
            or "9999-12-31",
            course["facility"],
            course["title"],
        )
    )

    for course in (
        eligible_courses[
            :INITIAL_SEED_LIMIT
        ]
    ):
        new_notifications.append(
            make_notification(
                course,
                "初期登録",
            )
        )

else:
    for key, course in (
        current_courses.items()
    ):
        if not course["eligible"]:
            continue

        previous = (
            previous_courses.get(key)
        )

        # 新規コース
        if previous is None:
            new_notifications.append(
                make_notification(
                    course,
                    "新規掲載",
                )
            )
            continue

        # 前回は対象外だったが、
        # 今回受付可能になった
        if (
            not previous.get(
                "eligible",
                False,
            )
            and course["eligible"]
        ):
            new_notifications.append(
                make_notification(
                    course,
                    "受付対象に変更",
                )
            )


notifications = (
    new_notifications
    + notifications
)

# 同一guid重複除去
unique_notifications = []
seen_guids = set()

for notification in notifications:
    guid = notification["guid"]

    if guid in seen_guids:
        continue

    seen_guids.add(guid)

    unique_notifications.append(
        notification
    )

notifications = (
    unique_notifications[
        :MAX_RSS_ITEMS
    ]
)


new_state = {
    "version": 1,
    "facility_lists": (
        current_lists
    ),
    "courses": (
        current_courses
    ),
    "notifications": (
        notifications
    ),
}


save_state(
    new_state
)

generate_rss(
    notifications
)


eligible_count = generate_current_csv(
    current_courses
)


print()
print("=" * 70)
print("SUMMARY")
print("=" * 70)

print(
    "施設一覧:",
    len(facilities),
)

print(
    "正常取得施設:",
    len(
        successful_facilities
    ),
)

print(
    "取得失敗施設:",
    len(
        failed_facilities
    ),
)

print(
    "取得コース総数:",
    len(current_courses),
)

print(
    "現在受付対象件数:",
    eligible_count,
)

print(
    "今回の新規通知:",
    len(new_notifications),
)

print(
    "RSS保持件数:",
    len(notifications),
)

print(
    "初回実行:",
    first_run,
)


print()
print("=" * 70)
print("STATUS")
print("=" * 70)

for category, count in (
    category_counter.most_common()
):
    print(
        f"{category}: {count}"
    )


print()
print("=" * 70)
print("UNKNOWN STATUS")
print("=" * 70)

if not unknown_counter:
    print("なし")
else:
    for raw, count in (
        unknown_counter.most_common()
    ):
        print(
            f"{raw}: {count}"
        )


print()
print("=" * 70)
print("FAILED FACILITIES")
print("=" * 70)

if not failed_facilities:
    print("なし")
else:
    for name, error in (
        failed_facilities
    ):
        print(
            name,
            "|",
            error,
        )


print()
print("=" * 70)
print("NEW NOTIFICATIONS")
print("=" * 70)

if not new_notifications:
    print("なし")
else:
    for notification in (
        new_notifications[:50]
    ):
        print(
            notification["title"],
            "|",
            notification["url"],
        )


print()
print(
    OUTPUT_FILE,
    len(notifications),
)

print(
    STATE_FILE,
    len(current_courses),
)
print(
    CURRENT_CSV_FILE,
    eligible_count,
)
