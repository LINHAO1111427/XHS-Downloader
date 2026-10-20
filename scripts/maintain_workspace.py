"""Archive obsolete root artifacts; remove only regenerable project caches.

Dry-run by default. --apply requires an archive directory outside this project.
Media, databases, environments, .tmp, output and historical backups are excluded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(root):
    names = {
        'MODIFIED_FILE', 'MODIFIED_FILE.baseline', 'DIFF_FILE', 'VERIFICATION.txt',
        'ROLLBACK.sh', 'CONTINUATION_RECORD.md', 'NARRATIVE_REMIX_MODIFIED_FILE.txt',
        'hello', 'baidu.html', 'bing.html', 'douyin_search.html', 'dy_api.json',
        'so_search.html', 'tmpsearch.html', 'tmp_ks.html', 'test_dy.mp4',
        'm-offer.html', 'offer-live.html', 'pelican-ride.html',
        'pelican_bicycle_animation.html', 'pelican_bicycle_animation.html.original',
        '.pelican_bicycle_animation.baseline', '.pelican_bicycle_animation.original.sha256',
    }
    patterns = [r'.+\.diff', r'.+_(?:ROLLBACK\.sh|VERIFICATION\.txt)',
                r'[a-f0-9]{24}\.json', r'ks_.+\.(?:js|html|json)',
                r'.+\.[a-zA-Z0-9_-]{8,}\.js', r'index(?:-legacy)?-[a-zA-Z0-9_-]+\.js']
    candidates = [p for p in root.iterdir() if p.is_file() and
                  (p.name in names or any(re.fullmatch(pattern, p.name) for pattern in patterns))]
    code = list(root.glob('*.py'))
    for directory in ['source', 'static', 'tests', 'scripts', 'deploy']:
        code.extend(p for p in (root / directory).rglob('*') if p.suffix in
                    {'.py', '.js', '.html', '.css', '.ps1', '.yml', '.toml'})
    references = {}
    for p in code:
        if p.resolve() == Path(__file__).resolve() or not p.is_file():
            continue
        text = p.read_text(encoding='utf-8', errors='replace')
        for candidate in candidates:
            if candidate.name in text:
                references.setdefault(candidate.name, []).append(str(p.relative_to(root)))
    files = [p for p in candidates if p.name not in references]
    caches = [root / name for name in ['__pycache__', '.pytest_cache', '.ruff_cache']]
    for directory in ['source', 'tests', 'scripts']:
        caches.extend((root / directory).rglob('__pycache__'))
    caches = [p for p in caches if p.is_dir() and not p.is_symlink()]
    return files, caches, references


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    files, caches, references = inventory(root)
    records = [{'path': str(p.relative_to(root)), 'bytes': p.stat().st_size, 'sha256': digest(p)} for p in files]
    cache_bytes = sum(f.stat().st_size for p in caches for f in p.rglob('*') if f.is_file())
    report = {'root': str(root), 'archived_files': records,
              'archive_bytes': sum(r['bytes'] for r in records),
              'caches': [str(p.relative_to(root)) for p in caches], 'cache_bytes': cache_bytes,
              'retained_references': references, 'applied': False}
    if args.apply:
        if not args.archive:
            parser.error('--apply requires --archive')
        archive = args.archive.resolve()
        if archive == root or root in archive.parents:
            parser.error('archive must be outside the project')
        archive.mkdir(parents=True, exist_ok=False)
        destination = archive / 'root-history.zip'
        with zipfile.ZipFile(destination, 'x', zipfile.ZIP_DEFLATED) as z:
            for p in files:
                z.write(p, p.name)
        with zipfile.ZipFile(destination) as z:
            assert z.testzip() is None
            for item in records:
                assert hashlib.sha256(z.read(item['path'])).hexdigest() == item['sha256']
        # Recheck exact targets and bytes immediately before unlinking.
        for p, item in zip(files, records):
            assert p.resolve().parent == root and not p.is_symlink()
            assert digest(p) == item['sha256']
            p.unlink()
        for p in caches:
            assert root in p.resolve().parents and not p.is_symlink()
            shutil.rmtree(p)
        report.update(applied=True, archive=str(destination), archive_sha256=digest(destination))
        (archive / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
