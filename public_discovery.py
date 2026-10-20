"""Bounded public-page observations, with no saved login cookies or profiles."""
from __future__ import annotations

import os
import re
from time import time
from urllib.parse import parse_qs, urlsplit, urljoin

from discovery_adapters import DiscoveryError, attached_products, checkpoint, comment_rows
from server_limits import limited_browser
from source.expansion.converter import Converter
from viral_notes import follower_count, normalize_note, parse_count


def note_media(raw, products):
    """Preserve observed images and explicit merchandise evidence on the host."""
    urls = []
    rows = raw.get('imageList') or raw.get('image_list') or []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        url = row.get('urlDefault') or row.get('url') or row.get('urlPre')
        if not url:
            info = row.get('infoList') or row.get('info_list') or []
            url = next((v.get('url') for v in info if isinstance(v, dict) and v.get('url')), None)
        if isinstance(url, str) and url.startswith(('https://', 'http://')) and url not in urls:
            urls.append(url)
    return {'note_type': {'normal': 'graphic', 'video': 'video'}.get(raw.get('type'), 'unknown'),
            'cover_url': urls[0] if urls else '', 'image_urls': urls,
            'image_scope': 'detail_returned_image_list', 'full_image_set_observed': False,
            'body_scope': 'detail_returned_text_unverified_completeness',
            'mounted_product_evidence': {'status': 'observed' if products else 'missing',
                'source_field': 'detail_explicit_merchandise_container',
                'product_ids': [p['product_id'] for p in products if p.get('product_id')]}}


def public_target(url, kind):
    try:
        p = urlsplit(url)
        if (p.scheme == 'https' and p.hostname in {'xhslink.com', 'xhslink.cn'} and not p.username
                and not p.password and p.port in (None, 443) and re.fullmatch(r'/(?:m|o)/[a-zA-Z0-9]+/?', p.path)):
            return 'share:' + p.path
        pattern = r'/(?:explore|discovery/item|search_result)/([a-fA-F0-9]{24})/?' if kind == 'detail' else r'/goods-detail/([a-fA-F0-9]{24})/?'
        match = re.fullmatch(pattern, p.path)
        if (p.scheme != 'https' or p.hostname not in {'www.xiaohongshu.com', 'xiaohongshu.com'}
                or p.username or p.password or p.port not in (None, 443) or not match):
            raise ValueError()
        return match[1]
    except (ValueError, TypeError):
        raise DiscoveryError('请填写 HTTPS 小红书完整笔记分享链接或 goods-detail 商品链接') from None


def resolve_public_target(url, kind, stop):
    """Resolve only normal public redirects, validating each host before access."""
    if not public_target(url, kind).startswith('share:'):
        return url
    from curl_cffi.requests import Session
    with Session(timeout=15, trust_env=False, headers={'User-Agent': 'Mozilla/5.0'}) as session:
        for _ in range(4):
            checkpoint(stop)
            try:
                response = session.get(url, allow_redirects=False)
                if response.status_code not in (301, 302, 303, 307, 308):
                    break
                url = urljoin(url, response.headers.get('Location', ''))
                identity = public_target(url, kind)
                if not identity.startswith('share:'):
                    return url
            except DiscoveryError:
                raise
            except Exception as error:
                raise DiscoveryError('公开分享短链解析失败；未加载登录信息') from error
    raise DiscoveryError('公开分享短链未跳转到匹配的商品或笔记详情')


