# -*- coding: utf-8 -*-
"""
星河影视 (https://xhkan1.top) —— FongMi / 影视仓 / 默影视 / OK影视 / TVBox  drpy-python 源   v1

站点形态：自研 Next.js SPA + JSON API（数据源为 360kan 聚合），无会员墙，四端通用。
风控说明：首页 HTML 有滑动验证盾（403），但 /api/* 接口不校验盾 cookie，
          仅需常规 UA + `X-Requested-With: XMLHttpRequest` 即 200，实测移动 UA / PC UA / okhttp UA 均可。
          若壳端被 403，优先检查是否漏带 X-Requested-With。

接口（2026-09 实测）：
  GET  /api/config                                        站点配置（分类/筛选/热词）
  GET  /api/filter?catId=1&page=1[&type=&area=&year=&size=]  分类列表  total/currentPage
         catId: 1电影 2电视剧 3综艺 4动漫；筛选项为中文值；size 默认 24，上限实测 50
  GET  /api/detail?cat=&id=                              详情；id 为 ENID（如 QbZsbn7nTGHmMn）
         [+&site=qiyi&start=1&end=N] 取剧集分页（start>=1，end<=total，每批 <=50）
  GET  /api/search?q=&page=                              搜索
  GET  /api/player/token                                 播放凭证 {disabled,nonce,timestamp,sig}
  POST /api/player/resolve {playUrl,nonce?,timestamp?,sig?,statVodId,statSource,statVodName}
         → {success,mode:"direct",url:m3u8,useProxy,encrypted}
  POST /api/player/decrypt {encrypted,nonce} → {url}
  GET  /api/player/proxy?url=                            仅在 useProxy=true 时使用

播放：resolve 服务端走"管解"（第三方解析）把站点外链解析为 m3u8 直链，实测电影/剧集均成功，
      useProxy=false，直链可直接播（带 Referer 更稳）。

依赖：硬 import 仅 http.client / json / re / time / urllib.parse；gzip / zlib / io / ssl / threading 全部软降级。
"""

import re
import json
import time
import urllib.parse

try:
    import http.client as _hc
except Exception:      # 极端环境（依赖模块被壳端屏蔽）下不崩，请求直接返回失败
    _hc = None

try:
    import gzip
except Exception:
    gzip = None
try:
    import io
except Exception:
    io = None
try:
    import zlib
except Exception:
    zlib = None

try:
    import ssl as _ssl
    _CTX = _ssl.create_default_context()
    _CTX.check_hostname = False
    _CTX.verify_mode = _ssl.CERT_NONE
    _HAS_SSL = True
except Exception:
    _CTX = None
    _HAS_SSL = False

try:
    import threading
except Exception:
    threading = None

SITE_NAME = '星河影视'
HOSTS = ['https://xhkan1.top']

MOBILE_UA = ('Mozilla/5.0 (Linux; Android 13; 22127RK46C) AppleWebKit/537.36 '
             '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36')
PC_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
         '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')

TIMEOUT = 10
_CACHE_TTL = 180
_CACHE_MAX = 160

CLASSES = [('1', '电影'), ('2', '电视剧'), ('3', '综艺'), ('4', '动漫')]

# catId -> filterConfig 键
_CFG_KEY = {'1': 'movie', '2': 'tv', '3': 'variety', '4': 'anime'}

SITE_NAMES = {
    'qiyi': '爱奇艺', 'qiyi1': '爱奇艺', 'qq': '腾讯视频', 'youku': '优酷', 'mgtv': '芒果TV',
    'imgo': '芒果TV', 'bilibili': '哔哩哔哩', 'bilibili1': '哔哩哔哩', 'leshi': '乐视',
    'sohu': '搜狐', 'pptv': 'PPTV', '1905': '1905电影网', 'xigua': '西瓜视频', 'migu': '咪咕',
}

_LOCAL = threading.local() if threading else None
if _LOCAL is None:
    _LOCAL = type('L', (), {})()
