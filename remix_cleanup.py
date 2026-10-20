"""Remove known render intermediates only, with a reviewable hash manifest."""
import hashlib
import re
from pathlib import Path


INTERMEDIATE = re.compile(r"(?:\d{2}\.(?:mp4|png)|end\.(?:jpg|mp4)|joined\.mp4|with_music\.mp4|pre_layers\.mp4|concat\.txt)$")


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def plan_cleanup(workspace, roots, protected=()):
    workspace = Path(workspace).resolve()
    protected = {Path(p).resolve() for p in protected}
    result = []
    for root in roots:
        root = Path(root).resolve()
        if (not root.is_relative_to(workspace / 'output')
                or root.name not in {'render', 'render_final', 'render_fullframe_v3'}):
            raise ValueError('Only designated render work folders can be cleaned')
        for path in sorted(root.rglob('*')):
            if (not path.is_file() or path.is_symlink() or path.resolve() in protected
                    or not path.resolve().is_relative_to(root) or not INTERMEDIATE.fullmatch(path.name)):
                continue
            result.append({'path': path.relative_to(workspace).as_posix(),
                           'sha256': digest(path), 'bytes': path.stat().st_size,
                           'reason': 'reproducible render intermediate; no active file reference'})
    return result


def apply_cleanup(workspace, manifest, protected=()):
    workspace = Path(workspace).resolve()
    protected = {Path(p).resolve() for p in protected}
    # Preflight the ENTIRE manifest before deleting any file.
    paths = []
    for item in manifest:
        path = (workspace / item['path']).resolve()
        if (not path.is_relative_to(workspace / 'output') or path in protected
                or not any(part in {'render','render_final','render_fullframe_v3'} for part in path.relative_to(workspace/'output').parts[:-1])
                or not INTERMEDIATE.fullmatch(path.name) or digest(path) != item['sha256']):
            raise ValueError('Cleanup manifest changed or references a protected file')
        paths.append(path)
    for path in paths:
        path.unlink()
    return {'deleted_files': len(paths), 'freed_bytes': sum(item['bytes'] for item in manifest)}
