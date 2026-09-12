# -*- coding: utf-8 -*-
"""
蝴蝶影视 - www.ahshfshygzc.com
参考歪比巴卜(wbbb1.com)插件架构适配本站（ewave 模板 / MacCMS v10 路由）：

1. 路由差异适配：
   - 分类列表  /vodtype/{tid}.html 与 /vodtype/{tid}-{page}.html（尾页/页码 span 取总页数）
   - 分类筛选  /vodshow/ 12 段固定位（tid-area--class-lang-letter--page---year，与歪比巴卜同布局）
   - 详情      /voddetail/{id}.html
   - 播放      /vodplay/{id}-{sid}-{nid}.html
   - 搜索      /vodsearch/{关键词}----------{page}---.html
2. 播放解密：player_aaaa 直接返回真实 m3u8（encrypt=0 直链），无需外部解析 API；
   保留 encrypt=1(URL解码)/encrypt=2(base64+URL解码) 基础处理，异常回退解析页。
3. 稳健性：会话 Cookie 维护、频率限制冷却与重试、播放地址缓存(30min)、
   懒预热、片名后缀清洗，兼容 FongMi/TVBox 聚合搜索与换源。
"""
import re
import json
import time
import base64
import urllib.parse
import requests
from urllib.parse import quote
from base.spider import Spider


