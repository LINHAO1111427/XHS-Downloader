"""Visible, account-bound Chrome collection. Reuses the project's page collector.

Like the local Taobao publisher: normal Chrome process -> local CDP -> durable
account profile -> visible controls -> observed result. No generated content.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from threading import Event
import time
from urllib.parse import urlsplit, parse_qs
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from viral_browser import BrowserDiscoveryClient
from viral_notes import PlatformError, normalize_note, parse_count, follower_count
from discovery_adapters import attached_products, comment_rows

DEFAULT_OUT = ROOT / 'DockerData/creative-brain/fragrance-media-20261005/browser-collection-20261008'
OWNER = '4701b875c5224e8ca1f69be64221773e'
SPACE = 'bd24d68a50684a45ab397b42f72fc188'
KEYWORDS = ['无火香薰', '柑橘香薰', '藤条香薰', '茶香 香薰', '无火香薰 礼物']
METHOD_IDS = [
    'document-5de0f2870ec9bbf0e7a15b9b0ff0b46b39a4c441be2997814d86db2d4ac08cbb',
    'document-ffe98b9bace1dc27ce340758b6629d786da45924c9e89c69707e632847bb0ba9',
    'user-creative-framework-three-levels-20261003',
    'user-creative-brain-framework-20261002',
]


def knowledge_plan(out, args):
    """Read the running data store before browser work, retaining exact sources."""
    code = '''import sqlite3,json,sys
ids=json.load(sys.stdin)
c=sqlite3.connect('file:/data/knowledge.db?mode=ro',uri=True);c.row_factory=sqlite3.Row
rows=[dict(x) for x in c.execute("select * from knowledge_entries where active=1 and (id in ("+','.join('?' for _ in ids)+") or (origin='user_requirement' and (content like '%香薰%' or id='user-local-knowledge-first')))",ids)]
print(json.dumps(rows,ensure_ascii=False))
'''
    result = subprocess.run(['docker','exec','-i','xhs-personal-app-1','python','-c',code],
                            input=json.dumps(METHOD_IDS),text=True,encoding='utf8',capture_output=True)
    if result.returncode:
        raise RuntimeError('Running knowledge.db retrieval failed: ' + result.stderr[-300:])
    rows = json.loads(result.stdout)
    if not set(METHOD_IDS).issubset({x['id'] for x in rows}):
        raise RuntimeError('Required local collection methods are missing or inactive')
    plan = {'retrieved_at':time.time(),'database':'/data/knowledge.db',
            'method_ids':METHOD_IDS,'sources':rows,
            'keywords':args.keywords,'sort':args.sort,
            'screening':{'min_likes':args.min_likes,'max_age_days':args.max_age_days,
                         'preferred_followers':1000,'relaxed_followers':5000,
                         'missing_commerce_is_not_zero':True},
            'goal':'以完整原帖、实际封面、评论需求与互动快照补足同类商品选题；跨品只借结构',
            'latest_user_requirement':'先按本地淘宝实现模拟人工采集，基于底层知识库获取有用信息，再分析产出',
            'source_digests':{x['id']:hashlib.sha256(x['content'].encode()).hexdigest() for x in rows}}
    save(out/'knowledge-plan.json',plan)
    return plan


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local_endpoint(port):
    port = int(port)
    if not 1024 <= port <= 65535:
        raise ValueError('Invalid local browser port')
    return f'http://127.0.0.1:{port}'


def chrome_session(account, out):
    """Never attach an arbitrary browser or borrow another application's profile."""
    profile = ROOT / '.install/xhs-human-browser' / hashlib.sha256(account.encode()).hexdigest()[:24]
    profile.mkdir(parents=True, exist_ok=True)
    binding = profile / 'account-binding.json'
    if binding.exists():
        assert json.loads(binding.read_text('utf-8'))['account'] == account
    else:
        save(binding, {'account': account, 'purpose': 'visible_xhs_research'})
    endpoint_file = profile / 'DevToolsActivePort'
    opener = build_opener(ProxyHandler({}))
    if endpoint_file.exists():
        try:
            endpoint = local_endpoint(endpoint_file.read_text().splitlines()[0])
            with opener.open(endpoint + '/json/version', timeout=3) as response:
                assert 'webSocketDebuggerUrl' in json.load(response)
            return endpoint, profile, 'reused'
        except (OSError, ValueError, AssertionError):
            pass
    choices = [Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Google/Chrome/Application/chrome.exe',
               Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Google/Chrome/Application/chrome.exe',
               Path(os.environ.get('LOCALAPPDATA', 'C:/Users/Administrator/AppData/Local')) / 'Google/Chrome/Application/chrome.exe']
    executable = next((p for p in choices if p.is_file()), None)
    if executable is None:
        raise RuntimeError('Installed Google Chrome was not found')
    # Chrome chooses a free port and records it in its own profile.
    command = [str(executable), '--user-data-dir=' + str(profile), '--remote-debugging-port=0',
               '--remote-debugging-address=127.0.0.1', '--no-first-run', '--no-default-browser-check',
               '--start-maximized', 'https://www.xiaohongshu.com/explore']
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        if endpoint_file.exists():
            try:
                endpoint = local_endpoint(endpoint_file.read_text().splitlines()[0])
                with opener.open(endpoint + '/json/version', timeout=2) as response:
                    assert 'webSocketDebuggerUrl' in json.load(response)
                save(out / 'browser-session.json', {'endpoint': endpoint, 'profile': str(profile), 'pid': process.pid,
                     'account_binding': account, 'browser': str(executable), 'browser_launch': 'installed_chrome_then_cdp'})
                return endpoint, profile, 'launched'
            except (OSError, ValueError, AssertionError, IndexError):
                pass
        time.sleep(.25)
    raise RuntimeError('Normal Chrome launched but no local CDP endpoint became available')


