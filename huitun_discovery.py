"""Bounded Hongshu public first-page collection; no account or saved cookies."""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import json
import re
from time import time
from urllib.parse import urlencode
from threading import Event

from curl_cffi.requests import Session
from curl_cffi.requests.exceptions import RequestException

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

from discovery_adapters import DiscoveryBlocked, DiscoveryError, checkpoint

CN = timezone(timedelta(hours=8))
BOARDS = {
    'low_fan': ('低粉爆文榜', '/rank/lowPowderExplosionTextV2'),
    'commerce': ('带货笔记榜', '/rank/goodsNoteV2'),
    'goods': ('商品销量榜', '/rank/goods/sale'),
}
API = 'https://xhsapi.huitun.com'
# Public display codec from main.14ac5b0b.chunk.js, SHA256
# 86e3e07b46d7c8b9e833dc4ec019cfe87f024662d0a4fa3fc187157082464e9a.
# This is page formatting, not account/session material. Fail closed on changes.
_CODEC_PARTS = ([93, 24, 43, 91, 81, 72, 3, 99, 125, 28, 45, 112, 118, 45, 0, 108], [19, 47, 83, 11, 101, 37, 72, 90, 14, 77, 31, 6, 58, 21, 99, 40])


def decode_response(payload):
    if not isinstance(payload, dict):
        raise DiscoveryError('灰豚返回格式变化，未保存为成功结果')
    if payload.get('status') in (1000, 1001, 2001):
        raise DiscoveryBlocked('灰豚要求登录或限制访问，本批已停止；已取得的结果保留')
    if payload.get('status') != 0:
        raise DiscoveryError('灰豚本次未返回可用榜单，请稍后再试')
    data = payload.get('extData')
    if payload.get('encrypt') is True:
        try:
            left, right = _CODEC_PARTS
            key = bytes(a ^ b for a, b in zip(left, right))
            assert len(key) == 16 and sum(key) == 1289
            decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
            raw = decryptor.update(base64.b64decode(data.replace(' ', '+').strip(), validate=True)) + decryptor.finalize()
            unpadder = PKCS7(128).unpadder()
            text = (unpadder.update(raw) + unpadder.finalize()).decode('utf-8')
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = json.loads(re.sub(r'([{,])(\d+):', r'\1"\2":', text))
        except Exception as error:
            raise DiscoveryError('灰豚网页数据格式已变化，需更新采集器；未使用历史数据代替本次结果') from error
    if not isinstance(data, dict) or not isinstance(data.get('list'), list):
        raise DiscoveryError('灰豚本次未返回榜单记录，可能需要登录或稍后重试')
    if any(not isinstance(row, dict) for row in data['list']):
        raise DiscoveryError('灰豚榜单记录格式变化，未保存为成功结果')
    return data['list'][:10]


def observed_count(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, str) and re.fullmatch(r'\d+', value):
        return int(value)
    return None


def provider_time(value):
    try:
        return datetime.strptime(value, '%Y-%m-%d %H:%M:%S').replace(tzinfo=CN).timestamp()
    except (ValueError, TypeError):
        return None


def normalize_product(raw):
    pid = str(raw.get('goodsId') or '')
    if not re.fullmatch(r'[a-fA-F0-9]{24}', pid):
        return None
    observed = time()
    return {
        'product_id': pid.lower(), 'spu_id': str(raw.get('spuId') or ''), 'source': 'xiaohongshu.com',
        'title': str(raw.get('shortTitle') or raw.get('title') or '商品标题未取得'),
        'url': 'https://www.xiaohongshu.com/goods-detail/' + pid.lower(),
        'price': str(raw['price']) if raw.get('price') is not None else '',
        'shop_name': str(raw.get('shopName') or ''), 'observed_at': observed,
        'metric_source': 'huitun_public_rank', 'metric_source_url': 'https://xhs.huitun.com/',
        'sales_text': str(raw['saleTol']) if raw.get('saleTol') is not None else '',
        'sales_total': None, 'provider_sales_raw': raw.get('saleTol'),
        'cart_24h': {'status': 'missing', 'value': None, 'window_hours': 24, 'product_id': pid.lower(),
                    'source': 'huitun_public_rank', 'observed_at': observed,
                    'reason': '灰豚公开榜单未提供24小时加购，销量不代替加购'},
    }


def normalize_note(raw, board):
    identity = str(raw.get('noteId') or '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', identity):
        raise DiscoveryError('灰豚笔记缺少有效来源编号')
    products = []
    goods = raw.get('goodsList')
    for value in goods if isinstance(goods, list) else []:
        if isinstance(value, dict) and (product := normalize_product(value)):
            if product['product_id'] not in {p['product_id'] for p in products}:
                products.append(product)
    return {
        'platform': 'huitun', 'origin_platform': 'xiaohongshu', 'kind': 'note',
        'note_id': identity, 'provider_note_id': identity, 'source': 'huitun_public_rank',
        'source_board': board, 'source_board_label': BOARDS[board][0],
        'title': str(raw.get('title') or ''), 'body': str(raw.get('desc') or '').replace('\\n', '\n').replace('\\t', '\t'),
        'note_type': {'normal': 'graphic', 'video': 'video'}.get(raw.get('type'), 'unknown'),
        'cover_url': str(raw.get('imageUrl') or ''),
        'image_urls': [str(raw['imageUrl'])] if raw.get('imageUrl') else [],
        'image_scope': 'provider_cover_only', 'full_image_set_observed': False,
        'body_scope': 'provider_description_unverified_completeness',
        'provider_read_count': observed_count(raw.get('read')),
        'read_count_scope': 'third_party_value_not_verified_impressions_or_ctr',
        # Numeric provider IDs are not XHS note IDs; do not invent original links.
        'url': '', 'provider_url': 'https://xhs.huitun.com/',
        'author': str(raw.get('nick') or ''),
        'author_id': 'huitun:' + str(raw['anchorId']) if raw.get('anchorId') else '',
        'followers': observed_count(raw.get('fans')), 'likes': observed_count(raw.get('like')),
        'collects': observed_count(raw.get('coll')), 'comments': observed_count(raw.get('comm')),
        'shares': observed_count(raw.get('sharedCount', raw.get('share'))),
        'published_at': provider_time(raw.get('ts')), 'provider_updated_at': provider_time(raw.get('updateTime')),
        'metrics_raw': {k: raw.get(k) for k in ['fans', 'like', 'coll', 'comm', 'sharedCount', 'updateTime']},
        'metrics_scope': '灰豚第三方快照，尚未逐条与小红书主页复核',
        'collection_access': 'anonymous', 'products': products, 'comment_items': [],
        'mounted_product_evidence': {'status': 'observed' if products else 'missing',
                                     'source_field': 'goodsList', 'provider': 'huitun',
                                     'product_ids': [p['product_id'] for p in products]},
        'comments_scope': '仅取得评论计数，未取得评论正文',
    }