class Spider(Spider):
    # ==================== 基础配置 ====================
    name = "蝴蝶影视"
    base_url = "https://www.ahshfshygzc.com"
    site_url = "https://www.ahshfshygzc.com"

    # 聚合搜索配置：支持壳子全局搜索、快速搜索、筛选和换源聚合
    searchable = 1
    quickSearch = 1
    filterable = 1
    changeable = 1

    # ==================== 分类映射（导航菜单实测） ====================
    class_name = ["电影", "电视剧", "综艺", "动漫", "短剧", "动画片", "4K电影", "Netflix作品"]
    class_url = ["1", "2", "3", "4", "20", "35", "36", "37"]
    CATEGORY_NAMES = {
        "1": "电影", "2": "电视剧", "3": "综艺", "4": "动漫",
        "20": "短剧", "35": "动画片", "36": "4K电影", "37": "Netflix作品",
    }

    # ==================== 请求头 ====================
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://www.ahshfshygzc.com/",
        "Connection": "keep-alive",
    }

    play_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.ahshfshygzc.com/",
        "Accept": "*/*",
    }

    # ==================== 筛选器配置（key 与 /vodshow/ 12段URL字段位置对应） ====================
    # 布局: {tid}-{area}--{class}-{lang}-{letter}--{page}---{year}.html
    FILTERS = {
        "1": [
            {"key": "area", "name": "地区", "value": [
                {"n": "全部", "v": ""},
                {"n": "大陆", "v": "大陆"},
                {"n": "香港", "v": "香港"},
                {"n": "台湾", "v": "台湾"},
                {"n": "美国", "v": "美国"},
                {"n": "法国", "v": "法国"},
                {"n": "英国", "v": "英国"},
                {"n": "日本", "v": "日本"},
                {"n": "韩国", "v": "韩国"},
                {"n": "泰国", "v": "泰国"},
            ]},
            {"key": "class", "name": "剧情", "value": [
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
                {"n": "悬疑", "v": "悬疑"},
                {"n": "惊悚", "v": "惊悚"},
            ]},
            {"key": "lang", "name": "语言", "value": [
                {"n": "全部", "v": ""},
                {"n": "国语", "v": "国语"},
                {"n": "粤语", "v": "粤语"},
                {"n": "英语", "v": "英语"},
                {"n": "韩语", "v": "韩语"},
                {"n": "日语", "v": "日语"},
                {"n": "法语", "v": "法语"},
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
        "2": [
            {"key": "area", "name": "地区", "value": [
                {"n": "全部", "v": ""},
                {"n": "大陆", "v": "大陆"},
                {"n": "香港", "v": "香港"},
                {"n": "台湾", "v": "台湾"},
                {"n": "韩国", "v": "韩国"},
                {"n": "日本", "v": "日本"},
                {"n": "美国", "v": "美国"},
                {"n": "泰国", "v": "泰国"},
            ]},
            {"key": "class", "name": "剧情", "value": [
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
            {"key": "lang", "name": "语言", "value": [
                {"n": "全部", "v": ""},
                {"n": "国语", "v": "国语"},
                {"n": "粤语", "v": "粤语"},
                {"n": "英语", "v": "英语"},
                {"n": "韩语", "v": "韩语"},
                {"n": "日语", "v": "日语"},
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
            ]},
        ],
        "3": [
            {"key": "area", "name": "地区", "value": [
                {"n": "全部", "v": ""},
                {"n": "大陆", "v": "大陆"},
                {"n": "香港", "v": "香港"},
                {"n": "台湾", "v": "台湾"},
                {"n": "日本", "v": "日本"},
                {"n": "韩国", "v": "韩国"},
                {"n": "美国", "v": "美国"},
            ]},
            {"key": "year", "name": "年份", "value": [
                {"n": "全部", "v": ""},
                {"n": "2026", "v": "2026"},
                {"n": "2025", "v": "2025"},
                {"n": "2024", "v": "2024"},
                {"n": "2023", "v": "2023"},
                {"n": "2022", "v": "2022"},
            ]},
        ],
        "4": [
            {"key": "area", "name": "地区", "value": [
                {"n": "全部", "v": ""},
                {"n": "大陆", "v": "大陆"},
                {"n": "香港", "v": "香港"},
                {"n": "台湾", "v": "台湾"},
                {"n": "日本", "v": "日本"},
                {"n": "韩国", "v": "韩国"},
                {"n": "美国", "v": "美国"},
            ]},
            {"key": "class", "name": "剧情", "value": [
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
            ]},
        ],
    }

    # ==================== 工具方法 ====================
    def _log(self, msg):
        print(f"[{self.name}] {msg}")

    def _clean_html(self, text):
        if not text:
            return ""
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _clean_vod_name(self, name):
        """清洗片名，去掉清晰度/版本/集数后缀，方便壳子聚合搜索其它源"""
        if not name:
            return name
        pattern = re.compile(
            r'[\s\-_]*(?:HD|TC|TS|抢先版|枪版|DVD|BD|1080P|720P|4K|2K|高清|超清|蓝光|国语|粤语|中字|中英双字|完整版|全集|未删减版|(?:第[0-9一二三四五六七八九十百]+[集季期]))\s*$',
            re.I
        )
        prev = name
        while True:
            cleaned = pattern.sub('', prev).strip()
            if cleaned == prev:
                break
            prev = cleaned
        return prev

    def __init__(self):
        super().__init__()
        # 复用 TCP 连接，降低多次请求的握手开销
        self._session = requests.Session()
        self._session.headers.update(self.headers)
        self._cookies = ""
        self._play_cache = {}
        self._cache_ttl = 1800
        # 请求间隔控制，降低触发站点频率限制的概率
        self._last_req_time = 0
        self._min_req_interval = 1.0
        self._block_until = 0
        # 预编译常用正则
        self._re_play_link = re.compile(r'<a[^>]*href="/vodplay/(\d+)-(\d+)-(\d+)\.html"[^>]*>(?:<[^>]+>)*([^<]*)</a>', re.DOTALL)

    # ==================== 请求封装 ====================
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
        elapsed = now - self._last_req_time
        interval = self._min_req_interval
        if 0 < elapsed < interval:
            time.sleep(interval - elapsed)
        self._last_req_time = time.time()

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
            if "Set-Cookie" in resp.headers:
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
        """检测频率限制等异常页面"""
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
        """GET请求封装（Session 自动维护 Cookie，含异常捕获+重试+频率限制冷却）"""
        h = self.headers.copy()
        html = ""
        try:
            for attempt in range(max_retry):
                resp = self.fetch(url, headers=h, timeout=timeout)
                self._extract_cookies(resp)
                html = resp.text
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

    # ==================== 列表解析（分类/首页/搜索通用） ====================
    def _parse_vod_list(self, html):
        """解析 ewave 模板的影片卡片列表（兼容 div 卡片与 a 卡片两种结构）"""
        videos = []
        if not html:
            return videos
        # 卡片外层：ewave-vodlist__box（分类/首页），搜索页为 detail 容器
        pattern = re.compile(
            r'<div[^>]*class="[^"]*ewave-vodlist__box[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</li>',
            re.DOTALL,
        )
        matched = False
        for m in pattern.finditer(html):
            matched = True
            video = self._parse_one_card(m.group(1))
            if video:
                videos.append(video)
        # 搜索页兜底：直接匹配 thumb 链接块
        if not matched:
            pattern2 = re.compile(
                r'<a[^>]*class="[^"]*ewave-vodlist__thumb[^"]*"[^>]*>(.*?)</a>',
                re.DOTALL,
            )
            for m in pattern2.finditer(html):
                video = self._parse_one_card(m.group(0))
                if video and not any(v["vod_id"] == video["vod_id"] for v in videos):
                    videos.append(video)
        return videos

    def _parse_one_card(self, block):
        """解析单个卡片块 -> dict；失败返回 None"""
        # 链接：优先 thumb 自身 href，其次块内 thumb-link
        link = re.search(r'<a[^>]*class="[^"]*ewave-vodlist__thumb[^"]*"[^>]*href="(/voddetail/(\d+)\.html)"', block)
        if not link:
            link = re.search(r'<a[^>]*class="thumb-link"[^>]*href="(/voddetail/(\d+)\.html)"', block)
        if not link:
            return None
        vod_id = link.group(2)
        # 标题：优先 title 属性，其次内部 title a
        title = re.search(r'<a[^>]*class="[^"]*ewave-vodlist__thumb[^"]*"[^>]*title="([^"]*)"', block)
        if not title:
            title = re.search(r'<h4[^>]*class="[^"]*title[^"]*"[^>]*><a[^>]*title="([^"]*)"', block)
        if not title:
            title = re.search(r'<a[^>]*class="[^"]*title[^"]*"[^>]*title="([^"]*)"', block)
        vod_name = self._clean_vod_name(title.group(1).strip()) if title else "未知"
        # 图片
        pic = re.search(r'data-original="([^"]+)"', block)
        vod_pic = pic.group(1).strip() if pic else ""
        if vod_pic.startswith("//"):
            vod_pic = "https:" + vod_pic
        # 备注（更新状态/清晰度）
        note = re.search(r'class="[^"]*pic-text[^"]*"[^>]*>([^<]*)</span>', block)
        vod_remarks = note.group(1).strip() if note else ""
        return {
            "vod_id": vod_id,
            "vod_name": vod_name,
            "vod_pic": vod_pic,
            "vod_remarks": vod_remarks,
        }

    # ==================== 详情页解析 ====================
    def _parse_play_sources(self, html, vod_id):
        """解析播放线路与集数（ewave tab-content 结构）"""
        sources = []
        if not html:
            return sources

        # 1. 线路名：<a href="#playlist{n}" data-toggle="tab">名称</a>
        name_map = {}
        for m in re.finditer(r'<a[^>]*href="#playlist(\d+)"[^>]*data-toggle="tab"[^>]*>([^<]*)</a>', html):
            name_map[int(m.group(1))] = m.group(2).strip()

        # 2. 集数块：外层 <div class="...tab-content..."><div id="playlist{n}" class="tab-pane...">...<ul>...
        #    实际 id 在内层 div 上，故按 id 定位后取到 </ul> 为止
        blocks = {}
        for m in re.finditer(r'<div[^>]*id="playlist(\d+)"[^>]*>(.*?)</ul>', html, re.DOTALL):
            idx = int(m.group(1))
            eps = []
            for em in self._re_play_link.finditer(m.group(2)):
                id_, sid, nid, name = em.groups()
                name = name.strip()
                # 过滤"立即播放"按钮等非集数链接
                if not name or name in ("立即播放", "播放"):
                    continue
                eps.append({"name": name, "link": f"{id_}-{sid}-{nid}"})
            if eps:
                blocks[idx] = eps

        # 3. 按 tab 序号对齐线路名与集数块
        if name_map or blocks:
            for idx in sorted(set(list(name_map.keys()) + list(blocks.keys()))):
                if idx in blocks:
                    sources.append({
                        "source_name": name_map.get(idx, f"源{idx}"),
                        "episodes": blocks[idx],
                    })

        # 4. 兜底：全页面匹配 vplay 链接
        if not sources:
            eps = []
            for em in self._re_play_link.finditer(html):
                id_, sid, nid, name = em.groups()
                name = name.strip()
                if not name or name in ("立即播放", "播放"):
                    continue
                eps.append({"name": name, "link": f"{id_}-{sid}-{nid}"})
            if eps:
                sources.append({"source_name": "默认", "episodes": eps})

        # 5. 4K/蓝光线路置顶（该站多为单线路，保留排序逻辑以兼容多线路源）
        if sources:
            def _rank(i):
                name = sources[i]["source_name"]
                is_4k = any(k in name for k in ("4K", "4k", "2160", "2160P", "2160p"))
                is_bluray = "蓝光" in name
                cnt = len(sources[i]["episodes"])
                no_eps = 1 if cnt == 0 else 0
                order = 0 if is_4k else (1 if is_bluray else 2)
                return (no_eps, order, i)
            sources = [sources[i] for i in sorted(range(len(sources)), key=_rank)]

        return sources

    # ==================== 播放地址解析 ====================
    def _extract_player_aaaa(self, html):
        """从播放页 HTML 中提取 player_aaaa 字典（支持嵌套对象，跳过字符串内部花括号）"""
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
        """获取真实播放地址（player_aaaa.url），带缓存"""
        play_page = f"{self.base_url}/vodplay/{vod_id}-{sid}-{nid}.html"
        cache_key = f"{vod_id}-{sid}-{nid}"
        now = time.time()
        if cache_key in self._play_cache:
            url, ts = self._play_cache[cache_key]
            if now - ts < self._cache_ttl:
                self._log(f"播放地址缓存命中: {cache_key}")
                return url

        try:
            html = self._get(play_page, max_retry=2, timeout=6)
            if not html:
                self._log(f"播放页无响应, 使用 WebView 兜底: {play_page}")
                return play_page

            player_data = self._extract_player_aaaa(html)
            if not player_data:
                self._log("未能提取到player_aaaa, 使用 WebView 兜底")
                return play_page

            enc_url = player_data.get("url", "")
            encrypt = str(player_data.get("encrypt", "0"))
            self._log(f"player_aaaa encrypt={encrypt}, url={enc_url[:60]}...")

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

            # 已经是直链则直接返回
            if re.search(r'\.(m3u8|mp4|flv|ts|mkv)(\?|#|$)', enc_url, re.I):
                self._log(f"player_aaaa已是直链: {enc_url[:80]}")
                self._play_cache[cache_key] = (enc_url, now)
                return enc_url

            # 非直链（如加密后的通用资源地址）：该站 encrypt=0 直链为主，
            # 其余情况回退到播放页（壳子 WebView 可尝试解析）
            self._log(f"非直链地址, 使用播放页兜底: {enc_url[:80]}")
            return play_page
        except Exception as e:
            self._log(f"获取播放地址异常: {e}")
            return play_page

    # ==================== TVBox 五大核心方法 ====================
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
            # 同时返回 filters/filter 两种键名，兼容不同壳子
            result["filters"] = self.FILTERS
            result["filter"] = self.FILTERS
        return result

    def homeVideoContent(self):
        try:
            html = self._get(self.base_url)
            if not html:
                return {"list": []}
            # 定位"热播推荐"区块（首页第一个视频面板）
            block = None
            for m in re.finditer(r'<h3[^>]*class="title"[^>]*>(.*?)</h3>', html, re.DOTALL):
                title_text = self._clean_html(m.group(1))
                if '热播推荐' in title_text:
                    seg = html[m.end():m.end() + 12000]
                    # 找到区块内第一个 vodlist 卡片开始位置
                    card = seg.find('ewave-vodlist__box')
                    if card > 0:
                        block = seg[max(0, card - 200):]
                    break
            if not block:
                # 兜底：取第一个包含卡片的面板
                idx = html.find('ewave-vodlist__box')
                if idx > 0:
                    block = html[idx - 300:]
            if not block:
                return {"list": []}
            videos = self._parse_vod_list(block)
            return {"list": videos[:20]}
        except Exception as e:
            self._log(f"homeVideoContent异常: {e}")
            return {"list": []}

    def _quote_filter_value(self, v):
        """对筛选值统一编码，避免壳子传中文时 URL 拼接错误；已编码的值不二次编码。"""
        if not v:
            return ""
        try:
            return quote(urllib.parse.unquote(str(v)))
        except Exception:
            return quote(str(v))

    def _build_show_url(self, tid, pg, flt):
        """构造 /vodshow/ 分类筛选 URL：字段位置固定为 12 段（与站点实测一致）"""
        area = self._quote_filter_value(flt.get("area", ""))
        class_ = self._quote_filter_value(flt.get("class", ""))
        lang = self._quote_filter_value(flt.get("lang", ""))
        letter = self._quote_filter_value(flt.get("letter", ""))
        year = self._quote_filter_value(flt.get("year", ""))
        # 字段映射：1-type_id, 2-area, 3-空, 4-class, 5-lang, 6-letter, 7-8-空, 9-page, 10-11-空, 12-year
        parts = [
            str(tid), area, "", class_, lang, letter, "", "",
            str(pg) if pg > 1 else "", "", "", year
        ]
        return f"{self.base_url}/vodshow/{'-'.join(parts)}.html"

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

            has_filter = any(flt.get(k) for k in ("area", "class", "lang", "letter", "year"))
            if has_filter:
                url = self._build_show_url(tid, pg, flt)
                self._log(f"分类筛选请求: {url}")
            else:
                # 无筛选走 /vodtype/ 分页路由，可靠且带真实总页数
                page_part = f"-{pg}" if pg > 1 else ""
                url = f"{self.base_url}/vodtype/{tid}{page_part}.html"
                self._log(f"分类请求: {url}")

            html = self._get(url)
            if not html:
                return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}
            videos = self._parse_vod_list(html)

            # 总页数：优先取页面分页器的 1/1224，其次尾页链接
            pagecount = 1
            num = re.search(r'class="num"[^>]*>(\d+)/(\d+)</span>', html)
            if num:
                pagecount = int(num.group(2))
            else:
                last = re.search(r'href="/vodtype/' + str(tid) + r'-\d+\.html"[^>]*>[^<]*尾页[^<]*</a>', html)
                if last:
                    pagecount = int(re.search(r'(\d+)\.html', last.group(0)).group(1))
            if pagecount < 1:
                pagecount = 1

            return {
                "list": videos,
                "page": pg,
                "pagecount": pagecount,
                "limit": 20,
                "total": pagecount * 20,
            }
        except Exception as e:
            self._log(f"categoryContent异常: {e}")
            return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}

    def searchContent(self, key, quick=False, pg="1"):
        try:
            pg = max(1, int(pg or 1))
        except (TypeError, ValueError):
            pg = 1
        keyword = str(key or "").strip()
        if not keyword:
            return {"page": pg, "pagecount": 1, "limit": 0, "total": 0, "list": []}
        is_quick = bool(quick)
        encoded_key = quote(keyword)
        # 构造分页 URL：第 9 段为 page，其余为空
        page_part = str(pg) if pg > 1 else ""
        url = f"{self.base_url}/vodsearch/{encoded_key}----------{page_part}---.html"
        self._log(f"搜索请求: {url}, quick={is_quick}")

        try:
            html = self._get(url)
            if not html:
                return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}
            videos = self._parse_vod_list(html)

            # quick（快速/聚合搜索）模式下直接返回结果，减少壳子聚合等待
            if not is_quick:
                # 普通搜索按标题相关度排序：完全匹配 > 开头匹配 > 包含关键词 > 其他
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
                "total": 999999,
            }
        except Exception as e:
            self._log(f"searchContent异常: {e}")
            return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}

    def detailContent(self, ids):
        try:
            vod_id = ids[0] if isinstance(ids, list) else str(ids)
            url = f"{self.base_url}/voddetail/{vod_id}.html"
            self._log(f"详情请求: {url}")
            html = self._get(url)
            if not html:
                return {"list": []}

            # 标题
            title = re.search(r'<h1[^>]*class="title"[^>]*><span[^>]*>([^<]*)</span>', html)
            vod_name = self._clean_vod_name(title.group(1).strip()) if title else "未知"

            # 封面图（ewave-content__thumb 区块）
            vod_pic = ""
            thumb = re.search(r'class="ewave-content__thumb"(.*?)</div>', html, re.DOTALL)
            if thumb:
                pic = re.search(r'data-original="([^"]+)"', thumb.group(1))
                if pic:
                    vod_pic = pic.group(1).strip()
            if not vod_pic:
                pic = re.search(r'class="[^"]*ewave-vodlist__thumb[^"]*"[^>]*data-original="([^"]+)"', html)
                if pic:
                    vod_pic = pic.group(1).strip()
            if vod_pic.startswith("//"):
                vod_pic = "https:" + vod_pic

            # 详情信息区 <p class="data"> 各行
            vod_area = vod_year = vod_actor = vod_director = ""

            def _val_after(seg, key):
                """取 '地区：</span>...<a>值</a>' 形式的下一个链接文本"""
                m = re.search(r'<span[^>]*>%s[:：]?</span>\s*(?:&nbsp;)*\s*<a[^>]*>(.*?)</a>' % key, seg, re.DOTALL)
                return self._clean_html(m.group(1)) if m else ""

            for row in re.finditer(r'<p class="data[^"]*">(.*?)</p>', html, re.DOTALL):
                seg = row.group(1)
                # 类型/地区/年份同处一行，按 span 关键词分别取值
                if '类型：' in seg or '类型:' in seg:
                    if not vod_area:
                        vod_area = _val_after(seg, '地区')
                    if not vod_year:
                        vod_year = _val_after(seg, '年份')
                    continue
                label = re.search(r'<span class="[^"]*text-muted[^"]*">([^<]*)</span>', seg)
                if not label:
                    continue
                lab = label.group(1).replace("：", "").strip()
                values = [self._clean_html(v) for v in re.findall(r'<a[^>]*>(.*?)</a>', seg)]
                if lab == "主演":
                    vod_actor = " ".join(v for v in values if v)
                elif lab == "导演":
                    vod_director = " ".join(v for v in values if v)
                    if not vod_director:
                        # 导演可能为纯文本"未知"
                        txt = self._clean_html(re.sub(r'<span[^>]*>[^<]*</span>', '', seg))
                        vod_director = txt

            # 简介
            vod_content = ""
            desc = re.search(r'<p class="desc[^"]*">(.*?)</p>', html, re.DOTALL)
            if desc:
                seg = re.sub(r'<a[^>]*>.*?</a>', '', desc.group(1), flags=re.DOTALL)
                vod_content = self._clean_html(seg)
                vod_content = re.sub(r'^简介[:：]?\s*', '', vod_content)

            # 更新/集数状态（详情页右侧角标）
            vod_remarks = ""
            note = re.search(r'class="ewave-content__thumb"(.*?)</div>', html, re.DOTALL)
            if note:
                n = re.search(r'class="[^"]*pic-text[^"]*"[^>]*>([^<]*)</span>', note.group(1))
                if n:
                    vod_remarks = n.group(1).strip()

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
            play_page = f"{self.base_url}/vodplay/{vod_id}-{sid}-{nid}.html"
            play_url = self._get_play_url(vod_id, sid, nid)

            if not play_url:
                play_url = play_page

            # 直链判断：路径或查询串出现常见视频扩展名
            is_direct = bool(re.search(r'\.(m3u8|mp4|flv|ts|mkv)([?#&]|$)', play_url, re.I))
            # 回退到本站播放页则交还壳子 WebView 解析
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
