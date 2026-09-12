# coding=utf-8
"""
目标站: 大米星球 (www.dmxq39.com)
站点类型: 影视资源站 (MacCMS 苹果CMS)
技术栈: PHP + MacCMS + ArtPlayer + AES加密播放

URL 结构:
    首页: /
    分类: /vodtype/<id>-<page>.html
    筛选: /vodshow/<id>-----------<page>.html?area=..&by=..&class=..&year=..
    详情: /voddetail/<id>.html
    播放: /vodplay/<id>-<line>-<episode>.html
    搜索: /vodsearch/<keyword>-------------.html

播放机制:
    播放页包含 player_aaaa 变量 (JSON)，含 url, from, encrypt 字段。
    encrypt=3: url 经过 AES-CBC 加密，密钥/IV 存储在混淆 JS 中。
    播放器使用 ArtPlayer，通过 /dmplayer.html 加载。

    所有线路均通过嗅探模式 (parse=1) 播放:
    TVBox 内置嗅探器加载播放页，自动拦截 m3u8 请求。

线路类型:
    - xlm3u8: m3u8 资源 (encrypt=3, AES加密)
    - 其他线路: 同样使用嗅探模式

备用域名:
    - dmyy16.top
    - dami13.com
    - dami27.com
    - dmxq.net
    - dami0.com
    动态从首页抓取最新可用域名。

优化:
    1. 多域名故障转移 (站长换域名/单域名宕机时自动切换)
    2. 动态备用域名抓取 (从首页提取最新域名)
    3. 播放页嗅探 + Referer 优化 (确保嗅探成功)
    4. 分类筛选器 (排序/类型/地区/年份)
    5. 下拉自动加载翻页
    6. 连播预取 (后台预解析下一集)
    7. 播放结果缓存 (避免重复解析)
"""
import re
import sys
import json
import time
import base64
import urllib.parse
import urllib.request

try:
    import threading
    _HAS_THREADING = True
except Exception:
    threading = None
    _HAS_THREADING = False

# AES 解密支持 (优先使用 pycryptodome, 回退到纯 Python 实现)
try:
    from Crypto.Cipher import AES as _PyCryptoAES
    _HAS_AES = True
except Exception:
    _PyCryptoAES = None
    _HAS_AES = False

sys.path.append('..')
from base.spider import Spider

# heimuer 播放器 AES 密钥 (从混淆 JS 中提取)
_HEIMUER_AES_KEY = "81f834a7f68d4c52"
_HEIMUER_AES_IV = "zkz8scsGXttFVZBb"

# ==================== 纯 Python AES-128-CBC 解密 ====================
# 当 pycryptodome 不可用时使用

# AES S-box
_AES_SBOX = [
    0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
    0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
    0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
    0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
    0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
    0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
    0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
    0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
    0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
    0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
    0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
    0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
    0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
    0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
    0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
    0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16,
]

# AES 逆 S-box
_AES_INV_SBOX = [0] * 256
for _i in range(256):
    _AES_INV_SBOX[_AES_SBOX[_i]] = _i

# AES 轮常数
_AES_RCON = [0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1b,0x36]

def _aes_xtime(a):
    a <<= 1
    if a & 0x100:
        a ^= 0x11b
    return a & 0xff

def _aes_mul(a, b):
    r = 0
    while b:
        if b & 1:
            r ^= a
        a = _aes_xtime(a)
        b >>= 1
    return r

