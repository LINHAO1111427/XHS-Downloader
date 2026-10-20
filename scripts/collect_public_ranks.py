"""Collect bounded public rank snapshots from the Windows host or any CLI.

This does not use credentials, change proxy settings, or write live databases.
The output retains source/time/unknown metrics for subsequent normal import.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from threading import Event
from time import time
from types import SimpleNamespace
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from huitun_discovery import HuitunClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output already exists')
    runs = []
    for board in ['low_fan', 'commerce']:
        run = {'id': uuid4().hex, 'created_at': time(), 'source_board': board,
               'items': [], 'errors': [], 'warnings': [], 'collection_host': 'host_cli'}
        def emit(item):
            item.update(collected_at=time(), source_key=f"huitun:{item['kind']}:{item['note_id']}")
            run['items'].append(item)
        def warn(message, informational=False):
            run['warnings' if informational else 'errors'].append(message)
        try:
            HuitunClient().collect(SimpleNamespace(huitun_board=board), Event(), emit, warn)
        except Exception as error:
            run['errors'].append(str(error))
        run['state'] = ('partial' if run['items'] else 'failed') if run['errors'] else 'success'
        run['finished_at'] = time()
        runs.append(run)
    payload = {'format': 'xhs-public-ranks-v1', 'observed_at': datetime.now(timezone.utc).isoformat(), 'runs': runs}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(json.dumps({'path': str(args.output.resolve()), 'sha256': hashlib.sha256(args.output.read_bytes()).hexdigest(),
                      'runs': [{'board': r['source_board'], 'state': r['state'], 'count': len(r['items']), 'errors': r['errors']} for r in runs]}, ensure_ascii=False))
    return 1 if any(r['state'] == 'failed' for r in runs) else 0


if __name__ == '__main__':
    raise SystemExit(main())