_ALL_CONNS = []
_CACHE = {}
_T0 = time.time()


def _log(*a):
    try:
        print('[xhkan1]', *a)
    except Exception:
        pass


def _ms():
    return (time.time() - _T0) * 1000.0


# ---------------- 缓存 ----------------
def _ck(url):
    if '://' in url:
        return url.split('://', 1)[1]
    return url


def _cache_get(key):
    item = _CACHE.get(key)
    if not item:
        return None
    ts, val = item
    if time.time() - ts > _CACHE_TTL:
        _CACHE.pop(key, None)
        return None
    return val


def _cache_put(key, val):
    if not key or not val or len(val) < 80:
        return
    if len(_CACHE) > _CACHE_MAX:
        for k in list(_CACHE)[:32]:
            _CACHE.pop(k, None)
    _CACHE[key] = (time.time(), val)


# ---------------- 连接池 ----------------
def _pool():
    p = getattr(_LOCAL, 'pool', None)
    if p is None:
        p = {}
        _LOCAL.pool = p
    return p


def _new_conn(scheme, netloc, timeout):
    host, port = netloc, None
    if ':' in netloc:
        h, _, p = netloc.partition(':')
        if p.isdigit():
            host, port = h, int(p)
    if scheme == 'https':
        return _hc.HTTPSConnection(host, port, timeout=timeout, context=_CTX)
    return _hc.HTTPConnection(host, port, timeout=timeout)