def _aes_key_expansion(key):
    """AES-128 密钥扩展: 16字节 -> 176字节 (44个4字节字)"""
    w = list(key)
    for i in range(4, 44):
        temp = w[(i-1)*4:(i-1)*4+4]
        if i % 4 == 0:
            temp = temp[1:] + temp[:1]
            temp = [_AES_SBOX[b] for b in temp]
            temp[0] ^= _AES_RCON[i//4 - 1]
        for j in range(4):
            w.append(w[(i-4)*4+j] ^ temp[j])
    return w

def _aes_inv_sub_bytes(state):
    return [_AES_INV_SBOX[b] for b in state]

def _aes_inv_shift_rows(state):
    s = state[:]
    # Row 1: shift right 1
    s[1],s[5],s[9],s[13] = s[13],s[1],s[5],s[9]
    # Row 2: shift right 2
    s[2],s[6],s[10],s[14] = s[10],s[14],s[2],s[6]
    # Row 3: shift right 3
    s[3],s[7],s[11],s[15] = s[7],s[11],s[15],s[3]
    return s

def _aes_inv_mix_columns(state):
    s = state[:]
    for c in range(4):
        i = c * 4
        a = s[i:i+4]
        s[i]   = _aes_mul(a[0],0x0e) ^ _aes_mul(a[1],0x0b) ^ _aes_mul(a[2],0x0d) ^ _aes_mul(a[3],0x09)
        s[i+1] = _aes_mul(a[0],0x09) ^ _aes_mul(a[1],0x0e) ^ _aes_mul(a[2],0x0b) ^ _aes_mul(a[3],0x0d)
        s[i+2] = _aes_mul(a[0],0x0d) ^ _aes_mul(a[1],0x09) ^ _aes_mul(a[2],0x0e) ^ _aes_mul(a[3],0x0b)
        s[i+3] = _aes_mul(a[0],0x0b) ^ _aes_mul(a[1],0x0d) ^ _aes_mul(a[2],0x09) ^ _aes_mul(a[3],0x0e)
    return s

def _aes_add_round_key(state, w, round):
    for i in range(16):
        state[i] ^= w[round*16 + i]
    return state

def _aes_decrypt_block(block, expanded_key):
    """解密单个 16 字节块"""
    state = list(block)
    state = _aes_add_round_key(state, expanded_key, 10)
    for r in range(9, 0, -1):
        state = _aes_inv_shift_rows(state)
        state = _aes_inv_sub_bytes(state)
        state = _aes_add_round_key(state, expanded_key, r)
        state = _aes_inv_mix_columns(state)
    state = _aes_inv_shift_rows(state)
    state = _aes_inv_sub_bytes(state)
    state = _aes_add_round_key(state, expanded_key, 0)
    return bytes(state)

def _aes_cbc_decrypt(ciphertext, key, iv):
    """AES-128-CBC 解密 + PKCS7 去填充"""
    key_bytes = key.encode('utf-8') if isinstance(key, str) else key
    iv_bytes = iv.encode('utf-8') if isinstance(iv, str) else iv

    if _HAS_AES:
        # 使用 pycryptodome
        cipher = _PyCryptoAES.new(key_bytes, _PyCryptoAES.MODE_CBC, iv_bytes)
        plaintext = cipher.decrypt(ciphertext)
    else:
        # 纯 Python 实现
        expanded_key = _aes_key_expansion(list(key_bytes))
        plaintext = b''
        prev = iv_bytes
        for i in range(0, len(ciphertext), 16):
            block = ciphertext[i:i+16]
            decrypted = _aes_decrypt_block(block, expanded_key)
            plaintext += bytes(a ^ b for a, b in zip(decrypted, prev))
            prev = block

    # PKCS7 去填充
    if plaintext and len(plaintext) > 0:
        pad_len = plaintext[-1]
        if 1 <= pad_len <= 16 and all(b == pad_len for b in plaintext[-pad_len:]):
            plaintext = plaintext[:-pad_len]

    return plaintext.decode('utf-8', errors='ignore')


def _decrypt_heimuer_url(encrypted_url):
    """
    解密 heimuer 播放器 encrypt=3 的 URL
    1. URL 预处理: O0O0O -> =, o000o -> +, oo00o -> /
    2. Base64 解码
    3. AES-128-CBC 解密
    """
    try:
        # URL 预处理
        processed = encrypted_url
        processed = processed.replace('O0O0O', '=')
        processed = processed.replace('o000o', '+')
        processed = processed.replace('oo00o', '/')

        # Base64 解码
        # 补齐 padding
        missing = len(processed) % 4
        if missing:
            processed += '=' * (4 - missing)

        ciphertext = base64.b64decode(processed)

        # AES-CBC 解密
        plaintext = _aes_cbc_decrypt(ciphertext, _HEIMUER_AES_KEY, _HEIMUER_AES_IV)

        return plaintext if plaintext else None
    except Exception:
        return None

# 缓存 TTL (秒)
_HOME_CACHE_TTL = 300
_PLAY_HTML_TTL = 120
_PLAY_RESULT_TTL = 600
_DOMAIN_CACHE_TTL = 3600

# 默认域名列表 (可通过 ext 参数覆盖)
_DEFAULT_DOMAINS = [
    "https://www.dmxq39.com",
    "https://dmyy7.vip",
    "https://dami29.com",
    "https://dami27.com",
    "https://dmxq.net",
]

# 已知备用域名主机 (用于 URL 重写)
_KNOWN_HOSTS = {
    "www.dmxq39.com", "dmxq39.com",
    "dmyy16.top", "www.dmyy16.top",
    "dmyy7.vip", "www.dmyy7.vip",
    "dami27.com", "www.dami27.com",
    "dami29.com", "www.dami29.com",
    "dami13.com", "www.dami13.com",
    "dami3.com", "www.dami3.com",
    "dami0.com", "www.dami0.com",
    "dmxq.net", "www.dmxq.net",
    "www.dmxq.fun", "dmxq.fun",
}


class _NullLock(object):
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def acquire(self, blocking=True, timeout=-1):
        return True
    def release(self):
        pass


class Spider(Spider):

    DEFAULT_DOMAINS = _DEFAULT_DOMAINS

    def init(self, extend=""):
        self._domains, self._base_hosts = self._parse_domains(extend)
        self._domain_idx = 0

        self.default_pic = ""
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }

        self.categories = self._fetch_categories()
        self.filters_data = self._build_filters()

        # 缓存
        self._home_cache = ("", 0)
        self._play_html_cache = {}
        self._play_cache = {}
        self._domain_cache = ("", 0)
        self._page_first_id_cache = {}  # 各分类第一页第一个视频ID (用于检测重复页/网站回绕)
        self._prefetch_enabled = _HAS_THREADING
        self._cache_lock = threading.Lock() if _HAS_THREADING else _NullLock()
        self._session_cookies = ""

    # ==================== 域名管理 ====================

    @property
    def site_url(self):
        return self._domains[self._domain_idx % len(self._domains)]

    def _parse_domains(self, extend):
        domains = []
        ext = (extend or "").strip()
        if ext:
            candidates = []
            if ext.startswith('['):
                try:
                    arr = json.loads(ext)
                    if isinstance(arr, list):
                        candidates = [str(x).strip() for x in arr]
                except (json.JSONDecodeError, ValueError):
                    pass
            elif ext.startswith('{'):
                try:
                    cfg = json.loads(ext)
                    if isinstance(cfg, dict) and 'sites' in cfg:
                        candidates = [str(x).strip() for x in cfg['sites']]
                except (json.JSONDecodeError, ValueError):
                    pass
            else:
                candidates = [ext]
            for c in candidates:
                c = c.rstrip('/')
                if c.startswith('http') and c not in domains:
                    domains.append(c)
        for d in self.DEFAULT_DOMAINS:
            if d not in domains:
                domains.append(d)
        hosts = set()
        for d in domains:
            try:
                hosts.add(urllib.parse.urlsplit(d).netloc.lower())
            except Exception:
                pass
        hosts.update(_KNOWN_HOSTS)
        return domains, hosts

    def _rewrite_url(self, url):
        if len(self._domains) <= 1:
            return url
        try:
            sp = urllib.parse.urlsplit(url)
            if sp.netloc.lower() in self._base_hosts:
                active = urllib.parse.urlsplit(self.site_url)
                return urllib.parse.urlunsplit(
                    (active.scheme, active.netloc, sp.path, sp.query, sp.fragment))
        except Exception:
            pass
        return url

    def _rotate_domain(self):
        if len(self._domains) > 1:
            self._domain_idx += 1

    def _fetch_backup_domains(self):
        """从首页动态抓取备用域名"""
        cached, expire = self._domain_cache
        now = time.time()
        if cached and expire > now:
            return cached

        html = self._get_home_html()
        found = []
        if html:
            # 从首页链接中提取域名
            for m in re.finditer(r'https?://([a-z0-9]+\.(?:top|com|net|org|cc|me|tv|xyz|info|vip|fun|co))', html, re.I):
                host = m.group(1).lower()
                # 过滤非视频站点域名
                if host in ('www.googletagmanager.com', 't.me', 'ingest.lputol.com'):
                    continue
                if host not in found:
                    found.append(host)

        # 转为完整 URL
        new_domains = []
        for host in found:
            url = "https://%s" % host
            if url not in new_domains:
                new_domains.append(url)

        # 合并到已有域名列表
        if new_domains:
            for d in new_domains:
                if d not in self._domains:
                    self._domains.append(d)
                    try:
                        self._base_hosts.add(urllib.parse.urlsplit(d).netloc.lower())
                    except Exception:
                        pass

        self._domain_cache = (new_domains, now + _DOMAIN_CACHE_TTL)
        return new_domains

    # ==================== 基础工具 ====================

    def _is_cf_error(self, text):
        if not text:
            return True
        head = text[:1000] if len(text) >= 600 else text
        if 'cf-wrapper' in head or 'cf-error' in head:
            return True
        if 'cf-browser-status' in head or 'cf-cloudflare-status' in head:
            return True
        if 'cdn-cgi/styles' in head:
            return True
        if 'error code: 520' in head.lower():
            return True
        if len(text) < 600 and ('403' in head or 'Forbidden' in head):
            return True
        return False

    def _fetch_with_retry(self, url, max_retries=5, referer=None, min_len=1000, quick=False):
        hdrs = dict(self.headers)
        if referer:
            hdrs['Referer'] = referer
        if self._session_cookies:
            hdrs['Cookie'] = self._session_cookies

        retries = 2 if quick else max_retries
        for i in range(retries):
            try:
                req_url = self._rewrite_url(url)
                resp = self.fetch(req_url, headers=hdrs)
                if resp and resp.text:
                    text = resp.text
                    if len(text) >= min_len and not self._is_cf_error(text):
                        return text
                    if 'error code: 520' in text[:500].lower():
                        break
            except Exception:
                pass
            if i >= 1 and i < retries - 1:
                self._rotate_domain()
            if i < retries - 1:
                time.sleep(min(0.3 * (i + 1), 2.0))
        return ""

    def _fetch_page(self, url, referer=None, min_len=1000, timeout=10):
        """直接使用 urllib 抓取 (带超时控制, 用于播放页)"""
        hdrs = dict(self.headers)
        if referer:
            hdrs['Referer'] = referer
        if self._session_cookies:
            hdrs['Cookie'] = self._session_cookies

        for attempt in range(3):
            try:
                req_url = self._rewrite_url(url)
                req = urllib.request.Request(req_url, headers=hdrs)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    text = resp.read().decode('utf-8', errors='ignore')
                    if text and len(text) >= min_len and not self._is_cf_error(text):
                        return text
                    if 'error code: 520' in text[:500].lower():
                        break
            except Exception:
                pass
            if attempt < 2:
                time.sleep(0.3 * (attempt + 1))
        return ""

    def _fix_url(self, url):
        if not url:
            return ""
        if url.startswith("//"):
            return "https:" + url
        if not url.startswith("http"):
            return urllib.parse.urljoin(self.site_url + "/", url)
        return url

    def _get_pic(self, el):
        for attr in ['data-original', 'data-src', 'src']:
            pic = el.get(attr, '')
            if pic and 'base64' not in pic and 'gif' not in pic and 'favicon' not in pic:
                # 过滤占位图 (社区视频缩略图, 非真实海报)
                if 'community.image.video' in pic or 'qpic.cn/v_station' in pic:
                    continue
                return pic
        return ""

    def _parse_card(self, card):
        """解析视频卡片 (支持 module-poster-item 和 module-card-item 两种结构)
        也支持 topicdetail 链接 (专题列表卡片)"""
        link = None
        is_poster_item = card.name == 'a' and 'module-poster-item' in (card.get('class', []) or [])
        # 结构1: a.module-poster-item (首页/分类页, a 标签即卡片)
        if is_poster_item:
            link = card
        else:
            # 结构2: div.module-card-item (搜索页, 卡片为 div, 内含 a 链接)
            link = card.find('a', href=re.compile(r'/voddetail/'))
        if not link:
            # 尝试匹配 topicdetail 链接 (专题列表卡片)
            link = card if is_poster_item else card.find('a', href=re.compile(r'/topicdetail'))
        if not link:
            return None

        href = link.get('href', '')
        # 匹配 voddetail 或 topicdetail
        m = re.search(r'/voddetail/(\d+)\.html', href)
        if m:
            vid = m.group(1)
        else:
            m = re.search(r'/topicdetail-(\d+)\.html', href)
            if m:
                vid = "topicdetail-" + m.group(1)
            else:
                return None

        # 标题提取 (注意: module-card-item 的 a 链接内含 .module-item-note,
        # 不能用 link.get_text() 否则会取到备注文字)
        title = ""
        if is_poster_item:
            # 首页/分类: a.module-poster-item 有 title 属性
            title = link.get('title', '')
            if not title:
                title_el = card.select_one('.module-poster-item-title, .module-item-title')
                if title_el:
                    title = title_el.get_text(strip=True)
        else:
            # 搜索: div.module-card-item, 标题在 .module-card-item-title
            title_el = card.select_one('.module-card-item-title, .module-item-title')
            if title_el:
                title = title_el.get_text(strip=True)
            if not title:
                title = link.get('title', '')
        # 最后尝试从 img alt 属性提取 (搜索结果含 <em> 高亮)
        if not title:
            img_el = card.find('img')
            if img_el and img_el.get('alt'):
                title = img_el['alt']
        if not title:
            return None
        # 清理 HTML 标签 (搜索结果标题含 <em> 高亮)
        title = re.sub(r'<[^>]+>', '', title).strip()

        img = card.find('img')
        pic = self._get_pic(img) if img else ""
        pic = self._fix_url(pic)

        remark = ""
        remark_el = card.select_one('.module-item-note')
        if remark_el:
            remark = remark_el.get_text(strip=True)

        return {
            "vod_id": vid,
            "vod_name": title.strip(),
            "vod_pic": pic,
            "vod_remarks": remark
        }

    def _parse_rank_link(self, a_tag, rank_cat=""):
        """解析排行榜卡片中的单个视频链接
        结构: <a href="/voddetail/N.html"><div class="num">1</div><div class="info"><span>标题</span><p>质量</p></div></a>
        """
        href = a_tag.get('href', '')
        m = re.search(r'/voddetail/(\d+)\.html', href)
        if not m:
            return None
        vid = m.group(1)

        # 提取标题
        title = ""
        title_el = a_tag.select_one('.module-paper-item-infotitle')
        if title_el:
            title = title_el.get_text(strip=True)
        if not title:
            title = a_tag.get('title', '')
        if not title:
            # 从文本中提取 (格式: "1阿凡达2水之道1080P")
            text = a_tag.get_text(strip=True)
            # 移除开头的排名数字
            text = re.sub(r'^\d+', '', text)
            # 移除结尾的质量标记
            text = re.sub(r'(HD|HD中字|正片|1080P|720P|完结|更新.*?|共\d+集|更新至.*?|第\d+集)$', '', text).strip()
            title = text
        if not title:
            return None

        # 提取备注 (质量/集数信息)
        remark = rank_cat or ""
        p_el = a_tag.select_one('p')
        if p_el:
            quality = p_el.get_text(strip=True)
            if quality:
                remark = ("%s %s" % (rank_cat, quality)).strip() if rank_cat else quality

        return {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": "",
            "vod_remarks": remark
        }

    def _select_cards(self, soup):
        """统一选择视频卡片 (支持 module-poster-item, module-card-item, module-paper-item)"""
        cards = soup.select('a.module-poster-item')
        if not cards:
            cards = soup.select('div.module-card-item')
        if not cards:
            cards = soup.select('.module-item-cover')
        if not cards:
            # 排行榜: module-paper-item 内含多个 voddetail 链接
            cards = soup.select('div.module-paper-item')
        return cards

    def _get_home_html(self):
        html, expire = self._home_cache
        now = time.time()
        if html and expire > now:
            return html
        html = self._fetch_with_retry(self.site_url + "/", min_len=5000)
        if html:
            self._home_cache = (html, now + _HOME_CACHE_TTL)
            # 异步抓取备用域名
            if _HAS_THREADING:
                try:
                    t = threading.Thread(target=self._fetch_backup_domains, daemon=True)
                    t.start()
                except Exception:
                    pass
        return html

    # ==================== 分类 ====================

    def _fetch_categories(self):
        # 按首页导航栏顺序排列
        return [
            {"type_id": "label_netflix", "type_name": "Netflix"},
            {"type_id": "20", "type_name": "电影"},
            {"type_id": "21", "type_name": "电视剧"},
            {"type_id": "36", "type_name": "短剧"},
            {"type_id": "22", "type_name": "动漫"},
            {"type_id": "23", "type_name": "综艺"},
            {"type_id": "35", "type_name": "福利"},
            {"type_id": "label_week", "type_name": "追剧周表"},
            {"type_id": "label_new", "type_name": "今日更新"},
            {"type_id": "label_topic", "type_name": "专题列表"},
            {"type_id": "label_hot", "type_name": "排行榜"},
        ]

    def _extract_nav_categories(self, soup):
        """从首页导航栏动态提取分类列表 (保持导航栏原始顺序)"""
        try:
            # 找到导航栏容器
            nav = soup.find(class_='navbar-items') or soup.find(class_='nav') or soup.find('nav')
            if not nav:
                return None

            cats = []
            seen = set()
            for a in nav.find_all('a', href=True):
                href = a.get('href', '')
                title = a.get('title', '').strip()
                text = a.get_text(strip=True)

                # 匹配 vodtype 分类
                m = re.search(r'/vodtype/(\d+)', href)
                if m:
                    tid = m.group(1)
                    name = title or text
                    if not name or name.isdigit() or len(name) > 10:
                        continue
                    if any(kw in name for kw in ['排行', '最佳', '热门', '推荐', '每周']):
                        continue
                    if tid not in seen:
                        seen.add(tid)
                        cats.append({"type_id": tid, "type_name": name})
                    continue

                # 匹配 label 分类
                m = re.search(r'/label/([a-zA-Z0-9_-]+)', href)
                if m:
                    label_id = m.group(1)
                    # 跳过非分类页面
                    if label_id in ('topic', 'more', 'search'):
                        # topic 专题列表也保留
                        if label_id == 'topic':
                            tid = "label_" + label_id
                            if tid not in seen:
                                seen.add(tid)
                                cats.append({"type_id": tid, "type_name": "专题列表"})
                        continue
                    name = title or text
                    if not name or len(name) > 15:
                        continue
                    # 清理名称中的数字 (如 "今日更新2089" -> "今日更新")
                    name = re.sub(r'\d+$', '', name).strip()
                    if not name:
                        continue
                    tid = "label_" + label_id
                    if tid not in seen:
                        seen.add(tid)
                        cats.append({"type_id": tid, "type_name": name})

            if len(cats) >= 2:
                return cats
        except Exception:
            pass
        return None

    # ==================== 筛选器 ====================

    def _build_filters(self):
        def opts(items):
            return [{"n": n, "v": v} for n, v in items]

        by_filter = {
            "key": "by", "name": "排序",
            "value": opts([("全部", ""), ("最新", "time"), ("最热", "hits"), ("评分", "score")])
        }
        area_filter = {
            "key": "area", "name": "地区",
            "value": opts([("全部", ""), ("大陆", "大陆"), ("香港", "香港"), ("台湾", "台湾"),
                           ("美国", "美国"), ("韩国", "韩国"), ("日本", "日本"), ("法国", "法国"),
                           ("英国", "英国"), ("德国", "德国"), ("泰国", "泰国"), ("印度", "印度"),
                           ("意大利", "意大利"), ("西班牙", "西班牙"), ("加拿大", "加拿大"),
                           ("俄罗斯", "俄罗斯"), ("其他", "其他")])
        }
        years = [("全部", "")] + [(str(y), str(y)) for y in range(2026, 2009, -1)]
        year_filter = {"key": "year", "name": "年份", "value": opts(years)}

        class_map = {
            "20": [("全部", ""), ("动作", "动作"), ("喜剧", "喜剧"), ("爱情", "爱情"),
                   ("科幻", "科幻"), ("恐怖", "恐怖"), ("惊悚", "惊悚"), ("悬疑", "悬疑"),
                   ("剧情", "剧情"), ("战争", "战争"), ("动画", "动画"), ("犯罪", "犯罪"),
                   ("冒险", "冒险"), ("家庭", "家庭"), ("奇幻", "奇幻"), ("古装", "古装"),
                   ("武侠", "武侠"), ("历史", "历史"), ("音乐", "音乐"), ("传记", "传记")],
            "21": [("全部", ""), ("国产剧", "国产剧"), ("港台剧", "港台剧"), ("日韩剧", "日韩剧"),
                   ("欧美剧", "欧美剧"), ("海外剧", "海外剧")],
            "22": [("全部", ""), ("国产动漫", "国产动漫"), ("日本动漫", "日本动漫"),
                   ("欧美动漫", "欧美动漫"), ("海外动漫", "海外动漫")],
            "23": [("全部", ""), ("国产综艺", "国产综艺"), ("港台综艺", "港台综艺"),
                   ("日韩综艺", "日韩综艺"), ("欧美综艺", "欧美综艺"), ("海外综艺", "海外综艺")],
            "35": [("全部", ""), ("亚洲无码", "亚洲无码"), ("欧美无码", "欧美无码"),
                   ("有码", "有码"), ("国产", "国产"), ("动漫", "动漫")],
            "36": [("全部", ""), ("短剧", "短剧")],
        }
        default_class = [("全部", ""), ("剧情", "剧情"), ("喜剧", "喜剧"), ("动作", "动作"),
                         ("爱情", "爱情"), ("科幻", "科幻")]

        filters = {}
        for cat in self.categories:
            tid = cat["type_id"]
            # label 页面 (如 Netflix) 没有筛选器
            if tid.startswith("label_"):
                continue
            klass = class_map.get(tid, default_class)
            # 福利分类不支持 vodshow 筛选, 仅保留排序
            if tid == "35":
                filters[tid] = [by_filter]
            else:
                filters[tid] = [
                    by_filter,
                    {"key": "class", "name": "类型", "value": opts(klass)},
                    area_filter,
                    year_filter,
                ]
        return filters

    def _build_filter_url(self, tid, page, area, year, klass, by):
        """构建筛选 URL
        vodshow URL 格式 (12个位置, 11个短横线分隔):
        /vodshow/{id}-{area}-{p3}-{class}-{p5}-{p6}-{p7}-{p8}-{p9}-{p10}-{year}-{by}.html?page={page}

        筛选参数放在 URL 路径中 (非查询参数), 页码通过 ?page=N 传递。
        vodtype 页面不支持分页和筛选参数, 必须使用 vodshow。
        """
        parts = [tid, area or '', '', klass or '', '', '', '', '', '', '', year or '', by or '']
        path = '-'.join(parts)
        # URL 编码路径中的中文 (保留短横线分隔符)
        encoded_path = urllib.parse.quote(path, safe='-')
        url = "%s/vodshow/%s.html?page=%d" % (self.site_url, encoded_path, page)
        return url

    def _category_rank(self, page):
        """排行榜: 从多个分类按热度取前几名, 合并展示 (带海报)"""
        rank_cats = [("20", "电影"), ("21", "电视剧"), ("36", "短剧"),
                     ("22", "动漫"), ("23", "综艺"), ("35", "福利")]
        per_cat = 5

        video_list = []
        seen = set()

        for cat_id, cat_name in rank_cats:
            # 使用 vodshow + hits 排序, page 通过查询参数传递
            # vodtype 不支持 by 参数且不支持分页, 必须用 vodshow
            url = "%s/vodshow/%s-----------hits.html?page=%d" % (self.site_url, cat_id, page)
            html = self._fetch_with_retry(url, min_len=2000)
            if not html:
                continue
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            cards = self._select_cards(soup)
            count = 0
            for card in cards:
                if count >= per_cat:
                    break
                item = self._parse_card(card)
                if item and item["vod_id"] not in seen:
                    seen.add(item["vod_id"])
                    if item.get("vod_remarks"):
                        item["vod_remarks"] = "%s %s" % (cat_name, item["vod_remarks"])
                    else:
                        item["vod_remarks"] = cat_name
                    video_list.append(item)
                    count += 1

        return {
            "list": video_list,
            "page": page,
            "pagecount": page + 1 if video_list else page,
            "limit": 30,
            "total": len(video_list) * (page + 1)
        }

    def _clean_line_name(self, name):
        if not name:
            return ""
        name = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', name)
        name = re.sub(r'[▼▽▾⌄]', '', name)
        name = re.sub(r'\s+', ' ', name).strip()
        return name

    def _extract_line_names(self, soup):
        """提取线路名称列表 (按 Tab 顺序)"""
        tab_names = []
        tab_items = soup.select('.module-tab-item.tab-item')
        if not tab_items:
            tab_items = soup.select('.module-tab-item')
        if not tab_items:
            tab_items = soup.select('[data-dropdown-value]')

        for tab in tab_items:
            span = tab.find('span')
            name = span.get_text(strip=True) if span else tab.get_text(strip=True)
            name = self._clean_line_name(name)
            if name:
                tab_names.append(name)
        return tab_names

    def _extract_line_ids_ordered(self, soup):
        """从播放链接中提取 lineId 的出现顺序"""
        line_ids = []
        seen = set()
        for box in soup.select('.module-play-list-content'):
            link = box.find('a', href=re.compile(r'/vodplay/'))
            if link:
                m = re.match(r'/vodplay/\d+-(\d+)-\d+\.html', link.get('href', ''))
                if m and m.group(1) not in seen:
                    seen.add(m.group(1))
                    line_ids.append(m.group(1))
        if not line_ids:
            for a in soup.find_all('a', href=re.compile(r'/vodplay/')):
                href = a.get('href', '')
                m = re.match(r'/vodplay/\d+-(\d+)-\d+\.html', href)
                if m and m.group(1) not in seen:
                    seen.add(m.group(1))
                    line_ids.append(m.group(1))
        return line_ids

    # ==================== TVBox 接口 ====================

    def homeContent(self, filter):
        html = self._get_home_html()
        video_list = []
        if html:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            nav_cats = self._extract_nav_categories(soup)
            if nav_cats and len(nav_cats) >= len(self.categories):
                self.categories = nav_cats
                self.filters_data = self._build_filters()

            cards = self._select_cards(soup)
            seen = set()
            for card in cards:
                item = self._parse_card(card)
                if item and item["vod_id"] not in seen:
                    seen.add(item["vod_id"])
                    video_list.append(item)
                if len(video_list) >= 30:
                    break
        return {"class": self.categories, "list": video_list, "filters": self.filters_data}

    def homeVideoContent(self):
        html = self._get_home_html()
        video_list = []
        if html:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            cards = self._select_cards(soup)
            seen = set()
            for card in cards:
                item = self._parse_card(card)
                if item and item["vod_id"] not in seen:
                    seen.add(item["vod_id"])
                    video_list.append(item)
                if len(video_list) >= 20:
                    break
        return {"list": video_list}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        ext = extend or {}
        if isinstance(ext, str):
            try:
                ext = json.loads(ext)
            except (json.JSONDecodeError, ValueError):
                ext = {}
        area = str(ext.get('area') or '').strip()
        year = str(ext.get('year') or '').strip()
        klass = str(ext.get('class') or '').strip()
        by = str(ext.get('by') or '').strip()

        # 处理 label 页面
        if tid.startswith("label_"):
            label_id = tid[6:]  # 去掉 "label_" 前缀

            # 排行榜: 使用 vodshow + by=hits 获取带海报的排行视频
            if label_id == "hot":
                return self._category_rank(page)

            # 其他 label 页面 (Netflix, 追剧周表, 今日更新, 专题列表)
            # 统一使用 /label/{id}/page/{page}.html 格式
            # /label/{id}.html 返回压缩乱码, 必须用 /page/N.html 格式
            url = "%s/label/%s/page/%d.html" % (self.site_url, label_id, page)
        else:
            # 普通分类: 统一使用 vodshow (支持分页和筛选)
            # vodtype 页面不支持分页 (page 2+ 返回与 page 1 相同内容)
            url = self._build_filter_url(tid, page, area, year, klass, by)

        html = self._fetch_with_retry(url, min_len=3000)
        video_list = []
        pagecount = page
        if html:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            cards = self._select_cards(soup)
            seen = set()
            for card in cards:
                # 排行榜: module-paper-item 内含多个视频链接, 需要展开
                if card.name == 'div' and 'module-paper-item' in (card.get('class', []) or []):
                    rank_title_el = card.select_one('.module-paper-item-title')
                    rank_cat = rank_title_el.get_text(strip=True) if rank_title_el else ''
                    for a in card.find_all('a', href=re.compile(r'/voddetail/')):
                        item = self._parse_rank_link(a, rank_cat)
                        if item and item["vod_id"] not in seen:
                            seen.add(item["vod_id"])
                            video_list.append(item)
                    continue
                # 普通卡片
                item = self._parse_card(card)
                if item and item["vod_id"] not in seen:
                    seen.add(item["vod_id"])
                    video_list.append(item)

            # 提取分页信息 (支持 vodtype/vodshow/label 三种 URL 格式)
            page_links = soup.find_all('a', href=re.compile(r'/(?:vod(?:type|show)/\d+|label/[a-zA-Z0-9_-]+)'))
            for a in page_links:
                href = a.get('href', '')
                # 格式1: /vodtype/20-2.html 或 /vodshow/20-...-2.html
                m = re.search(r'-(\d+)\.html', href)
                if m:
                    pagecount = max(pagecount, int(m.group(1)))
                # 格式2: ?page=2 (查询参数模式)
                m2 = re.search(r'[?&]page=(\d+)', href)
                if m2:
                    pagecount = max(pagecount, int(m2.group(1)))
                # 格式3: /label/netflix/page/N.html
                m3 = re.search(r'/label/[^/]+/page/(\d+)\.html', href)
                if m3:
                    pagecount = max(pagecount, int(m3.group(1)))

        # 分页计数逻辑:
        # - 有分页链接: 使用链接中的最大页码
        # - 无分页链接但有视频: 允许尝试下一页 (page + 1)
        # - 无分页链接且无视频: 停止翻页 (pagecount=page)
        # - 重复检测: 仅在 page>=2 时生效, page=1 永远正常返回
        #   (TVBox 刷新时会重新调用 page=1, 不能误判为重复)
        # - 重要: 停止翻页时 pagecount = page (不能用 page-1, 否则 TVBox 会清空已有列表)
        cache_key = "%s_%s_%s_%s_%s" % (tid, area, year, klass, by)
        if pagecount > page:
            final_pagecount = pagecount
        elif video_list:
            first_id = video_list[0]["vod_id"] if video_list else ""
            cached_first_id = self._page_first_id_cache.get(cache_key, "")
            if page == 1:
                # 第一页: 记录基准, 正常返回内容
                self._page_first_id_cache[cache_key] = first_id
                final_pagecount = page + 1
            elif first_id == cached_first_id:
                # 与第一页内容相同 (网站回绕), 停止翻页
                # pagecount=page: 告诉 TVBox 当前页是最后一页, 保留已有内容
                final_pagecount = page
                video_list = []
            else:
                # 不同内容, 允许继续翻页
                final_pagecount = page + 1
        else:
            # 无视频: 停止翻页
            # pagecount=page: 告诉 TVBox 当前页是最后一页, 保留已有内容
            final_pagecount = page

        return {
            "list": video_list,
            "page": page,
            "pagecount": final_pagecount,
            "limit": 30,
            "total": len(video_list) * final_pagecount
        }

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vod_id = ids[0]

        # 处理专题详情页 (topicdetail-N)
        if vod_id.startswith("topicdetail-"):
            return self._detail_topic(vod_id)

        url = "%s/voddetail/%s.html" % (self.site_url, vod_id)
        html = self._fetch_with_retry(url, min_len=5000)
        if not html:
            return {"list": []}

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')

        # 标题
        vod_name = ""
        title_tag = soup.find('title')
        if title_tag:
            t = title_tag.get_text(strip=True)
            m = re.search(r'^(.+?)(?:高清|完整版|免费|在线|观看|动漫|电影|电视剧)', t)
            if m:
                vod_name = m.group(1).strip()
            else:
                m = re.search(r'《([^》]+)》', t)
                if m:
                    vod_name = m.group(1)
        if not vod_name:
            for h in soup.find_all(['h1', 'h2']):
                t = h.get_text(strip=True)
                if t and len(t) > 1 and t not in ['影片参数', '排序角色', '播放记录', '相关影片']:
                    vod_name = t
                    break

        # 海报
        vod_pic = ""
        for img in soup.find_all('img'):
            alt = img.get('alt', '')
            if vod_name and vod_name in alt:
                vod_pic = self._get_pic(img)
                break
        if not vod_pic:
            for img in soup.find_all('img'):
                src = self._get_pic(img)
                if src and 'favicon' not in src and 'user' not in src and 'base64' not in src and 'logo' not in src:
                    vod_pic = src
                    break
        vod_pic = self._fix_url(vod_pic)

        # 详情信息
        vod_content = ""
        vod_actor = ""
        vod_director = ""
        vod_area = ""
        vod_year = ""
        vod_class = ""

        text = soup.get_text()
        field_keywords = ['导演', '主演', '地区', '年份', '类型', '状态', '简介',
                          '描述', '频道', '上映', '语言', '更新']
        for kw, attr_name in [('导演', 'vod_director'), ('主演', 'vod_actor'),
                               ('地区', 'vod_area'), ('年份', 'vod_year'),
                               ('类型', 'vod_class'), ('状态', 'remark'),
                               ('简介', 'vod_content'), ('描述', 'vod_content')]:
            m = re.search(kw + r'[：:]\s*([^\n<]+)', text)
            if m:
                val = m.group(1).strip()
                for next_kw in field_keywords:
                    if next_kw == kw:
                        continue
                    cut_idx = val.find(next_kw)
                    if cut_idx > 0:
                        val = val[:cut_idx].strip()
                val = val[:200]
                if attr_name == 'vod_director':
                    vod_director = val
                elif attr_name == 'vod_actor':
                    vod_actor = val
                elif attr_name == 'vod_area':
                    vod_area = val
                elif attr_name == 'vod_year':
                    vod_year = val
                elif attr_name == 'vod_class':
                    vod_class = val
                elif attr_name == 'vod_content':
                    vod_content = val

        # 播放线路和剧集
        play_links = soup.find_all('a', href=re.compile(r'/vodplay/'))
        lines = {}
        line_order = []
        for a in play_links:
            href = a.get('href', '')
            m = re.match(r'/vodplay/\d+-(\d+)-(\d+)\.html', href)
            if not m:
                continue
            line_id = m.group(1)
            ep_num = int(m.group(2))
            ep_name = a.get_text(strip=True) or ("%d" % ep_num)
            ep_name = re.sub(
                r'^(4K|蓝光|超清|高清|HD|1080[Pp]|720[Pp])[\s\-—]*',
                '', ep_name
            ).strip()
            if not ep_name:
                ep_name = "第%d集" % ep_num
            elif ep_name.isdigit():
                ep_name = "第%s集" % ep_name
            if line_id not in lines:
                lines[line_id] = []
                line_order.append(line_id)
            existing_eps = [e[0] for e in lines[line_id]]
            if ep_num not in existing_eps:
                lines[line_id].append((ep_num, ep_name, href))

        # 线路名称
        tab_names = self._extract_line_names(soup)
        line_ids = self._extract_line_ids_ordered(soup)

        line_names = {}
        if tab_names and line_ids and len(tab_names) == len(line_ids):
            for i, name in enumerate(tab_names):
                line_names[line_ids[i]] = name
        elif tab_names:
            for i, name in enumerate(tab_names):
                if i < len(line_order):
                    line_names[line_order[i]] = name
                else:
                    line_names[str(i + 1)] = name

        play_from_list = []
        play_url_list = []
        for lid in line_order:
            eps = sorted(lines[lid], key=lambda x: x[0])
            line_name = line_names.get(lid, "线路%s" % lid)
            ep_strs = []
            for ep_num, ep_name, href in eps:
                ep_strs.append("%s$%s:%s:%d" % (ep_name, vod_id, lid, ep_num))
            if ep_strs:
                play_from_list.append(line_name)
                play_url_list.append("#".join(ep_strs))

        if not play_url_list:
            play_from_list.append("默认线路")
            play_url_list.append("暂无播放$%s:1:1" % vod_id)

        vod_play_from = "$$$".join(play_from_list)
        vod_play_url = "$$$".join(play_url_list)

        result = [{
            "vod_id": vod_id,
            "vod_name": vod_name,
            "vod_pic": vod_pic,
            "vod_content": vod_content,
            "vod_actor": vod_actor,
            "vod_director": vod_director,
            "vod_area": vod_area,
            "vod_year": vod_year,
            "vod_class": vod_class,
            "vod_play_from": vod_play_from,
            "vod_play_url": vod_play_url
        }]
        return {"list": result}

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        encoded_key = urllib.parse.quote(key)
        # 搜索 URL 格式: /vodsearch/<keyword>----------<page>---.html
        url = "%s/vodsearch/%s----------%d---.html" % (self.site_url, encoded_key, page)
        html = self._fetch_with_retry(url, min_len=1000)
        video_list = []
        pagecount = page
        if html:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            cards = self._select_cards(soup)
            seen = set()
            for card in cards:
                item = self._parse_card(card)
                if item and item["vod_id"] not in seen:
                    seen.add(item["vod_id"])
                    video_list.append(item)
            # 提取分页: 从 .page-link 元素获取最大页码
            for pl in soup.select('.page-link'):
                txt = pl.get_text(strip=True)
                if txt.isdigit():
                    pagecount = max(pagecount, int(txt))
            # 尾页链接包含最大页码
            for a in soup.select('a.page-next'):
                href = a.get('href', '')
                m = re.search(r'-(\d+)---\.html', href)
                if m:
                    pagecount = max(pagecount, int(m.group(1)))
        return {"list": video_list, "page": page, "pagecount": pagecount}

    # ==================== 播放器 ====================

    def _extract_player_aaaa(self, html):
        """从播放页 HTML 中提取 player_aaaa 变量"""
        start = html.find('player_aaaa')
        if start < 0:
            return None
        brace_start = html.find('{', start)
        if brace_start < 0:
            return None
        depth = 0
        in_string = False
        string_char = None
        escape = False
        for idx in range(brace_start, len(html)):
            c = html[idx]
            if escape:
                escape = False
                continue
            if c == '\\':
                escape = True
                continue
            if not in_string and (c == '"' or c == "'"):
                in_string = True
                string_char = c
                continue
            if in_string and c == string_char:
                in_string = False
                string_char = None
                continue
            if in_string:
                continue
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    raw = html[brace_start:idx + 1]
                    try:
                        return json.loads(raw)
                    except (json.JSONDecodeError, ValueError):
                        pass
                    try:
                        fixed = raw.replace("'", '"')
                        return json.loads(fixed)
                    except (json.JSONDecodeError, ValueError):
                        pass
                    try:
                        url_m = re.search(r'["\']url["\']\s*:\s*["\']([^"\']+)["\']', raw)
                        from_m = re.search(r'["\']from["\']\s*:\s*["\']([^"\']+)["\']', raw)
                        enc_m = re.search(r'["\']encrypt["\']\s*:\s*(\d+)', raw)
                        if url_m:
                            return {
                                'url': url_m.group(1),
                                'from': from_m.group(1) if from_m else '',
                                'encrypt': int(enc_m.group(1)) if enc_m else 0
                            }
                    except Exception:
                        pass
                    return None
        return None

    def _cache_get(self, cache, key):
        try:
            with self._cache_lock:
                hit = cache.get(key)
            if hit and hit[0] > time.time():
                return hit[1]
        except Exception:
            pass
        return None

    def _cache_put(self, cache, key, value, ttl):
        try:
            with self._cache_lock:
                cache[key] = (time.time() + ttl, value)
                if len(cache) > 200:
                    now = time.time()
                    for k in [k for k, v in cache.items() if v[0] < now]:
                        del cache[k]
        except Exception:
            pass

    def _resolve_play_url(self, drama_id, line_id, ep_num, flag=""):
        """
        核心播放解析流程:
        1. 抓取播放页 HTML (带缓存)
        2. 提取 player_aaaa (获取加密URL和线路信息)
        3. encrypt=3: AES-CBC 解密 -> parse=0 直连播放 (极速秒开)
        4. 解密失败: parse=1 嗅探模式 (TVBox 加载播放页拦截 m3u8)

        测试结论: 所有线路的 m3u8 服务器均不需要 Referer, 可直接 parse=0 播放。
        线路类型: snm3u8, wsym3u8, hnm3u8, bfzym3u8, dyttm3u8 (全部 encrypt=3)
        """
        html_key = "%s-%s-%s" % (drama_id, line_id, ep_num)
        play_url = "%s/vodplay/%s-%s-%d.html" % (self.site_url, drama_id, line_id, ep_num)
        detail_url = "%s/voddetail/%s.html" % (self.site_url, drama_id)

        fb_header = dict(self.headers)
        fb_header['Referer'] = detail_url

        # 播放页 HTML 缓存
        html = self._cache_get(self._play_html_cache, html_key)
        if html is None:
            html = self._fetch_page(play_url, referer=detail_url, min_len=1000, timeout=8)
            if html:
                self._cache_put(self._play_html_cache, html_key, html, _PLAY_HTML_TTL)

        if not html:
            return {"parse": 1, "url": play_url, "header": fb_header}

        # 提取 player_aaaa
        data = self._extract_player_aaaa(html)
        if not data:
            return {"parse": 1, "url": play_url, "header": fb_header}

        encrypt = data.get('encrypt', 0)
        from_val = data.get('from', '')
        enc_url = data.get('url', '')

        # encrypt=3: AES 解密获取直链 m3u8/mp4 URL
        # 所有线路 (snm3u8/wsym3u8/hnm3u8/bfzym3u8/dyttm3u8) 均使用同一套密钥
        # 解密后的 URL 可直接访问 (无需 Referer), 使用 parse=0 秒开
        if encrypt == 3 and enc_url:
            decrypted = _decrypt_heimuer_url(enc_url)
            if decrypted and decrypted.startswith('http'):
                # parse=0: 直连播放, TVBox 直接加载 m3u8/mp4 URL
                # 无需嗅探, 启动速度最快
                play_header = dict(self.headers)
                result = {
                    "parse": 0,
                    "url": decrypted,
                    "header": play_header
                }
                self._cache_put(self._play_cache,
                                "%s|%s:%s:%d" % (flag, drama_id, line_id, ep_num),
                                result, _PLAY_RESULT_TTL)
                return result

        # 回退: 嗅探模式 (parse=1)
        # 解密失败时, TVBox 加载播放页并通过浏览器嗅探拦截 m3u8 请求
        result = {"parse": 1, "url": play_url, "header": fb_header}
        self._cache_put(self._play_cache, "%s|%s:%s:%d" % (flag, drama_id, line_id, ep_num),
                        result, _PLAY_RESULT_TTL)
        return result

    def _schedule_prefetch(self, flag, drama_id, line_id, ep_num):
        """连播预取: 后台线程预解析下一集, 换集秒启动"""
        if not self._prefetch_enabled:
            return
        next_ep = ep_num + 1
        next_key = "%s|%s:%s:%d" % (flag, drama_id, line_id, next_ep)
        with self._cache_lock:
            if next_key in self._play_cache:
                return
        try:
            t = threading.Thread(
                target=self._prefetch_worker,
                args=(flag, drama_id, line_id, next_ep),
                daemon=True)
            t.start()
        except Exception:
            pass

    def _prefetch_worker(self, flag, drama_id, line_id, ep_num):
        try:
            self._resolve_play_url(drama_id, line_id, ep_num, flag)
        except Exception:
            pass

    def _detail_topic(self, vod_id):
        """处理专题详情页: 将专题内的视频作为剧集列表展示"""
        topic_num = vod_id.replace("topicdetail-", "")
        url = "%s/topicdetail-%s.html" % (self.site_url, topic_num)
        html = self._fetch_with_retry(url, min_len=1000)
        if not html:
            return {"list": []}

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')

        # 提取专题标题
        title_tag = soup.find('title')
        topic_title = ""
        if title_tag:
            topic_title = title_tag.get_text(strip=True).split('-')[0].strip()

        # 提取专题内所有视频
        play_links = []
        seen = set()
        for a in soup.find_all('a', href=re.compile(r'/voddetail/')):
            href = a.get('href', '')
            m = re.search(r'/voddetail/(\d+)\.html', href)
            if m:
                vid = m.group(1)
                if vid not in seen:
                    seen.add(vid)
                    ep_name = a.get_text(strip=True) or ("第%d集" % (len(play_links) + 1))
                    play_links.append({
                        "vid": vid,
                        "name": ep_name,
                        "href": href
                    })

        if not play_links:
            return {"list": []}

        # 构建播放列表 (单线路, 每个视频作为一集, epNum=1 因为每个视频是独立节目)
        episode_str_list = []
        for ep in play_links:
            episode_str_list.append("%s$%s:%s:%d" % (
                ep["name"], ep["vid"], "1", 1))

        vod_play_from = "专题列表"
        vod_play_url = "#".join(episode_str_list)

        return {
            "list": [{
                "vod_id": vod_id,
                "vod_name": topic_title or "专题",
                "vod_pic": "",
                "vod_content": "专题列表, 共%d个视频" % len(play_links),
                "vod_play_from": vod_play_from,
                "vod_play_url": vod_play_url
            }]
        }

    def playerContent(self, flag, id, vipFlags):
        """
        播放: 从播放页提取 player_aaaa, 使用嗅探模式播放。
        id 格式: dramaId:lineId:epNum
        """
        parts = id.split(":")
        if len(parts) >= 3:
            drama_id = parts[0]
            line_id = parts[1]
            ep_num = int(parts[2])
        elif len(parts) >= 2:
            drama_id = parts[0]
            line_id = parts[1]
            ep_num = 1
        else:
            drama_id = id
            line_id = "1"
            ep_num = 1

        cache_key = "%s|%s" % (flag, id)
        cached = self._cache_get(self._play_cache, cache_key)
        if cached is not None:
            try:
                self._schedule_prefetch(flag, drama_id, line_id, ep_num)
            except Exception:
                pass
            return cached

        result = self._resolve_play_url(drama_id, line_id, ep_num, flag)

        # 预取下一集
        self._schedule_prefetch(flag, drama_id, line_id, ep_num)

        return result

    def isVideoFormat(self, url):
        if not url:
            return False
        url_lower = url.lower()
        if '.m3u8' in url_lower or '.mp4' in url_lower:
            return True
        if 'video' in url_lower and ('url' in url_lower or 'play' in url_lower):
            return True
        return False

    def manualVideoSniff(self, url):
        """嗅探规则: 匹配 m3u8 和 mp4"""
        if not url:
            return False
        url_lower = url.lower()
        return '.m3u8' in url_lower or '.mp4' in url_lower or 'video' in url_lower
