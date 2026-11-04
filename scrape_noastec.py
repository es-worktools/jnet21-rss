"""Conservative NOASTEC RSS writer; preserve verified history on any failure.

Successful live HTML remains unverified as of 2026-11-04 (HTTP 403).
Restoring history does not certify that new-article monitoring has recovered.
"""
import argparse
import copy
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

FEEDS = [
    {"name": "NOASTEC セミナー・イベント", "label": "セミナー・イベント",
     "url": "https://www.noastec.jp/news/seminar-event", "output": "noastec-seminar.xml", "minimum": 10},
    {"name": "NOASTEC プレスリリース", "label": "プレスリリース",
     "url": "https://www.noastec.jp/news/pressrelease", "output": "noastec-pressrelease.xml", "minimum": 9},
    {"name": "NOASTEC 補助・助成", "label": "補助・助成",
     "url": "https://www.noastec.jp/news/subsidy", "output": "noastec-subsidy.xml", "minimum": 10},
]
HEADERS = {"User-Agent": "Mozilla/5.0"}
NS = "urn:jnet21-rss:noastec:safety:v1"
SOURCE_COUNT = "{" + NS + "}sourceCount"
ET.register_namespace("noastec", NS)
ARTICLE = re.compile(r"^/news/[^/]+/post_[0-9]+\.html$")


class GuardError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def valid_url(url):
    p = urlsplit(url)
    return (p.scheme == "https" and p.netloc == "www.noastec.jp"
            and ARTICLE.fullmatch(p.path) and not p.query and not p.fragment)


def read_baseline(path, config, data=None):
    try:
        root = ET.fromstring(path.read_bytes() if data is None else data)
        channel = root.find("channel")
        if root.tag != "rss" or root.get("version") != "2.0" or channel is None:
            raise ValueError("invalid RSS structure")
        if channel.findtext("link") != config["url"] or channel.findtext("title") != config["name"]:
            raise ValueError("channel identity mismatch")
        items = channel.findall("item")
        if not items:
            raise ValueError("empty baseline; separately reviewed restoration required")
        if len(items) < config["minimum"]:
            raise ValueError("baseline has fewer than the verified historical items")
        seen = set()
        for item in items:
            guid, link = item.findtext("guid"), item.findtext("link")
            if not guid or guid != link or not valid_url(link) or not (item.findtext("title") or "").strip():
                raise ValueError("invalid baseline item")
            if guid in seen:
                raise ValueError("duplicate baseline GUID")
            seen.add(guid)
        count = int(channel.findtext(SOURCE_COUNT, str(len(items))))
        if count <= 0 or count > len(items):
            raise ValueError("invalid sourceCount")
        return root, items, max(config["minimum"], count)
    except (OSError, ET.ParseError, ValueError) as exc:
        raise GuardError("BASELINE_ERROR", str(exc)) from exc


def parse_articles(body, config):
    soup = BeautifulSoup(body, "html.parser")
    if config["label"] not in soup.get_text(" ", strip=True):
        raise GuardError("CONTENT_ERROR", "category label missing")
    candidates = {}
    for a in soup.find_all("a", href=True):
        url = urljoin(config["url"], a["href"])
        path = urlsplit(url).path
        # Detect changed article URL patterns rather than silently omitting them.
        if not path.startswith("/news/") or not ("/post_" in path or path.endswith(".html")):
            continue
        if not valid_url(url):
            raise GuardError("PARSE_ERROR", "unexpected article URL: " + url)
        title = a.get_text(" ", strip=True)
        candidates.setdefault(url, set())
        if title:
            candidates[url].add(title)
    if not candidates:
        raise GuardError("ZERO_ITEMS", "no article candidates in HTTP 200 HTML")
    articles = []
    for url, titles in candidates.items():
        if len(titles) != 1:
            raise GuardError("PARSE_ERROR", "missing/conflicting title for " + url)
        articles.append((url, next(iter(titles))))
    return articles


def fetch_articles(config, get):
    # No retries, alternate hosts, cookies, proxies, or access-control workarounds.
    response = get(config["url"], headers=HEADERS, timeout=30, allow_redirects=False)
    if response.status_code != 200:
        raise GuardError("HTTP_ERROR", "HTTP " + str(response.status_code))
    if response.url.rstrip("/") != config["url"]:
        raise GuardError("CONTENT_ERROR", "unexpected response URL")
    media = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if media not in ("text/html", "application/xhtml+xml"):
        raise GuardError("CONTENT_ERROR", "not HTML: " + media)
    return parse_articles(response.content, config)


