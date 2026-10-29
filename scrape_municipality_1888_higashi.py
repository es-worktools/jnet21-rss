"""East village: official news and complete reviewed business category scope.
Every discovered article must resolve; never discard a failed/404 article.
"""
import hashlib, json, re, sys, threading
from html import escape
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen
from xml.etree.ElementTree import Element, SubElement, ElementTree
from lxml import html

HOST = 'www.vill.higashi.okinawa.jp'
BASE = 'https://' + HOST + '/'
TITLE = '1888_【GH】沖縄県東村 新着情報'
OUTPUT = 'municipality-1888-higashi.xml'
JST = timezone(timedelta(hours=9))
SCOPE = ['oshirase', 'boshuu', 'sangyo_shigoto', 'hojokin_joseikin', 'boshuosagasu']

def norm(s):
    return re.sub(r'\s+', ' ', s or '').strip()

def safe(url):
    p = urlparse(url)
    if p.scheme not in ('https', 'http') or p.netloc != HOST or p.username or p.password:
        raise RuntimeError('Unexpected official URL: ' + url)
    return urlunparse(('https', HOST, p.path, p.params, p.query, ''))

def parse_article(raw, row):
    doc = html.fromstring(raw)
    titles = doc.xpath('//*[@id="contents"]/h1')
    dates = doc.xpath('//*[@id="contents"]//p[contains(concat(" ",normalize-space(@class)," ")," update ")]')
    bodies = doc.xpath('//*[@id="contents-in"]')
    if len(titles) != 1 or len(dates) != 1 or len(bodies) != 1:
        raise RuntimeError('Article structure changed: ' + row['url'])
    title = norm(titles[0].text_content())
    if title != row['title']:
        if row.get('json_dates'):
            raise RuntimeError('Official JSON/title mismatch: ' + row['url'])
        # HTML category links can use abbreviated labels. The individual
        # official H1 is the article title; retain the label as evidence.
        row = dict(row, listing_label=row['title'])
    match = re.search(r'更新日[：:]\s*(\d{4})年(\d{1,2})月(\d{1,2})日', norm(dates[0].text_content()))
    if not match:
        raise RuntimeError('Official update date missing: ' + row['url'])
    date = datetime(*map(int, match.groups()), tzinfo=JST)
    if date > datetime.now(JST):
        raise RuntimeError('Future update date: ' + row['url'])
    body_node = bodies[0]
    for element in body_node.xpath('.//script|.//style|.//aside|.//*[contains(concat(" ",normalize-space(@class)," ")," toiawase ")]'):
        element.drop_tree()
    body = norm(body_node.text_content())
    image_only = not bool(body)
    images = []
    if image_only:
        for img in body_node.xpath('.//img[@src]'):
            images.append({'url': safe(urljoin(row['url'], img.get('src'))), 'alt': norm(img.get('alt'))})
        if not images:
            raise RuntimeError('Official article body empty: ' + row['url'])
        body = '画像本文：' + ' / '.join(img['alt'] or '掲載画像' for img in images)
    canonical = doc.xpath('//link[@rel="canonical"]/@href')
    canonical = safe(urljoin(row['url'], canonical[0])) if len(canonical) == 1 else row['url']
    return dict(row, title=title, date=date.isoformat(), date_basis='official individual page update date (date only, JST)', body=body, image_only=image_only, images=images, canonical_url=canonical)

