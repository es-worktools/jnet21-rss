"""Use the official top page's own news JSON, with official publication times."""
import json
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from xml.etree.ElementTree import Element, SubElement, ElementTree
from lxml import html

SOURCE_URL = 'https://www.village.ohira.miyagi.jp/index.html'
JSON_URL = 'https://www.village.ohira.miyagi.jp/index.update.json'
ALLOWED_DOMAIN = 'www.village.ohira.miyagi.jp'
# Explicit shortcut from the official JSON. It is copied, never requested.
EXTERNAL_ARTICLE_URLS = {'https://sites.google.com/gs.myswan.ed.jp/ohirasho'}
CHANNEL_TITLE = '0296_【GH】宮城県大衡村 新着情報'
OUTPUT_FILE = 'municipality-0296-ohira.xml'
MAX_ITEMS = 30
JST = timezone(timedelta(hours=9))

def normalize(text):
    if not isinstance(text, str):
        raise RuntimeError('Invalid official title')
    return re.sub(r'\s+', ' ', text).strip()

def fetch(url):
    for attempt in range(2):
        try:
            with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=30) as response:
                if response.status != 200 or urlparse(response.url).netloc != ALLOWED_DOMAIN:
                    raise RuntimeError('Unexpected official response or redirect')
                return response.read().decode('utf-8')
        except HTTPError as error:
            if error.code in {401, 403, 429} or attempt == 1:
                raise
            time.sleep(2)
        except Exception:
            if attempt == 1:
                raise
            time.sleep(2)

def top_config(text):
    doc = html.fromstring(text)
    # New-information block has a recent-span marker; the events block uses
    # a tag filter. Never accidentally limit the feed to events only.
    blocks = doc.xpath('//*[@data-url and @data-recent-span and not(@data-tag-filter-targets)]')
    blocks = [x for x in blocks if urljoin(SOURCE_URL, x.get('data-url')) == JSON_URL]
    if len(blocks) != 1:
        raise RuntimeError('Official top-page news configuration changed')
    block = blocks[0]
    days, display_limit = int(block.get('data-date-span')), int(block.get('data-limit'))
    if days != 90 or display_limit != 10 or block.get('data-show-index') or block.get('data-show-mobile'):
        raise RuntimeError('Official top-page news filtering changed')
    return days, display_limit

def parse_source(text, now, days=90):
    source = json.loads(text)
    if not isinstance(source, list) or not source:
        raise RuntimeError('Official news JSON missing; existing RSS preserved')
    items = {}
    for row in source:
        if not isinstance(row, dict):
            raise RuntimeError('Official news row structure changed')
        if row.get('is_category_index') or row.get('is_keitai_page'):
            continue
        title = normalize(row['page_name'])
        url = row['url']
        parsed = urlparse(url)
        if not title or parsed.scheme != 'https' or parsed.username or parsed.password:
            raise RuntimeError('Invalid official article title or URL')
        if parsed.netloc != ALLOWED_DOMAIN and url not in EXTERNAL_ARTICLE_URLS:
            raise RuntimeError('Unverified external shortcut; existing RSS preserved')
        date = datetime.fromisoformat(row['publish_datetime'])
        if date.utcoffset() != timedelta(hours=9):
            raise RuntimeError('Official date missing JST offset')
        if not now - timedelta(days=days) <= date <= now:
            continue
        if url not in items or date > items[url][0]:
            items[url] = (date, title, url)
    if not items:
        raise RuntimeError('No recent dated articles; existing RSS preserved')
    return sorted(items.values(), key=lambda x: x[0], reverse=True)[:MAX_ITEMS]

def main():
    days, display_limit = top_config(fetch(SOURCE_URL))
    rows = parse_source(fetch(JSON_URL), datetime.now(JST), days)
    rss = Element('rss', version='2.0')
    channel = SubElement(rss, 'channel')
    SubElement(channel, 'title').text = CHANNEL_TITLE
    SubElement(channel, 'link').text = SOURCE_URL
    SubElement(channel, 'description').text = '公式トップ新着情報の参照JSONを使用。直近90日・最大30件。'
    for date, title, url in rows:
        item = SubElement(channel, 'item')
        SubElement(item, 'title').text = title
        SubElement(item, 'link').text = url
        SubElement(item, 'guid', isPermaLink='true').text = url
        SubElement(item, 'pubDate').text = format_datetime(date)
    temp = Path(OUTPUT_FILE + '.tmp')
    ElementTree(rss).write(temp, encoding='utf-8', xml_declaration=True)
    temp.replace(OUTPUT_FILE)
    print(OUTPUT_FILE, len(rows), 'official top display limit:', display_limit)
    print(json.dumps([{'date':d.isoformat(), 'title':t, 'url':u} for d,t,u in rows], ensure_ascii=False))

if __name__ == '__main__':
    main()