def _drop(key):
    conn = _pool().pop(key, None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        try:
            _ALL_CONNS.remove(conn)
        except Exception:
            pass


def _decompress(raw, ce):
    if not raw:
        return b''
    if raw[:2] == b'\x1f\x8b':
        if gzip is not None and io is not None:
            try:
                return gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
            except Exception:
                pass
        if zlib is not None:
            try:
                return zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(raw)
            except Exception:
                pass
    elif 'deflate' in (ce or '').lower() and zlib is not None:
        for wb in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
            try:
                return zlib.decompress(raw, wb)
            except Exception:
                pass
    return raw


def _decode_text(raw):
    if not raw:
        return ''
    try:
        return raw.decode('utf-8')
    except Exception:
        pass
    for enc in ('gbk', 'gb18030', 'big5'):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode('utf-8', 'ignore')


def _fetch(url, method='GET', body=None, headers=None, timeout=TIMEOUT, cache=False):
    """线程本地长连接请求（自动跟随 301/302），返回 (status, text)；status<0 异常"""
    if not url or _hc is None:
        return -1, ''
    if not url.startswith('http'):
        url = 'http://' + url
    if url.startswith('https') and not _HAS_SSL:
        url = 'http://' + url[8:]
    ckey = (method or 'GET').upper() + '|' + _ck(url)
    if cache and body is None:
        hit = _cache_get(ckey)
        if hit is not None:
            _log('cache hit %d bytes %s' % (len(hit), url[-46:]))
            return 200, hit

    hops = 0
    last = (-1, '')
    while True:
        scheme, _, rest = url.partition('://')
        netloc, _, path = rest.partition('/')
        path = '/' + path
        if '?' in netloc:
            netloc, _, q = netloc.partition('?')
            path = '/' + q + path[1:] if False else path
        key = scheme + '://' + netloc
        p = _pool()
        try:
            conn = p.get(key)
            if conn is None:
                conn = _new_conn(scheme, netloc, timeout)
                p[key] = conn
                _ALL_CONNS.append(conn)
            conn.request(method, path, body=body, headers=headers or {})
            resp = conn.getresponse()
            status = resp.status
            ce = resp.getheader('Content-Encoding', '')
            cl = resp.getheader('Connection', '')
            loc = resp.getheader('Location', '')
            raw = resp.read()
            if cl and cl.lower() == 'close':
                _drop(key)
        except Exception as e:
            _drop(key)
            last = (-1, 'EXC %s: %s' % (type(e).__name__, e))
            break
        last = (status, _decode_text(_decompress(raw, ce)))
        if status in (301, 302, 303, 307, 308) and loc and hops < 2:
            url = urllib.parse.urljoin(url, loc)
            hops += 1
            if method != 'GET':
                method, body = 'GET', None
            continue
        break
    if cache and last[0] == 200 and last[1]:
        _cache_put(ckey, last[1])
    return last


def _norm_extend(ext):
    """壳端 extend 兼容：dict / JSON 串 / form 串 / None → dict"""
    try:
        if ext is None:
            return {}
        if isinstance(ext, dict):
            return ext
        s = str(ext).strip()
        if not s:
            return {}
        if s.startswith('{'):
            try:
                d = json.loads(s)
                return d if isinstance(d, dict) else {}
            except Exception:
                return {}
        d = {}
        for kv in s.split('&'):
            if '=' in kv:
                k, v = kv.split('=', 1)
                d[urllib.parse.unquote(k)] = urllib.parse.unquote(v)
            elif kv:
                d[kv] = ''
        return d
    except Exception:
        return {}


def _fix_pic(u):
    u = (u or '').strip()
    if u.startswith('//'):
        u = 'https:' + u
    return u


class Spider(object):
    def __init__(self, extend=''):
        self.host = HOSTS[0]
        self.extend = _norm_extend(extend)
        self.header = {
            'User-Agent': MOBILE_UA,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Referer': self.host + '/',
            'X-Requested-With': 'XMLHttpRequest',
        }
        self.timeout = TIMEOUT
        self._cfg = None
        self._filters = None
        self._warm = None

    # ---------------- 壳接口 ----------------
    def init(self, extend=''):
        ext = _norm_extend(extend) or self.extend
        if isinstance(ext, dict) and ext:
            u = ext.get('url') or ext.get('host') or ext.get('ext') or ''
            if isinstance(u, str) and u.startswith('http'):
                self.host = u.rstrip('/')
                self.header['Referer'] = self.host + '/'
        _log('init host=%s' % self.host)
        try:
            if threading is not None and self._warm is None:
                t = threading.Thread(target=self._warmup)
                t.daemon = True
                t.start()
                self._warm = t
        except Exception:
            self._warm = None

    def _warmup(self):
        try:
            self._config()
            for tid, _n in CLASSES:
                self.get_json('/api/filter?catId=%s&page=1' % tid, cache=True)
            _log('warmup done %.0fms filters=%d' % (_ms(), len(self._filters or {})))
        except Exception:
            pass

    def _join_warm(self, max_wait=1.2):
        try:
            if self._warm is not None:
                self._warm.join(max_wait)
        except Exception:
            pass

    def getName(self):
        return SITE_NAME

    def getDependence(self):
        return []

    def isVideoFormat(self, url):
        if not url:
            return False
        return bool(re.search(r'\.(?:m3u8|mp4|flv|mkv|ts)(?:\?|$)', url, re.I))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        for c in list(_ALL_CONNS):
            try:
                c.close()
            except Exception:
                pass
        try:
            _ALL_CONNS.clear()
        except Exception:
            pass
        try:
            _pool().clear()
        except Exception:
            pass
        return

    # ---------------- 请求 ----------------
    def get_json(self, path, cache=True, timeout=None):
        if not path.startswith('http'):
            path = self.host + (path if path.startswith('/') else '/' + path)
        st, txt = _fetch(path, 'GET', None, self.header, timeout or self.timeout, cache=cache)
        if st != 200 or not txt:
            _log('GET FAIL %s -> %s' % (path[-70:], st if st else (txt or '')[:60]))
            return None
        try:
            return json.loads(txt)
        except Exception as e:
            _log('JSON ERR %s %s' % (path[-50:], e))
            return None

    def post_json(self, path, body, timeout=None):
        if not path.startswith('http'):
            path = self.host + (path if path.startswith('/') else '/' + path)
        h = dict(self.header)
        h['Content-Type'] = 'application/json;charset=UTF-8'
        h['X-Player-Request'] = '1'
        try:
            data = json.dumps(body, ensure_ascii=False).encode('utf-8')
        except Exception:
            return None
        st, txt = _fetch(path, 'POST', data, h, timeout or max(self.timeout, 30), cache=False)
        if st != 200 or not txt:
            _log('POST FAIL %s -> %s %s' % (path[-40:], st, (txt or '')[:80]))
            return None
        try:
            return json.loads(txt)
        except Exception:
            return None

    # ---------------- 配置 / 筛选 ----------------
    def _config(self):
        if self._cfg:
            return self._cfg
        j = self.get_json('/api/config', cache=True)
        if isinstance(j, dict):
            self._cfg = j
        return self._cfg or {}

    def _years(self, cfg):
        out = ['全部']
        try:
            n = int((cfg.get('filterConfig') or {}).get('yearCount') or 12)
        except Exception:
            n = 12
        y = time.localtime().tm_year
        for i in range(n):
            out.append(str(y - i))
        return out

    def _filters_all(self):
        if self._filters:
            return self._filters
        cfg = self._config()
        fc = cfg.get('filterConfig') or {}
        years = self._years(cfg)
        out = {}
        for tid in ('1', '2', '3', '4'):
            seg = fc.get(_CFG_KEY[tid]) or {}
            arr = []
            types = [x for x in (seg.get('types') or []) if x]
            if types:
                arr.append({'key': 'type', 'name': '类型',
                            'value': [{'n': x, 'v': ('' if x == '全部' else x)} for x in types]})
            areas = [x for x in (seg.get('areas') or []) if x]
            if areas:
                arr.append({'key': 'area', 'name': '地区',
                            'value': [{'n': x, 'v': ('' if x == '全部' else x)} for x in areas]})
            if years:
                arr.append({'key': 'year', 'name': '年份',
                            'value': [{'n': x, 'v': ('' if x == '全部' else x)} for x in years]})
            if arr:
                out[tid] = arr
        if out:
            self._filters = out
        return out

    # ---------------- 映射 ----------------
    def _list_item(self, m, cat):
        pic = _fix_pic(m.get('cdncover') or m.get('cover') or '')
        try:
            total = int(m.get('total') or 0)
        except Exception:
            total = 0
        remark = ''
        if total > 1:
            remark = '更新至%d集' % total
        elif m.get('pubdate'):
            remark = str(m.get('pubdate'))[:10]
        return {
            'vod_id': '%s|%s' % (cat, m.get('id') or ''),
            'vod_name': (m.get('title') or '').strip(),
            'vod_pic': pic,
            'vod_remarks': remark,
            'vod_year': str(m.get('pubdate') or '')[:4],
        }

    def _filter_list(self, cat, page, ext):
        q = ['catId=%s' % cat, 'page=%d' % page]
        for k in ('type', 'area', 'year'):
            v = (ext or {}).get(k)
            v = '' if v is None else str(v)
            if v and v not in ('全部', 'all'):
                q.append('%s=%s' % (k, urllib.parse.quote(v)))
        j = self.get_json('/api/filter?' + '&'.join(q), cache=True)
        if not isinstance(j, dict):
            return [], 0
        movies = j.get('movies') or []
        total = j.get('total') or 0
        try:
            total = int(total)
        except Exception:
            total = 0
        return [self._list_item(m, cat) for m in movies if m.get('id')], total

    # ---------------- 首页 ----------------
    def homeContent(self, filter=False):
        try:
            self._join_warm(1.5)
            lst, _total = self._filter_list('1', 1, {})
            fl = self._filters_all()
            _log('home list=%d filters=%s' % (len(lst), sorted(fl)))
            return {'class': [{'type_id': t, 'type_name': n} for t, n in CLASSES],
                    'filters': fl, 'list': lst}
        except Exception as e:
            _log('homeContent ERR %s: %s' % (type(e).__name__, e))
            return {'class': [{'type_id': t, 'type_name': n} for t, n in CLASSES],
                    'filters': {}, 'list': []}

    def homeVideoContent(self):
        try:
            lst, _t = self._filter_list('1', 1, {})
            return {'list': lst}
        except Exception as e:
            _log('homeVideoContent ERR %s' % e)
            return {'list': []}

    # ---------------- 分类 ----------------
    def categoryContent(self, tid, pg=1, filter=False, extend=None):
        tid = str(tid or '1')
        if tid not in ('1', '2', '3', '4'):
            tid = '1'
        try:
            page = int(pg or 1)
        except Exception:
            page = 1
        try:
            ext = _norm_extend(extend)
            vlist, total = self._filter_list(tid, page, ext)
            pc = page
            if total > 0:
                pc = int(total / 24) + (1 if total % 24 else 0)
                pc = min(max(pc, 1), 3000)
            res = {'list': vlist, 'page': page, 'pagecount': pc,
                   'limit': len(vlist), 'total': total or 999999}
            fl = self._filters_all()
            if fl.get(tid):
                res['filters'] = {tid: fl[tid]}
            _log('cat tid=%s pg=%s list=%d total=%s ext=%s' % (tid, page, len(vlist), total, ext))
            return res
        except Exception as e:
            _log('categoryContent ERR %s: %s' % (type(e).__name__, e))
            return {'list': [], 'page': page, 'pagecount': page, 'limit': 0, 'total': 0}

    # ---------------- 详情 ----------------
    def _detail(self, cat, enid, cache=True):
        return self.get_json('/api/detail?cat=%s&id=%s' % (cat, enid), cache=cache)

    def _episode_names(self, cat, enid, site, d):
        """返回 [(集号, 集名)]；电影返回 [(0, '正片')]"""
        pld = d.get('playlinksdetail') or {}
        try:
            total = int(d.get('total') or 0)
        except Exception:
            total = 0
        upinfo = d.get('allupinfo') or {}
        try:
            site_total = int(upinfo.get(site) or 0) or total
        except Exception:
            site_total = total
        if cat == '1' or site_total <= 1:
            item = pld.get(site) or {}
            if item.get('default_url') or item.get('pageurl') or item.get('mini_url'):
                return [(0, '正片')]
            return []
        eps, seen = [], set()
        start = 1
        while start <= site_total and len(seen) < 4000:
            end = min(start + 49, site_total)
            j = self.get_json('/api/detail?cat=%s&id=%s&site=%s&start=%d&end=%d' % (cat, enid, site, start, end), cache=True)
            arr = (((j or {}).get('data') or {}).get('allepidetail') or {}).get(site) or []
            if not arr:
                break
            for it in arr:
                try:
                    n = int(it.get('playlink_num') or 0)
                except Exception:
                    n = 0
                if n <= 0 or n in seen or not it.get('url'):
                    continue
                seen.add(n)
                eps.append((n, '第%d集' % n))
            if end >= site_total:
                break
            start = end + 1
        eps.sort(key=lambda x: x[0])
        return eps

    def detailContent(self, ids):
        raw = ids[0] if isinstance(ids, (list, tuple)) else ids
        raw = str(raw or '')
        cat, _, enid = raw.partition('|')
        if cat not in ('1', '2', '3', '4') or not enid:
            _log('detail bad id %s' % raw)
            return {'list': []}
        try:
            t0 = time.time()
            j = self._detail(cat, enid)
            d = (j or {}).get('data') or {}
            if not d:
                _log('detail EMPTY %s' % raw)
                return {'list': []}
            pld = d.get('playlinksdetail') or {}
            sites = d.get('playlink_sites') or list(pld.keys())
            # 多线路并发抓集数（剧集需按 start/end 分页，单线路最坏多轮请求）
            ep_map = {}
            if threading is not None and len(sites) > 1:
                lock = threading.Lock()

                def _work(si):
                    try:
                        r = self._episode_names(cat, enid, si, d)
                    except Exception:
                        r = []
                    try:
                        lock.acquire()
                        ep_map[si] = r
                    finally:
                        try:
                            lock.release()
                        except Exception:
                            pass

                ths = []
                for si in sites:
                    t = threading.Thread(target=_work, args=(si,))
                    t.daemon = True
                    t.start()
                    ths.append(t)
                for t in ths:
                    try:
                        t.join(9)
                    except Exception:
                        pass
            else:
                for si in sites:
                    try:
                        ep_map[si] = self._episode_names(cat, enid, si, d)
                    except Exception:
                        ep_map[si] = []
            froms, urls = [], []
            for site in sites:
                eps = ep_map.get(site) or []
                if not eps:
                    continue
                parts = ['%s$%s|%s|%s|%d' % (nm, cat, enid, site, n) for n, nm in eps]
                froms.append(SITE_NAMES.get(site, site))
                urls.append('#'.join(parts))
            if not froms:
                froms = [SITE_NAME]
                urls = ['正片$%s|%s|%s|0' % (cat, enid, (sites or ['qiyi'])[0])]
            cats = d.get('moviecategory') or []
            areas = d.get('area') or []
            actors = d.get('actor') or []
            directors = d.get('director') or []
            try:
                total = int(d.get('total') or 0)
            except Exception:
                total = 0
            remark = ('更新至%d集' % total) if (cat != '1' and total > 1) else '正片'
            _log('detail %s %s from=%d %.0fms' % (cat, enid, len(froms), (time.time() - t0) * 1000))
            return {'list': [{
                'vod_id': raw,
                'vod_name': d.get('title') or '',
                'vod_pic': _fix_pic(d.get('cdncover') or d.get('cover')),
                'vod_remarks': remark,
                'vod_year': str(d.get('pubdate') or '')[:4],
                'vod_area': ' '.join(str(x) for x in areas[:2]),
                'type_name': ' '.join(str(x) for x in cats[:3]),
                'vod_actor': ' '.join(str(x) for x in actors[:8])[:200],
                'vod_director': ' '.join(str(x) for x in directors[:3])[:100],
                'vod_content': (d.get('description') or d.get('comment') or '')[:900],
                'vod_play_from': '$$$'.join(froms),
                'vod_play_url': '$$$'.join(urls),
            }]}
        except Exception as e:
            _log('detailContent ERR %s: %s' % (type(e).__name__, e))
            return {'list': []}

    # ---------------- 搜索 ----------------
    def searchContent(self, key, quick=False, pg=1):
        try:
            page = int(pg or 1)
        except Exception:
            page = 1
        try:
            j = self.get_json('/api/search?q=%s&page=%d' % (urllib.parse.quote(str(key or '')), page), cache=True)
            out = []
            for it in ((j or {}).get('results') or []):
                cat = str(it.get('cat_id') or '1')
                if cat not in ('1', '2', '3', '4'):
                    cat = '1'
                enid = it.get('en_id') or it.get('id') or ''
                if not enid:
                    continue
                ci = it.get('coverInfo') or {}
                out.append({
                    'vod_id': '%s|%s' % (cat, enid),
                    'vod_name': (it.get('titleTxt') or it.get('title') or '').strip(),
                    'vod_pic': _fix_pic(it.get('cover')),
                    'vod_remarks': ci.get('txt') or (it.get('cat_name') or ''),
                    'vod_year': str(it.get('year') or ''),
                })
            _log('search %s pg=%s list=%d' % (key, page, len(out)))
            return {'list': out, 'page': page, 'pagecount': page if out else page,
                    'limit': len(out), 'total': 999999}
        except Exception as e:
            _log('search ERR %s' % e)
            return {'list': [], 'page': page, 'pagecount': page, 'limit': 0, 'total': 0}

    # ---------------- 播放 ----------------
    def _pick_play_url(self, cat, enid, site, n, d):
        pld = d.get('playlinksdetail') or {}
        if cat == '1' or n <= 0:
            item = pld.get(site) or {}
            return item.get('default_url') or item.get('pageurl') or item.get('mini_url') or ''
        j = self.get_json('/api/detail?cat=%s&id=%s&site=%s&start=%d&end=%d' % (cat, enid, site, n, n), cache=True)
        arr = (((j or {}).get('data') or {}).get('allepidetail') or {}).get(site) or []
        for it in arr:
            try:
                if int(it.get('playlink_num') or 0) == n and it.get('url'):
                    return it['url']
            except Exception:
                continue
        return arr[0].get('url') if arr and arr[0].get('url') else ''

    def playerContent(self, flag, id, vipFlags=None):
        header = {'User-Agent': MOBILE_UA, 'Referer': self.host + '/'}
        raw = str(id or flag or '')
        parts = raw.split('|')
        if len(parts) != 4:
            _log('play bad id %s' % raw)
            return {'parse': 1, 'playUrl': '', 'url': raw, 'header': header}
        cat, enid, site, ns = parts
        try:
            n = int(ns)
        except Exception:
            n = 0
        try:
            t0 = time.time()
            j = self._detail(cat, enid)
            d = (j or {}).get('data') or {}
            if not d:
                return {'parse': 1, 'playUrl': '', 'url': raw, 'header': header}
            play_url = self._pick_play_url(cat, enid, site, n, d)
            if not play_url:
                _log('play no url %s' % raw)
                return {'parse': 1, 'playUrl': '', 'url': raw, 'header': header}

            tk = self.get_json('/api/player/token', cache=False) or {}
            body = {
                'playUrl': play_url,
                'statVodId': str(d.get('id') or ''),
                'statSource': site,
                'statVodName': d.get('title') or '',
            }
            if tk.get('disabled') is not True:
                body['nonce'] = tk.get('nonce') or ''
                body['timestamp'] = tk.get('timestamp') or 0
                body['sig'] = tk.get('sig') or ''
            r = self.post_json('/api/player/resolve', body) or {}
            url = r.get('url') or ''
            if r.get('encrypted'):
                dr = self.post_json('/api/player/decrypt',
                                    {'encrypted': r.get('encrypted'), 'nonce': tk.get('nonce') or ''}) or {}
                url = dr.get('url') or url
            if not url:
                _log('play resolve fail %s %s' % (raw, str(r)[:120]))
                return {'parse': 1, 'playUrl': '', 'url': raw, 'header': header}
            if r.get('useProxy'):
                url = self.host + '/api/player/proxy?url=' + urllib.parse.quote(url, safe='')
            _log('play OK %.0fms %s' % ((time.time() - t0) * 1000, url[:90]))
            return {'parse': 0, 'playUrl': '', 'url': url, 'header': header}
        except Exception as e:
            _log('playerContent ERR %s: %s' % (type(e).__name__, e))
            return {'parse': 1, 'playUrl': '', 'url': raw, 'header': header}


# ---------------- 模块级函数别名（兼容不实例化的壳） ----------------
_SINGLETON = None


def _sp():
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = Spider()
        _SINGLETON.init()
    return _SINGLETON


def init(extend=''):
    return _sp().init(extend)


def getName():
    return SITE_NAME


def homeContent(filter=False):
    return _sp().homeContent(filter)


def homeVideoContent():
    return _sp().homeVideoContent()


def categoryContent(tid, pg=1, filter=False, extend=None):
    return _sp().categoryContent(tid, pg, filter, extend)


def detailContent(ids):
    return _sp().detailContent(ids)


def searchContent(key, quick=False, pg=1):
    return _sp().searchContent(key, quick, pg)


def playerContent(flag, id, vipFlags=None):
    return _sp().playerContent(flag, id, vipFlags)


home = homeContent
category = categoryContent
detail = detailContent
search = searchContent
play = playerContent