def collect(evidence):
    lock = threading.Lock()
    requests = []
    evidence['requests'] = requests
    candidates = {}
    visited = set()
    def fetch(url):
        url = safe(url)
        rec = {'url': url, 'checked_at': datetime.now(JST).isoformat()}
        with lock:
            if len(requests) >= 400:
                raise RuntimeError('Reviewed request bound exceeded')
            requests.append(rec)
        try:
            with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=30) as response:
                rec.update(status=response.status, final_url=safe(response.url))
                raw = response.read()
            rec.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            return raw
        except Exception as error:
            rec.update(status=getattr(error, 'code', None), error=repr(error))
            raise
    def get_json(url):
        data = json.loads(fetch(url))
        if not isinstance(data, list):
            raise RuntimeError('Official JSON schema changed')
        return data
    def add(url, title, source, published=None):
        url = safe(url)
        if not norm(title):
            raise RuntimeError('Empty official title')
        row = candidates.setdefault(url, {'url': url, 'title': norm(title), 'sources': [], 'json_dates': []})
        if row['title'] != norm(title):
            raise RuntimeError('Conflicting official title: ' + url)
        if source not in row['sources']:
            row['sources'].append(source)
        if published and published not in row['json_dates']:
            row['json_dates'].append(published)
    def html_category(url, depth):
        if depth > 10:
            raise RuntimeError('Category depth changed')
        url = safe(url)
        if url in visited:
            return
        visited.add(url)
        doc = html.fromstring(fetch(url))
        pages = doc.xpath('//*[@id="contents-in"]//li[contains(concat(" ",normalize-space(@class)," ")," page ")]/a[@href]')
        dirs = doc.xpath('//*[@id="contents-in"]//li[contains(concat(" ",normalize-space(@class)," ")," dir ")]/a[@href]')
        if not pages and not dirs:
            # Some official folder shortcuts point to a content page (for example,
            # the cat-adoption page), whose body is not a child-page list.
            titles = doc.xpath('//*[@id="contents"]/h1')
            body = doc.xpath('//*[@id="contents-in"]/div[contains(concat(" ",normalize-space(@class)," ")," free-layout-area ")]')
            if len(titles) == 1 and body and norm(' '.join(e.text_content() for e in body)):
                dates = doc.xpath('//*[@id="contents"]//p[contains(concat(" ",normalize-space(@class)," ")," update ")]')
                if not dates:
                    # An undated category is a source, not an RSS article. Follow
                    # the actual article links within its body instead.
                    links = [a for b in body for a in b.xpath('.//a[@href]') if re.search(r'/\d+\.html$', urljoin(url, a.get('href')))]
                    if not links:
                        raise RuntimeError('Undated category has no article links: ' + url)
                    evidence.setdefault('undated_category_pages', []).append({'url': url, 'title': norm(titles[0].text_content()), 'article_links': len(links)})
                    for a in links:
                        add(urljoin(url, a.get('href')), a.text_content(), url)
                    return
                add(url, titles[0].text_content(), url)
                evidence.setdefault('content_category_pages', []).append(url)
                return
            raise RuntimeError('Category unexpectedly empty: ' + url)
        for a in pages:
            add(urljoin(url, a.get('href')), a.text_content(), url)
        for a in dirs:
            html_category(urljoin(url, a.get('href')), depth + 1)
    def nodes(data, source, depth=0):
        if depth > 12:
            raise RuntimeError('Category depth changed')
        for node in data:
            if 'is_category_index' not in node:
                raise RuntimeError('Official JSON schema changed')
            if node.get('is_keitai_page'):
                continue
            if not node['is_category_index']:
                add(node['url'], node['page_name'], source, node.get('publish_datetime'))
                continue
            if 'child_pages' in node:
                nodes(node['child_pages'], source, depth + 1)
            elif node.get('child_pages_count', 0) > 0:
                url = safe(node['url'])
                if node.get('is_shortcut') and not url.endswith('/index.html'):
                    html_category(url, depth + 1)
                else:
                    tree = url[:-5] + '.tree.json'
                    if tree not in visited:
                        visited.add(tree)
                        children = get_json(tree)
                        if not children:
                            evidence.setdefault('json_empty_html_fallbacks', []).append({'json': tree, 'html': url})
                            html_category(url, depth + 1)
                        else:
                            nodes(children, tree, depth + 1)
    root = get_json(BASE + 'index.tree.json')
    evidence['scope'] = []
    for scope in SCOPE:
        expected = BASE + scope + '/index.html'
        matches = [node for node in root if safe(node['url']) == expected]
        if len(matches) != 1 or not matches[0].get('child_pages'):
            raise RuntimeError('Required scope missing: ' + scope)
        nodes(matches, BASE + 'index.tree.json#' + scope)
        evidence['scope'].append({'name': scope, 'url': expected, 'listed_children': len(matches[0]['child_pages'])})
    nodes(get_json(BASE + 'index.update.json'), BASE + 'index.update.json')
    # Independently compare both full HTML lists with the root JSON, including old articles.
    for scope in ['oshirase', 'boshuu']:
        url = BASE + scope + '/index.html'
        doc = html.fromstring(fetch(url))
        links = doc.xpath('//*[@id="contents-in"]//li[contains(concat(" ",normalize-space(@class)," ")," page ")]/a[@href]')
        expected = {safe(urljoin(url, a.get('href'))) for a in links}
        actual = {u for u, r in candidates.items() if BASE + 'index.tree.json#' + scope in r['sources']}
        if not expected or expected != actual:
            raise RuntimeError('HTML/JSON listing disagreement: ' + scope)
    evidence['candidates'] = list(candidates.values())
    def article(row):
        return parse_article(fetch(row['url']), row)
    rows, errors = [], []
    def checked(row):
        try:
            return article(row)
        except Exception as error:
            with lock:
                errors.append({'url': row['url'], 'error': repr(error)})
            return None
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(checked, candidates.values()))
    evidence['article_errors'] = errors
    evidence['verified_articles'] = [r for r in rows if r]
    if errors:
        raise RuntimeError(f'{len(errors)} articles failed; no articles silently excluded; RSS preserved')
    # RSS uses the canonical URLs explicitly advertised by the official site.
    # Verify those URLs directly too; a working shortcut alone is insufficient.
    missing_canonical = {}
    for row in rows:
        key = row['canonical_url']
        if key not in candidates:
            missing_canonical.setdefault(key, dict(row, url=key))
    with ThreadPoolExecutor(max_workers=3) as pool:
        canonical_rows = list(pool.map(checked, missing_canonical.values()))
    evidence['canonical_checks'] = [r for r in canonical_rows if r]
    if errors:
        raise RuntimeError('Canonical URL verification failed; RSS preserved')
    by_url = {r['url']: r for r in rows + canonical_rows}
    for row in rows:
        canonical = by_url[row['canonical_url']]
        if canonical['canonical_url'] != row['canonical_url'] or (row['title'], row['date'], row['body'], row['images']) != (canonical['title'], canonical['date'], canonical['body'], canonical['images']):
            raise RuntimeError('Canonical content differs: ' + row['url'])
    merged = {}
    for row in rows:
        key = row['canonical_url']
        if key in merged:
            prev = merged[key]
            if (prev['title'], prev['date'], prev['body'], prev['images']) != (row['title'], row['date'], row['body'], row['images']):
                raise RuntimeError('Conflicting canonical article: ' + key)
            prev['aliases'].append(row['url'])
            prev['sources'] = sorted(set(prev['sources'] + row['sources']))
        else:
            merged[key] = dict(row, url=key, aliases=[row['url']])
    allrows = sorted(merged.values(), key=lambda r: (r['date'], r['url']), reverse=True)
    if len(allrows) < 20:
        raise RuntimeError('Too few articles; RSS preserved')
    evidence['all_articles'] = allrows
    evidence['output_articles'] = allrows[:100]
    return allrows[:100]

