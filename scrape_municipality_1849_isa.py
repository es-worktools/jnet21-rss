"""Isa: business/agriculture news, general notices and tender sources.
Dated posts use the date on the individual official page. Undated permanent
business/contract pages omit pubDate and use a content-hash GUID for updates.
Any failed source/article aborts without overwriting the existing RSS.
"""
import base64
import copy
import hashlib
import json
import re
import sys
import threading
import zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen
from xml.etree.ElementTree import Element, SubElement, ElementTree
from lxml import html

HOST = 'www.city.isa.kagoshima.jp'
BASE = 'https://' + HOST + '/'
TITLE = '1849_【GH】鹿児島県伊佐市 新着情報'
OUTPUT = 'municipality-1849-isa.xml'
JST = timezone(timedelta(hours=9))
CLASS = 'contains(concat(" ",normalize-space(@class)," ")," %s ")'
ROOTS = ['residency/', 'politics/', 'politics/agreement/kouji/',
         'blog/category/info-residency/', 'blog/category/info-gyousei/',
         'blog/category/info-prompt/', 'blog/category/topics/']


def norm(text):
    return re.sub(r'\s+', ' ', text or '').strip()


def safe(url):
    p = urlparse(url)
    if p.scheme not in ('https', 'http') or p.netloc != HOST or p.username or p.password:
        raise RuntimeError('Unexpected official URL: ' + url)
    return urlunparse(('https', HOST, p.path, '', p.query, ''))


def day(text):
    m = re.fullmatch(r'(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日', norm(text))
    if not m:
        raise RuntimeError('Official date missing: ' + text)
    value = datetime(*map(int, m.groups()), tzinfo=JST)
    if value.date() > datetime.now(JST).date():
        raise RuntimeError('Unexpected future date: ' + text)
    return value.isoformat()


