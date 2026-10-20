"""Run inside the personal container; export seeds or atomically import host observations."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from time import time


def visible_runs(db, owner):
    return [r for p, in db.execute('SELECT payload FROM discovery_runs ORDER BY created DESC')
            if (r := json.loads(p)).get('owner_id') == owner]


def export_seeds(root):
    settings = json.loads((root/'discovery-settings.json').read_text())['daily_selection']
    owner = settings['owner_id']
    pairs, keywords = [], []
    with sqlite3.connect(f'file:{root}/xhs_operations.db?mode=ro', uri=True) as db:
        for table, mode in [('operation_notes', 'detail'), ('operation_products', 'product')]:
            for row in db.execute(f'SELECT t.url,t.title,s.name,s.id FROM {table} t JOIN operation_spaces s ON t.space_id=s.id WHERE s.owner_id=? AND t.url != ?', (owner, '')):
                pairs.append(dict(zip(['url', 'title', 'space', 'space_id'], row), mode=mode, seed_source=table))
        for name, in db.execute('SELECT title FROM operation_products WHERE space_id IN (SELECT id FROM operation_spaces WHERE owner_id=?)', (owner,)):
            if 1 < len(name.strip()) <= 20:
                keywords.append(name.strip())
    with sqlite3.connect(f'file:{root}/market_discovery.db?mode=ro', uri=True) as db:
        runs = visible_runs(db, owner)
    known = {}
    for run in runs:
        for item in run.get('items', []):
            key = item['source_key']
            known[key] = max(known.get(key, 0), item.get('collected_at', 0))
            if item.get('url') and item.get('kind') == 'note':
                pairs.append({'url': item['url'], 'mode': 'detail', 'seed_source': 'discovery_note'})
            for p in item.get('products', []):
                if p.get('url'):
                    pairs.append({'url': p['url'], 'title': p.get('title', ''), 'mode': 'product',
                                  'seed_source': 'attached_product', 'note_source_key': key if item.get('kind') == 'note' else ''})
    words = [settings.get('selection', {}).get('product', ''), *keywords, *settings['keywords']]
    return {'owner_id': owner, 'selection': settings['selection'], 'keywords': list(dict.fromkeys(w for w in words if w))[:6],
            'pairs': pairs, 'known': known}


def import_snapshot(root, payload):
    from knowledge_base import KnowledgeBase
    from market_discovery import DiscoveryRequest
    from selection_strategy import SelectionStrategy
    from xhs_operations import OperationStore
    settings = json.loads((root/'discovery-settings.json').read_text())['daily_selection']
    assert payload['format'] == 'xhs-host-discovery-v2'
    assert payload['owner_id'] == settings['owner_id']
    assert len(payload['runs']) <= 10
    strategy = SelectionStrategy(KnowledgeBase(root/'knowledge.db'), OperationStore(root/'xhs_operations.db'))
    prepared = []
    for observed in payload['runs']:
        assert len(observed['items']) <= 100
        request = DiscoveryRequest.model_validate(observed['request'])
        plan = strategy.plan(request, payload['owner_id'])
        run = copy.deepcopy(observed)
        run.update(owner_id=payload['owner_id'], selection_plan=plan, collection_host='host_worker',
                   automation={'kind': 'host_collection', 'schedule': payload.get('schedule', '')})
        seen = set()
        for item in run['items']:
            assert item['platform'] in {'xiaohongshu', 'huitun'} and item['kind'] in {'note', 'product'}
            assert item['source_key'] == f"{item['platform']}:{item['kind']}:{item['note_id']}"
            assert item['source_key'] not in seen
            assert observed['created_at'] <= item['collected_at'] <= observed['finished_at']
            seen.add(item['source_key'])
            item['selection'] = strategy.evaluate(item, plan)
        run['host_snapshot_hash'] = hashlib.sha256(json.dumps(observed, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        prepared.append(run)
    db = sqlite3.connect(root/'market_discovery.db', timeout=30)
    previous = visible_runs(db, payload['owner_id'])
    known = {i['source_key'] for r in previous for i in r.get('items', [])}
    known_products = {p.get('product_id') for r in previous for i in r.get('items', []) for p in i.get('products', []) if p.get('product_id')}
    backup = root/'.maintenance'/('host-before-'+payload['id']+'.db')
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        with sqlite3.connect(backup) as dst: db.backup(dst)
    records, new_keys, new_products = [], set(), set()
    try:
        with db:
            for run in prepared:
                old = db.execute('SELECT payload FROM discovery_runs WHERE id=?', (run['id'],)).fetchone()
                if old:
                    assert json.loads(old[0]).get('host_snapshot_hash') == run['host_snapshot_hash'], 'Run ID collision'
                    records.append({'id': run['id'], 'state': 'already_imported', 'count': len(run['items'])})
                    continue
                new_keys.update(i['source_key'] for i in run['items'] if i['source_key'] not in known)
                new_products.update(p['product_id'] for i in run['items'] for p in i.get('products', []) if p.get('product_id') and p['product_id'] not in known_products)
                db.execute('INSERT INTO discovery_runs VALUES (?,?,?)', (run['id'], run['created_at'], json.dumps(run, ensure_ascii=False)))
                for item in run['items']:
                    db.execute('INSERT INTO discovery_snapshots VALUES (?,?,?,?)', (item['source_key'], run['id'], item['collected_at'], json.dumps(item, ensure_ascii=False)))
                records.append({'id': run['id'], 'state': run['state'], 'count': len(run['items']), 'knowledge_methods': run['selection_plan']['coverage']['methods']})
        for run in prepared:
            saved=json.loads(db.execute('SELECT payload FROM discovery_runs WHERE id=?',(run['id'],)).fetchone()[0])
            assert saved['host_snapshot_hash']==run['host_snapshot_hash'] and len(saved['items'])==len(run['items'])
    finally:
        db.close()
    return {'runs': records, 'new_source_records': len(new_keys), 'new_notes': sum(':note:' in k for k in new_keys),
            'new_product_pages': sum(':product:' in k for k in new_keys), 'new_product_ids': len(new_products), 'backup': str(backup)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path('/data'))
    parser.add_argument('--export', action='store_true')
    args = parser.parse_args()
    result = export_seeds(args.root) if args.export else import_snapshot(args.root, json.load(sys.stdin))
    print(json.dumps(result, ensure_ascii=False))
