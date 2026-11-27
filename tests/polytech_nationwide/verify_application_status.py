import csv
import json
from collections import Counter
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path
from sys import argv
from tempfile import TemporaryDirectory
from unittest.mock import patch
from xml.etree import ElementTree

from requests import RequestException, Session


STATUS = "お申込みを募集中！"
STATE = "polytech-nationwide-state.json"
RSS = "polytech-nationwide.xml"
CSV = "polytech-nationwide-current.csv"
TODAY = date(2026, 11, 27)
MATSUMOTO = "ポリテクセンター松本"
EXPECTED = {(MATSUMOTO, "9X021"), (MATSUMOTO, "9M502")}


def load_scraper(path, hour=16):
    definitions, separator, pipeline = path.read_text(encoding="utf-8").partition(
        "\nstate = load_state()\n"
    )
    assert separator, path
    namespace = {}
    exec(compile(definitions, str(path), "exec"), namespace)
    namespace["NOW"] = datetime(2026, 11, 27, hour, tzinfo=namespace["JST"])
    namespace["TODAY"] = TODAY
    namespace["FISCAL_YEAR"] = TODAY.year
    return namespace, compile(separator + pipeline, str(path), "exec")


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def rss_items(path):
    return [ElementTree.tostring(item) for item in ElementTree.parse(path).findall("channel/item")]


def run(source, directory, input_state, hour=16):
    scraper, pipeline = load_scraper(source, hour)
    directory.mkdir()
    (directory / STATE).write_bytes(input_state)
    scraper.update(
        STATE_FILE=str(directory / STATE),
        OUTPUT_FILE=str(directory / RSS),
        CURRENT_CSV_FILE=str(directory / CSV),
    )
    log = StringIO()
    with redirect_stdout(log):
        exec(pipeline, scraper)
    result = json.loads((directory / STATE).read_bytes())
    return scraper, result, log.getvalue()


def check_status_boundaries(before, after):
    cases = (
        ("募集終了", TODAY, False),
        ("受付終了", TODAY, False),
        ("お申込みを募集中！ 募集終了", TODAY, False),
        ("お申込みを募集中！ 中止", TODAY, False),
        ("お申込みを募集中！ 満席", TODAY, False),
        ("お申込みを募集中！ 受付予定", TODAY, False),
        ("お申込みを募集中！ 申込締切日 2026年11月26日", TODAY, False),
        ("申込締切日 2026年11月26日", TODAY, False),
        ("開催済み", TODAY, False),
        (STATUS, TODAY - timedelta(days=1), False),
        ("募集中", TODAY, True),
        ("お申込みを絶賛受付中！", TODAY, True),
        ("申込締切日 2026年11月27日", TODAY, True),
    )
    for raw, start, expected in cases:
        for scraper in (before, after):
            category = scraper["normalize_status"](raw)
            assert scraper["is_eligible"](category, raw, start) is expected, (raw, category)
    assert before["normalize_status"](STATUS) == "その他"
    assert after["normalize_status"](STATUS) == "受付中"
    print(f"Status and date regression checks passed: {len(cases)} cases")


def verify(base, after_source, output):
    old_data = (base / STATE).read_bytes()
    saved = json.loads(old_data)
    match_counts = Counter(
        course["facility"] for course in saved["courses"].values() if course["raw_status"] == STATUS
    )
    assert match_counts == {MATSUMOTO: 2}, match_counts
    print(f"Scheduled state: {len(saved['courses'])} courses, matching status {dict(match_counts)}")

    # Freeze every HTTP response (and request failure) from the first live scan.
    fetch = Session.get
    responses = {}

    def fetch_once(session, url, **kwargs):
        if url not in responses:
            try:
                responses[url] = fetch(session, url, **kwargs)
            except RequestException as error:
                responses[url] = error
        response = responses[url]
        if isinstance(response, RequestException):
            raise response
        return response

    before_dir, after_dir, repeat_dir = (output / label for label in ("before", "after", "repeat"))
    with patch.object(Session, "get", fetch_once):
        before, old, old_log = run(base / "before.py", before_dir, old_data)
        captured_urls = set(responses)
        after, new, new_log = run(after_source, after_dir, old_data)
        repeat, repeated, repeat_log = run(after_source, repeat_dir, (after_dir / STATE).read_bytes(), hour=17)
    assert set(responses) == captured_urls
    print(f"Live input replayed: {len(responses)} HTTP URLs")
    for label, log in (("before", old_log), ("after", new_log), ("repeat", repeat_log)):
        summary, _, _ = log.partition("STATUS")
        failed = log.split("FAILED FACILITIES", 1)[1].split("COVERAGE WARNINGS", 1)[0]
        print(label, summary.strip(), failed.strip(), sep="\n")

    check_status_boundaries(before, after)
    assert old["version"] == new["version"] == saved["version"]
    assert old["facility_lists"] == new["facility_lists"]
    assert old["courses"].keys() == new["courses"].keys()
    additions = {}
    for key, original in old["courses"].items():
        changed = new["courses"][key]
        if original == changed:
            continue
        assert original["raw_status"] == STATUS and original["status_category"] == "その他"
        assert changed == {**original, "status_category": "受付中", "eligible": True}
        assert saved["courses"][key]["eligible"] is False
        additions[key] = changed
    assert {(c["facility"], c["code"]) for c in additions.values()} == EXPECTED

    original_guids = {entry["guid"] for entry in saved["notifications"]}
    old_guids = {entry["guid"] for entry in old["notifications"]}
    new_guids = {entry["guid"] for entry in new["notifications"]}
    assert original_guids <= old_guids <= new_guids
    notices = [entry for entry in new["notifications"] if entry["course_key"] in additions]
    transition_notices = [entry for entry in notices if entry["guid"] not in old_guids]
    assert len(transition_notices) == len(additions) == len(new_guids - old_guids)
    assert {entry["course_key"] for entry in transition_notices} == additions.keys()
    for entry in transition_notices:
        assert entry["description"].startswith("検知：受付対象に変更 / ")
        course = additions[entry["course_key"]]
        print("追加通知", course["facility"], course["code"], course["start_date"], course["title"], course["url"], entry["guid"], sep=" | ")
    assert [entry for entry in new["notifications"] if entry["guid"] in old_guids] == old["notifications"]
    assert [entry for entry in new["notifications"] if entry["guid"] in original_guids] == saved["notifications"]
    assert set(rss_items(base / RSS)) <= set(rss_items(before_dir / RSS)) <= set(rss_items(after_dir / RSS))
    assert len(rss_items(after_dir / RSS)) == len(new_guids)

    before_rows = read_csv(before_dir / CSV)
    after_rows = read_csv(after_dir / CSV)
    added_rows = [row for row in after_rows if row["受付状況"] == STATUS]
    assert {(row["施設名"], row["コース番号"]) for row in added_rows} == EXPECTED
    assert [row for row in after_rows if row not in added_rows] == before_rows
    print(f"CSV count: scheduled {len(read_csv(base / CSV))}, before {len(before_rows)}, after {len(after_rows)}")
    print(f"RSS count: scheduled {len(original_guids)}, before {len(old_guids)}, after {len(new_guids)}")

    assert repeat["new_notifications"] == []
    assert repeated == new
    for filename in (STATE, RSS, CSV):
        assert (repeat_dir / filename).read_bytes() == (after_dir / filename).read_bytes()
    print("Repeat with a different detection timestamp: zero notifications; output files byte-identical")


if __name__ == "__main__":
    with TemporaryDirectory() as output:
        verify(Path(argv[1]), Path(argv[2]), Path(output))
