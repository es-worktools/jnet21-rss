"""Fail closed; retain reviewed history and never truncate this RSS.

History restoration is a separate reviewed operation, not a network fallback.
403 must remain an error and must never be labelled monitoring recovery.
"""
import argparse
import copy
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

SOURCE_URL = "https://www.taisyokukin.go.jp/topics/"
OUTPUT_FILE = "taisyokukin-topics.xml"
TITLE = "勤労者退職金共済機構 新着情報"
HEADERS = {"User-Agent": "Mozilla/5.0"}
GUID_RE = re.compile(r"urn:taisyokukin-topics:[0-9a-f]{64}\Z")
DATE_RE = re.compile(r"20\d{2}\.\d{1,2}\.\d{1,2}\Z")
GENERIC = {"こちら", "ホームページ", "リンク", "特設サイト"}
HISTORY_GUIDS = (
    'urn:taisyokukin-topics:1bb77158896840365a41f7304ae5daf92baf92122044fc686803405c9d276b94',
    'urn:taisyokukin-topics:eb9869231880a7d67d80d03a3dff58d6d6c284cccf92da3b595589e7d0661568',
    'urn:taisyokukin-topics:c39c2ef6cf7b9fb9fffcf76c2019f22c82b6b3015fa6514e9b6c4b797df1d924',
    'urn:taisyokukin-topics:b2acea04cb578a3bcec2bd3918037294d6137fb0a5eff3511571d34f9224c5f7',
    'urn:taisyokukin-topics:a0511c7691f0d670600988ddec83ffe51ec72cf7a1bf21ff16bffbaea08bfd4c',
    'urn:taisyokukin-topics:f8d8ba7216dae1d8c1b0dc35c2135fb2f38cbb23e224e0113826f437e389aa57',
    'urn:taisyokukin-topics:7a00377cbed9c4f655efbcd715e99c9cadedcc8bce37d811e9f67fc9d401cea0',
    'urn:taisyokukin-topics:ddb5c02d3355c3ea4f888a1fcb747bfc727b2140ab6db5d3b7f924b44a27ea72',
    'urn:taisyokukin-topics:2355818c749fe852dbd9526ed74144933fd159e963dade20a11d786b50a347b5',
    'urn:taisyokukin-topics:7a8aea430064de664cc92407b798b2a4b0e192d3aad78ca1ac844c5594700c31',
    'urn:taisyokukin-topics:dcb0f9c1660dad23cc80541117baf6a2b5ded82d517c48e53c064fd32ae9a085',
    'urn:taisyokukin-topics:9002067795ea99c5fb96b63b92f167f0d01fd6e3aff887a897fbc7c3837beb59',
    'urn:taisyokukin-topics:3a576a9f8a7f9ea99285347110d37e22f07875e932f4ac95438f38b6e563f47d',
    'urn:taisyokukin-topics:6d806b63aa98a63ee13651e77a6c90f8075c08fa88d1afc24ad38e4000307e65',
    'urn:taisyokukin-topics:223d691e1ea3ea80ffc8418ffc73478b1baf8932ee55c911926ae49b4508483e',
    'urn:taisyokukin-topics:a49fb896a1da4e6d624f439f569458fb945cd8b0b343ff9dec7345dfb94c664b',
    'urn:taisyokukin-topics:f5e1bfccb15f5d2a1a6989c45f5a7395f387fd7c2397b875dd8b5ec1fc7f4546',
    'urn:taisyokukin-topics:13e42eff2936061f8a2987982123beb7f9a0ae602d66be8d1b06634fe23c18e1',
    'urn:taisyokukin-topics:541991a50a62af078dec94beae982e2b6d41fbeb3839af79755f141533b99aba',
    'urn:taisyokukin-topics:c29ee2cc746eec1f70c319cbca2ab477f8c5ffaff310afb748d5da8fbf485b7f',
    'urn:taisyokukin-topics:773def9a91fb2059e35c59057c7f8ba0fa025641440577c605f4dc70506521dd',
    'urn:taisyokukin-topics:f75f7cde62a8015009c3b9455e8d7747c241d8949a982b6baf30f30e23176f34',
    'urn:taisyokukin-topics:626d84a22cc88e62c6395202366e051ce93222e788511af2910f2c87fa4b6665',
    'urn:taisyokukin-topics:5d222851e4be3699374434f546f35f9eef3e1ecc0482954f825afebd5a957ce1',
)
HISTORY_FINGERPRINT = 'b75bf8414a8877666918fe6892a3a29be4e92621c64643016d3aaabf1d31cc26'
VERIFIED_SOURCE_GUIDS = frozenset(HISTORY_GUIDS + (
    'urn:taisyokukin-topics:211d7836896c9d6f62cd26954c9107203003391245252e339e7749344a58aa04',
    'urn:taisyokukin-topics:804ef3bd77c3d2daf90aa487161a73483d258241264572094896ace1b1c97461',
    'urn:taisyokukin-topics:58d46da1c5e3c9d99d2ce373001a71bc00bb1e422d0e4e87db3176edc274b512',
    'urn:taisyokukin-topics:cf62efc6f3014c6151507066ce3cf62affd734eaccd7c173c8c7587aa0df3803',
    'urn:taisyokukin-topics:e1727d2939089bda69e28f4aeedf27a1c95ce0ebded459d1d5d66ab18c46da58',
    'urn:taisyokukin-topics:e036a4bb458ae0e8e0662e22765f72f5781d63a2f40d1f245847d29b381230ee',
    'urn:taisyokukin-topics:dba4749b3511694b4f58c64f719a6634dcfc2bdc812e8adb68599ac8aed09f02',
    'urn:taisyokukin-topics:85d8dca1a991ad8c03e9fc1593911da03dd84c306b5d56f28633129e8a15a476',
    'urn:taisyokukin-topics:d94330550070629744fe5040a9c7fca57c8a6a4b64d41bec7fa7a77592ff32fa',
))
DC = "http://purl.org/dc/elements/1.1/"
ET.register_namespace("dc", DC)


