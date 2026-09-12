# -*- coding: utf-8 -*-
"""
M1999藍光影視網 - m1999.sbs
TVBox/FongMi 影视壳子爬虫插件

站点信息：
  - 站名：M1999藍光影視網
  - base_url：https://m1999.sbs
  - 模板：dsn2（MacCMS 标准）
  - 无反爬机制（无验证码、无cookie挑战、无滑动验证）

URL 结构：
  - 首页：/
  - 分类：/vod/show/id/{type_id}.html（支持筛选）
  - 详情：/vod/detail/id/{id}.html
  - 播放：/vod/play/id/{id}/sid/{sid}/nid/{nid}.html
  - 搜索：/vod/search/wd/{keyword}.html 或 /vod/search/page/{page}/wd/{keyword}.html

分类：
  1: 最新電影  2: 國産劇  3: 日韓劇  4: 美劇  5: 番劇

功能：
  1. 继承 base.spider.Spider，实现 TVBox 六大核心方法
  2. 纯 Python RC4/AES 兜底（站点后续若加密可即时生效）
  3. Session 复用、Cookie 管理
  4. 请求间隔控制、频率限制检测
  5. 片名清洗（_clean_vod_name）
  6. 播放缓存
  7. 预编译正则
  8. 4K/蓝光线路置顶排序
  9. searchable/quickSearch/filterable/changeable 声明
  10. 播放地址解析：从播放页HTML提取 player_aaaa JS变量，处理加密播放地址
  11. 所有解密失败回退到播放页URL（parse=1）
"""
import re
import json
import hashlib
import base64
import time
import urllib.parse
import requests
from urllib.parse import quote
from base.spider import Spider as BaseSpider

# ==================== 纯Python RC4（无第三方库兜底）====================
def _rc4_crypt(data, key):
    S = list(range(256))
    j = 0
    key = key if isinstance(key, bytes) else key.encode('utf-8')
    for i in range(256):
        j = (j + S[i] + key[i % len(key)]) % 256
        S[i], S[j] = S[j], S[i]
    i = j = 0
    out = bytearray()
    for ch in (data if isinstance(data, bytes) else data.encode('utf-8')):
        i = (i + 1) % 256
        j = (j + S[i]) % 256
        S[i], S[j] = S[j], S[i]
        out.append(ch ^ S[(S[i] + S[j]) % 256])
    return bytes(out)

# ==================== 纯 Python AES-128-CBC（无 Crypto 时兜底）====================
def _aes_bytes2matrix(data):
    return [list(data[i:i+4]) for i in range(0, 16, 4)]

def _aes_matrix2bytes(matrix):
    return bytes(sum(matrix, []))

def _aes_split_blocks(data, block_size=16):
    return [data[i:i+block_size] for i in range(0, len(data), block_size)]

def _aes_xor_bytes(a, b):
    return bytes(i ^ j for i, j in zip(a, b))

def _aes_unpad(data):
    if not data:
        return data
    pad = data[-1]
    # 严格 PKCS7：校验全部填充字节，避免把正常数据结尾误当填充剥掉
    if 1 <= pad <= 16 and data[-pad:] == bytes([pad]) * pad:
        return data[:-pad]
    return data

_AES_SBOX = bytes([
    0x63,0x7C,0x77,0x7B,0xF2,0x6B,0x6F,0xC5,0x30,0x01,0x67,0x2B,0xFE,0xD7,0xAB,0x76,
    0xCA,0x82,0xC9,0x7D,0xFA,0x59,0x47,0xF0,0xAD,0xD4,0xA2,0xAF,0x9C,0xA4,0x72,0xC0,
    0xB7,0xFD,0x93,0x26,0x36,0x3F,0xF7,0xCC,0x34,0xA5,0xE5,0xF1,0x71,0xD8,0x31,0x15,
    0x04,0xC7,0x23,0xC3,0x18,0x96,0x05,0x9A,0x07,0x12,0x80,0xE2,0xEB,0x27,0xB2,0x75,
    0x09,0x83,0x2C,0x1A,0x1B,0x6E,0x5A,0xA0,0x52,0x3B,0xD6,0xB3,0x29,0xE3,0x2F,0x84,
    0x53,0xD1,0x00,0xED,0x20,0xFC,0xB1,0x5B,0x6A,0xCB,0xBE,0x39,0x4A,0x4C,0x58,0xCF,
    0xD0,0xEF,0xAA,0xFB,0x43,0x4D,0x33,0x85,0x45,0xF9,0x02,0x7F,0x50,0x3C,0x9F,0xA8,
    0x51,0xA3,0x40,0x8F,0x92,0x9D,0x38,0xF5,0xBC,0xB6,0xDA,0x21,0x10,0xFF,0xF3,0xD2,
    0xCD,0x0C,0x13,0xEC,0x5F,0x97,0x44,0x17,0xC4,0xA7,0x7E,0x3D,0x64,0x5D,0x19,0x73,
    0x60,0x81,0x4F,0xDC,0x22,0x2A,0x90,0x88,0x46,0xEE,0xB8,0x14,0xDE,0x5E,0x0B,0xDB,
    0xE0,0x32,0x3A,0x0A,0x49,0x06,0x24,0x5C,0xC2,0xD3,0xAC,0x62,0x91,0x95,0xE4,0x79,
    0xE7,0xC8,0x37,0x6D,0x8D,0xD5,0x4E,0xA9,0x6C,0x56,0xF4,0xEA,0x65,0x7A,0xAE,0x08,
    0xBA,0x78,0x25,0x2E,0x1C,0xA6,0xB4,0xC6,0xE8,0xDD,0x74,0x1F,0x4B,0xBD,0x8B,0x8A,
    0x70,0x3E,0xB5,0x66,0x48,0x03,0xF6,0x0E,0x61,0x35,0x57,0xB9,0x86,0xC1,0x1D,0x9E,
    0xE1,0xF8,0x98,0x11,0x69,0xD9,0x8E,0x94,0x9B,0x1E,0x87,0xE9,0xCE,0x55,0x28,0xDF,
    0x8C,0xA1,0x89,0x0D,0xBF,0xE6,0x42,0x68,0x41,0x99,0x2D,0x0F,0xB0,0x54,0xBB,0x16,
])

_AES_INV_SBOX = bytes([
    0x52,0x09,0x6A,0xD5,0x30,0x36,0xA5,0x38,0xBF,0x40,0xA3,0x9E,0x81,0xF3,0xD7,0xFB,
    0x7C,0xE3,0x39,0x82,0x9B,0x2F,0xFF,0x87,0x34,0x8E,0x43,0x44,0xC4,0xDE,0xE9,0xCB,
    0x54,0x7B,0x94,0x32,0xA6,0xC2,0x23,0x3D,0xEE,0x4C,0x95,0x0B,0x42,0xFA,0xC3,0x4E,
    0x08,0x2E,0xA1,0x66,0x28,0xD9,0x24,0xB2,0x76,0x5B,0xA2,0x49,0x6D,0x8B,0xD1,0x25,
    0x72,0xF8,0xF6,0x64,0x86,0x68,0x98,0x16,0xD4,0xA4,0x5C,0xCC,0x5D,0x65,0xB6,0x92,
    0x6C,0x70,0x48,0x50,0xFD,0xED,0xB9,0xDA,0x5E,0x15,0x46,0x57,0xA7,0x8D,0x9D,0x84,
    0x90,0xD8,0xAB,0x00,0x8C,0xBC,0xD3,0x0A,0xF7,0xE4,0x58,0x05,0xB8,0xB3,0x45,0x06,
    0xD0,0x2C,0x1E,0x8F,0xCA,0x3F,0x0F,0x02,0xC1,0xAF,0xBD,0x03,0x01,0x13,0x8A,0x6B,
    0x3A,0x91,0x11,0x41,0x4F,0x67,0xDC,0xEA,0x97,0xF2,0xCF,0xCE,0xF0,0xB4,0xE6,0x73,
    0x96,0xAC,0x74,0x22,0xE7,0xAD,0x35,0x85,0xE2,0xF9,0x37,0xE8,0x1C,0x75,0xDF,0x6E,
    0x47,0xF1,0x1A,0x71,0x1D,0x29,0xC5,0x89,0x6F,0xB7,0x62,0x0E,0xAA,0x18,0xBE,0x1B,
    0xFC,0x56,0x3E,0x4B,0xC6,0xD2,0x79,0x20,0x9A,0xDB,0xC0,0xFE,0x78,0xCD,0x5A,0xF4,
    0x1F,0xDD,0xA8,0x33,0x88,0x07,0xC7,0x31,0xB1,0x12,0x10,0x59,0x27,0x80,0xEC,0x5F,
    0x60,0x51,0x7F,0xA9,0x19,0xB5,0x4A,0x0D,0x2D,0xE5,0x7A,0x9F,0x93,0xC9,0x9C,0xEF,
    0xA0,0xE0,0x3B,0x4D,0xAE,0x2A,0xF5,0xB0,0xC8,0xEB,0xBB,0x3C,0x83,0x53,0x99,0x61,
    0x17,0x2B,0x04,0x7E,0xBA,0x77,0xD6,0x26,0xE1,0x69,0x14,0x63,0x55,0x21,0x0C,0x7D,
])

