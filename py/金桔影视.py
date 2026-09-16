import base64
import re
import threading
import time
from html import unescape

from base.spider import Spider


"""
金桔影视 (htsdaz.com) —— 由 CatVod T4 JS 源移植的 TVBox / 影视仓 Python 接口源。
站点类型：stui 模板 HTML 解析站。

铁律落实（务必保持）：
  - 全程使用框架自带 self.fetch()，绝不依赖 requests 库（播放器运行时未必自带该库）。
  - 不覆盖 __init__，属性在 init() 内初始化。
  - header 一律为 dict。
  - 不使用 self.post 的 json 参数。
  - _fetch 防双重 host：传入绝对 URL 不重复拼 host。
  - 三层分隔符：线路 "$$$"、集 "#"、名址 "$"。线路名只放 vod_play_from，
    绝不在 vod_play_url 的每一集前加线路前缀。
"""


class Spider(Spider):
    # ---------- 本地索引搜索配置 ----------
    # 站点原生搜索 /search/{wd}.html 被 Cloudflare 验证码墙(302->verify_captcha.jsp)硬拦截，
    # 即使带有效会话 Cookie 也无法通过（无 JS 执行能力）。故采用"抓取分类列表建本地索引"方案。
    # 分类页 /stream/{tid}_{pg}.html 返回 200 正常，可抓。
    CRAWL_CATS = ["1", "2", "3", "4", "34"]  # 电影/电视剧/综艺/动漫/短剧
    CRAWL_COLD = 6       # 冷启动：每类先抓前 N 页，启动后即可搜到近期内容
    CRAWL_MAX = 60       # 后台：每类最多抓到 N 页（加深索引，覆盖更多片库）
    CRAWL_DELAY = 0.2    # 请求间隔(秒)，避免触发风控

    def init(self, extend=""):
        self.host = "https://htsdaz.com"
        self.header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": self.host + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        if isinstance(extend, str) and extend.strip() and re.match(r"^https?://", extend.strip()):
            self.host = extend.strip().rstrip("/")
            self.header["Referer"] = self.host + "/"

        # 本地索引状态（后台线程写、主线程读，加锁保护）
        self._index_lock = threading.Lock()
        self._index = []          # [{vod_id, vod_name, vod_pic, vod_remarks}, ...]
        self._index_ids = set()   # 去重
        self._index_done = False
        self._start_crawler()

    def getName(self):
        return "金桔影视"

    # ---------- 基础请求 ----------
    def _fetch(self, url, headers=None):
        if not (url.startswith("http://") or url.startswith("https://")):
            url = self.host + (url if url.startswith("/") else "/" + url)
        h = dict(self.header)
        if headers:
            h.update(headers)
        resp = self.fetch(url, headers=h)
        if resp is None:
            return ""
        if hasattr(resp, "text"):
            return resp.text
        try:
            return resp.content.decode("utf-8", errors="ignore")
        except Exception:
            return ""

    # ---------- 分类筛选（复刻 JS myFilters） ----------
    @staticmethod
    def _movie_class():
        names = ["喜剧", "爱情", "恐怖", "动作", "科幻", "剧情", "战争", "警匪", "犯罪",
                 "动画", "奇幻", "武侠", "冒险", "枪战", "悬疑", "惊悚", "经典", "青春",
                 "文艺", "微电影", "古装", "历史", "运动", "农村", "儿童", "网络电影"]
        return [{"n": n, "v": n} for n in names]

    @staticmethod
    def _tv_class():
        names = ["国产剧", "港剧", "欧美剧", "日剧", "台剧", "泰剧", "韩剧", "海外剧", "Netflix自制剧"]
        return [{"n": n, "v": n} for n in names]

    @staticmethod
    def _area():
        names = ["大陆", "香港", "台湾", "美国", "法国", "英国", "日本", "韩国", "德国",
                 "泰国", "印度", "意大利", "西班牙", "加拿大", "其他"]
        return [{"n": n, "v": n} for n in names]

    @staticmethod
    def _lang():
        names = ["国语", "英语", "粤语", "闽南语", "韩语", "日语", "法语", "德语", "其它"]
        return [{"n": n, "v": n} for n in names]

    def _year(self):
        years = [{"n": "全部", "v": ""}]
        for y in range(2026, 1999, -1):
            years.append({"n": str(y), "v": str(y)})
        return {"key": "year", "name": "年份", "value": years}

    def _filters(self):
        area = [{"n": "全部", "v": ""}] + self._area()
        lang = [{"n": "全部", "v": ""}] + self._lang()
        common = [
            {"key": "area", "name": "地区", "value": area},
            {"key": "lang", "name": "语言", "value": lang},
            self._year(),
        ]
        return {
            "1": [
                {"key": "class", "name": "类型", "value": [{"n": "全部", "v": ""}] + self._movie_class()},
            ] + common,
            "2": [
                {"key": "class", "name": "类型", "value": [{"n": "全部", "v": ""}] + self._tv_class()},
            ] + common,
            "3": common,
            "4": common,
            "34": common,
        }

    # ---------- homeContent ----------
    def homeContent(self, filter):
        class_list = [
            {"type_id": "1", "type_name": "电影"},
            {"type_id": "2", "type_name": "电视剧"},
            {"type_id": "3", "type_name": "综艺"},
            {"type_id": "4", "type_name": "动漫"},
            {"type_id": "34", "type_name": "短剧"},
        ]
        return {"class": class_list, "filters": self._filters()}

    # ---------- 分类 URL 拼装（复刻 JS buildCategoryUrl） ----------
    def _build_cat_url(self, tid, pg, extend):
        extend = extend or {}
        cls = extend.get("class", "") or ""
        area = extend.get("area", "") or ""
        lang = extend.get("lang", "") or ""
        year = extend.get("year", "") or ""
        if cls or area or lang or year:
            filt = "%s-%s-%s-%s------" % (cls, area, lang, year)
            return "/stream/%s_%s/%s.html" % (tid, pg, filt)
        return "/stream/%s_%s.html" % (tid, pg)

    # ---------- 列表卡片解析（复刻 JS ul.stui-vodlist__thumb.lazyload） ----------
    def _parse_cards(self, html_text):
        items = []
        blocks = re.findall(
            r'<a\b[^>]*class="[^"]*stui-vodlist__thumb[^"]*"[^>]*>.*?</a>',
            html_text, re.S,
        )
        seen = set()
        for blk in blocks:
            href = re.search(r'href="([^"]+)"', blk)
            if not href:
                continue
            vid = href.group(1).strip()
            if not vid or vid in seen:
                continue
            title = re.search(r'title="([^"]*)"', blk)
            name = unescape(title.group(1).strip()) if title else ""
            if not name:
                # 退路：取 a 标签内文本
                inner = re.sub(r"<[^>]+>", "", blk)
                name = unescape(inner.strip())
            if not name:
                continue
            pic = re.search(r'data-original="([^"]*)"', blk)
            vod_pic = pic.group(1).strip() if pic else ""
            if vod_pic and not vod_pic.startswith("http"):
                vod_pic = self.host + (vod_pic if vod_pic.startswith("/") else "/" + vod_pic)
            rem = re.search(r'class="pic-text"[^>]*>([^<]*)</', blk)
            vod_remarks = unescape(rem.group(1).strip()) if rem else ""
            seen.add(vid)
            items.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": vod_pic,
                "vod_remarks": vod_remarks,
            })
        return items

    def _parse_pagecount(self, html_text):
        nums = re.findall(r'/stream/\d+_(\d+)', html_text)
        if nums:
            return max(int(n) for n in nums)
        return 1

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        url = self._build_cat_url(tid, pg, extend)
        html = self._fetch(url)
        if not html:
            return {"list": [], "pagecount": 1, "page": pg, "limit": 20, "total": 0}
        items = self._parse_cards(html)
        pagecount = self._parse_pagecount(html) or 1
        return {
            "list": items,
            "page": pg,
            "pagecount": pagecount,
            "limit": 20,
            "total": pagecount * 20,
        }

    # ---------- detailContent ----------
    @staticmethod
    def _clean_name(raw):
        # 去掉 h1 内联评分（如 "美少女壮士2018" + "8.0" -> 去掉末尾小数评分）
        name = unescape(re.sub(r"<[^>]+>", "", raw))
        name = re.sub(r"\s*\d+\.\d+\s*$", "", name)   # 小数评分 8.0
        name = re.sub(r"\s*\d{1,2}分\s*$", "", name)  # "8分"
        return name.strip()

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vid = ids[0]
        html = self._fetch(vid)
        if not html:
            return {"list": []}

        # 片名
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
        vod_name = self._clean_name(h1.group(1)) if h1 else ""

        # 海报
        img = re.search(r'<img[^>]*data-original="([^"]+)"', html)
        if not img:
            img = re.search(r'<div[^>]*class="[^"]*stui-content__thumb[^"]*"[^>]*>.*?<img[^>]*data-original="([^"]+)"', html, re.S)
        vod_pic = img.group(1).strip() if img else ""
        if vod_pic and not vod_pic.startswith("http"):
            vod_pic = self.host + (vod_pic if vod_pic.startswith("/") else "/" + vod_pic)

        # 演职 / 年份 / 地区 / 状态 / 简介
        vod_actor = vod_director = vod_remarks = vod_year = vod_area = ""
        vod_content = ""
        for p in re.findall(r'<p[^>]*class="[^"]*data[^"]*"[^>]*>(.*?)</p>', html, re.S):
            txt = unescape(re.sub(r"<[^>]+>", "", p))
            if "主演" in txt:
                as_ = re.findall(r'<a[^>]*>(.*?)</a>', p)
                vod_actor = ",".join(a.strip() for a in as_ if a.strip())
            elif "导演" in txt:
                ds_ = re.findall(r'<a[^>]*>(.*?)</a>', p)
                vod_director = ",".join(d.strip() for d in ds_ if d.strip())
            elif "状态" in txt:
                vod_remarks = re.sub(r".*状态[：:]?", "", txt).strip()
            elif "年份" in txt:
                ys = re.findall(r"<a[^>]*>(.*?)</a>", p)
                if ys:
                    ym = re.search(r"\d{4}", ys[0])
                    vod_year = ym.group(0) if ym else ""
            elif "地区" in txt:
                ars = re.findall(r"<a[^>]*>(.*?)</a>", p)
                vod_area = ars[0].strip() if ars else ""
        desc = re.search(r'<div[^>]*class="[^"]*(?:detail|desc)[^"]*"[^>]*>(.*?)</div>', html, re.S)
        if desc:
            vod_content = unescape(re.sub(r"<[^>]+>", "", desc.group(1))).strip()

        # 线路名（nav-tabs）
        raw_lines = []
        nav = re.search(r'<ul[^>]*class="[^"]*nav-tabs[^"]*"[^>]*>(.*?)</ul>', html, re.S)
        if nav:
            for a in re.findall(r"<a[^>]*>(.*?)</a>", nav.group(1)):
                ln = a.strip()
                if ln and ln != "全部":
                    raw_lines.append(ln)

        # 播放池（每个 stui-content__playlist 一个线路）
        raw_playlists = []
        for pool in re.findall(r'<ul[^>]*class="[^"]*stui-content__playlist[^"]*"[^>]*>(.*?)</ul>', html, re.S):
            eps = []
            for href, name in re.findall(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', pool):
                nm = unescape(name).strip()
                if nm and href:
                    eps.append("%s$%s" % (nm, href))
            raw_playlists.append(eps)

        if not raw_lines and raw_playlists:
            raw_lines = ["线路%d" % (i + 1) for i in range(len(raw_playlists))]

        final_lines, final_playlists = [], []
        for i in range(len(raw_lines)):
            if i < len(raw_playlists) and raw_playlists[i]:
                final_lines.append(raw_lines[i])
                final_playlists.append(raw_playlists[i])

        if not final_lines:
            return {"list": []}

        vod_play_from = "$$$".join(final_lines)
        vod_play_url = "$$$".join("#".join(eps) for eps in final_playlists)

        vod = {
            "vod_id": vid,
            "vod_name": vod_name,
            "vod_pic": vod_pic,
            "vod_actor": vod_actor,
            "vod_director": vod_director,
            "vod_remarks": vod_remarks,
            "vod_year": vod_year,
            "vod_area": vod_area,
            "vod_content": vod_content,
            "vod_play_from": vod_play_from,
            "vod_play_url": vod_play_url,
        }
        return {"list": [vod]}

    # ---------- 本地索引搜索 ----------
    def _start_crawler(self):
        try:
            t = threading.Thread(target=self._crawl_worker, daemon=True)
            t.start()
        except Exception:
            pass

    def _crawl_page(self, tid, pg):
        """抓一页分类列表并入索引。返回 False 表示被拦/空页（停止该类继续抓）。"""
        url = "/stream/%s_%s.html" % (tid, pg)
        try:
            html = self._fetch(url)
        except Exception:
            return False
        if not html or len(html) < 1500 or "verify_captcha" in html:
            return False
        items = self._parse_cards(html)
        if not items:
            return False
        with self._index_lock:
            for it in items:
                vid = it.get("vod_id")
                if vid and vid not in self._index_ids:
                    self._index_ids.add(vid)
                    self._index.append(it)
        return True

    def _crawl_worker(self):
        try:
            # 阶段1：冷启动，每类前 CRAWL_COLD 页，启动后即时可搜
            for tid in self.CRAWL_CATS:
                for pg in range(1, self.CRAWL_COLD + 1):
                    if not self._crawl_page(tid, pg):
                        break
                    time.sleep(self.CRAWL_DELAY)
            # 阶段2：加深索引，每类继续抓到 CRAWL_MAX 页（后台渐进，不阻塞搜索）
            for tid in self.CRAWL_CATS:
                for pg in range(self.CRAWL_COLD + 1, self.CRAWL_MAX + 1):
                    if not self._crawl_page(tid, pg):
                        break
                    time.sleep(self.CRAWL_DELAY)
        except Exception:
            pass
        finally:
            self._index_done = True

    def _local_search(self, key, pg):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        kl = (key or "").lower()
        with self._index_lock:
            matched = [it for it in self._index
                       if kl and kl in (it.get("vod_name") or "").lower()]
        # 相关性：片名前缀命中优先，其余按片名排序
        matched.sort(key=lambda it: (0 if (it.get("vod_name") or "").lower().startswith(kl) else 1,
                                     it.get("vod_name") or ""))
        limit = 20
        total = len(matched)
        pagecount = (total + limit - 1) // limit if total else 1
        start = (pg - 1) * limit
        page_items = matched[start:start + limit]
        return {
            "list": page_items,
            "page": pg,
            "pagecount": pagecount,
            "limit": limit,
            "total": total,
        }

    def _try_native_search(self, key):
        """兜底：少数情况下站点不拦原生搜索时可用；被验证码墙拦截则返回 None。"""
        try:
            url = "/search/%s.html" % self._enc(key)
            html = self._fetch(url)
            if not html or "verify_captcha" in html or "请输入验证码" in html:
                return None
            items = self._parse_cards(html)
            if not items:
                return None
            return {"list": items, "page": 1, "pagecount": 1, "limit": 20, "total": len(items)}
        except Exception:
            return None

    def searchContent(self, key, quick, pg="1"):
        # 主用本地索引；本地无命中且索引未建完时，尝试原生搜索兜底（通常仍被拦）
        res = self._local_search(key, pg)
        if res["list"]:
            return res
        native = self._try_native_search(key)
        if native and native["list"]:
            return native
        return res

    @staticmethod
    def _enc(s):
        # 搜索关键词按站点习惯做 UTF-8 百分号编码
        import urllib.parse
        return urllib.parse.quote(s)

    # ---------- playerContent ----------
    @staticmethod
    def _extract_video(html):
        # 1) const parts = [...] 拼接 base64 解码
        m = re.search(r"const\s+parts\s*=\s*\[(.*?)\]", html, re.S)
        if m:
            parts = re.findall(r'"([^"]*)"', m.group(1))
            s = "".join(parts)
            s = re.sub(r"[^A-Za-z0-9+/]", "", s)
            if s:
                try:
                    pad = (-len(s)) % 4
                    dec = base64.b64decode(s + "=" * pad).decode("utf-8", errors="ignore")
                    if dec.startswith("http"):
                        return dec
                except Exception:
                    pass
        # 2) var player_aaaa ... "url":"..."
        m2 = re.search(r'var\s+player_aaaa[\s\S]*?"url"\s*:\s*"([^"]+)"', html)
        if m2:
            return m2.group(1).replace("\\", "")
        # 3) iframe
        m3 = re.search(r'id="playerIframe"[^>]*src="([^"]+)"', html)
        if not m3:
            m3 = re.search(r"<iframe[^>]*src=\"([^\"]+)\"", html)
        if m3:
            return m3.group(1)
        return ""

    def playerContent(self, flag, id, vipFlags):
        # id 存的是相对路径 /draw/{id}-{线路}-{集}.html
        html = self._fetch(id)
        if not html:
            return {"parse": 0, "url": ""}
        video = self._extract_video(html)
        if not video:
            return {"parse": 0, "url": ""}
        h = {"User-Agent": self.header["User-Agent"], "Referer": self.host + "/"}
        if video.endswith(".m3u8") or video.endswith(".mp4") or \
           (video.startswith("http") and ".html" not in video):
            return {"parse": 0, "url": video, "header": h}
        return {"parse": 1, "url": video, "header": h}


"""
==============================================================================
部署 tv.json 示例：
{
  "key": "金桔影视",
  "name": "金桔影视",
  "type": 3,
  "api": "./py/金桔影视.py",
  "searchable": 1,
  "filterable": 1,
  "changeable": 1,
  "playerType": 2
}

说明：
- 分类含筛选（类型/地区/语言/年份），filterable 建议开启。
- 播放直链为 m3u8，parse:0 直出；个别源防盗链黑屏时，已带 Referer 头，
  仍不行可把 playerContent 兜底改为 parse:1。
- 【搜索已修复】站点原生搜索 /search/{wd}.html 被 Cloudflare 验证码墙硬拦截
  （302 -> verify_captcha.jsp，带会话 Cookie 也过不去，无 JS 执行能力），
  故改用"本地索引搜索"：后台线程抓取分类列表页 /stream/{tid}_{pg}.html
  （该类接口返回 200 正常）建立 片名->vod_id 索引，搜索时做子串匹配 + 前缀优先排序。
  - 冷启动：每类先抓前 6 页，源加载后即可搜到近期内容；
  - 后台：继续加深到每类 60 页（共约 300 页、近万部），渐进补全，不阻塞搜索。
  - 索引为"近期片库"抽样，极老/冷门片可能漏搜；深度可调 CRAWL_COLD / CRAWL_MAX。
  - 原生搜索仍保留为兜底（_try_native_search），站点若临时不拦即可直出实时结果。
==============================================================================
"""