class GuardError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def normalized(text):
    return re.sub(r"\s+", " ", text).strip()


def valid_url(url):
    try:
        p = urlsplit(url)
        return (p.scheme in {"http", "https"} and bool(p.hostname)
                and p.username is None and p.password is None
                and not re.search(r"[\s\x00-\x1f]", url))
    except ValueError:
        return False


def read_baseline(data):
    try:
        if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
            raise ValueError("DTD/entity forbidden")
        root = ET.fromstring(data)
        c = root.find("channel")
        if root.tag != "rss" or root.get("version") != "2.0" or c is None:
            raise ValueError("invalid RSS")
        if c.findtext("title") != TITLE or c.findtext("link") != SOURCE_URL:
            raise ValueError("channel identity mismatch")
        items = c.findall("item")
        if len(items) < 24:
            raise ValueError("fewer than 24 historical items; reviewed restoration required")
        guids = []
        for i in items:
            g = i.findtext("guid") or ""
            if (not GUID_RE.fullmatch(g) or not valid_url(i.findtext("link") or "")
                    or not (i.findtext("title") or "").strip()):
                raise ValueError("invalid item")
            guids.append(g)
        if len(set(guids)) != len(guids):
            raise ValueError("duplicate GUID")
        historical = [i for i in items if i.findtext("guid") in HISTORY_GUIDS]
        if hashlib.sha256(b"".join(ET.tostring(i) for i in historical)).hexdigest() != HISTORY_FINGERPRINT:
            raise ValueError("verified historical 24 items missing, changed or reordered")
        return root, items
    except (ET.ParseError, ValueError) as exc:
        raise GuardError("BASELINE_ERROR", str(exc)) from exc


def legacy_fields(block, body):
    """Exact former title/link identity algorithm; display quality is separate."""
    heading = re.search(r"〖(.+?)〗", body)
    a = block.find("a", href=True)
    title = (heading.group(1).strip() if heading else
             normalized(a.get_text(" ", strip=True)) if a else body)
    if title in {"資産運用部", "財形部"} and a:
        title = normalized(a.get_text(" ", strip=True))
    href = a.get("href", "") if a else ""
    url = urljoin(SOURCE_URL, href) if href and not href.startswith("#") else SOURCE_URL
    if title in {"こちら", "ホームページ"}:
        title = heading.group(1).strip() if heading else body
    if not title or not valid_url(url):
        raise GuardError("QUALITY_ERROR", "missing title or unsafe URL")
    # Do not silently hide a bad secondary link.
    for link in block.find_all("a", href=True):
        href = link["href"].strip()
        if href and not href.startswith("#") and not valid_url(urljoin(SOURCE_URL, href)):
            raise GuardError("QUALITY_ERROR", "unsafe source link")
    return title, url


