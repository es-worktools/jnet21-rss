"""1014 production integration. Explicit modes; fail closed; retain all history."""
import argparse
import copy
import hashlib
import html as escaping
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag, unquote
from urllib.request import Request, build_opener, HTTPRedirectHandler
from xml.etree import ElementTree as ET
from lxml import html

OFFICIAL = 'https://www.vill.higashishirakawa.gifu.jp/'
SIMPLE = 'http://www.50913.ne.jp/higashishirakawa/index.html'
WELFARE = urljoin(SIMPLE, 'sonfuku.html')
JST = timezone(timedelta(hours=9))
PRODUCTION_NAME = 'municipality-1014-higashishirakawa.xml'
DATE_TITLE = re.compile(r'^(20\d{2})\.(\d{1,2})\.(\d{1,2})\s*(.+)$')

def norm(text):
    return re.sub(r'\s+', ' ', text or '').strip()

def match_title(text):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', text or ''))

def checked_url(url):
    decoded = url
    for _ in range(4):
        decoded = unquote(decoded)
    if any(x in decoded for x in ('\\', '\r', '\n', '\t')) or '..' in urlparse(decoded).path:
        raise RuntimeError('Unsafe URL path')
    p = urlparse(url)
    if p.username or p.password or p.port or p.params or p.query:
        raise RuntimeError('Unexpected URL components: ' + url)
    if p.scheme == 'https' and p.netloc == 'www.vill.higashishirakawa.gifu.jp':
        return url
    if p.scheme == 'http' and p.netloc == 'www.50913.ne.jp' and p.path.startswith('/higashishirakawa/') and '..' not in p.path:
        return url
    raise RuntimeError('Unapproved source: ' + url)

class RestrictedRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        checked_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

