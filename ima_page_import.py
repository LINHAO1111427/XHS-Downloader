"""Capture an open IMA reading pane and import reviewed text into local knowledge.

Rendered DOM/UI captures are excerpts. An authenticated desktop reader can also
expose its original Markdown resource; those captures preserve and verify the
raw bytes separately. Pictures and linked resources need separate review.
Nothing is imported by the capture command alone.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sqlite3
import zipfile
from xml.etree import ElementTree
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from knowledge_base import KnowledgeBase


def digest(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def docx_body(raw: bytes) -> str:
    """Read actual Word body paragraphs/tables; images and headers are separate."""
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        info = archive.getinfo('word/document.xml')
        if info.file_size > 10_000_000:
            raise ValueError('Word 正文 XML 超过处理上限')
        document = ElementTree.fromstring(archive.read(info))
    ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    paragraphs = []
    for paragraph in document.iter(ns + 'p'):
        parts = []
        for node in paragraph.iter():
            if node.tag == ns + 't': parts.append(node.text or '')
            elif node.tag == ns + 'tab': parts.append('\t')
            elif node.tag in {ns + 'br', ns + 'cr'}: parts.append('\n')
        text = ''.join(parts).strip()
        if text: paragraphs.append(text)
    return '\n\n'.join(paragraphs)


def source_url(value: str, *, desktop: bool = False) -> str:
    parsed = urlsplit(value)
    is_web = parsed.scheme == 'https' and parsed.hostname == 'ima.qq.com'
    reader_pages = {('cbgfjbdckbpenliighcjcbjfiihnnkfe', '/markdown.html'),
                    ('jmfjadjclplhcchkjjnjoinbfmdhjkhh', '/template/doc.html')}
    is_reader = (desktop and parsed.scheme == 'chrome-extension'
                 and (parsed.hostname, parsed.path) in reader_pages)
    if not (is_web or is_reader):
        raise ValueError('请选择 ima.qq.com 的正文页面')
    # Query parameters may carry transient sharing or login tokens.
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, '', ''))


def validate_capture(data: dict) -> None:
    for field in ('title', 'library', 'content', 'url', 'captured_at'):
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise ValueError(f'采集记录缺少 {field}')
    original = data.get('capture_method') == 'ima_reader_resource'
    desktop = data.get('capture_method') in {'windows_uia', 'ima_reader_resource'}
    word = original and data.get('coverage') == 'original_docx_body'
    expected_container = 'docx-main-body' if word else 'markdown-viewer-container'
    if desktop and (data.get('application') != 'ima.copilot'
                    or data.get('reader_container') != expected_container):
        raise ValueError('桌面采集须来自已核验的 IMA 正文阅读器')
    source_url(data['url'], desktop=desktop)
    if desktop:
        expected_url = ('chrome-extension://jmfjadjclplhcchkjjnjoinbfmdhjkhh/template/doc.html' if word
                        else 'chrome-extension://cbgfjbdckbpenliighcjcbjfiihnnkfe/markdown.html')
        if source_url(data['url'], desktop=True) != expected_url:
            raise ValueError('阅读器类型与正文格式不匹配')
    content = data['content']
    if len(content.strip()) < 100 or content.strip() == data['title'].strip():
        raise ValueError('正文过短，请检查是否只选中了标题或目录')
    if len(content.encode('utf-8')) > 800_000:
        raise ValueError('请按章节分批采集')
    if data.get('content_sha256') != digest(content):
        raise ValueError('正文校验值不匹配')
    if original:
        if data.get('coverage') not in {'original_markdown_text', 'original_docx_body'} or data.get('source_host') != 'res-skb.ima.qq.com':
            raise ValueError('原文件采集须保留已核验的来源和读取范围')
        path = Path(data.get('original_path', ''))
        if not path.is_absolute():
            path = Path(__file__).resolve().parent / path
        raw = path.read_bytes()
        if (len(raw) != data.get('original_bytes')
                or hashlib.sha256(raw).hexdigest() != data.get('original_sha256')
                or (docx_body(raw) if word else raw.decode('utf-8-sig')) != content):
            raise ValueError('原文件与正文校验值不匹配')
    elif data.get('coverage') != 'visible_text_excerpt':
        raise ValueError('请保留可见文字节选标记，不将页面采集标为整库全文')


def capture(cdp: str, page_url: str, selector: str, title: str, library: str, output: Path, frame_url: str | None = None) -> dict:
    from playwright.sync_api import sync_playwright
    if urlsplit(cdp).hostname not in {'localhost', '127.0.0.1', '::1'}:
        raise ValueError('浏览器调试地址须为本机地址')
    source_url(page_url)
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(cdp)
        pages = [p for ctx in browser.contexts for p in ctx.pages if p.url == page_url]
        if len(pages) != 1:
            raise ValueError('没有找到唯一匹配的已打开 IMA 页面')
        page = pages[0]
        target = page
        if frame_url:
            frames = [f for f in page.frames if f.url == frame_url]
            if len(frames) != 1:
                raise ValueError('正文 iframe 未唯一匹配')
            target = frames[0]
        pane = target.locator(selector)
        if pane.count() != 1 or not pane.is_visible():
            raise ValueError('正文区域须唯一且可见，请检查选择器')
        text = pane.inner_text(timeout=10_000).strip()
        data = dict(title=title.strip(), library=library.strip(), content=text,
                    url=source_url(page.url), captured_at=datetime.now(timezone.utc).isoformat(),
                    content_sha256=digest(text), coverage='visible_text_excerpt',
                    images_in_pane=pane.locator('img').count(), capture_method='rendered_dom',
                    selector=selector)
        validate_capture(data)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        assert json.loads(output.read_text(encoding='utf-8')) == data
        # Exiting Playwright disconnects; do not close the user's browser.
    return {'capture': str(output.resolve()), 'characters': len(text), 'sha256': digest(text),
            'coverage': data['coverage'], 'images_in_pane': data['images_in_pane']}


def prepare_entries(data: dict) -> list[dict]:
    validate_capture(data)
    content = data['content']
    # Markdown image alt text in this library contains generated descriptions
    # and historical metrics. Archive it with the raw file, but do not treat it
    # as independently verified image content in the retrieval corpus.
    content = re.sub(r'!\[[^\]]*\]\([^\n]*\)', '', content)
    content = re.sub(r'\n{3,}', '\n\n', content)
    # Repeat provenance on each chunk so retrieval of a later chunk keeps attribution.
    paragraphs, pending = [], ''
    for paragraph in content.split('\n\n'):
        for offset in range(0, len(paragraph), 2500):
            part = paragraph[offset:offset + 2500]
            if len(pending) + len(part) + 2 > 2500:
                if pending:
                    paragraphs.append(pending)
                pending = ''
            pending = (pending + '\n\n' + part).strip()
    if pending:
        paragraphs.append(pending)
    if not paragraphs or len(paragraphs) > 250:
        raise ValueError('正文分段数量异常，请拆分章节')
    original = data.get('capture_method') == 'ima_reader_resource'
    # Transcripts often have opaque camera filenames. Retain their supplied
    # course chapter on every chunk so retrieval keeps useful context.
    chapters = []
    if content.startswith('---\n'):
        frontmatter = content.split('\n---', 1)[0]
        for line in frontmatter.splitlines():
            if line.startswith('course_pages:'):
                try:
                    values = json.loads(line.split(':', 1)[1].strip())
                except ValueError:
                    continue
                if isinstance(values, list):
                    chapters = [str(v).replace('\\', '/').rsplit('/', 1)[-1].removesuffix('.md')[:80]
                                for v in values if isinstance(v, str)][:2]
    chapter_label = '；'.join(chapters).replace('\n', ' ').replace('\r', ' ')
    chapter_source = f'课程章节：{chapter_label}\n' if chapter_label else ''
    coverage = ('读取范围：已取得原始 Markdown 完整文本；本段仅正文，图片替代说明及外链附件内容不计入。'
                if original else '读取范围：已查看页面中的文字节选；图片内容和未展开部分不计入。')
    if data.get('coverage') == 'original_docx_body':
        coverage = '读取范围：原始 Word 主文档正文与表格文字；图片、页眉页脚、批注和外链附件内容不计入。'
    provenance = (f'来源：{data["library"][:160]} / {data["title"][:160]}\n'
                  f'{chapter_source}'
                  f'原始页面：{source_url(data["url"], desktop=data.get("capture_method") in {"windows_uia", "ima_reader_resource"})}\n'
                  f'{coverage}\n\n')
    if len(provenance) > 750:
        raise ValueError('来源标注过长')
    label = '分段' if original else '节选'
    display_title = f'{chapter_label} / {data["title"]}' if chapter_label else data['title']
    return [{'title': f'{display_title[:70]} · {label} {i + 1}/{len(paragraphs)}',
             'content': provenance + part} for i, part in enumerate(paragraphs)]


def import_capture(capture_path: Path, database: Path, owner: str, reviewed_sha256: str,
                   kind: str = 'general', receipt_path: Path | None = None) -> dict:
    data = json.loads(capture_path.read_text(encoding='utf-8-sig'))
    entries = prepare_entries(data)
    if reviewed_sha256 != data['content_sha256']:
        raise ValueError('请先核对实际正文，再传入对应的校验值')
    if not database.is_file():
        raise ValueError('请指定已有的项目知识库数据库')
    if receipt_path is not None and receipt_path.exists():
        raise ValueError('导入记录已存在，请使用新的记录路径')
    # Preserve a consistent SQLite backup before a live import, including WAL pages.
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup = database.parent / 'ima-import-backups' / f'knowledge-{stamp}.db'
    backup.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as original, closing(sqlite3.connect(backup)) as saved:
        original.backup(saved)
        before = {r[0] for r in original.execute('SELECT id FROM knowledge_entries')}
    store = KnowledgeBase(database)
    filename = 'ima-visible-' + digest(data['library'] + '\n' + data['title'])[:16] + '.json'
    result = store.import_document(filename, json.dumps(entries, ensure_ascii=False).encode('utf-8'), kind, owner)
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        after = [dict(r) for r in connection.execute('SELECT * FROM knowledge_entries')]
    inserted = [r for r in after if r['id'] not in before and r['origin'] == 'document:' + filename]
    result = dict(imported=result['imported'], duplicates=result['duplicates'],
                  source_title=data['title'], capture_sha256=data['content_sha256'],
                  database=str(database.resolve()), backup=str(backup.resolve()),
                  inserted_rows=inserted, coverage=data['coverage'])
    if receipt_path is not None:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        assert json.loads(receipt_path.read_text(encoding='utf-8')) == result
    return result


def rollback(receipt: Path, database: Path) -> dict:
    record = json.loads(receipt.read_text(encoding='utf-8'))
    removed = 0
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.row_factory = sqlite3.Row
        connection.execute('BEGIN IMMEDIATE')
        for original in record['inserted_rows']:
            row = connection.execute('SELECT * FROM knowledge_entries WHERE id=?', (original['id'],)).fetchone()
            if row is None:
                continue
            current = dict(row)
            # Retrieval counters are allowed to change; user edits are not overwritten.
            fields = ('kind','title','content','tags','priority','active','origin','created_by','updated_at')
            if any(current[k] != original[k] for k in fields):
                raise ValueError('导入后条目已有编辑，已保留全部条目并停止本次回退')
            connection.execute('DELETE FROM knowledge_entries WHERE id=?', (original['id'],))
            removed += 1
    return {'removed': removed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    cap = sub.add_parser('capture')
    for name in ('cdp','page-url','selector','title','library','out'):
        cap.add_argument('--' + name, required=True)
    cap.add_argument('--frame-url')
    imp = sub.add_parser('import')
    for name in ('capture','db','owner','reviewed-sha256','receipt'):
        imp.add_argument('--' + name, required=True)
    imp.add_argument('--kind', choices=['general','note','image'], default='general')
    undo = sub.add_parser('rollback')
    undo.add_argument('--receipt', required=True)
    undo.add_argument('--db', required=True)
    args = parser.parse_args()
    if args.command == 'capture':
        result = capture(args.cdp,args.page_url,args.selector,args.title,args.library,Path(args.out),args.frame_url)
    elif args.command == 'import':
        result = import_capture(Path(args.capture),Path(args.db),args.owner,args.reviewed_sha256,args.kind,Path(args.receipt))
        result = {k:v for k,v in result.items() if k != 'inserted_rows'}
    else:
        result = rollback(Path(args.receipt),Path(args.db))
    print(json.dumps(result,ensure_ascii=False))


if __name__ == '__main__':
    main()