class HuitunClient:
    def __init__(self):
        self.stop = Event()

    def fetch(self, board, today):
        yesterday = str(today - timedelta(days=1))
        if board == 'low_fan':
            params = {'gender': '', 'noteType': '', 'lastDays': 3, 'dateStart': str(today - timedelta(days=2)),
                      'dateEnd': str(today), 'page': 1, 'pageSize': 10, 'sort': 0}
        elif board == 'commerce':
            params = {'noteType': '', 'dateStart': yesterday, 'dateEnd': yesterday, 'page': 1, 'pageSize': 10, 'sort': 0}
        else:
            params = {'tagIds': '', 'date': yesterday, 'type': 0, 'page': 1, 'pageSize': 10, 'keyword': ''}
        url = API + BOARDS[board][1] + '?' + urlencode(params)
        headers = {
            'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json',
            'Origin': 'https://xhs.huitun.com', 'Referer': 'https://xhs.huitun.com/',
        }
        # Reuse the project's TLS transport, with verification enabled. Retry
        # one transient read only; login, verification and 429 stop immediately.
        for attempt in range(2):
            checkpoint(self.stop)
            try:
                with Session(timeout=20, trust_env=False) as client:
                    response = client.get(url, headers=headers, allow_redirects=False, stream=True)
                    try:
                        status = response.status_code
                        if status in (401, 403, 429):
                            raise DiscoveryBlocked('灰豚限制访问或要求验证，本批已停止；请稍后重试')
                        if status in (408, 502, 503, 504) and attempt == 0:
                            pass
                        elif status != 200:
                            raise DiscoveryError(f'灰豚榜单请求失败（HTTP {status}）')
                        else:
                            raw = bytearray()
                            for chunk in response.iter_content(chunk_size=65536):
                                checkpoint(self.stop)
                                raw.extend(chunk)
                                if len(raw) > 2_000_000:
                                    raise DiscoveryError('灰豚单页响应超出限额，已停止读取')
                            try:
                                return decode_response(json.loads(raw))
                            except (ValueError, UnicodeError) as error:
                                if isinstance(error, DiscoveryError):
                                    raise
                                raise DiscoveryError('灰豚榜单响应不是有效JSON，未保存为成功结果') from error
                    finally:
                        response.close()
            except RequestException as error:
                if attempt:
                    raise DiscoveryError('灰豚HTTPS连接失败或超时（已重试1次）；请检查网络，未取得本次数据') from error
            if self.stop.wait(0.5):
                checkpoint(self.stop)

    def collect(self, request, stop, emit, warn):
        self.stop = stop
        boards = list(BOARDS) if request.huitun_board == 'all' else [request.huitun_board]
        warn('灰豚免登录公开首屏：每榜最多10条；不代表全量或定向搜索。粉丝和互动为第三方快照，24小时加购未取得。', informational=True)
        today = datetime.now(CN).date()
        for board in boards:
            checkpoint(stop)
            try:
                rows = self.fetch(board, today)
                checkpoint(stop)
                if not rows:
                    raise DiscoveryError(BOARDS[board][0] + '本次没有返回公开样本')
                emitted = skipped = 0
                for raw in rows:
                    checkpoint(stop)
                    if board == 'goods':
                        product = normalize_product(raw)
                        if product is None:
                            warn('商品榜一条记录缺少有效商品ID，已跳过')
                            continue
                        item = {'platform': 'huitun', 'origin_platform': 'xiaohongshu', 'kind': 'product',
                                'source': 'huitun_public_rank', 'note_id': product['product_id'],
                                'source_board': board, 'source_board_label': BOARDS[board][0],
                                'title': product['title'], 'body': '', 'url': product['url'],
                                'author': product['shop_name'], 'followers': None, 'products': [product],
                                'comment_items': [], 'collection_access': 'anonymous',
                                'metrics_scope': '灰豚商品榜快照；销量口径以原榜单为准', 'comments_scope': '商品记录，不是笔记'}
                    else:
                        item = normalize_note(raw, board)
                        if not item['products'] and board != 'low_fan':
                            skipped += 1
                            continue
                    emit(item)
                    emitted += 1
                if skipped:
                    warn(f'{BOARDS[board][0]}：跳过{skipped}条未取得有效挂载商品的笔记；正文提及商品或榜单名称不算挂载证据', informational=True)
                warn(f'{BOARDS[board][0]}：本次读取{emitted}条公开记录（跨榜重复笔记合并）', informational=True)
            except DiscoveryBlocked:
                raise
            except DiscoveryError as error:
                checkpoint(stop)
                warn(BOARDS[board][0] + '：' + str(error))