class Fetcher:
    def __init__(self, evidence):
        self.evidence = Path(evidence)
        self.evidence.mkdir(parents=True, exist_ok=True)
        self.manifest = []
        self.opener = build_opener(RestrictedRedirect())

    def get(self, url):
        checked_url(url)
        plain_url = urldefrag(url)[0]
        with self.opener.open(Request(plain_url, headers={'User-Agent': 'Mozilla/5.0 JNet21-RSS-validation'}), timeout=40) as r:
            checked_url(r.url)
            body = r.read(8_000_001)
            if len(body) > 8_000_000:
                raise RuntimeError('Response too large')
            if r.status != 200:
                raise RuntimeError('Unexpected status')
            entry = dict(url=url, final_url=r.url, status=r.status, size=len(body), sha256=hashlib.sha256(body).hexdigest(), checked_at=datetime.now(JST).isoformat(), content_type=r.headers.get('Content-Type'))
        name = hashlib.sha256(plain_url.encode()).hexdigest()[:16] + '.bin'
        (self.evidence / name).write_bytes(body)
        entry['file'] = name
        self.manifest.append(entry)
        (self.evidence / 'manifest.json').write_text(json.dumps(self.manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        return body

def authority(body):
    doc = html.fromstring(body)
    links = [urljoin(OFFICIAL, a) for a in doc.xpath('//a/@href')]
    if SIMPLE not in links or 'メンテナンス' not in doc.text_content():
        raise RuntimeError('Current official maintenance notice does not authorize the simple site; manual review required')

def section_for(doc, fragment):
    anchors = doc.xpath('//a[@name=$key or @id=$key]', key=fragment)
    if len(anchors) != 1:
        raise RuntimeError('Missing/ambiguous article anchor: ' + fragment)
    for parent in anchors[0].iterancestors('div'):
        if 'hpb-lay-photo1' in parent.get('class', '').split():
            return parent
    raise RuntimeError('Article section changed')

def parse_index(body):
    doc = html.fromstring(body)
    if '東白川村公式ホームページ(簡易版)' not in doc.xpath('string(//title)'):
        raise RuntimeError('Unexpected simple page identity')
    candidates = []
    seen = set()
    # Date-prefixed list entries, never event dates from headings or PDF names.
    notice_lists = doc.xpath('//div[@id="Layer9"]/ul')
    if len(notice_lists) != 1:
        raise RuntimeError('Dated notice list layout changed')
    entries = notice_lists[0].xpath('./li')
    if not entries or any(len(li.xpath('./a[@href]')) != 1 for li in entries):
        raise RuntimeError('Notice row missing a unique article link')
    for a in notice_lists[0].xpath('./li/a[@href]'):
        title = norm(a.text_content())
        m = DATE_TITLE.fullmatch(title)
        if not m:
            raise RuntimeError('Undated/changed notice entry: ' + title)
        y, month, day = map(int, m.groups()[:3])
        date = datetime(y, month, day, tzinfo=JST)
        if date > datetime.now(JST):
            raise RuntimeError('Future publication date requires review')
        url = checked_url(urljoin(SIMPLE, a.get('href')))
        p = urlparse(url)
        if urldefrag(url)[0] != SIMPLE or not p.fragment:
            raise RuntimeError('Notice URL layout changed')
        if url in seen:
            raise RuntimeError('Duplicate notice URL')
        seen.add(url)
        section = section_for(doc, p.fragment)
        headings = section.xpath('.//td[contains(@class,"hpb-subh02-cell1")]')
        if len(headings) != 1 or match_title(m.group(4)) not in match_title(headings[0].text_content()):
            raise RuntimeError('Notice title does not match article section')
        pdfs = [checked_url(urljoin(SIMPLE, u)) for u in section.xpath('.//a/@href') if urlparse(u).path.lower().endswith('.pdf')]
        text = norm(section.text_content())
        if not pdfs or len(text) < 50:
            raise RuntimeError('Article body/attachment missing')
        candidates.append(dict(title=norm(m.group(4)), url=url, date=date.isoformat(), date_source='official dated notice list', body=text, pdfs=sorted(set(pdfs))))
    if not candidates:
        raise RuntimeError('No dated notices; preserve previous feed')
    local_pages = sorted(set(checked_url(urljoin(SIMPLE, u)) for u in doc.xpath('//a/@href') if u.lower().endswith('.html') and not u.startswith(('mailto:', 'tel:'))))
    if local_pages != [WELFARE]:
        raise RuntimeError('Simple site page inventory changed; review coverage')
    return candidates

def parse_welfare(body):
    doc = html.fromstring(body)
    headings = [norm(x.text_content()) for x in doc.xpath('//td[contains(@class,"hpb-subh02-cell1")]')]
    if '戸籍の郵送請求' not in headings:
        raise RuntimeError('Welfare page structure changed')
    pdfs = sorted(set(checked_url(urljoin(WELFARE, u)) for u in doc.xpath('//a/@href') if urlparse(u).path.lower().endswith('.pdf')))
    if not pdfs:
        raise RuntimeError('Welfare PDF missing')
    return dict(title='戸籍の郵送請求', url=WELFARE, date=None, disposition='reference-only: no publication date, not a dated news notice', pdfs=pdfs)

def description(row):
    links = ''.join('<li><a href="' + escaping.escape(u, quote=True) + '">' + escaping.escape(u.rsplit('/',1)[-1]) + '</a></li>' for u in row['pdfs'])
    return '<p>公式簡易版による暫定監視。掲載範囲は限定されています。</p><p>' + escaping.escape(row['body']) + '</p><ul>' + links + '</ul>'

def merge(baseline_bytes, candidates):
    root = ET.fromstring(baseline_bytes)
    channel = root.find('channel')
    if root.tag != 'rss' or channel is None or channel.findtext('title') != '1014_岐阜県東白川村':
        raise RuntimeError('Unexpected baseline feed identity')
    existing = channel.findall('item')
    if not existing:
        raise RuntimeError('Empty baseline is not safe')
    result = copy.deepcopy(root)
    out = result.find('channel')
    by_guid = {}
    by_title_date = {}
    for item in out.findall('item'):
        guid = item.findtext('guid')
        if not guid or guid in by_guid:
            raise RuntimeError('Missing or duplicate baseline GUID')
        checked_url(item.findtext('link'))
        date = parsedate_to_datetime(item.findtext('pubDate'))
        by_guid[guid] = item
        by_title_date.setdefault((match_title(item.findtext('title')), date.date().isoformat()), []).append(item)
    added, aliases, updated = [], [], []
    for row in candidates:
        date = datetime.fromisoformat(row['date'])
        if date.tzinfo is None:
            raise RuntimeError('Date timezone missing')
        candidates_by_title = by_title_date.get((match_title(row['title']), date.date().isoformat()), [])
        if row['url'] in by_guid:
            item = by_guid[row['url']]
            if match_title(item.findtext('title')) != match_title(row['title']) or parsedate_to_datetime(item.findtext('pubDate')).date() != date.date():
                raise RuntimeError('Existing temporary URL reused for another title/date; review required')
            updated.append(row['url'])
        elif len(candidates_by_title) == 1:
            item = candidates_by_title[0]
            aliases.append(dict(simple_url=row['url'], retained_guid=item.findtext('guid'), title=row['title'], date=date.date().isoformat()))
        elif candidates_by_title:
            raise RuntimeError('Ambiguous title/date match')
        else:
            item = ET.SubElement(out, 'item')
            ET.SubElement(item, 'title').text = row['title']
            ET.SubElement(item, 'link').text = row['url']
            ET.SubElement(item, 'guid', isPermaLink='true').text = row['url']
            ET.SubElement(item, 'pubDate').text = format_datetime(date)
            by_guid[row['url']] = item
            by_title_date.setdefault((match_title(row['title']), date.date().isoformat()), []).append(item)
            added.append({k:v for k,v in row.items() if k != 'body'})
        item.find('link').text = row['url']
        desc = item.find('description')
        if desc is None:
            desc = ET.SubElement(item, 'description')
        desc.text = description(row)
    # Preserve every baseline GUID/date. No truncation during temporary operation.
    for old in existing:
        new = by_guid.get(old.findtext('guid'))
        if new is None or new.findtext('pubDate') != old.findtext('pubDate'):
            raise RuntimeError('Baseline retention failed')
    items = out.findall('item')
    for item in items:
        out.remove(item)
    for item in sorted(items, key=lambda x: parsedate_to_datetime(x.findtext('pubDate')), reverse=True):
        out.append(item)
    out.find('description').text = '1014_岐阜県東白川村 暫定RSS：公式簡易版の掲載情報を補完。通常サイトの全情報は網羅しません。'
    xml = ET.tostring(result, encoding='utf-8', xml_declaration=True)
    if len(ET.fromstring(xml).findall('./channel/item')) < len(existing):
        raise RuntimeError('Output lost baseline items')
    return xml, dict(baseline_count=len(existing), dated_notices=len(candidates), added=added, aliases=aliases, updated=updated, output_count=len(items), preserved_baseline_guids=True)


PUBLIC_RSS = 'https://es-worktools.github.io/jnet21-rss/' + PRODUCTION_NAME
FEED_TITLE = '1014_岐阜県東白川村'
SCOPE = 'Limited to explicitly listed dated notices; not bids, procurement or support-policy coverage'

def digest(data):
    return hashlib.sha256(data).hexdigest()

def public_rss():
    # This trusted endpoint is separate from the restricted municipal source fetcher.
    class PublicRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise RuntimeError('Public RSS redirect requires review')
    with build_opener(PublicRedirect()).open(Request(PUBLIC_RSS, headers={'User-Agent':'JNet21-RSS/1014'}), timeout=40) as r:
        data = r.read(8_000_001)
        if r.status != 200 or len(data) > 8_000_000:
            raise RuntimeError('Public RSS retrieval failed')
    feed_items(data)
    return data

def feed_items(data):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise RuntimeError('DTD/entities forbidden')
    root = ET.fromstring(data)
    channel = root.find('channel')
    if root.tag != 'rss' or channel is None or channel.findtext('title') != FEED_TITLE:
        raise RuntimeError('Unexpected RSS identity')
    items = {}
    for item in channel.findall('item'):
        guid, title, link, date = (item.findtext(k) for k in ('guid','title','link','pubDate'))
        if not guid or guid in items or not title or not date:
            raise RuntimeError('Incomplete/duplicate RSS identity')
        checked_url(guid)
        checked_url(link)
        dt = parsedate_to_datetime(date)
        if dt.tzinfo is None:
            raise RuntimeError('Timezone required')
        items[guid] = item
    if not items:
        raise RuntimeError('Empty RSS is not safe')
    return root, items

def empty_state():
    return dict(schema_version=1, last_mode=None, rss_sha256=None, items=[], temporary={}, reconciliation=[])

def load_state(path, local):
    state = json.loads(Path(path).read_text(encoding='utf-8'))
    if state.get('schema_version') != 1 or not isinstance(state.get('items'),list) or not isinstance(state.get('temporary'),dict) or state.get('last_mode') not in (None,'temporary','normal'):
        raise RuntimeError('Invalid persistent history')
    if state.get('rss_sha256') and digest(local) != state['rss_sha256']:
        raise RuntimeError('Local RSS/history pair mismatch; recover the last complete git commit')
    if not state.get('rss_sha256') and (state['items'] or state['temporary'] or state['last_mode']):
        raise RuntimeError('History without RSS hash is invalid')
    return state

def union_baseline(local, published, state):
    root, local_items = feed_items(local)
    _, published_items = feed_items(published)
    # Persistent full RSS snapshots retain items even if a current feed loses them.
    archived = {}
    if state['items']:
        skeleton = ET.Element('rss',version='2.0')
        ch = ET.SubElement(skeleton,'channel')
        ET.SubElement(ch,'title').text = FEED_TITLE
        for text in state['items']:
            if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
                raise RuntimeError('Unsafe history XML')
            ch.append(ET.fromstring(text))
        _, archived = feed_items(ET.tostring(skeleton))
    merged = dict(local_items)
    for source in (archived, published_items):
        for guid,item in source.items():
            if guid in merged:
                # Formatting of the official date is also retained verbatim.
                for field in ('title','pubDate'):
                    if item.findtext(field) != merged[guid].findtext(field):
                        raise RuntimeError('Conflicting preserved title/date for ' + guid)
            else:
                merged[guid] = copy.deepcopy(item)
    ch = root.find('channel')
    for item in ch.findall('item'): ch.remove(item)
    for item in merged.values(): ch.append(item)
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)

def collect_temporary(fetcher):
    authority(fetcher.get(OFFICIAL))
    rows = parse_index(fetcher.get(SIMPLE))
    ref = parse_welfare(fetcher.get(WELFARE))
    hashes = {}
    for u in sorted(set(u for row in rows+[ref] for u in row['pdfs'])):
        data = fetcher.get(u)
        if not data.startswith(b'%PDF-') or len(data) < 100:
            raise RuntimeError('Invalid PDF response: '+u)
        hashes[u] = digest(data)
    return rows, ref, hashes

def temporary_payload(baseline, state, fetcher):
    rows, ref, hashes = collect_temporary(fetcher)
    seen = set()
    for row in rows:
        key = (match_title(row['title']), row['date'][:10])
        if key in seen:
            raise RuntimeError('Ambiguous dated notice identity')
        seen.add(key)
        prior = state['temporary'].get(row['url'])
        if prior and (prior['title_key'],prior['official_date']) != key:
            raise RuntimeError('Temporary URL reused; manual reconciliation required')
    payload, report = merge(baseline,rows)
    _, out = feed_items(payload)
    now = datetime.now(JST).isoformat()
    for row in rows:
        matches = [i for i in out.values() if i.findtext('link') == row['url']]
        if len(matches) != 1:
            raise RuntimeError('Temporary GUID reconciliation ambiguous')
        item = matches[0]
        guid = item.findtext('guid')
        prior = state['temporary'].get(row['url'])
        if prior and prior['guid'] != guid:
            raise RuntimeError('Persistent GUID changed')
        entry = state['temporary'].setdefault(row['url'],dict(guid=guid,url=row['url'],title_key=match_title(row['title']),official_date=row['date'][:10],first_seen=now,versions=[]))
        version = dict(title=row['title'],body=row['body'],body_sha256=digest(row['body'].encode()),pdfs=[dict(url=u,sha256=hashes[u]) for u in row['pdfs']],rss_pubDate=item.findtext('pubDate'))
        if not entry['versions'] or any(entry['versions'][-1].get(k) != v for k,v in version.items()):
            entry['versions'].append(dict(version,observed_at=now))
    report.update(reference_only=[dict(ref,pdf_hashes={u:hashes[u] for u in ref['pdfs']})],pdfs_verified=hashes,scope=SCOPE,automatic_switchback=False)
    return payload, report

def normal_payload(baseline, state, rows, config):
    root, existing = feed_items(baseline)
    review = config.get('normal_review',{})
    aliases = review.get('articles',{})
    if state['temporary']:
        expected = {e['guid'] for e in state['temporary'].values()}
        if review.get('approved') is not True or not review.get('reviewed_at') or not review.get('coverage_note') or set(aliases) != expected:
            raise RuntimeError('Manual normal-site reconciliation and period coverage approval required')
        mapped = []
        for guid, decision in aliases.items():
            url = decision.get('normal_url')
            if url:
                checked_url(url)
                if not url.startswith(OFFICIAL+'news/detail/') or not decision.get('evidence'):
                    raise RuntimeError('Normal mapping needs verified detail URL and evidence')
                mapped.append(url)
            elif decision.get('retain_temporary') is not True or not decision.get('evidence'):
                raise RuntimeError('Unmatched temporary article needs explicit retention decision')
        if len(mapped) != len(set(mapped)):
            raise RuntimeError('Ambiguous normal URL mapping')
        # A normal GUID from a previous run must never duplicate a temporary GUID.
        for guid,d in aliases.items():
            if d.get('normal_url') in existing and d['normal_url'] != guid:
                raise RuntimeError('Duplicate normal GUID already exists; manual repair required')
        if not state['reconciliation'] or state['reconciliation'][-1] != review:
            state['reconciliation'].append(copy.deepcopy(review))
        for guid,decision in aliases.items():
            if decision.get('normal_url'):
                existing[guid].find('link').text = decision['normal_url']
    reverse = {d['normal_url']:guid for guid,d in aliases.items() if d.get('normal_url')}
    added = []
    source_seen = set()
    for row in rows:
        url = checked_url(row['url'])
        date = datetime.fromisoformat(row['date'])
        title = norm(row['title'])
        if not title or date.tzinfo is None or date > datetime.now(JST) or url in source_seen:
            raise RuntimeError('Invalid normal article identity')
        source_seen.add(url)
        guid = reverse.get(url,url)
        if guid in existing:
            # A recovered normal site's changes never silently alter issued identity/date.
            item = existing[guid]
            if (match_title(item.findtext('title')),parsedate_to_datetime(item.findtext('pubDate')).date()) != (match_title(title),date.date()):
                decision = aliases.get(guid,{})
                if decision.get('accept_identity_difference') is not True:
                    raise RuntimeError('Normal title/date differs; explicit reviewed mapping required')
            continue
        key = (match_title(title),date.date().isoformat())
        for entry in state['temporary'].values():
            if key == (entry['title_key'],entry['official_date']):
                raise RuntimeError('Unmapped normal duplicate of temporary article')
        item = ET.Element('item')
        for tag,value in (('title',title),('link',url),('guid',url),('pubDate',format_datetime(date))):
            ET.SubElement(item,tag,**({'isPermaLink':'true'} if tag=='guid' else {})).text=value
        root.find('channel').append(item)
        existing[guid] = item
        added.append(guid)
    if not rows:
        raise RuntimeError('Empty normal source')
    ch = root.find('channel')
    for item in ch.findall('item'): ch.remove(item)
    for item in sorted(existing.values(),key=lambda i:parsedate_to_datetime(i.findtext('pubDate')),reverse=True):ch.append(item)
    ch.find('description').text=FEED_TITLE+' GitHub generated RSS（暫定期間の記事・履歴を保持）'
    return ET.tostring(root,encoding='utf-8',xml_declaration=True),dict(added=added,output_count=len(existing),automatic_switchback=False)

def stage_pair(output, history, payload, state):
    """Publish only a validated pair; rollback ordinary I/O errors. Git commits both."""
    output, history = Path(output),Path(history)
    if output.resolve()==history.resolve(): raise RuntimeError('Output/history collision')
    _, items = feed_items(payload)
    state['items']=[ET.tostring(i,encoding='unicode') for i in items.values()]
    state['rss_sha256']=digest(payload)
    state_bytes=(json.dumps(state,ensure_ascii=False,indent=2)+'\n').encode()
    paths=(output,history)
    if any(p.is_symlink() for p in paths): raise RuntimeError('Symlink output forbidden')
    previous=[p.read_bytes() if p.exists() else None for p in paths]
    staged=[]
    try:
        for path,data in zip(paths,(payload,state_bytes)):
            path.parent.mkdir(parents=True,exist_ok=True)
            temp=path.with_name(path.name+'.pending')
            temp.write_bytes(data)
            staged.append(temp)
        for temp,path in zip(staged,paths): temp.replace(path)
    except BaseException:
        for path,data in zip(paths,previous):
            if data is None: path.unlink(missing_ok=True)
            else: path.write_bytes(data)
        raise
    finally:
        for temp in staged:temp.unlink(missing_ok=True)

def run(config_path, output, history, evidence, mode=None, fetcher=None, published=None, normal_provider=None):
    config=json.loads(Path(config_path).read_text(encoding='utf-8'))
    selected=mode or config.get('mode')
    if selected not in ('normal','temporary'): raise RuntimeError('Explicit mode required')
    # Output is the current checked-out production RSS, never a frozen fixture.
    local=Path(output).read_bytes()
    state=load_state(history,local)
    published=public_rss() if published is None else published
    baseline=union_baseline(local,published,state)
    if selected=='temporary':
        payload,report=temporary_payload(baseline,state,fetcher or Fetcher(evidence))
    else:
        if normal_provider is None:raise RuntimeError('Normal provider missing')
        payload,report=normal_payload(baseline,state,normal_provider(),config)
    _,old=feed_items(baseline)
    _,new=feed_items(payload)
    for guid,item in old.items():
        if guid not in new or any(item.findtext(k)!=new[guid].findtext(k) for k in ('title','pubDate')):
            raise RuntimeError('Existing GUID/title/official date lost')
    state['last_mode']=selected
    report.update(mode=selected,baseline_count=len(old),output_count=len(new),public_sha256=digest(published))
    stage_pair(output,history,payload,state)
    return report