def main():
    evidence = {'checked_at': datetime.now(JST).isoformat(), 'status': 'running'}
    try:
        rows = collect(evidence)
        rss = Element('rss', version='2.0')
        channel = SubElement(rss, 'channel')
        SubElement(channel, 'title').text = TITLE
        SubElement(channel, 'link').text = BASE
        SubElement(channel, 'description').text = TITLE + '（新着・お知らせ・募集・産業仕事・補助金を統合）'
        for row in rows:
            item = SubElement(channel, 'item')
            SubElement(item, 'title').text = row['title']
            SubElement(item, 'link').text = row['url']
            SubElement(item, 'guid', isPermaLink='true').text = row['url']
            SubElement(item, 'pubDate').text = format_datetime(datetime.fromisoformat(row['date']))
            description = escape(row['body'][:1500])
            for img in row['images']:
                description += '<p><img src="' + escape(img['url'], quote=True) + '" alt="' + escape(img['alt'], quote=True) + '"></p>'
            SubElement(item, 'description').text = description
        out = Path(OUTPUT)
        temp = Path(OUTPUT + '.tmp')
        ElementTree(rss).write(temp, encoding='utf-8', xml_declaration=True)
        temp.replace(out)
        evidence['status'] = 'success'
        print(json.dumps({'items': len(rows), 'candidates': len(evidence['candidates']), 'canonical_articles': len(evidence['all_articles']), 'requests': len(evidence['requests'])}))
    except Exception as error:
        evidence.update(status='failed', error=repr(error))
        raise
    finally:
        if '--diagnostic-out' in sys.argv:
            dest = Path(sys.argv[sys.argv.index('--diagnostic-out') + 1])
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(evidence, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