def commerce_observation(payload, url, *, observed_at=None):
    """Accept only an explicit rolling-24h cart label on this SKU's own page."""
    from xhs_products import parse_h5_product_response
    product = parse_h5_product_response(payload, url)[0]  # Checks success and SKU identity.
    observed_at = time() if observed_at is None else observed_at
    components = {}
    for part in payload['data']['template_data']:
        if isinstance(part, dict):
            components.update(part)
    matches = []
    # Visible merchant page text only. Do not mine tracking, recommendations or reviews.
    def scan(node, path):
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, (dict, list)):
                    scan(value, path + '.' + key)
                elif isinstance(value, str) and (key.lower().endswith('text') or key in {'label', 'title'}):
                    normalized = re.sub(r'\s+', '', value)
                    m = re.fullmatch(r'(?:近|最近|过去)?24小时(?:内)?(?:加购(?:人数|人次|量)?|加入购物车(?:人数|人次)?)[：:]?([0-9][0-9,]*)(人|次|件)?', normalized)
                    reverse = re.fullmatch(r'(?:近|最近|过去)?24小时(?:内)?([0-9][0-9,]*)(\+?)(人|次|件)?(?:加购|加入购物车)', normalized)
                    match = m or reverse
                    if match:
                        matches.append({'value': int(match[1].replace(',', '')), 'unit': (m[2] if m else reverse[3]) or '页面未注明',
                                        'comparison': 'gte' if reverse and reverse[2] else 'eq',
                                        'raw_text': value, 'field': path + '.' + key})
        elif isinstance(node, list):
            for index, value in enumerate(node):
                scan(value, path + f'[{index}]')
    for key in ('priceH5', 'descriptionH5', 'descriptionMain'):
        scan(components.get(key, {}), key)
    cart = {'status': 'missing', 'value': None, 'window_hours': 24, 'product_id': product.product_id,
            'source': 'anonymous_product_page', 'source_url': url.split('?')[0], 'observed_at': observed_at,
            'reason': '商品公开响应未提供可确认的24小时加购；已售、累计加购和互动不代替该指标'}
    if len({(m['value'], m['unit'], m['comparison']) for m in matches}) == 1:
        cart.update(matches[0], status='observed', reason='商品本页明确标注24小时口径；按页面原文保留单位')
    elif matches:
        cart.update(status='conflicting', reason='同页24小时加购文本冲突，待核验')
    sold = re.fullmatch(r'已售\s*([0-9][0-9,]*)\s*(?:件)?', product.sales)
    return {'product_id': product.product_id, 'title': product.title, 'url': url,
            'source': 'xiaohongshu.com', 'price': product.price, 'images': product.images, 'specs': product.specs,
            'sales_text': product.sales, 'sales_total': int(sold[1].replace(',', '')) if sold else None,
            'observed_at': observed_at, 'cart_24h': cart}


def load_public_product(url):
    """Observed H5 GET contract (2026-10-01); fresh session, no login or retries."""
    from curl_cffi.requests import Session
    from xhs_products import DETAIL_API_PATH, parse_h5_product_response
    identity = public_target(url, 'product')
    if identity.startswith('share:'):
        raise DiscoveryError('商品短链尚未解析')
    try:
        with Session(timeout=20, trust_env=False, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}) as session:
            response = session.get('https://mall.xiaohongshu.com' + DETAIL_API_PATH,
                                   params={'version': '0.0.5', 'item_id': identity}, allow_redirects=False)
        if response.status_code != 200:
            raise DiscoveryError(f'公开商品接口 HTTP {response.status_code}，本次未取得商品')
        payload = response.json()
        parse_h5_product_response(payload, url)  # Ensure the response belongs to the requested SKU.
        return payload, url
    except DiscoveryError:
        raise
    except Exception as error:
        raise DiscoveryError('公开商品接口未返回匹配详情；可能是商品失效、网络异常或访问验证') from error