def main():
    evidence = {'checked_at': datetime.now(JST).isoformat(), 'status': 'running',
                'requests': [], 'sources': [], 'rss_discovery': [], 'title_differences': []}
    lock = threading.Lock()
    cache = {}

    def fetch(url):
        url = safe(url)
        if url in cache:
            return cache[url]
        rec = {'url': url}
        with lock:
            if len(evidence['requests']) >= 230:
                raise RuntimeError('Reviewed request limit exceeded')
            evidence['requests'].append(rec)
        try:
            with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=35) as response:
                rec.update(status=response.status, final_url=safe(response.url))
                if rec['final_url'] != url:
                    raise RuntimeError('Unexpected redirect: ' + rec['final_url'])
                raw = response.read()
            doc = html.fromstring(raw)
            if 'メンテナンスのお知らせ' in ''.join(doc.xpath('//title/text()')):
                raise RuntimeError('Official maintenance page returned')
            rec.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            cache[url] = doc
            return doc
        except Exception as error:
            rec.update(error=repr(error), status=getattr(error, 'code', rec.get('status')))
            raise

    def discover(url, doc):
        found = doc.xpath('//link[contains(@type,"rss") or contains(@type,"atom")]/@href')
        found += [a.get('href') for a in doc.xpath('//a[@href]')
                  if re.search(r'RSS|Atom', norm(a.text_content()), re.I)]
        evidence['rss_discovery'].append({'url': url, 'links': sorted(set(found))})
        if found:
            raise RuntimeError('New advertised official RSS/Atom requires review')

    candidates = {}

    def add(url, title, date, source):
        url = safe(url)
        if not re.search(r'/blog/(?!category/).*/\d+/$', url):
            raise RuntimeError('Unexpected article link: ' + url)
        title = norm(title)
        if not title:
            raise RuntimeError('Empty listing title: ' + url)
        row = candidates.setdefault(url, {'url': url, 'listings': []})
        entry = {'source': source, 'title': title, 'date': date}
        if entry not in row['listings']:
            row['listings'].append(entry)

    def listing(url, doc):
        rows = []
        for dl in doc.xpath('//*[@id="ank_info"]//dl'):
            links = dl.xpath('./dd/a[@href]')
            dates = dl.xpath('./dt')
            if len(links) != 1 or len(dates) != 1:
                raise RuntimeError('News listing structure changed: ' + url)
            rows.append((links[0].get('href'), links[0].text_content(), day(dates[0].text_content())))
        for a in doc.xpath('//*[@id="post_data"]/a[@href]'):
            titles = a.xpath('.//span[' + CLASS % 'title' + ']')
            dates = a.xpath('.//span[' + CLASS % 'data' + ']')
            if len(titles) != 1 or len(dates) != 1:
                raise RuntimeError('Category listing structure changed: ' + url)
            rows.append((a.get('href'), titles[0].text_content(), day(dates[0].text_content())))
        if not rows:
            raise RuntimeError('Required listing empty: ' + url)
        for u, t, d in rows:
            add(urljoin(url, u), t, d, url)
        evidence['sources'].append({'url': url, 'listed': len(rows)})

    def content(doc, url, static=False):
        titles = doc.xpath('//*[@id="page_cont"]//h1')
        if len(titles) != 1 or not norm(titles[0].text_content()):
            raise RuntimeError('Official page heading missing: ' + url)
        title = norm(titles[0].text_content())
        dates = doc.xpath('//*[@id="p_main"]/p[' + CLASS % 'post_day' + ']')
        date = day(dates[0].text_content()) if len(dates) == 1 else None
        if not static and not date:
            raise RuntimeError('Article date missing: ' + url)
        bodies = doc.xpath('//*[@id="p_main"]' if static else '//*[@id="p_main"]/div[' + CLASS % 'post_box' + ']')
        if len(bodies) != 1:
            raise RuntimeError('Official body structure changed: ' + url)
        body = copy.deepcopy(bodies[0])
        for e in body.xpath('.//script|.//style|.//noscript|.//iframe|.//*[@id="ank_info"]|.//*[@class="ank_list"]'):
            e.drop_tree()
        links = []
        for a in body.xpath('.//a[@href]'):
            target = urljoin(url, a.get('href'))
            p = urlparse(target)
            if p.scheme in ('https', 'http') and not p.username and not p.password:
                label = norm(a.text_content()) or norm(' '.join(a.xpath('.//img/@alt')))
                links.append({'url': target, 'label': label})
        images = []
        for img in body.xpath('.//img[@src or @data-src]'):
            target = urljoin(url, img.get('data-src') or img.get('src'))
            if urlparse(target).scheme in ('https', 'http'):
                record = {'url': target, 'alt': norm(img.get('alt'))}
                if record not in images:
                    images.append(record)
        text = norm(body.text_content())
        if not text and not images and not links:
            raise RuntimeError('Empty official body: ' + url)
        semantic = {'text': text, 'links': links, 'images': images}
        digest = hashlib.sha256(json.dumps(semantic, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        return {'url': url, 'title': title, 'date': date, 'date_basis': 'official individual page date' if date else 'undated official permanent page; pubDate omitted',
                'body': text, 'links': links, 'images': images, 'body_sha256': digest, 'static': static}

    try:
        discover(BASE, fetch(BASE))
        roots = {}
        for path in ROOTS:
            u = BASE + path
            doc = fetch(u)
            roots[path] = doc
            discover(u, doc)
            listing(u, doc)
        # Expand the official category links, never invent page-number URLs.
        # Two older pages retain recent calls which have left the first twelve.
        for path in ['blog/category/info-prompt/', 'blog/category/info-gyousei/', 'blog/category/topics/']:
            root = roots[path]
            pages = root.xpath('//div[' + CLASS % 'wp-pagenavi' + ']//a[@href]/@href')
            seen = set()
            for target in pages:
                u = safe(urljoin(BASE + path, target))
                match = re.search(r'/page/(\d+)/?$', u)
                if match and int(match.group(1)) in (2, 3) and u not in seen:
                    seen.add(u)
                    listing(u, fetch(u))
        # Static business pages contain direct support schemes, tender documents
        # and qualification applications which need not become blog posts.
        static_urls = set()
        for a in roots['residency/'].xpath('//*[@id="p_main"]//a[@href]'):
            target = urljoin(BASE, a.get('href'))
            if urlparse(target).netloc != HOST:
                continue
            u = safe(target)
            if re.search(r'/residency/sangyou/[^/]+/$', u) or ('優遇制度' in a.text_content()):
                static_urls.add(u)
        agreement = BASE + 'politics/agreement/'
        doc = fetch(agreement)
        discover(agreement, doc)
        for a in doc.xpath('//*[@id="p_main"]//a[@href]'):
            u = safe(urljoin(agreement, a.get('href')))
            if u.startswith(agreement) and u != agreement:
                static_urls.add(u)
        if len(static_urls) < 10:
            raise RuntimeError('Business/contract scope unexpectedly reduced')
        static_rows = []
        for u in sorted(static_urls):
            doc = fetch(u)
            discover(u, doc)
            static_rows.append(content(doc, u, static=True))
            # Permanent pages can advertise news posts absent from current lists.
            for a in doc.xpath('//*[@id="p_main"]//a[@href]'):
                target = urljoin(u, a.get('href'))
                if urlparse(target).netloc == HOST and re.search(r'/blog/(?!category/).*/\d+/$', target):
                    add(target, a.text_content(), None, u)
        evidence['candidates'] = list(candidates.values())

        def article(row):
            result = content(fetch(row['url']), row['url'])
            result['listings'] = row['listings']
            for listing_row in row['listings']:
                if listing_row['date'] and listing_row['date'] != result['date']:
                    raise RuntimeError('Listing/article date mismatch: ' + row['url'])
                if norm(listing_row['title']) != result['title']:
                    with lock:
                        evidence['title_differences'].append({'url': row['url'], 'listing': listing_row['title'], 'article': result['title']})
            return result

        with ThreadPoolExecutor(max_workers=3) as pool:
            articles = list(pool.map(article, candidates.values()))
        if len(articles) < 40:
            raise RuntimeError('Unexpectedly few dated posts')
        evidence['articles'] = sorted(articles, key=lambda row: (row['date'], row['url']), reverse=True)
        evidence['static_pages'] = static_rows
        rows = evidence['articles'][:100] + static_rows
        if len({row['url'] for row in rows}) != len(rows):
            raise RuntimeError('Duplicate RSS article URL')
        evidence['output_urls'] = [row['url'] for row in rows]
        rss = Element('rss', version='2.0')
        ch = SubElement(rss, 'channel')
        SubElement(ch, 'title').text = TITLE
        SubElement(ch, 'link').text = BASE + 'residency/'
        SubElement(ch, 'description').text = '伊佐市の農林業・商工観光・募集・行政新着・入札契約情報。日付のない常設事業者ページは更新内容を識別し、配信日を付けず収録。'
        for row in rows:
            item = SubElement(ch, 'item')
            SubElement(item, 'title').text = row['title']
            SubElement(item, 'link').text = row['url']
            guid = row['url'] + ('#content-' + row['body_sha256'] if row['static'] else '')
            SubElement(item, 'guid', isPermaLink='false' if row['static'] else 'true').text = guid
            if row['date']:
                SubElement(item, 'pubDate').text = format_datetime(datetime.fromisoformat(row['date']))
            from html import escape
            desc = '<p>' + escape(row['body'][:3000]) + '</p>'
            for link in row['links']:
                desc += '<p><a href="' + escape(link['url'], quote=True) + '">' + escape(link['label'] or link['url']) + '</a></p>'
            if not row['body']:
                for img in row['images']:
                    desc += '<p><img src="' + escape(img['url'], quote=True) + '" alt="' + escape(img['alt'], quote=True) + '"></p>'
            SubElement(item, 'description').text = desc
        temp = Path(OUTPUT + '.tmp')
        ElementTree(rss).write(temp, encoding='utf-8', xml_declaration=True)
        temp.replace(OUTPUT)
        evidence['status'] = 'success'
        print(json.dumps({'status': 'success', 'sources': len(evidence['sources']), 'dated_articles': len(articles), 'undated_business_pages': len(static_rows), 'output_items': len(rows), 'requests': len(evidence['requests']), 'title_differences': len(evidence['title_differences']), 'rss_sha256': hashlib.sha256(Path(OUTPUT).read_bytes()).hexdigest()}))
    except Exception as error:
        evidence.update(status='failed', error=repr(error))
        raise
    finally:
        if '--diagnostic-out' in sys.argv:
            p = Path(sys.argv[sys.argv.index('--diagnostic-out') + 1])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
        if '--diagnostic-log' in sys.argv:
            print('ISA_EVIDENCE_ZLIB_BASE64=' + base64.b64encode(zlib.compress(json.dumps(evidence, ensure_ascii=False).encode())).decode())


if __name__ == '__main__':
    main()