class AttachedPageCollector(BrowserDiscoveryClient):
    """Keep the existing click/scroll/detail implementation; replace session ownership."""
    def __init__(self, endpoint, out):
        from playwright.sync_api import sync_playwright
        parts = urlsplit(endpoint)
        if parts.scheme != 'http' or parts.hostname != '127.0.0.1' or parts.username or parts.password:
            raise ValueError('Only an account-bound local Chrome endpoint is supported')
        self.out = Path(out)
        self.stop = Event()
        self.cookies = {}
        self.cookie_saver = None
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.connect_over_cdp(endpoint, timeout=30000)
        self.context = self.browser.contexts[0]
        official = [p for p in self.context.pages if urlsplit(p.url).hostname in {'www.xiaohongshu.com', 'xiaohongshu.com'}]
        self.page = official[0] if official else self.context.new_page()
        self.page.set_default_timeout(15000)
        self.responses = []
        self.challenge = ''
        self.search_cache = {}
        self.search_exhausted = set()
        self.note_keywords = {}
        self.search_cards = {}
        self.current_keyword = None
        self.last_action = 0.0
        self.closed = False
        self._owns_profile = False
        self.authenticated = False
        self.observed_identity = None
        self.active_note = None
        self.observed_searches = []
        self.note_comments = {}
        self.sort_evidence = {}
        self.context.on('response', self._capture_response)

    def _capture_response(self, response):
        super()._capture_response(response)
        parts = urlsplit(response.url)
        if parts.hostname in {'edith.xiaohongshu.com', 'www.xiaohongshu.com'}:
            try:
                if parts.path.endswith('/search/notes'):
                    params = response.request.post_data_json
                    self.observed_searches.append({k:params.get(k) for k in ('keyword','sort','page')})
                if parts.path.endswith('/comment/page'):
                    nid = (parse_qs(parts.query).get('note_id') or [''])[0]
                    payload = response.json()
                    if nid and payload.get('code',0) == 0:
                        rows = (payload.get('data') or {}).get('comments') or []
                        # Keep the original fields; the adapter also accepts camelCase.
                        rows = [{**x,'likeCount':x.get('like_count',x.get('likeCount')),
                                 'createTime':x.get('create_time',x.get('createTime'))} for x in rows]
                        self.note_comments[nid] = comment_rows(rows,10,xhs=True)
            except Exception:
                pass
        if parts.hostname in {'edith.xiaohongshu.com', 'www.xiaohongshu.com'} and parts.path.endswith('/user/me'):
            try:
                result = response.json(); data = result.get('data') or {}
                uid = data.get('user_id') or data.get('userId')
                if result.get('code', 0) == 0 and data.get('guest') is False and uid:
                    self.authenticated = True
                    self.observed_identity = hashlib.sha256(str(uid).encode()).hexdigest()
                    if self.challenge == 'guest=true':
                        self.challenge = ''
            except Exception:
                pass

    def _check_stop(self):
        if (self.out / 'STOP').exists():
            self.stop.set()
        super()._check_stop()

    def _check_challenge(self):
        super()._check_challenge()
        if self.active_note:
            note_dir = self.out / 'notes' / self.active_note
            title = self.page.locator('#detail-title')
            if title.count() and title.first.is_visible():
                note_dir.mkdir(parents=True, exist_ok=True)
                self.page.screenshot(path=str(note_dir / 'detail-visible.png'), full_page=False)
                (note_dir / 'visible-text.txt').write_text(self.page.locator('body').inner_text(), encoding='utf-8')

    def detail(self, note_id, token):
        self.active_note = note_id
        try:
            return super().detail(note_id, token)
        finally:
            self.active_note = None

    def search(self, keyword, page, search_id):
        marker = len(self.observed_searches)
        new_query = self.current_keyword != keyword
        result = super().search(keyword,page,search_id)
        if page == 2 and not result['items']:
            # A viewport-sized wheel may leave the same DOM cards in place.
            # Scroll a bounded number of times, always through the visible page.
            for _ in range(3):
                self._check_challenge()
                self.page.mouse.wheel(0,900)
                self._pause(1.5,2.5)
                result = super().search(keyword,page,search_id)
                if result['items']:
                    break
        if new_query and getattr(self,'search_sort','latest') == 'general':
            observed = [x for x in self.observed_searches[marker:] if x['keyword'] == keyword]
            if observed and any(x['sort'] != 'general' for x in observed):
                raise PlatformError('页面排序与本次综合搜索不符，已停止',True)
            self.sort_evidence[keyword] = 'general' if observed else 'page_default_unverified'
        for row in result['items']:
            link = self._visible_note_link(row['id'])
            if link:
                row['visible_card'] = link.evaluate('''e => {
                    const p=e.closest('section.note-item');
                    return p ? {title:p.querySelector('.title')?.innerText || '',
                     likes_text:p.querySelector('.count')?.innerText || '',
                     date_text:p.querySelector('.time')?.innerText || ''} : {};
                }''')
        save(self.out/'search-observations.json',self.observed_searches)
        return result

    def close(self):
        if self.closed:
            return
        self.closed = True
        # Disconnect this controller, leaving the normal Chrome/login profile open.
        self.playwright.stop()