_AES_RCON = (0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1B,0x36)

def _aes_xtime(a):
    return (((a << 1) ^ 0x1B) & 0xFF) if (a & 0x80) else (a << 1)

def _aes_mix_single_column(a):
    t = a[0] ^ a[1] ^ a[2] ^ a[3]
    u = a[0]
    a[0] ^= t ^ _aes_xtime(a[0] ^ a[1])
    a[1] ^= t ^ _aes_xtime(a[1] ^ a[2])
    a[2] ^= t ^ _aes_xtime(a[2] ^ a[3])
    a[3] ^= t ^ _aes_xtime(a[3] ^ u)

def _aes_inv_mix_columns(s):
    for i in range(4):
        u = _aes_xtime(_aes_xtime(s[i][0] ^ s[i][2]))
        v = _aes_xtime(_aes_xtime(s[i][1] ^ s[i][3]))
        s[i][0] ^= u
        s[i][1] ^= v
        s[i][2] ^= u
        s[i][3] ^= v
    _aes_mix_single_column(s[0])
    _aes_mix_single_column(s[1])
    _aes_mix_single_column(s[2])
    _aes_mix_single_column(s[3])

class _PureAES:
    def __init__(self, master_key):
        self.n_rounds = 10
        self._key_matrices = self._expand_key(master_key)

    def _expand_key(self, master_key):
        key_columns = _aes_bytes2matrix(master_key)
        i = 1
        while len(key_columns) < 44:
            word = list(key_columns[-1])
            if len(key_columns) % 4 == 0:
                word.append(word.pop(0))
                word = [_AES_SBOX[b] for b in word]
                word[0] ^= _AES_RCON[i - 1]
                i += 1
            word = _aes_xor_bytes(word, key_columns[-4])
            key_columns.append(word)
        return [key_columns[4*i:4*(i+1)] for i in range(len(key_columns) // 4)]

    def _decrypt_block(self, ciphertext):
        assert len(ciphertext) == 16
        state = _aes_bytes2matrix(ciphertext)
        self._add_round_key(state, self._key_matrices[-1])
        self._inv_shift_rows(state)
        self._inv_sub_bytes(state)
        for i in range(self.n_rounds - 1, 0, -1):
            self._add_round_key(state, self._key_matrices[i])
            _aes_inv_mix_columns(state)
            self._inv_shift_rows(state)
            self._inv_sub_bytes(state)
        self._add_round_key(state, self._key_matrices[0])
        return _aes_matrix2bytes(state)

    def _add_round_key(self, s, k):
        for i in range(4):
            for j in range(4):
                s[i][j] ^= k[i][j]

    def _inv_shift_rows(self, s):
        s[0][1], s[1][1], s[2][1], s[3][1] = s[3][1], s[0][1], s[1][1], s[2][1]
        s[0][2], s[1][2], s[2][2], s[3][2] = s[2][2], s[3][2], s[0][2], s[1][2]
        s[0][3], s[1][3], s[2][3], s[3][3] = s[1][3], s[2][3], s[3][3], s[0][3]

    def _inv_sub_bytes(self, s):
        for i in range(4):
            for j in range(4):
                s[i][j] = _AES_INV_SBOX[s[i][j]]

    def decrypt_cbc(self, ciphertext, iv):
        ciphertext = base64.b64decode(ciphertext) if isinstance(ciphertext, str) else ciphertext
        iv = iv if isinstance(iv, bytes) else iv.encode('utf-8')
        blocks = []
        previous = iv
        for block in _aes_split_blocks(ciphertext):
            blocks.append(_aes_xor_bytes(previous, self._decrypt_block(block)))
            previous = block
        return _aes_unpad(b''.join(blocks))

# 尝试导入官方加密库
try:
    from Crypto.Cipher import ARC4, AES
    from Crypto.Util.Padding import unpad
    def _rc4_crypt(data, key):
        key = key if isinstance(key, bytes) else key.encode('utf-8')
        data = data if isinstance(data, bytes) else data.encode('utf-8')
        return ARC4.new(key).decrypt(data)
    def _aes_decrypt(data, key, iv):
        cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv.encode('utf-8'))
        return unpad(cipher.decrypt(base64.b64decode(data)), AES.block_size).decode('utf-8')
    CRYPTO_OK = True
except ImportError:
    CRYPTO_OK = False
    def _aes_decrypt(data, key, iv):
        return _PureAES(key.encode('utf-8')).decrypt_cbc(data, iv).decode('utf-8')


class Spider(BaseSpider):
    # ==================== 基础配置 ====================
    name = "M1999藍光影視網"
    base_url = "https://m1999.sbs"
    site_url = "https://m1999.sbs"

    # 聚合搜索配置：声明本源支持壳子全局搜索、快速搜索、筛选和换源聚合
    searchable = 1
    quickSearch = 1
    filterable = 1
    changeable = 1

    # ==================== 请求头 ====================
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://m1999.sbs/",
        "Connection": "keep-alive",
    }

    play_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://m1999.sbs/",
        "Accept": "*/*",
    }

    def __init__(self):
        super().__init__()
        # 复用 TCP 连接
        self._session = requests.Session()
        self._session.headers.update(self.headers)
        self._cookies = ""
        self._play_cache = {}
        self._cache_ttl = 1800
        # 请求间隔控制
        self._last_req_time = 0
        self._min_req_interval = 0.8
        self._block_until = 0
        # 预编译常用正则
        self._re_detail_title = re.compile(r'<h[13][^>]*>([^<]+)</h[13]>')
        self._re_play_link = re.compile(
            r'<a[^>]*href="/vod/play/id/(\d+)/sid/(\d+)/nid/(\d+)\.html"[^>]*>(.*?)</a>'
        )
        # dsn2 模板：class 可能出现在 href 之前（如 <a class="this-link" href="...">）
        self._re_play_link_flex = re.compile(
            r'<a\b[^>]*?href="/vod/play/id/(\d+)/sid/(\d+)/nid/(\d+)\.html"[^>]*>(.*?)</a>'
        )
        # 清洗片名中影响壳子聚合搜索的清晰度/版本/集数后缀
        self._re_name_garbage = re.compile(
            r'[\s\-_]*(?:HD|TC|TS|抢先版|枪版|DVD|BD|1080P|720P|4K|2K|高清|超清|蓝光|国语|粤语|中字|中英双字|完整版|全集|未删减版|(?:第[0-9一二三四五六七八九十]+[集季期]))\s*$',
            re.I
        )

    def _clean_vod_name(self, name):
        """清洗片名，去掉清晰度/版本/集数后缀，方便壳子聚合搜索其它源"""
        if not name:
            return name
        prev = name
        while True:
            cleaned = self._re_name_garbage.sub('', prev).strip()
            if cleaned == prev:
                break
            prev = cleaned
        return prev

    def fetch(self, url, headers=None, timeout=15):
        self._apply_req_delay()
        return self._session.get(url, headers=headers or {}, timeout=timeout)

    def post(self, url, data=None, headers=None, timeout=15):
        self._apply_req_delay()
        return self._session.post(url, data=data, headers=headers or {}, timeout=timeout)

    def _apply_req_delay(self):
        now = time.time()
        if now < self._block_until:
            wait = self._block_until - now
            self._log(f"频率限制冷却中，等待 {wait:.1f}s")
            time.sleep(wait)
            now = time.time()  # 冷却后刷新时间戳，避免用冷却前时间漏算间隔
        elapsed = now - self._last_req_time
        interval = self._min_req_interval
        if 0 < elapsed < interval:
            time.sleep(interval - elapsed)
        self._last_req_time = time.time()

    # ==================== 分类映射（5个分类）====================
    class_name = ["最新電影", "國産劇", "日韓劇", "美劇", "番劇"]
    class_url = ["1", "2", "3", "4", "5"]
    CATEGORY_NAMES = {
        "1": "最新電影",
        "2": "國産劇",
        "3": "日韓劇",
        "4": "美劇",
        "5": "番劇",
    }

    # ==================== 筛选器配置 ====================
    FILTERS = {
        "1": [
            {"key": "area", "name": "地区", "value": [
                {"n": "全部", "v": ""},
                {"n": "大陆", "v": "大陆"},
                {"n": "港台", "v": "港台"},
                {"n": "美国", "v": "美国"},
                {"n": "韩国", "v": "韩国"},
                {"n": "日本", "v": "日本"},
                {"n": "泰国", "v": "泰国"},
                {"n": "印度", "v": "印度"},
                {"n": "法国", "v": "法国"},
                {"n": "英国", "v": "英国"},
            ]},
            {"key": "class", "name": "类型", "value": [
                {"n": "全部", "v": ""},
                {"n": "喜剧", "v": "喜剧"},
                {"n": "爱情", "v": "爱情"},
                {"n": "恐怖", "v": "恐怖"},
                {"n": "动作", "v": "动作"},
                {"n": "科幻", "v": "科幻"},
                {"n": "剧情", "v": "剧情"},
                {"n": "战争", "v": "战争"},
                {"n": "警匪", "v": "警匪"},
                {"n": "犯罪", "v": "犯罪"},
                {"n": "动画", "v": "动画"},
                {"n": "奇幻", "v": "奇幻"},
                {"n": "武侠", "v": "武侠"},
                {"n": "冒险", "v": "冒险"},
            ]},
            {"key": "lang", "name": "语言", "value": [
                {"n": "全部", "v": ""},
                {"n": "国语", "v": "国语"},
                {"n": "粤语", "v": "粤语"},
                {"n": "韩语", "v": "韩语"},
                {"n": "日语", "v": "日语"},
                {"n": "英语", "v": "英语"},
                {"n": "泰语", "v": "泰语"},
            ]},
            {"key": "year", "name": "年份", "value": [
                {"n": "全部", "v": ""},
                {"n": "2026", "v": "2026"},
                {"n": "2025", "v": "2025"},
                {"n": "2024", "v": "2024"},
                {"n": "2023", "v": "2023"},
                {"n": "2022", "v": "2022"},
                {"n": "2021", "v": "2021"},
                {"n": "2020", "v": "2020"},
                {"n": "2019", "v": "2019"},
                {"n": "2018", "v": "2018"},
                {"n": "2017", "v": "2017"},
                {"n": "2016", "v": "2016"},
                {"n": "2015", "v": "2015"},
            ]},
            {"key": "letter", "name": "字母", "value": [
                {"n": "全部", "v": ""},
                {"n": "A", "v": "A"}, {"n": "B", "v": "B"}, {"n": "C", "v": "C"},
                {"n": "D", "v": "D"}, {"n": "E", "v": "E"}, {"n": "F", "v": "F"},
                {"n": "G", "v": "G"}, {"n": "H", "v": "H"}, {"n": "I", "v": "I"},
                {"n": "J", "v": "J"}, {"n": "K", "v": "K"}, {"n": "L", "v": "L"},
                {"n": "M", "v": "M"}, {"n": "N", "v": "N"}, {"n": "O", "v": "O"},
                {"n": "P", "v": "P"}, {"n": "Q", "v": "Q"}, {"n": "R", "v": "R"},
                {"n": "S", "v": "S"}, {"n": "T", "v": "T"}, {"n": "U", "v": "U"},
                {"n": "V", "v": "V"}, {"n": "W", "v": "W"}, {"n": "X", "v": "X"},
                {"n": "Y", "v": "Y"}, {"n": "Z", "v": "Z"},
            ]},
        ],
        "2": [
            {"key": "area", "name": "地区", "value": [
                {"n": "全部", "v": ""},
                {"n": "大陆", "v": "大陆"},
                {"n": "港台", "v": "港台"},
                {"n": "韩国", "v": "韩国"},
                {"n": "日本", "v": "日本"},
            ]},
            {"key": "class", "name": "类型", "value": [
                {"n": "全部", "v": ""},
                {"n": "古装", "v": "古装"},
                {"n": "爱情", "v": "爱情"},
                {"n": "悬疑", "v": "悬疑"},
                {"n": "都市", "v": "都市"},
                {"n": "家庭", "v": "家庭"},
                {"n": "剧情", "v": "剧情"},
                {"n": "历史", "v": "历史"},
                {"n": "战争", "v": "战争"},
                {"n": "犯罪", "v": "犯罪"},
                {"n": "武侠", "v": "武侠"},
            ]},
            {"key": "year", "name": "年份", "value": [
                {"n": "全部", "v": ""},
                {"n": "2026", "v": "2026"},
                {"n": "2025", "v": "2025"},
                {"n": "2024", "v": "2024"},
                {"n": "2023", "v": "2023"},
                {"n": "2022", "v": "2022"},
                {"n": "2021", "v": "2021"},
                {"n": "2020", "v": "2020"},
                {"n": "2019", "v": "2019"},
                {"n": "2018", "v": "2018"},
            ]},
        ],
        "3": [
            {"key": "area", "name": "地区", "value": [
                {"n": "全部", "v": ""},
                {"n": "日本", "v": "日本"},
                {"n": "韩国", "v": "韩国"},
            ]},
            {"key": "class", "name": "类型", "value": [
                {"n": "全部", "v": ""},
                {"n": "爱情", "v": "爱情"},
                {"n": "悬疑", "v": "悬疑"},
                {"n": "都市", "v": "都市"},
                {"n": "家庭", "v": "家庭"},
                {"n": "剧情", "v": "剧情"},
                {"n": "历史", "v": "历史"},
            ]},
            {"key": "year", "name": "年份", "value": [
                {"n": "全部", "v": ""},
                {"n": "2026", "v": "2026"},
                {"n": "2025", "v": "2025"},
                {"n": "2024", "v": "2024"},
                {"n": "2023", "v": "2023"},
                {"n": "2022", "v": "2022"},
                {"n": "2021", "v": "2021"},
                {"n": "2020", "v": "2020"},
                {"n": "2019", "v": "2019"},
                {"n": "2018", "v": "2018"},
            ]},
        ],
        "4": [
            {"key": "area", "name": "地区", "value": [
                {"n": "全部", "v": ""},
                {"n": "美国", "v": "美国"},
                {"n": "英国", "v": "英国"},
                {"n": "加拿大", "v": "加拿大"},
            ]},
            {"key": "class", "name": "类型", "value": [
                {"n": "全部", "v": ""},
                {"n": "动作", "v": "动作"},
                {"n": "科幻", "v": "科幻"},
                {"n": "剧情", "v": "剧情"},
                {"n": "悬疑", "v": "悬疑"},
                {"n": "犯罪", "v": "犯罪"},
                {"n": "奇幻", "v": "奇幻"},
            ]},
            {"key": "year", "name": "年份", "value": [
                {"n": "全部", "v": ""},
                {"n": "2026", "v": "2026"},
                {"n": "2025", "v": "2025"},
                {"n": "2024", "v": "2024"},
                {"n": "2023", "v": "2023"},
                {"n": "2022", "v": "2022"},
                {"n": "2021", "v": "2021"},
                {"n": "2020", "v": "2020"},
                {"n": "2019", "v": "2019"},
                {"n": "2018", "v": "2018"},
            ]},
        ],
        "5": [
            {"key": "area", "name": "地区", "value": [
                {"n": "全部", "v": ""},
                {"n": "日本", "v": "日本"},
                {"n": "大陆", "v": "大陆"},
                {"n": "美国", "v": "美国"},
            ]},
            {"key": "class", "name": "类型", "value": [
                {"n": "全部", "v": ""},
                {"n": "热血", "v": "热血"},
                {"n": "冒险", "v": "冒险"},
                {"n": "科幻", "v": "科幻"},
                {"n": "搞笑", "v": "搞笑"},
                {"n": "奇幻", "v": "奇幻"},
                {"n": "恋爱", "v": "恋爱"},
                {"n": "战斗", "v": "战斗"},
                {"n": "日常", "v": "日常"},
            ]},
            {"key": "year", "name": "年份", "value": [
                {"n": "全部", "v": ""},
                {"n": "2026", "v": "2026"},
                {"n": "2025", "v": "2025"},
                {"n": "2024", "v": "2024"},
                {"n": "2023", "v": "2023"},
                {"n": "2022", "v": "2022"},
                {"n": "2021", "v": "2021"},
                {"n": "2020", "v": "2020"},
            ]},
        ],
    }

    # ==================== 工具方法 ====================
    def _log(self, msg):
        print(f"[{self.name}] {msg}")

    def _md5(self, s):
        return hashlib.md5(s.encode('utf-8')).hexdigest()

    def _rc4_encrypt(self, data, key):
        key_b = key.encode('utf-8') if isinstance(key, str) else key
        data_b = data.encode('utf-8') if isinstance(data, str) else data
        return base64.b64encode(_rc4_crypt(data_b, key_b)).decode('utf-8')

    def _rc4_decrypt(self, data, key):
        key_b = key.encode('utf-8') if isinstance(key, str) else key
        data_b = base64.b64decode(data)
        return _rc4_crypt(data_b, key_b).decode('utf-8')

    def _aes_decrypt(self, data, key, iv):
        return _aes_decrypt(data, key, iv)

    def _clean_html(self, text):
        if not text:
            return ""
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _extract_div_block(self, html, start):
        """从 start 处的 <div ...> 开始，按标签配对提取完整 div 块（兼容 <div> 无属性写法）"""
        open_re = re.compile(r'<div\b[^>]*>', re.I)
        close_re = re.compile(r'</div\s*>', re.I)
        mo = open_re.match(html, start)
        if not mo:
            return ""
        pos = mo.end()
        depth = 1
        while pos < len(html) and depth > 0:
            m_open = open_re.search(html, pos)
            m_close = close_re.search(html, pos)
            if not m_close:
                break
            if m_open and m_open.start() < m_close.start():
                depth += 1
                pos = m_open.end()
            else:
                depth -= 1
                pos = m_close.end()
        return html[start:pos]

    # ==================== Cookie 维护 ====================
    def _extract_cookies(self, resp):
        """从响应中提取 Set-Cookie 并追加到 self._cookies"""
        cookie_list = []
        try:
            if hasattr(resp, 'cookies') and resp.cookies:
                for c in resp.cookies:
                    cookie_list.append(f"{c.name}={c.value}")
        except Exception:
            pass
        try:
            if hasattr(resp.headers, "get_all"):
                for c in resp.headers.get_all("Set-Cookie"):
                    cookie_list.append(c.split(";")[0])
            elif "Set-Cookie" in resp.headers:
                raw = resp.headers["Set-Cookie"]
                if isinstance(raw, list):
                    for c in raw:
                        cookie_list.append(c.split(";")[0])
                else:
                    cookie_list.append(raw.split(";")[0])
        except Exception:
            pass
        if cookie_list:
            existing = {k.strip(): v for k, v in [x.split('=', 1) for x in self._cookies.split('; ') if '=' in x]}
            for c in cookie_list:
                if '=' in c:
                    k, v = c.split('=', 1)
                    existing[k.strip()] = v
            self._cookies = "; ".join(f"{k}={v}" for k, v in existing.items())

    def _fetch_cookies(self):
        try:
            h = {"User-Agent": self.headers["User-Agent"], "Accept": "text/html", "Referer": self.base_url + "/"}
            resp = self.fetch(self.base_url, headers=h)
            self._extract_cookies(resp)
            if self._cookies:
                self._log(f"Cookie获取成功: {self._cookies[:80]}")
        except Exception as e:
            self._log(f"Cookie获取失败: {e}")
            self._cookies = ""

    def _is_blocked_page(self, html):
        """检测 IP 频率限制等封禁页面"""
        if not html:
            return True
        markers = (
            'You are being rate limited',
            'Error 1015',
            'cf-error-details',
            'Access denied |',
            'Banned',
            '您的访问过于频繁',
        )
        return any(m in html for m in markers)

    def _get(self, url, max_retry=3, timeout=10):
        """GET请求封装（依赖 Session 自动维护 Cookie，含异常捕获+重试+频率限制检测）"""
        h = self.headers.copy()
        html = ""
        try:
            for attempt in range(max_retry):
                resp = self.fetch(url, headers=h, timeout=timeout)
                self._extract_cookies(resp)
                if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
                    resp.encoding = resp.apparent_encoding or "utf-8"
                html = resp.text
                # 触发频率限制时冷却后重试
                if self._is_blocked_page(html):
                    wait = 2 + attempt * 2
                    self._block_until = time.time() + wait
                    self._log(f"请求被频率限制，进入 {wait}s 冷却: {url}")
                    if attempt < max_retry - 1:
                        time.sleep(wait)
                        continue
                    return ""
                return html
            return html
        except Exception as e:
            self._log(f"请求失败: {url}, {e}")
            if not self._cookies:
                self._log("尝试重新获取Cookie...")
                self._fetch_cookies()
                try:
                    return self.fetch(url, headers=h, timeout=timeout).text
                except Exception as e2:
                    self._log(f"重试失败: {e2}")
            return ""

    def _post_api(self, api, data, max_retry=2, timeout=12):
        """dsn2 模板列表接口：POST /index.php/{api}，返回 JSON dict，失败返回 {}"""
        url = f"{self.base_url}/index.php/{api}"
        h = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{self.base_url}/vod/show/id/{data.get('type', '1')}.html",
        }
        for attempt in range(max_retry):
            try:
                self._apply_req_delay()
                resp = self._session.post(url, data=data, headers=h, timeout=timeout)
                self._extract_cookies(resp)
                j = resp.json()
                if isinstance(j, dict) and j.get("code") in (1, "1"):
                    return j
                self._log(f"接口返回异常: {str(j)[:100]}")
            except Exception as e:
                self._log(f"接口请求失败({attempt+1}/{max_retry}): {url}, {e}")
                time.sleep(1 + attempt)
        return {}

    def _norm_item(self, item):
        """把 dsn2 JSON 条目统一成壳子列表结构"""
        vod = {
            "vod_id": str(item.get("vod_id", "")),
            "vod_name": self._clean_vod_name(item.get("vod_name", "") or ""),
            "vod_pic": item.get("vod_pic", "") or "",
            "vod_remarks": item.get("vod_remarks", "") or "",
        }
        if vod["vod_pic"].startswith("//"):
            vod["vod_pic"] = "https:" + vod["vod_pic"]
        return vod

    # ==================== 解析方法 ====================
    def _extract_dsn2_field(self, html, label):
        """dsn2 详情页字段：<strong>导演 :</strong><a>郭帆</a><span>,</span><a>..."""
        m = re.search(
            r'<strong[^>]*>\s*' + label + r'\s*[:：]\s*</strong>(.*?)(?=<strong[^>]*>|$)',
            html, re.DOTALL
        )
        if not m:
            return ""
        names = re.findall(r'<a[^>]*>(.*?)</a>', m.group(1), re.DOTALL)
        names = [self._clean_html(n) for n in names if self._clean_html(n)]
        return ",".join(names)

    def _parse_search_list_dsn2(self, html):
        """dsn2 模板搜索页解析：vod-detail/search-list 块结构"""
        videos = []
        if not html:
            return videos
        for m in re.finditer(r'<div[^>]*class="[^"]*search-list[^"]*"[^>]*>', html):
            block = self._extract_div_block(html, m.start())

            link = re.search(r'<a[^>]*href="/vod/detail/id/(\d+)\.html"', block)
            if not link:
                continue
            vod_id = link.group(1)

            title = re.search(r'<h3[^>]*>(.*?)</h3>', block, re.DOTALL)
            vod_name = self._clean_vod_name(self._clean_html(title.group(1))) if title else "未知"

            pic = re.search(r'<img[^>]*data-src="([^"]+)"', block)
            if not pic:
                pic = re.search(r'<img[^>]*data-original="([^"]+)"', block)
            vod_pic = pic.group(1) if pic else ""
            if vod_pic.startswith("//"):
                vod_pic = "https:" + vod_pic

            note = re.search(r'<span[^>]*class="[^"]*slide-info-remarks[^"]*"[^>]*>(.*?)</span>', block, re.DOTALL)
            vod_remarks = self._clean_html(note.group(1)) if note else ""

            year = re.search(r'/vod/search/year/(\d{4})\.html', block)
            area = re.search(r'/vod/search/area/([^"\']+)\.html', block)
            ctype = re.search(r'/vod/search/class/([^"\']+)\.html', block)
            video = {
                "vod_id": vod_id,
                "vod_name": vod_name,
                "vod_pic": vod_pic,
                "vod_remarks": vod_remarks,
            }
            if year:
                video["vod_year"] = year.group(1)
            if area:
                video["vod_area"] = urllib.parse.unquote(area.group(1))
            if ctype:
                video["vod_type"] = urllib.parse.unquote(ctype.group(1))
            videos.append(video)
        return videos

    def _parse_play_sources_dsn2(self, html, vod_id):
        """dsn2 模板详情页：anthology-tab 线路名 + anthology-list-box 集数块"""
        sources = []
        if not html:
            return sources

        # 1. 线路名称：<div class="anthology-tab ..."><div class="swiper-wrapper"><a ...>蓝光专线</a>...
        names = []
        tab_m = re.search(r'<div[^>]*class="[^"]*anthology-tab[^"]*"[^>]*>(.*?)</div>\s*<div[^>]*class="[^"]*anthology-list', html, re.DOTALL)
        if tab_m:
            for a in re.finditer(r'<a\b[^>]*>(.*?)</a>', tab_m.group(1), re.DOTALL):
                nm = self._clean_html(a.group(1)).replace('\xa0', ' ').strip()
                nm = re.sub(r'^(?:&nbsp;|\s)+', '', nm)
                if nm and nm not in names:
                    names.append(nm)

        # 2. 集数块：<ul class="anthology-list-play ..."> ... </ul>
        blocks = re.findall(r'<ul[^>]*class="[^"]*anthology-list-play[^"]*"[^>]*>(.*?)</ul>', html, re.DOTALL)

        for idx, block in enumerate(blocks):
            eps = []
            for em in self._re_play_link.finditer(block):
                id_, sid, nid, name = em.groups()
                name = self._clean_html(name)
                ep_name = name if name else f"第{nid}集"
                eps.append({"name": ep_name, "link": f"{id_}-{sid}-{nid}"})
            if eps:
                sources.append({
                    "source_name": names[idx] if idx < len(names) else f"源{idx+1}",
                    "episodes": eps,
                })
        return sources

    def _parse_video_list(self, html):
        """通用列表解析（首页/分类页）"""
        videos = []
        if not html:
            return videos

        # MacCMS dsn2 模板标准列表结构
        # 模式1: module-poster-item 风格
        pattern = (
            r'<a[^>]*href="/vod/detail/id/(\d+)\.html"[^>]*class="[^"]*module-poster-item[^"]*"[^>]*>'
            r'.*?<div[^>]*class="[^"]*module-item-note[^"]*"[^>]*>([^<]*)</div>'
            r'.*?<img[^>]*(?:data-original|data-src)="([^"]+)"[^>]*>'
            r'.*?<div[^>]*class="[^"]*module-poster-item-title[^"]*"[^>]*>([^<]*)</div>'
        )
        for m in re.finditer(pattern, html, re.DOTALL):
            vod_id   = m.group(1)
            vod_note = m.group(2).strip()
            vod_pic  = m.group(3).strip()
            vod_name = self._clean_vod_name(m.group(4).strip())
            if vod_pic.startswith("//"):
                vod_pic = "https:" + vod_pic
            videos.append({
                "vod_id": vod_id,
                "vod_name": vod_name,
                "vod_pic": vod_pic,
                "vod_remarks": vod_note,
            })

        if videos:
            return videos

        # 模式2: 更宽松的匹配
        pattern2 = (
            r'<a[^>]*href="/vod/detail/id/(\d+)\.html"[^>]*>'
            r'.*?<img[^>]*(?:data-original|data-src)="([^"]+)"[^>]*>'
            r'.*?<(?:div|span)[^>]*class="[^"]*module-item-note[^"]*"[^>]*>([^<]*)</(?:div|span)>'
            r'.*?<div[^>]*class="[^"]*(?:title|name)[^"]*"[^>]*>([^<]*)</div>'
        )
        for m in re.finditer(pattern2, html, re.DOTALL):
            vod_id   = m.group(1)
            vod_pic  = m.group(2).strip()
            vod_note = m.group(3).strip()
            vod_name = self._clean_vod_name(m.group(4).strip())
            if vod_pic.startswith("//"):
                vod_pic = "https:" + vod_pic
            videos.append({
                "vod_id": vod_id,
                "vod_name": vod_name,
                "vod_pic": vod_pic,
                "vod_remarks": vod_note,
            })

        if videos:
            return videos

        # 模式3: 通用 vod 卡片匹配（兜底）
        pattern3 = (
            r'<a[^>]*href="/vod/detail/id/(\d+)\.html"[^>]*>'
            r'.*?<img[^>]*(?:data-original|data-src)="([^"]+)"[^>]*>'
            r'.*?title="([^"]*)"'
        )
        for m in re.finditer(pattern3, html, re.DOTALL):
            vod_id   = m.group(1)
            vod_pic  = m.group(2).strip()
            vod_name = self._clean_vod_name(m.group(3).strip())
            if vod_pic.startswith("//"):
                vod_pic = "https:" + vod_pic
            videos.append({
                "vod_id": vod_id,
                "vod_name": vod_name,
                "vod_pic": vod_pic,
                "vod_remarks": "",
            })

        return videos

    def _parse_search_list(self, html):
        """搜索页专用解析（优先 dsn2 search-list 结构，回退 apple cms module-card-item）"""
        videos = []
        if not html:
            return videos

        # dsn2 模板：search-list 块
        if "search-list" in html:
            videos = self._parse_search_list_dsn2(html)
            if videos:
                return videos

        # 匹配搜索结果卡片
        for m in re.finditer(r'<div[^>]*class="(?:[^"]*\s)?module-card-item(?:\s[^"]*)?"[^>]*>', html):
            block = self._extract_div_block(html, m.start())

            link = re.search(r'<a[^>]*href="/vod/detail/id/(\d+)\.html"', block)
            if not link:
                continue
            vod_id = link.group(1)

            title = re.search(r'<h3[^>]*>(.*?)</h3>', block, re.DOTALL)
            vod_name = self._clean_vod_name(self._clean_html(title.group(1))) if title else "未知"

            pic = re.search(r'<img[^>]*(?:data-original|data-src)="([^"]+)"', block)
            vod_pic = pic.group(1) if pic else ""
            if vod_pic.startswith("//"):
                vod_pic = "https:" + vod_pic

            note = re.search(r'<div[^>]*class="[^"]*module-item-note[^"]*"[^>]*>([^<]*)</div>', block)
            vod_remarks = note.group(1).strip() if note else ""

            video = {
                "vod_id": vod_id,
                "vod_name": vod_name,
                "vod_pic": vod_pic,
                "vod_remarks": vod_remarks,
            }
            # 提取年份/地区/类型辅助聚合匹配
            info_text = re.sub(r'<[^>]+>', ' ', block)
            year = re.search(r'年份[:：\s]+(\d{4})', info_text)
            if year:
                video["vod_year"] = year.group(1)
            area = re.search(r'地区[:：\s]+([^\s<]+)', info_text)
            if area:
                video["vod_area"] = area.group(1).strip()
            ctype = re.search(r'类型[:：\s]+([^\s<]+)', info_text)
            if ctype:
                video["vod_type"] = ctype.group(1).strip()

            videos.append(video)

        # 兜底：如果 module-card-item 没匹配到，用更宽松的方式
        if not videos:
            for m in re.finditer(
                r'<a[^>]*href="/vod/detail/id/(\d+)\.html"[^>]*>.*?'
                r'<img[^>]*(?:data-original|data-src)="([^"]+)".*?'
                r'<h3[^>]*>(.*?)</h3>',
                html, re.DOTALL
            ):
                vod_id = m.group(1)
                vod_pic = m.group(2).strip()
                vod_name = self._clean_vod_name(self._clean_html(m.group(3)))
                if vod_pic.startswith("//"):
                    vod_pic = "https:" + vod_pic
                videos.append({
                    "vod_id": vod_id,
                    "vod_name": vod_name,
                    "vod_pic": vod_pic,
                    "vod_remarks": "",
                })

        return videos

    def _parse_play_sources(self, html, vod_id):
        """解析播放线路与集数（优先 dsn2 anthology 结构，回退 apple cms tab-item）"""
        sources = []
        if not html:
            return sources

        # dsn2 模板：anthology-tab / anthology-list-box
        if "anthology-list-play" in html:
            sources = self._parse_play_sources_dsn2(html, vod_id)
            if sources:
                pass
            else:
                sources = []
        if not sources and "anthology" in html:
            sources = self._parse_play_sources_dsn2(html, vod_id)
        if sources:
            self._rank_sources(sources)
            return sources

        # 1. 提取线路名称
        _BAD_NAMES = ("排序", "更多", "切换", "展开", "收起", "选择播放源")
        source_names = []
        # 优先从 data-dropdown-value 属性取
        for m in re.finditer(r'<div[^>]*class="[^"]*tab-item[^"]*"[^>]*data-dropdown-value="([^"]+)"', html):
            name = m.group(1).strip()
            if name and name not in source_names and name not in _BAD_NAMES:
                source_names.append(name)
        # 兜底：从 span 文本取
        if not source_names:
            for m in re.finditer(r'<div[^>]*class="[^"]*tab-item[^"]*"[^>]*>.*?<span[^>]*>([^<]*)</span>', html, re.DOTALL):
                name = m.group(1).strip()
                if name and name not in source_names and name not in _BAD_NAMES:
                    source_names.append(name)
        if not source_names:
            for m in re.finditer(r'<span[^>]*class="[^"]*module-tab-value"[^>]*>([^<]*)</span>', html):
                name = m.group(1).strip()
                if name and name not in source_names and name not in _BAD_NAMES:
                    source_names.append(name)

        # 2. 用正则提取 module-list 块
        list_blocks = []
        for m in re.finditer(r'<div[^>]*class="[^"]*module-list[^"]*tab-list[^"]*"[^>]*>', html):
            block = self._extract_div_block(html, m.start())
            if '/vod/play/' in block:
                list_blocks.append(block)

        # 3. 对齐名称与块数量
        if len(source_names) > len(list_blocks):
            source_names = source_names[:len(list_blocks)]
        while len(source_names) < len(list_blocks):
            source_names.append(f"源{len(source_names)+1}")

        # 4. 解析每个块的集数
        for idx, block in enumerate(list_blocks):
            eps = []
            for m in self._re_play_link.finditer(block):
                id_, sid, nid, name = m.groups()
                name = self._clean_html(name)
                ep_name = name if name else f"第{nid}集"
                eps.append({"name": ep_name, "link": f"{id_}-{sid}-{nid}"})
            if eps:
                sources.append({
                    "source_name": source_names[idx] if idx < len(source_names) else f"源{idx+1}",
                    "episodes": eps
                })

        # 5. 最终兜底：全页面匹配
        if not sources:
            eps = []
            for m in self._re_play_link.finditer(html):
                id_, sid, nid, name = m.groups()
                name = self._clean_html(name)
                ep_name = name if name else f"第{nid}集"
                eps.append({"name": ep_name, "link": f"{id_}-{sid}-{nid}"})
            if eps:
                sources.append({"source_name": "默认", "episodes": eps})

        # 6. 4K/蓝光线路置顶
        self._rank_sources(sources)
        return sources

    def _rank_sources(self, sources):
        """4K/蓝光线路置顶、空集数线路沉底（原地排序）"""
        if not sources:
            return
        def _rank(i):
            name = sources[i]["source_name"]
            is_4k = any(k in name for k in ("4K", "4k", "2160", "2160P", "2160p"))
            is_bluray = "蓝光" in name
            cnt = len(sources[i]["episodes"])
            no_eps = 1 if cnt == 0 else 0
            order = 0 if is_4k else (1 if is_bluray else 2)
            return (no_eps, order, i)
        sources[:] = [sources[i] for i in sorted(range(len(sources)), key=_rank)]

    # ==================== 播放地址解析 ====================
    def _extract_player_aaaa(self, html):
        """从播放页 HTML 中提取 player_aaaa 字典"""
        if not html:
            return None
        m = re.search(r'var\s+player_aaaa\s*=\s*', html)
        if not m:
            return None
        start = m.end()
        while start < len(html) and html[start] != '{':
            start += 1
        if start >= len(html):
            return None

        depth = 1
        i = start + 1
        in_string = False
        escape = False
        while i < len(html) and depth > 0:
            c = html[i]
            if in_string:
                if escape:
                    escape = False
                elif c == '\\':
                    escape = True
                elif c == '"':
                    in_string = False
            else:
                if c == '"':
                    in_string = True
                elif c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
            i += 1

        if depth == 0:
            try:
                return json.loads(html[start:i])
            except Exception as e:
                self._log(f"player_aaaa JSON解析失败: {e}")
        return None

    def _get_play_url(self, vod_id, sid, nid):
        """获取真实播放地址"""
        play_page = f"{self.base_url}/vod/play/id/{vod_id}/sid/{sid}/nid/{nid}.html"
        cache_key = f"{vod_id}-{sid}-{nid}"
        now = time.time()
        if cache_key in self._play_cache:
            url, ts = self._play_cache[cache_key]
            if now - ts < self._cache_ttl:
                self._log(f"播放地址缓存命中: {cache_key}")
                return url

        try:
            html = self._get(play_page, max_retry=2, timeout=8)
            if not html:
                self._log(f"播放页无响应, 回退播放页URL: {play_page}")
                return play_page

            player_data = self._extract_player_aaaa(html)
            if not player_data:
                self._log("未能提取到player_aaaa, 回退播放页URL")
                return play_page

            enc_url = player_data.get("url", "")
            encrypt = str(player_data.get("encrypt", "0"))
            from_ = str(player_data.get("from", ""))
            self._log(f"player_aaaa encrypt={encrypt}, from={from_}, url={enc_url[:60]}...")

            # 处理 MacCMS 加密方式
            if encrypt == "1":
                try:
                    enc_url = urllib.parse.unquote(enc_url)
                except Exception:
                    pass
            elif encrypt == "2":
                try:
                    enc_url = urllib.parse.unquote(base64.b64decode(enc_url).decode('utf-8'))
                except Exception:
                    pass

            if not enc_url:
                return play_page

            # 如果已经是直链（m3u8/mp4/flv等）
            if re.search(r'\.(m3u8|mp4|flv|ts|mkv)(\?|#|$)', enc_url, re.I):
                self._log(f"player_aaaa已是直链: {enc_url[:80]}")
                self._play_cache[cache_key] = (enc_url, now)
                return enc_url

            # 非直链，回退到播放页让壳子 WebView 解析
            self._log(f"非直链地址，回退播放页URL: {enc_url[:80]}")
            self._play_cache[cache_key] = (play_page, now)
            return play_page

        except Exception as e:
            self._log(f"获取播放地址异常: {e}")
            return play_page

    # ==================== TVBox 核心方法 ====================
    def init(self, extend=''):
        self._fetch_cookies()
        self._log("初始化完成")

    def homeContent(self, filter=False):
        result = {
            "class": [
                {"type_id": tid, "type_name": name}
                for tid, name in self.CATEGORY_NAMES.items()
            ]
        }
        if filter:
            result["filters"] = self.FILTERS
            result["filter"] = self.FILTERS
        return result

    def homeVideoContent(self):
        try:
            html = self._get(self.base_url)
            if not html:
                return {"list": []}
            videos = self._parse_video_list(html)
            if not videos:
                # 兜底：从任意详情链接+图片中提取（首页结构多变时保底）
                videos = self._parse_home_fallback(html)
            # 首页可能混入重复/非影片条目，去重后取前20
            seen = set()
            uniq = []
            for v in videos:
                if v["vod_id"] in seen or not v.get("vod_pic"):
                    continue
                seen.add(v["vod_id"])
                uniq.append(v)
            return {"list": uniq[:20]}
        except Exception as e:
            self._log(f"homeVideoContent异常: {e}")
            return {"list": []}

    def _parse_home_fallback(self, html):
        """首页兜底：从 detail 链接附近提取 id/图片/标题"""
        videos = []
        for m in re.finditer(
            r'<a[^>]*href="/vod/detail/id/(\d+)\.html"[^>]*>(.*?)</a>',
            html, re.DOTALL
        ):
            vod_id, inner = m.group(1), m.group(2)
            pic = re.search(r'<img[^>]*(?:data-original|data-src|src)="([^"]+)"', inner)
            if not pic:
                continue
            vod_pic = pic.group(1)
            if vod_pic.startswith("data:"):
                continue
            if vod_pic.startswith("//"):
                vod_pic = "https:" + vod_pic
            t = re.search(r'title="([^"]+)"', m.group(0))
            vod_name = self._clean_vod_name(t.group(1)) if t else ""
            videos.append({"vod_id": vod_id, "vod_name": vod_name, "vod_pic": vod_pic, "vod_remarks": ""})
        return videos

    def _quote_filter_value(self, v):
        """对筛选值统一编码"""
        if not v:
            return ""
        try:
            return quote(urllib.parse.unquote(str(v)))
        except Exception:
            return quote(str(v))

    def _build_category_url(self, tid, pg, flt):
        """构造分类筛选 URL: /vod/show/id/{type_id}/area/{area}/class/{class}/lang/{lang}/year/{year}/page/{page}.html"""
        area = self._quote_filter_value(flt.get("area", ""))
        class_ = self._quote_filter_value(flt.get("class", ""))
        lang = self._quote_filter_value(flt.get("lang", ""))
        year = self._quote_filter_value(flt.get("year", ""))
        letter = self._quote_filter_value(flt.get("letter", ""))

        url = f"{self.base_url}/vod/show/id/{tid}"
        if area:
            url += f"/area/{area}"
        if class_:
            url += f"/class/{class_}"
        if lang:
            url += f"/lang/{lang}"
        if letter:
            url += f"/letter/{letter}"
        if year:
            url += f"/year/{year}"
        if pg > 1:
            url += f"/page/{pg}"
        url += ".html"
        return url

    def categoryContent(self, tid, pg, filter=False, content=None):
        try:
            pg = int(pg)
            if str(tid) not in self.CATEGORY_NAMES:
                return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}

            flt = {}
            if content:
                try:
                    flt = json.loads(content) if isinstance(content, str) else content
                except Exception:
                    flt = {}

            # dsn2 模板：分类页为壳，列表走 POST /index.php/ds_api/vod JSON 接口
            data = {
                "type": str(tid),
                "class": self._quote_filter_value(flt.get("class", "")),
                "area": self._quote_filter_value(flt.get("area", "")),
                "year": self._quote_filter_value(flt.get("year", "")),
                "lang": self._quote_filter_value(flt.get("lang", "")),
                "version": "",
                "state": "",
                "letter": self._quote_filter_value(flt.get("letter", "")),
                "time": "",
                "level": "0",
                "weekday": "",
                "by": str(flt.get("by", "")),
                "page": pg,
            }
            j = self._post_api("ds_api/vod", data)
            if j:
                videos = [self._norm_item(it) for it in j.get("list", []) if isinstance(it, dict)]
                pagecount = int(j.get("pagecount") or pg or 1)
                total = int(j.get("total") or len(videos))
                limit = int(j.get("limit") or 40)
                self._log(f"分类接口成功: tid={tid} pg={pg}, {len(videos)}条/{total}条, {pagecount}页")
                return {
                    "list": videos,
                    "page": pg,
                    "pagecount": max(pagecount, 1),
                    "limit": limit,
                    "total": total,
                }

            # 兜底：老的 HTML 分页路径（站点模板回退时仍可用）
            url = self._build_category_url(tid, pg, flt)
            self._log(f"JSON接口失败，回退HTML分类请求: {url}")
            html = self._get(url)
            if not html:
                return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}
            videos = self._parse_video_list(html)
            pagecount = 1
            pages = re.findall(r'/page/(\d+)', html)
            if pages:
                pagecount = max(int(p) for p in pages)
            return {
                "list": videos,
                "page": pg,
                "pagecount": max(pagecount, 1),
                "limit": 20,
                "total": pagecount * 20
            }
        except Exception as e:
            self._log(f"categoryContent异常: {e}")
            return {"list": [], "page": pg if 'pg' in dir() else 1, "pagecount": 1, "limit": 20, "total": 0}

    def searchContent(self, key, quick=False, pg="1"):
        """站点搜索（m1999 无反爬验证码，直接请求即可）"""
        try:
            pg = max(1, int(pg or 1))
        except (TypeError, ValueError):
            pg = 1
        keyword = str(key or "").strip()
        if not keyword:
            return {"page": pg, "pagecount": 1, "limit": 0, "total": 0, "list": []}
        is_quick = bool(quick)
        encoded_key = quote(keyword)

        # 构造搜索 URL
        if pg > 1:
            url = f"{self.base_url}/vod/search/page/{pg}/wd/{encoded_key}.html"
        else:
            url = f"{self.base_url}/vod/search/wd/{encoded_key}.html"
        self._log(f"搜索请求: {url}, quick={is_quick}")

        try:
            html = self._get(url)
            if not html:
                return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}
            videos = self._parse_search_list(html)

            if not is_quick:
                # 普通搜索按标题相关度排序
                key_lower = keyword.lower()
                def _sort_score(v):
                    name = v.get('vod_name', '').lower()
                    if name == key_lower:
                        return 0
                    if name.startswith(key_lower):
                        return 1
                    if key_lower in name:
                        return 2
                    return 3
                videos = sorted(videos, key=_sort_score)

            return {
                "list": videos,
                "page": pg,
                "pagecount": 9999,
                "limit": 20,
                "total": 999999
            }
        except Exception as e:
            self._log(f"搜索Content异常: {e}")
            return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}

    def detailContent(self, ids):
        try:
            vod_id = ids[0] if isinstance(ids, list) else str(ids)
            url = f"{self.base_url}/vod/detail/id/{vod_id}.html"
            self._log(f"详情请求: {url}")
            html = self._get(url)
            if not html:
                return {"list": []}

            is_dsn2 = ("anthology-list-play" in html) or ("slide-info-title" in html)

            # 提取标题
            vod_name = "未知"
            title = None
            if is_dsn2:
                title = re.search(r'<h3[^>]*class="[^"]*slide-info-title[^"]*"[^>]*>(.*?)</h3>', html, re.DOTALL)
            if not title:
                title = self._re_detail_title.search(html)
            if title:
                vod_name = self._clean_vod_name(self._clean_html(title.group(1)))

            # 提取图片
            vod_pic = ""
            if is_dsn2:
                pic = re.search(r'<div[^>]*class="[^"]*detail-pic[^"]*"[^>]*>.*?<img[^>]*data-src="([^"]+)"', html, re.DOTALL)
                if pic:
                    vod_pic = pic.group(1)
            if not vod_pic:
                for pattern in [
                    r'<div[^>]*class="[^"]*module-item-pic[^"]*"[^>]*>.*?<img[^>]*(?:data-original|data-src)="([^"]+)"',
                    r'<img[^>]*(?:data-original|data-src)="([^"]+)"[^>]*class="[^"]*cover[^"]*"',
                    r'<img[^>]*(?:data-original|data-src)="([^"]+)"',
                ]:
                    pic = re.search(pattern, html, re.DOTALL)
                    if pic:
                        vod_pic = pic.group(1)
                        break
            if vod_pic.startswith("//"):
                vod_pic = "https:" + vod_pic

            # 提取简介
            vod_content = ""
            if is_dsn2:
                desc = re.search(r'<div[^>]*id="height_limit"[^>]*>(.*?)</div>', html, re.DOTALL)
                if desc:
                    vod_content = self._clean_html(desc.group(1))
            if not vod_content:
                desc = re.search(r'<div[^>]*class="[^"]*module-info-introduction-content[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
                if not desc:
                    desc = re.search(r'简介[：:]*\s*</span>.*?(?:<p[^>]*>|<div[^>]*>)(.*?)</(?:p|div)>', html, re.DOTALL)
                if desc:
                    vod_content = self._clean_html(desc.group(1))

            # 提取演员（dsn2: 演员 : 后跟若干 <a>）
            vod_actor = ""
            if is_dsn2:
                vod_actor = self._extract_dsn2_field(html, "演员")
            if not vod_actor:
                actor = re.search(r'主演[：:]\s*</span>.*?<div[^>]*class="[^"]*module-info-item-content[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
                if not actor:
                    actor = re.search(r'主演[：:]\s*</span>\s*(.*?)(?:</div>|</p>|<span)', html, re.DOTALL)
                if actor:
                    vod_actor = self._clean_html(actor.group(1))

            # 提取导演
            vod_director = ""
            if is_dsn2:
                vod_director = self._extract_dsn2_field(html, "导演")
            if not vod_director:
                director = re.search(r'[导導]演[：:]\s*</span>.*?<div[^>]*class="[^"]*module-info-item-content[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
                if not director:
                    director = re.search(r'[导導]演[：:]\s*</span>\s*(.*?)(?:</div>|</p>|<span)', html, re.DOTALL)
                if director:
                    vod_director = self._clean_html(director.group(1))

            # 提取年份
            vod_year = ""
            if is_dsn2:
                year = re.search(r'/vod/search/year/(\d{4})\.html', html)
                if not year:
                    year = re.search(r'(\d{4})-\d{2}-\d{2}上映', html)
                if year:
                    vod_year = year.group(1)
            if not vod_year:
                year = re.search(r'<a[^>]*title="(\d{4})"', html)
                if not year:
                    year = re.search(r'年份[：:]\s*</span>\s*(\d{4})', html)
                if year:
                    vod_year = year.group(1)

            # 提取地区
            vod_area = ""
            if is_dsn2:
                area = re.search(r'/vod/search/area/([^"\']+)\.html', html)
                if area:
                    vod_area = urllib.parse.unquote(area.group(1))
            if not vod_area:
                area_match = re.search(r'地区[：:]\s*</span>\s*(.*?)(?:</div>|</p>|<span|<a)', html, re.DOTALL)
                if area_match:
                    vod_area = self._clean_html(area_match.group(1))

            # 提取类型
            vod_type = ""
            if is_dsn2:
                types = re.findall(r'/vod/search/class/([^"\']+)\.html', html)
                if types:
                    vod_type = ",".join(dict.fromkeys(urllib.parse.unquote(t) for t in types))
            if not vod_type:
                type_match = re.search(r'[类類]型[：:]\s*</span>\s*(.*?)(?:</div>|</p>|<span|<a)', html, re.DOTALL)
                if type_match:
                    vod_type = self._clean_html(type_match.group(1))

            # 提取更新/集数状态
            vod_remarks = ""
            if is_dsn2:
                rm = re.search(r'<span[^>]*class="[^"]*slide-info-remarks[^"]*"[^>]*>(.*?)</span>', html, re.DOTALL)
                if rm:
                    vod_remarks = self._clean_html(rm.group(1))
            if not vod_remarks:
                remark_patterns = [
                    r'集[数數][：:]\s*</span>.*?<div[^>]*class="[^"]*module-info-item-content[^"]*"[^>]*>(.*?)</div>',
                    r'更新[：:]\s*</span>.*?(?:<p[^>]*>|<div[^>]*class="[^"]*module-info-item-content[^"]*"[^>]*>)(.*?)</(?:p|div)>',
                    r'[状狀]态[：:]\s*</span>.*?<div[^>]*class="[^"]*module-info-item-content[^"]*"[^>]*>(.*?)</div>',
                ]
                for pat in remark_patterns:
                    m = re.search(pat, html, re.DOTALL)
                    if m:
                        vod_remarks = self._clean_html(m.group(1))
                        if vod_remarks:
                            break

            # 解析播放源
            sources = self._parse_play_sources(html, vod_id)
            if not sources:
                self._log("未能解析到播放源")
                return {"list": []}

            from_list = []
            url_list = []
            for src in sources:
                from_list.append(src["source_name"])
                eps_str = "#".join([f"{ep['name']}${ep['link']}" for ep in src["episodes"]])
                url_list.append(eps_str)

            vod_play_from = "$$$".join(from_list)
            vod_play_url = "$$$".join(url_list)

            video = {
                "vod_id": vod_id,
                "vod_name": vod_name,
                "vod_pic": vod_pic,
                "vod_year": vod_year,
                "vod_area": vod_area,
                "vod_type": vod_type,
                "vod_actor": vod_actor,
                "vod_director": vod_director,
                "vod_content": vod_content,
                "vod_remarks": vod_remarks,
                "vod_play_from": vod_play_from,
                "vod_play_url": vod_play_url,
            }
            self._log(f"详情解析成功: {vod_name}, 线路: {vod_play_from}")
            return {"list": [video]}
        except Exception as e:
            self._log(f"detailContent异常: {e}")
            return {"list": []}

    def playerContent(self, flag, id, vipFlags=None):
        try:
            parts = str(id).split("-")
            if len(parts) != 3:
                return {"parse": 0, "url": "", "header": ""}
            vod_id, sid, nid = parts
            play_page = f"{self.base_url}/vod/play/id/{vod_id}/sid/{sid}/nid/{nid}.html"
            play_url = self._get_play_url(vod_id, sid, nid)

            if not play_url:
                play_url = play_page

            # 判断是否为直链
            is_direct = bool(re.search(r'\.(m3u8|mp4|flv|ts|mkv)([?#&]|$)', play_url, re.I))
            is_parse_page = play_url.startswith(play_page)
            parse_flag = 0 if (is_direct or not is_parse_page) else 1
            self._log(f"播放URL: {play_url[:80]}..., parse={parse_flag}")

            if parse_flag == 0:
                return {"parse": 0, "url": play_url, "header": self.play_headers.copy()}
            else:
                return {"parse": 1, "url": play_url, "header": ""}
        except Exception as e:
            self._log(f"playerContent异常: {e}")
            return {"parse": 0, "url": "", "header": ""}

    def getName(self):
        return self.name

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    def localProxy(self, param):
        pass