def build_candidate(root, old_items, articles, minimum):
    if len(articles) < minimum:
        raise GuardError("PARTIAL_ITEMS", f"source count {len(articles)} < required {minimum}")
    old = {i.findtext("guid"): i for i in old_items}
    incoming = {url for url, _ in articles}
    if not incoming.intersection(old):
        raise GuardError("DISJOINT_ITEMS", "no overlap with baseline; manual review required")
    candidate = copy.deepcopy(root)
    channel = candidate.find("channel")
    for item in channel.findall("item"):
        channel.remove(item)
    counter = channel.find(SOURCE_COUNT)
    if counter is None:
        counter = ET.SubElement(channel, SOURCE_COUNT)
    counter.text = str(len(articles))
    for url, title in articles:
        if url in old:
            # Keep the entire existing item, including GUID, dates, attributes, title.
            item = copy.deepcopy(old[url])
        else:
            item = ET.Element("item")
            ET.SubElement(item, "title").text = title
            ET.SubElement(item, "link").text = url
            ET.SubElement(item, "guid").text = url
        channel.append(item)
    for guid, item in old.items():
        if guid not in incoming:
            channel.append(copy.deepcopy(item))
    return ET.tostring(candidate, encoding="utf-8", xml_declaration=True)


def validate_candidate(data, old_items):
    root = ET.fromstring(data)
    items = root.findall("./channel/item")
    guids = [i.findtext("guid") for i in items]
    if not items or len(guids) != len(set(guids)) or not all(guids):
        raise GuardError("OUTPUT_ERROR", "empty/duplicate/invalid candidate GUIDs")
    result = {i.findtext("guid"): i for i in items}
    for old in old_items:
        new = result.get(old.findtext("guid"))
        if new is None or ET.tostring(old) != ET.tostring(new):
            raise GuardError("OUTPUT_ERROR", "baseline item lost or changed")


def atomic_write(path, data, validate, expected=None):
    """Validate a same-directory temp file before one atomic replacement."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix="." + path.name + ".", suffix=".tmp", delete=False) as f:
            temporary = Path(f.name)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temporary, stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644)
        validate(temporary.read_bytes())
        if expected is not None and path.read_bytes() != expected:
            raise GuardError("CONCURRENT_CHANGE", "baseline changed during generation")
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def process_feed(config, directory, get):
    path = directory / config["output"]
    try:
        before = path.read_bytes()
    except OSError as exc:
        raise GuardError("BASELINE_ERROR", str(exc)) from exc
    root, old_items, minimum = read_baseline(path, config, before)
    articles = fetch_articles(config, get)
    data = build_candidate(root, old_items, articles, minimum)
    validate_candidate(data, old_items)
    changed = data != before
    if changed:
        atomic_write(path, data, lambda value: validate_candidate(value, old_items), expected=before)
    elif path.read_bytes() != before:
        raise GuardError("CONCURRENT_CHANGE", "baseline changed during generation")
    return {"file": config["output"], "status": "updated" if changed else "unchanged",
            "source_items": len(articles), "rss_items": len(ET.fromstring(data).findall("./channel/item")),
            "sha256": hashlib.sha256(data).hexdigest()}


def run(directory, get=requests.get):
    results = []
    for config in FEEDS:
        try:
            result = process_feed(config, directory, get)
        except GuardError as exc:
            result = {"file": config["output"], "status": "failed", "code": exc.code, "error": str(exc)}
        except requests.RequestException as exc:
            result = {"file": config["output"], "status": "failed", "code": "TRANSPORT_ERROR", "error": str(exc)}
        except Exception as exc:
            # Keep trying independent categories, but never mark a partial run successful.
            result = {"file": config["output"], "status": "failed", "code": "INTERNAL_OR_SAVE_ERROR", "error": type(exc).__name__ + ": " + str(exc)}
        results.append(result)
        print(json.dumps(result, ensure_ascii=False))
    return {"schema": 1, "complete": True, "results": results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=Path("."))
    parser.add_argument("--summary", type=Path, default=Path("noastec-status.json"))
    args = parser.parse_args()
    args.summary.unlink(missing_ok=True)  # no stale receipt after a crash
    summary = run(args.directory)
    data = (json.dumps(summary, ensure_ascii=False, indent=2) + "\n").encode()
    atomic_write(args.summary, data, json.loads)
    return int(any(r["status"] == "failed" for r in summary["results"]))


if __name__ == "__main__":
    raise SystemExit(main())