def display_title(block, legacy):
    if legacy not in GENERIC and len(legacy) <= 100:
        return legacy
    # Extract literal source wording; never summarize or invent a headline.
    lines = [normalized(x) for x in block.get_text("\n", strip=True).splitlines()]
    lines = [x for x in lines if x and not re.fullmatch(r"【[^】]+】", x)]
    if not lines:
        raise GuardError("QUALITY_ERROR", "no meaningful title line")
    if legacy in GENERIC:
        return normalized(block.get_text(" ", strip=True))
    return lines[0]


def parse_articles(body):
    try:
        text = body.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise GuardError("ENCODING_ERROR", str(exc)) from exc
    soup = BeautifulSoup(text, "html.parser")
    containers = soup.select("#updatelist2")
    if len(containers) != 1 or "新着情報一覧" not in containers[0].get_text():
        raise GuardError("STRUCTURE_ERROR", "unique news container/label missing")
    container = containers[0]
    lists = container.select("dl.listdt")
    dates = container.find_all("dt")
    if not lists or not dates or len(dates) > 1000:
        raise GuardError("ZERO_OR_ABNORMAL_COUNT", "no dates or implausible source count")
    if len(container.find_all("dd")) != len(dates):
        raise GuardError("PARSE_ERROR", "unpaired date/content")
    records, seen = [], set()
    for dt in dates:
        if dt.parent not in lists:
            raise GuardError("PARSE_ERROR", "unexpected date parent")
        literal = re.sub(r"\s+", "", dt.get_text())
        if not DATE_RE.fullmatch(literal):
            raise GuardError("DATE_ERROR", "unrecognized source date: " + literal)
        try:
            published = date(*map(int, literal.split(".")))
        except ValueError as exc:
            raise GuardError("DATE_ERROR", str(exc)) from exc
        block = dt.find_next_sibling()
        if block is None or block.name != "dd":
            raise GuardError("PARSE_ERROR", "date not followed by dd")
        body_text = normalized(block.get_text(" ", strip=True))
        if not body_text:
            raise GuardError("QUALITY_ERROR", "empty article body")
        title, url = legacy_fields(block, body_text)
        guid = "urn:taisyokukin-topics:" + hashlib.sha256(
            f"{literal}|{title}|{url}".encode("utf-8")).hexdigest()
        if guid in seen:
            raise GuardError("DUPLICATE_ITEM", "duplicate source GUID")
        seen.add(guid)
        records.append({"guid": guid, "title": display_title(block, title), "link": url,
                        "legacy_title": title, "date": published.isoformat(),
                        "source_date_literal": literal, "description": body_text})
    # Stable ordering for equal dates, with calendar validation already complete.
    records.sort(key=lambda r: r["date"], reverse=True)
    return records


def fetch_articles(get):
    # Single normal request. No retries, alternate routes, proxies or credentials.
    r = get(SOURCE_URL, headers=HEADERS, timeout=30, allow_redirects=False)
    if r.status_code != 200:
        raise GuardError("HTTP_ERROR", "HTTP " + str(r.status_code))
    if r.url != SOURCE_URL:
        raise GuardError("CONTENT_ERROR", "unexpected URL")
    media = r.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if media not in {"text/html", "application/xhtml+xml"}:
        raise GuardError("CONTENT_ERROR", "not HTML")
    return parse_articles(r.content)


