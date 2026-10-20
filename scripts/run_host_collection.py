"""Resumable Windows-host collection; import through the live container without restarting it."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Event
from time import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from discovery_adapters import attached_products
from huitun_discovery import CN, HuitunClient
from public_discovery import commerce_observation, load_public_product, public_target, resolve_public_target, note_media
from viral_notes import PlatformError, normalize_note, follower_count
from viral_browser import BrowserDiscoveryClient


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def pending_snapshots(directory):
    return [p for p in sorted(directory.glob('snapshot-*.json'))
            if not p.name.endswith('.imported.json') and not p.with_suffix('.imported.json').exists()]


def plan_products(pairs, known, state, now, maximum):
    """Prefer unseen page IDs. Fresh successes and recent failures are not retried."""
    unique = {}
    for seed in pairs:
        if seed['mode'] != 'product': continue
        try: identity = public_target(seed['url'], 'product')
        except Exception: continue
        if identity not in unique: unique[identity] = dict(seed, identity=identity)
    rows = []
    for identity, seed in unique.items():
        saved = state.get('products', {}).get(identity, {})
        until = saved.get('retry_at', 0)
        if until > now: continue
        key = 'xiaohongshu:product:'+identity
        if known.get(key, 0) > now-86400: continue
        seed['new_page'] = key not in known
        rows.append(seed)
    rows.sort(key=lambda seed: not seed['new_page'])
    return rows[:maximum], len(unique)


def new_run(request, day):
    return {'id': uuid4().hex, 'created_at': time(), 'request': request, 'items': [], 'errors': [], 'warnings': [],
            'collection_scope': {'host_day': day}, 'collection_host': 'host_worker'}


def add_item(run, item):
    item.update(collected_at=time(), source_key=f"{item['platform']}:{item['kind']}:{item['note_id']}")
    if item['source_key'] not in {old['source_key'] for old in run['items']}:
        run['items'].append(item)


def finish(run):
    run.update(finished_at=time(), state=('partial' if run['items'] else 'failed') if run['errors'] else 'success')


def collect_logged_notes(settings, keywords, limit, selection, day, *, interactive=False):
    run = new_run({'platform':'xiaohongshu', 'mode':'search', 'access':'authenticated', 'query':keywords[0],
                   'sort':'latest', 'pages':2, 'limit':limit, 'comments':0, 'selection':selection}, day)
    run['collection_scope']['keywords'] = keywords
    run['collection_scope']['method'] = 'visible_browser_controls'
    if not interactive:
        run['errors'].append('账号搜索已暂停：仅允许人工在场的可见浏览器采集；后台任务不会使用账号 Cookie。')
        finish(run)
        return run
    stop = Event(); client = None
    try:
        client = BrowserDiscoveryClient(settings, stop)
        authors, seen, exhausted = {}, set(), set()
        searches = {word: uuid4().hex[:21] for word in keywords}
        failures = 0
        for page in range(1, 3):
            for word in keywords:
                if word in exhausted: continue
                data = client.search(word, page, searches[word])
                if not data.get('has_more'): exhausted.add(word)
                for row in data.get('items', []):
                    identity = str(row.get('id') or '')
                    token = row.get('xsec_token') or row.get('xsecToken')
                    if len(identity) != 24 or identity in seen: continue
                    seen.add(identity)
                    if len(seen) > 60: return run
                    try:
                        raw = client.detail(identity, token)
                        item = normalize_note(raw, token)
                        assert item['note_id'] == identity
                        item.update(platform='xiaohongshu', kind='note', source='host_visible_browser_search',
                                    body=item.pop('description'), products=attached_products(raw), source_query=word,
                                    comment_items=[], comments_scope='本轮仅采集公开评论计数，未请求评论正文', collection_access='authenticated')
                        uid = item.get('author_id')
                        if uid not in authors:
                            try: authors[uid] = follower_count(client.author(uid)) if uid else None
                            except PlatformError as error:
                                if error.fatal: raise
                                authors[uid] = None
                                run['warnings'].append('一位作者粉丝数暂未取得；保留笔记并标记未知。')
                        item['followers'] = authors[uid]
                        item.update(note_media(raw, item['products']))
                        add_item(run,item); failures=0
                        if len(run['items']) >= limit: return run
                    except PlatformError as error:
                        run['errors'].append(str(error));failures+=1
                        if error.fatal or failures>=3:return run
    except (PlatformError, ValueError) as error:
        run['errors'].append(str(error))
    finally:
        if client:client.close()
        finish(run)
    return run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, default=ROOT/'.install/host-discovery')
    parser.add_argument('--container', default='xhs-personal-app-1')
    parser.add_argument('--max-products', type=int, default=80, choices=range(1,81))
    parser.add_argument('--max-notes', type=int, default=30, choices=range(1,31))
    parser.add_argument('--no-search', action='store_true')
    parser.add_argument('--interactive-search', action='store_true',
                        help='仅在账号状态正常且人工在场时，通过可见页面搜索；默认暂停账号搜索')
    parser.add_argument('--no-ranks', action='store_true')
    parser.add_argument('--schedule', default='每日 09:10（北京时间）')
    args = parser.parse_args()
    directory=args.state_dir.resolve();directory.mkdir(parents=True,exist_ok=True)
    # OS file locking releases automatically after a crash; no stale pid lock.
    lock=(directory/'worker.lock').open('a+b')
    try:
        if os.name=='nt':
            import msvcrt
            lock.seek(0);lock.write(b'1');lock.flush();lock.seek(0)
            try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:return 0
        else:
            import fcntl
            try:fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:return 0
        try:
            return work(args,directory)
        except Exception as error:
            status_path=directory/'status.json'
            status=json.loads(status_path.read_text(encoding='utf-8')) if status_path.exists() else {}
            status.update(state='failed',finished_at=time(),error=str(error))
            atomic_json(status_path,status)
            raise
    finally:lock.close()


def work(args,directory):
    bridge=(ROOT/'scripts/host_discovery_bridge.py').read_text(encoding='utf-8')
    def remote(export=False,payload=None):
        command=['docker','exec','-i',args.container,'python','-c',bridge]+(['--export'] if export else [])
        p=subprocess.run(command,input=None if payload is None else json.dumps(payload,ensure_ascii=False).encode(),capture_output=True,timeout=180)
        if p.returncode:raise RuntimeError('容器读取/导入失败：'+p.stderr.decode('utf-8',errors='replace')[-1200:])
        return json.loads(p.stdout)
    state_path=directory/'checkpoint.json'
    state=json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {'products':{},'ranks':{}}
    # Finish imports left pending by an interrupted previous execution first.
    for pending in pending_snapshots(directory):
        marker=pending.with_suffix('.imported.json')
        if not marker.exists():atomic_json(marker,remote(payload=json.loads(pending.read_text(encoding='utf-8'))))
    seeds=remote(export=True);today=datetime.now(CN).date().isoformat();stop=Event()
    payload={'format':'xhs-host-discovery-v2','id':uuid4().hex,'owner_id':seeds['owner_id'],'schedule':args.schedule,'runs':[]}
    path=directory/('snapshot-'+payload['id']+'.json')
    summary={'state':'processing','started_at':time(),'snapshot':str(path),'new_product_pages':0,'product_successes':0,'product_errors':0}
    def save():
        atomic_json(path,payload);atomic_json(directory/'status.json',summary);atomic_json(state_path,state)
    # Only finished batches are saved to the import payload; partial products are checkpointed below.
    if not args.no_ranks:
        from types import SimpleNamespace
        for board in ['low_fan','commerce']:
            if state['ranks'].get(board)==today:continue
            run=new_run({'platform':'huitun','mode':'ranks','huitun_board':board,'selection':seeds['selection']},today)
            HuitunClient().collect(SimpleNamespace(huitun_board=board),stop,lambda i:add_item(run,i),lambda m,informational=False:run['warnings' if informational else 'errors'].append(m))
            finish(run);payload['runs'].append(run)
            if run['state']=='success':state['ranks'][board]=today
            for item in run['items']:
                for p in item.get('products',[]):
                    if p.get('url'):seeds['pairs'].append({'url':p['url'],'mode':'product','seed_source':'new_rank_product','note_source_key':item['source_key']})
            save()
    if not args.no_search:
        settings=json.loads((ROOT/'DockerData/settings.json').read_text(encoding='utf-8'))
        run=collect_logged_notes(settings,seeds['keywords'],args.max_notes,seeds['selection'],today,
                                 interactive=getattr(args,'interactive_search',False))
        payload['runs'].append(run)
        summary['search']={'state':run['state'],'count':len(run['items']),'errors':run['errors']}
        for item in run['items']:
            for p in item.get('products',[]):
                if p.get('url'):seeds['pairs'].append({'url':p['url'],'mode':'product','seed_source':'new_search_product','note_source_key':item['source_key']})
        save()
    queue,available=plan_products(seeds['pairs'],seeds['known'],state,time(),args.max_products)
    summary.update(unique_product_seeds=available,queued_products=len(queue))
    if queue:
        run=new_run({'platform':'xiaohongshu','mode':'product','access':'anonymous','query':queue[0]['url'],'selection':seeds['selection']},today)
        run['collection_scope'].update(mode='linked_product_batch',seed_count=len(queue),product_urls=[s['url'] for s in queue])
        payload['runs'].append(run)
        failures=0
        for seed in queue:
            try:
                url=resolve_public_target(seed['url'],'product',stop)
                raw,final=load_public_product(url)
                product=commerce_observation(raw,final)
                item={'platform':'xiaohongshu','kind':'product','note_id':product['product_id'],'title':product['title'],
                      'body':'','url':final,'source':'anonymous_h5_product','products':[product],'followers':None,
                      'comment_items':[],'comments_scope':'商品页，不是笔记','collection_access':'anonymous',
                      'source_query':seed['url'],'host_seed':seed}
                add_item(run,item)
                state['products'][seed['identity']]={'state':'success','product_id':product['product_id'],'retry_at':time()+86400}
                summary['product_successes']+=1;failures=0
            except Exception as error:
                run['errors'].append(f"商品 {seed['identity']}：{error}")
                state['products'][seed['identity']]={'state':'failed','retry_at':time()+6*3600}
                summary['product_errors']+=1;failures+=1
            finish(run);save()
            if failures>=3:
                run['warnings'].append('连续3条商品失败，本轮暂停；其余链接留待下轮。');finish(run);save();break
            stop.wait(1.5)
    if payload['runs']:
        save();result=remote(payload=payload);atomic_json(path.with_suffix('.imported.json'),result)
    else:result={'runs':[],'new_source_records':0,'new_product_pages':0,'new_product_ids':0,'new_notes':0}
    summary.update(state='partial' if any(r['errors'] for r in payload['runs']) else 'success',finished_at=time(),import_result=result,
                   new_product_pages=result['new_product_pages'],new_product_ids=result['new_product_ids'],new_notes=result['new_notes'])
    atomic_json(directory/'status.json',summary)
    print(json.dumps(summary,ensure_ascii=True),flush=True)
    return 0 if any(r['items'] for r in payload['runs']) or not payload['runs'] else 1


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as error:
        print(json.dumps({'state':'failed','error':str(error)},ensure_ascii=True),flush=True)
        raise SystemExit(1)