class PublicXhsClient:
    def collect(self, request, stop, emit, warn):
        checkpoint(stop)
        if request.mode in {'detail', 'product'}:
            request = request.model_copy(update={'query': resolve_public_target(request.query, request.mode, stop)})
        if request.mode == 'product':
            expected = public_target(request.query, 'product')
            try:
                payload, final = load_public_product(request.query)
                if public_target(final, 'product') != expected:
                    raise ValueError('Product redirect mismatch')
                product = commerce_observation(payload, final)
            except Exception as error:
                raise DiscoveryError('公开商品页未取得有效数据（加载超时、访问验证或商品失效）；已保留其他任务结果') from error
            checkpoint(stop)
            emit({'platform': 'xiaohongshu', 'kind': 'product', 'note_id': expected,
                  'title': product['title'], 'body': '', 'url': request.query, 'source': 'anonymous_h5_product',
                  'products': [product], 'comment_items': [], 'followers': None,
                  'collection_access': 'anonymous', 'comments_scope': '商品页，不是笔记'})
        elif request.mode == 'detail':
            self.note(request, stop, emit, warn)
        else:
            raise DiscoveryError('公开关键词搜索尚未取得可用笔记结果；请添加完整分享链接，或选用已登录搜索。商品和已知笔记任务将独立执行')

    @limited_browser
    def note(self, request, stop, emit, warn):
        from playwright.sync_api import sync_playwright
        expected = public_target(request.query, 'detail')
        with sync_playwright() as driver:
            browser = driver.chromium.launch(headless=True, **({'channel': os.getenv('XHS_PRODUCT_BROWSER_CHANNEL', 'msedge')} if os.name == 'nt' else {}))
            try:
                context = browser.new_context(viewport={'width': 1280, 'height': 900})
                page = context.new_page()
                try:
                    page.goto(request.query, wait_until='domcontentloaded', timeout=30000)
                    if stop.wait(2):
                        checkpoint(stop)
                    conv = Converter()
                    raw_state = conv._extract_object(page.content())
                    data = conv._convert_object(raw_state) if raw_state else {}
                    raw = conv._filter_object(data)
                    if not isinstance(raw, dict) or str(raw.get('noteId') or raw.get('note_id') or '') != expected:
                        raise DiscoveryError('公开笔记页未返回匹配正文（可能跳转首页、登录或验证页）')
                    token = (parse_qs(urlsplit(request.query).query).get('xsec_token') or [''])[0]
                    note = normalize_note(raw, token)
                    note.update(url=request.query, body=note.pop('description'), platform='xiaohongshu', kind='note',
                                source='anonymous_share_page', collection_access='anonymous', followers=None,
                                followers_observed_at=None, products=attached_products(raw))
                    detail = (data.get('note', {}).get('noteDetailMap', {}) or {}).get(expected, {})
                    comments = detail.get('comments', {})
                    note['comment_items'] = comment_rows(comments.get('list', []), request.comments, xhs=True)
                    note['comments_scope'] = '公开页实际返回的评论样本；评论计数不代表取得评论全文'
                    note['metrics_raw'] = raw.get('interactInfo') or raw.get('interact_info') or {}
                    uid = note['author_id']
                    if re.fullmatch('[a-fA-F0-9]{24}', uid):
                        checkpoint(stop)
                        try:
                            profile_url = 'https://www.xiaohongshu.com/user/profile/' + uid
                            page.goto(profile_url, wait_until='domcontentloaded', timeout=20000)
                            if stop.wait(2):
                                checkpoint(stop)
                            state = conv._extract_object(page.content())
                            profile = conv._convert_object(state) if state else {}
                            if urlsplit(page.url).path.rstrip('/') == '/user/profile/' + uid:
                                info = profile.get('user', {}).get('userPageData', {})
                                note['followers'] = follower_count(info)
                                if note['followers'] is not None:
                                    note.update(followers_observed_at=time(), followers_source=profile_url)
                        except DiscoveryError:
                            raise
                        except Exception:
                            pass  # Author failure must not discard the obtained note.
                    if note['followers'] is None:
                        warn('公开作者页未取得粉丝数；该笔记保留但不确认低粉', informational=True)
                    checkpoint(stop)
                    note.update(note_media(raw,note['products']))
                    emit(note)
                except DiscoveryError:
                    raise
                except Exception as error:
                    raise DiscoveryError('公开笔记加载失败或超时；未使用保存的登录信息') from error
            finally:
                browser.close()