def build_candidate(root, old_items, articles):
    old_guids = {i.findtext("guid") for i in old_items}
    incoming = {r["guid"] for r in articles}
    if len(articles) != len(incoming) or not incoming:
        raise GuardError("PARSE_ERROR", "empty/duplicate incoming articles")
    # Stronger than a count check: equal-size replacement or one lost old article
    # also blocks writes. A source correction/archive rollover needs human review.
    missing = (old_guids | VERIFIED_SOURCE_GUIDS) - incoming
    if missing:
        raise GuardError("PARTIAL_OR_CHANGED_SOURCE", f"{len(missing)} known articles missing/changed")
    candidate = copy.deepcopy(root)
    c = candidate.find("channel")
    new = [r for r in articles if r["guid"] not in old_guids]
    if not new:
        return None  # preserve exact baseline bytes and all old fields
    old_first = list(c).index(c.find("item"))
    old_by_guid = {i.findtext("guid"): i for i in old_items}
    for i in c.findall("item"):
        c.remove(i)
    for offset, r in enumerate(articles):
        if r["guid"] in old_by_guid:
            c.insert(old_first + offset, copy.deepcopy(old_by_guid[r["guid"]]))
            continue
        i = ET.Element("item")
        ET.SubElement(i, "title").text = r["title"]
        ET.SubElement(i, "link").text = r["link"]
        ET.SubElement(i, "guid", isPermaLink="false").text = r["guid"]
        # The source supplies a date only; do not fabricate a publication time.
        ET.SubElement(i, "{" + DC + "}date").text = r["date"]
        ET.SubElement(i, "description").text = "掲載日: " + r["date"] + "\n" + r["description"]
        c.insert(old_first + offset, i)
    return ET.tostring(candidate, encoding="utf-8", xml_declaration=True)


def validate_candidate(data, old_items):
    _, items = read_baseline(data)
    old = {i.findtext("guid"): i for i in old_items}
    retained = [i for i in items if i.findtext("guid") in old]
    if len(retained) != len(old_items):
        raise GuardError("OUTPUT_ERROR", "historical item missing")
    for before, after in zip(old_items, retained):
        if ET.tostring(before) != ET.tostring(after):
            raise GuardError("OUTPUT_ERROR", "history fields/order changed")


def atomic_write(path, data, validate, expected=None):
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix="." + path.name + ".",
                                         suffix=".tmp", delete=False) as f:
            temp = Path(f.name)
            if f.write(data) != len(data):
                raise OSError("short write")
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temp, stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644)
        saved = temp.read_bytes()
        if saved != data:
            raise GuardError("SAVE_ERROR", "temp bytes mismatch")
        validate(saved)
        if expected is not None and path.read_bytes() != expected:
            raise GuardError("CONCURRENT_CHANGE", "baseline changed during generation")
        os.replace(temp, path)
        temp = None
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def process(path, get):
    before = path.read_bytes()
    root, old = read_baseline(before)
    articles = fetch_articles(get)
    data = build_candidate(root, old, articles)
    if data is not None:
        validate_candidate(data, old)
        atomic_write(path, data, lambda value: validate_candidate(value, old), expected=before)
    else:
        data = before
        if path.read_bytes() != before:
            raise GuardError("CONCURRENT_CHANGE", "baseline changed during generation")
    return {"status": "updated" if data != before else "unchanged", "file": OUTPUT_FILE,
            "baseline_sha256": hashlib.sha256(before).hexdigest(),
            "sha256": hashlib.sha256(data).hexdigest(), "source_items": len(articles),
            "rss_items": len(ET.fromstring(data).findall("./channel/item")),
            "added_items": len(ET.fromstring(data).findall("./channel/item")) - len(old)}


def run(path, summary, get=requests.get):
    # A stale successful receipt must never authorize staging after a crash.
    summary.unlink(missing_ok=True)
    try:
        result = process(path, get)
    except GuardError as exc:
        result = {"status": "failed", "code": exc.code, "error": str(exc)}
    except requests.RequestException as exc:
        result = {"status": "failed", "code": "TRANSPORT_ERROR", "error": str(exc)}
    except Exception as exc:
        result = {"status": "failed", "code": "INTERNAL_OR_SAVE_ERROR",
                  "error": type(exc).__name__ + ": " + str(exc)}
    receipt = {"schema": 1, "complete": True, "result": result}
    atomic_write(summary, (json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode(), json.loads)
    print(json.dumps(receipt, ensure_ascii=False))
    return int(result["status"] == "failed")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--directory", type=Path, default=Path("."))
    p.add_argument("--summary", type=Path, default=Path("taisyokukin-status.json"))
    args = p.parse_args()
    if args.summary.resolve() == (args.directory / OUTPUT_FILE).resolve():
        p.error("summary must be separate from RSS")
    return run(args.directory / OUTPUT_FILE, args.summary)


if __name__ == "__main__":
    raise SystemExit(main())