def image_urls(raw):
    result = []
    for row in raw.get('image_list') or raw.get('imageList') or []:
        url = row.get('url_default') or row.get('urlDefault') or row.get('url') or row.get('urlPre')
        if not url:
            url = next((x.get('url') for x in row.get('info_list', row.get('infoList', [])) if x.get('url')), None)
        p = urlsplit(url or '')
        if p.scheme in {'https', 'http'} and (p.hostname or '').endswith('.xhscdn.com') and url not in result:
            result.append(url)
    return result


def download_images(item, out):
    """Only download image URLs actually returned by the opened note."""
    files = []; errors = []
    folder = out / 'notes' / item['note_id']; folder.mkdir(parents=True, exist_ok=True)
    opener = build_opener(ProxyHandler({}))
    for index, url in enumerate(item['image_urls'][:12]):
        try:
            request = Request(url, headers={'Referer': 'https://www.xiaohongshu.com/', 'User-Agent': 'Mozilla/5.0'})
            with opener.open(request, timeout=25) as response:
                data = response.read(30 * 1024 * 1024 + 1)
            if len(data) > 30 * 1024 * 1024:
                raise ValueError('Image exceeds 30 MiB')
            from PIL import Image
            import io
            im = Image.open(io.BytesIO(data)); image_format = im.format; im.verify()
            suffix = {'JPEG':'.jpg','PNG':'.png','WEBP':'.webp','GIF':'.gif'}.get(image_format, '.img')
            target = folder / (f'{index+1:02}' + suffix)
            target.write_bytes(data)
            files.append({'index': index+1, 'path': str(target), 'sha256': digest(target), 'bytes': len(data), 'source_url': url})
        except Exception as error:
            errors.append({'index': index+1, 'error_type': type(error).__name__})
    return files, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT / ('knowledge-guided-' + time.strftime('%Y%m%d-%H%M%S')))
    parser.add_argument('--limit', type=int, choices=range(1, 31), default=24)
    parser.add_argument('--per-query', type=int, choices=range(1, 11), default=4)
    parser.add_argument('--login-timeout', type=int, default=1800)
    parser.add_argument('--keywords', nargs='+', default=KEYWORDS)
    parser.add_argument('--sort', choices=['latest','general'], default='general')
    parser.add_argument('--min-likes', type=int, default=100)
    parser.add_argument('--max-age-days', type=int, default=30)
    parser.add_argument('--exclude-collection', nargs='*', type=Path, default=[])
    args = parser.parse_args()
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    status = {'target': '香薰笔记与封面真实资料采集', 'state': 'starting', 'space_id': SPACE,
              'started_at': time.time(), 'collected': 0, 'keywords': args.keywords, 'new_content_generated': False}
    def report(state, **values):
        status.update(state=state, updated_at=time.time(), **values)
        save(out/'status.json', status)
        print(json.dumps(status, ensure_ascii=False), flush=True)
    plan = knowledge_plan(out,args)
    client = None
    run_path = out / 'collection.json'
    run = json.loads(run_path.read_text('utf-8')) if run_path.exists() else {
        'id': uuid4().hex, 'created_at': time.time(), 'items': [], 'errors': [], 'warnings': [],
        'request': {'platform':'xiaohongshu','mode':'search','query':args.keywords[0],
                    'sort':args.sort,'pages':2,'limit':args.limit,'comments':10,
                    'selection':{'preset':'broad','space_id':SPACE,'product':'香薰'}},
        'collection_scope': {'method':'installed_chrome_visible_controls','keywords':args.keywords,'image_text_only':True},
        'collection_host':'host_worker'}
    # Keep resumed snapshots compatible with the application's validated import schema.
    run['request'].pop('access', None)
    run['request']['selection'] = {'preset':'broad','space_id':SPACE,'product':'香薰'}
    if run['request']['sort'] != args.sort:
        raise RuntimeError('Resumed run has a different sort; use a separate output directory')
    run['knowledge_plan_path'] = str(out/'knowledge-plan.json')
    run['knowledge_method_ids'] = plan['method_ids']
    run.setdefault('screened_out',[])
    authors = {}
    try:
        endpoint, profile, mode = chrome_session(OWNER + ':' + SPACE, out)
        client = AttachedPageCollector(endpoint, out)
        client.search_sort = args.sort
        report('opening_login', profile=str(profile), browser_session=mode)
        try:
            client.page.goto('https://www.xiaohongshu.com/explore', wait_until='domcontentloaded', timeout=30000)
        except Exception as error:
            report('navigation_wait', error_type=type(error).__name__)
        deadline = time.monotonic() + args.login_timeout
        reported = False
        while not client.authenticated:
            client._check_stop()
            text = client.page.locator('body').inner_text(timeout=5000)
            if 'ERR_' in text and ('无法访问' in text or "can't be reached" in text):
                client.page.screenshot(path=str(out/'network-error-visible.png'))
                raise RuntimeError('Chrome network error before login: ' + text[-180:])
            if any(x in text for x in ['IP存在风险','安全验证','请完成验证']):
                report('waiting_manual_verification', collected=len(run['items']))
                client.page.screenshot(path=str(out/'login-visible.png'))
                return 3
            if not reported:
                client.page.screenshot(path=str(out/'login-visible.png'))
                (out/'login-visible.txt').write_text(text, encoding='utf-8')
                report('waiting_login', collected=len(run['items']))
                reported = True
                for label in ['登录', '立即登录']:
                    buttons = client.page.get_by_text(label, exact=True)
                    visible = next((buttons.nth(i) for i in range(buttons.count()) if buttons.nth(i).is_visible()), None)
                    if visible:
                        visible.click(timeout=3000)
                        client.page.screenshot(path=str(out/'login-visible.png'))
                        break
            if time.monotonic() >= deadline:
                report('login_timeout', collected=len(run['items']))
                return 2
            client.page.wait_for_timeout(800)
        identity_file = profile / 'observed-account.json'
        if identity_file.exists():
            if json.loads(identity_file.read_text())['identity_hash'] != client.observed_identity:
                report('account_mismatch'); return 4
        else:
            save(identity_file, {'identity_hash':client.observed_identity})
        client.challenge = ''
        report('collecting', collected=len(run['items']), authentication='observed_page_user_response')
        seen = {x['note_id'] for x in run['items']}
        prior_ids = {x['note_id'] for p in args.exclude_collection
                     for x in json.loads(p.read_text('utf8'))['items']}
        for keyword in args.keywords:
            count = sum(x.get('source_query') == keyword for x in run['items'])
            for page_number in (1, 2):
                if count >= args.per_query or len(seen) >= args.limit:
                    break
                data = client.search(keyword, page_number, uuid4().hex[:21])
                client.page.screenshot(path=str(out/f'search-{args.keywords.index(keyword)+1}-{page_number}.png'))
                for row in data.get('items', []):
                    nid = row['id']
                    if nid in seen or nid in prior_ids:
                        continue
                    card = row.get('visible_card',{})
                    card_likes = parse_count(card.get('likes_text'))
                    card_date = client._page_timestamp(card.get('date_text',''))
                    reason = ('card_likes_below_threshold_or_unknown' if args.min_likes and (card_likes is None or card_likes < args.min_likes)
                              else 'card_outside_time_window' if args.max_age_days and card_date and time.time()-card_date > args.max_age_days*86400 else '')
                    if reason:
                        run['screened_out'].append({'note_id':nid,'query':keyword,'reason':reason,'visible_card':card})
                        save(run_path,run)
                        continue
                    try:
                        raw = client.detail(nid, row.get('xsec_token', ''))
                        item = normalize_note(raw, row.get('xsec_token', ''))
                        if not item['title'] or not item['description']:
                            run['warnings'].append({'note_id':nid,'reason':'Incomplete title/body'}); continue
                        if item['note_type'] != 'image_text':
                            run['warnings'].append({'note_id':nid,'reason':'Not an image-text note'}); continue
                        if args.min_likes and (item['likes'] is None or item['likes'] < args.min_likes):
                            run['screened_out'].append({'note_id':nid,'reason':'detail_likes_below_threshold_or_unknown'}); continue
                        if args.max_age_days and (not item['published_at'] or not 0 <= time.time()-item['published_at'] <= args.max_age_days*86400):
                            run['screened_out'].append({'note_id':nid,'reason':'detail_date_outside_window_or_unknown'}); continue
                        if not any(word in item['title'] + item['description'] for word in ['香薰','香氛','柑橘','扩香']):
                            run['warnings'].append({'note_id':nid,'reason':'Not relevant to fragrance'}); continue
                        products = attached_products(raw)
                        urls = image_urls(raw)
                        author_id = item.get('author_id')
                        if args.min_likes and author_id and author_id not in authors:
                            try:
                                author = client.author(author_id)
                                authors[author_id] = follower_count(author)
                                save(out/'authors'/f'{author_id}.json',{'observed_at':time.time(),'data':author})
                            except PlatformError as error:
                                if error.fatal: raise
                                authors[author_id] = None
                        comments = client.note_comments.get(nid,[])
                        item.update(platform='xiaohongshu',kind='note',body=item.pop('description'),
                          source='host_visible_browser_search',source_key='xiaohongshu:note:'+nid,
                          source_query=keyword,collected_at=time.time(),products=products,image_urls=urls,
                          cover_url=urls[0] if urls else '',collection_access='authenticated',followers=authors.get(author_id),
                          add_to_cart=None,orders=None,comment_items=comments,comments_scope='页面加载的首屏评论样本' if comments else '未取得评论正文',
                          body_scope='opened_note_detail_text',full_image_set_observed=False,
                          mounted_product_evidence={'status':'observed' if products else 'missing','source_field':'opened_note_detail'},
                          knowledge_method_ids=plan['method_ids'],sort_observed=client.sort_evidence.get(keyword,args.sort),
                          screening_evidence={'min_likes':args.min_likes,'max_age_days':args.max_age_days,'visible_card':card})
                        files, errors = download_images(item, out)
                        item.update(local_images=files,image_download_errors=errors)
                        item['full_image_set_observed'] = bool(urls) and len(files) == len(urls)
                        save(out/'notes'/nid/'source.json', {'raw_note':raw,'normalized':item})
                        run['items'].append(item);seen.add(nid);count += 1
                        run['finished_at'] = time.time();run['state'] = 'partial'
                        save(run_path, run)
                        report('collecting', collected=len(seen), current_keyword=keyword, last_title=item['title'])
                        if count >= args.per_query or len(seen) >= args.limit:
                            break
                    except PlatformError as error:
                        run['errors'].append({'note_id':nid,'message':str(error)})
                        save(run_path,run)
                        if error.fatal:
                            raise
                if not data.get('has_more'):
                    break
        run.update(finished_at=time.time(), state='partial' if run['errors'] else 'success')
        save(run_path, run)
        snapshot = {'format':'xhs-host-discovery-v2','id':run['id'],'owner_id':OWNER,
                    'schedule':'用户在场香薰专项采集','runs':[run]}
        save(out/'import-snapshot.json',snapshot)
        if run['items']:
            result = subprocess.run(['docker','exec','-i','xhs-personal-app-1','python','-c',
                (ROOT/'scripts/host_discovery_bridge.py').read_text('utf-8')],
                input=json.dumps(snapshot,ensure_ascii=False),text=True,encoding='utf-8',capture_output=True)
            save(out/'import-result.json',{'exit_status':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
            if result.returncode:
                report('collected_import_pending', collected=len(seen));return 5
        report('completed',collected=len(seen),image_files=sum(len(x.get('local_images',[])) for x in run['items']))
        return 0
    except Exception as error:
        if client:
            save(out/'sort-trace.json',getattr(client,'sort_trace',[]))
            try:client.page.screenshot(path=str(out/'failure-visible.png'))
            except Exception:pass
        run.update(finished_at=time.time(),state='partial' if run['items'] else 'failed')
        run['errors'].append({'type':type(error).__name__,'message':str(error)[:400]})
        save(run_path,run)
        report('stopped',collected=len(run['items']),error_type=type(error).__name__,error=str(error)[:400])
        return 1
    finally:
        if client:
            client.close()


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
