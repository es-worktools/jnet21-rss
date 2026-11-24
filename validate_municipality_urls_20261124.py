import importlib
import sys
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import urljoin
from xml.etree.ElementTree import parse

from lxml import html

CHECKS = {
    "0281_tomiya": (30, (
        "https://www.tomiya-city.miyagi.jp/information/2026/11/8f2ad156a518f54ddcb815c1047bc946a7c09d17.html",
        "https://www.tomiya-city.miyagi.jp/information/2026/11/a51ccbe797751576c1472280a23d402d8935194b.html",
    )),
    "0354_tozawa": (20, ()),
    "0408_asakawa": (30, (
        "https://www.town.asakawa.fukushima.jp/information/shinsai/000554.html",
    )),
    "0517_kawaba": (15, (
        "https://www.vill.kawaba.gunma.jp/kurashi/news/item/d9fd7f327e8a3f90ab619ad28aa79666.pdf",
    )),
}


def read_items(path):
    records = parse(path).findall("./channel/item")
    links = [item.findtext("link") for item in records]
    guids = [item.findtext("guid") for item in records]
    assert links == guids and len(set(guids)) == len(guids), "Missing or duplicate URL/GUID"
    dates = [parsedate_to_datetime(item.findtext("pubDate")) for item in records]
    assert dates == sorted(dates, reverse=True), "Wrong date order"
    return set(guids)


def check_urls(module, special_url):
    now = datetime.now(module.JST)
    for invalid_url in ("javascript:void(0)", "https://example.com/news", special_url + "#unknown"):
        try:
            module.add({}, "Test", invalid_url, now, module.SOURCE_URL)
        except RuntimeError as error:
            assert str(error) == "Unexpected article URL"
        else:
            raise AssertionError(f"Accepted unexpected URL: {invalid_url}")


def validate(key, snapshots=None):
    module = importlib.import_module(f"scrape_municipality_{key}")
    old_count, expected_new = CHECKS[key]
    special_url = getattr(module, "ALLOWED_EXTERNAL_ARTICLE_URL", None)
    retired_url = getattr(module, "RETIRED_ARTICLE_URL", None)
    check_urls(module, special_url or retired_url)
    if snapshots:
        name = key.split("_")[1]
        body = {url: (snapshots / f"{name}-{i}.html").read_text() for i, url in enumerate(module.SOURCES)}
    else:
        body = {url: module.fetch(url) for url in module.SOURCES}

    original = Path(module.OUTPUT_FILE)
    before = read_items(original)
    assert len(before) == old_count, (key, "baseline count", len(before))
    with TemporaryDirectory() as directory:
        output = Path(directory) / original.name
        copyfile(original, output)
        with patch.object(module, "OUTPUT_FILE", str(output)), patch.object(module, "fetch", body.__getitem__):
            module.main()
            first = output.read_bytes()
            module.main()
            assert output.read_bytes() == first, "Different results on unchanged input"
        after = read_items(output)
        assert before <= after, ("lost existing URL/GUID", before - after)
        assert set(expected_new) <= after - before, ("missing expected additions", set(expected_new) - after)
        if special_url:
            assert special_url in after - before
        if retired_url:
            assert retired_url not in after

        altered = dict(body)
        for url, value in body.items():
            document = html.fromstring(value)
            for link in document.xpath("//a[@href]"):
                if urljoin(url, link.get("href").strip()) == (special_url or retired_url):
                    link.set("href", "https://example.com/not-in-scope")
                    altered[url] = html.tostring(document, encoding="unicode")
        assert altered != body, "Expected failing URL was absent from the official lists"
        with patch.object(module, "OUTPUT_FILE", str(output)), patch.object(module, "fetch", altered.__getitem__):
            try:
                module.main()
            except RuntimeError as error:
                assert str(error) == "Unexpected article URL"
            else:
                raise AssertionError("Unexpected link did not abort generation")
        assert output.read_bytes() == first, "Existing RSS changed on validation failure"

        current = {}
        for url, value in body.items():
            module.parse_source(value, url, current)
        print(f"{key}: prior={len(before)} retained={len(before & after)} added={len(after-before)} total={len(after)} "
              f"duplicates=0 live_latest={max(row[0] for row in current.values()).date()}")
        for url in sorted(after - before):
            print(f"  added {url}")


if __name__ == "__main__":
    validate(sys.argv[1], Path(sys.argv[2]) if len(sys.argv) > 2 else None)
