# -*- coding: utf-8 -*-
"""
兄弟影视（brovod.com）TVBox / 影视仓 Python 接口源 —— 重写版 v2

设计要点（对照 TVBox_py 源制作经验）：
1. 零第三方依赖：只使用播放器运行时提供的 base.spider（self.fetch / self.get），
   不再 import requests / bs4，避免"壳无 requests 直接加载失败"。
2. header 使用 dict（契约要求），不再 json.dumps 成字符串。
3. 播放地址为 emoji 加密（encrypt=0），本源将其交给 play.brovod.com 二次解析
   （parse:1）。纯 Python 无法执行该站混淆 JS 解密出直链，需壳支持 JS 解析；
   若要纯直连播放需 localProxy 渲染（依赖壳能力，本文件未实现）。
4. 浏览全链路（首页 / 分类 / 搜索 / 详情）直连抓取，正则解析，离线可测。

站点为 MacCMS 模板（public-list-exp / detail / play / player_aaaa）。
"""
import re
import json
from urllib.parse import quote, urlparse

try:
    from base.spider import Spider as BaseSpider
except Exception:
    BaseSpider = object


class Spider(BaseSpider):
    name = "兄弟影视"
    # 主域名候选（自动探测可用）
    HOSTS = (
        "https://www.brovod.com",
        "https://www.brovods.top",
        "https://brovod.com",
        "https://www.brovod.top",
    )
    PARSER = "https://play.brovod.com/?url="   # emoji 二次解析服务
    DEFAULT_PIC = "https://www.brovod.com/img/logo.png"
    TIMEOUT = 15
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    CATEGORIES = (
        ("Movies", "电影"),
        ("TV", "电视剧"),
        ("Shows", "综艺"),
        ("Anime", "动漫"),
        ("Snaps", "短剧"),
        ("Documentaries", "纪录片"),
    )
    DIRECT_RE = re.compile(r"\.(?:m3u8|mp4|flv|mkv|mov|avi)(?:[?#].*)?$", re.I)

    def __init__(self):
        try:
            super(Spider, self).__init__()
        except Exception:
            pass
        self.host = self.HOSTS[0]
        self._host_ready = False

    # ---------- 基础网络（依赖 base.spider，不依赖 requests） ----------
    def init(self, extend=""):
        self._resolve_host()

    def getName(self):
        return self.name

    def getDependence(self):
        return []   # 零第三方依赖

    def _get(self, url):
        """统一用 base.spider.fetch；兼容个别实现不支持 headers 参数。带重试以应对偶发抖动。"""
        last = ""
        for _ in range(3):
            try:
                r = self.fetch(url, headers=self.HEADERS)
            except TypeError:
                try:
                    r = self.fetch(url)
                except Exception as e:
                    last = str(e)
                    continue
            except Exception as e:
                last = str(e)
                continue
            if r is None:
                last = "empty"
                continue
            return r
        print("[兄弟影视] 请求失败(重试耗尽): %s | %s" % (url, last))
        return ""

    def _fetch(self, path):
        raw = str(path or "")
        # 防双重 host：已是完整 URL 直接使用，否则拼 host（host 不带尾斜杠）
        if raw.startswith(("http://", "https://")):
            url = raw
        else:
            url = self.host.rstrip("/") + "/" + raw.lstrip("/")
        try:
            r = self._get(url)
        except Exception as e:
            print("[兄弟影视] 请求失败: %s" % e)
            return ""
        if r is None:
            return ""
        if isinstance(r, str):
            return r
        text = getattr(r, "text", "") or ""
        final = getattr(r, "url", "") or ""
        if final and "brovod" in final:
            self.host = final.split("//", 1)[0] + "//" + urlparse(final).netloc
        return text

    def _resolve_host(self):
        for h in self.HOSTS:
            try:
                r = self._get(h + "/")
                if r is None:
                    continue
                text = r if isinstance(r, str) else (getattr(r, "text", "") or "")
                if "兄弟影视" in text or "maccms" in text.lower():
                    self.host = h
                    self._host_ready = True
                    return
            except Exception:
                continue
        self._host_ready = True   # 探测失败则用默认主域名

    # ---------- HTML 文本清洗 ----------
    @staticmethod
    def _clean(value):
        value = re.sub(r"<[^>]+>", " ", str(value or ""))
        value = re.sub(r"&[a-z]+;|&#\d+;", " ", value)
        value = re.sub(r"[\x00-\x1f\x7f]+", " ", value)
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _safe(value):
        # 集名/线路名里若含 $ # 会破坏分隔符，替换为空格
        return Spider._clean(value).replace("$", " ").replace("#", " ")

    @staticmethod
    def _pic(inner_html):
        for attr in ("data-src", "data-original", "src"):
            m = re.search(r'%s="([^"]+)"' % attr, inner_html)
            if m and not m.group(1).startswith("data:"):
                return m.group(1)
        return ""

    # ---------- 列表卡片解析（首页 / 分类 / 搜索通用） ----------
    def _parse_cards(self, html, limit=0):
        if not html:
            return []
        videos, seen = [], set()
        # 卡片：class 含 public-list-exp 的 <a href="/detail/...">
        for m in re.finditer(
            r'<a\b[^>]*class="[^"]*public-list-exp[^"]*"[^>]*href="(/detail/[^"?#]*)"[^>]*>(.*?)</a>',
            html, re.S,
        ):
            href, inner = m.group(1), m.group(2)
            if href in seen:
                continue
            seen.add(href)
            # 标题：优先 a 的 title 属性，其次 img 的 alt（去掉"封面图"后缀）
            tm = re.search(r'title="([^"]*)"', m.group(0))
            title = tm.group(1).strip() if tm else ""
            if not title:
                im = re.search(r'alt="([^"]*)"', inner)
                if im:
                    title = im.group(1).replace("封面图", "").strip()
            if not title:
                continue
            pm = re.search(r'data-src="([^"]+)"', inner) or re.search(r'data-original="([^"]+)"', inner) or re.search(r'src="([^"]+)"', inner)
            pic = pm.group(1) if (pm and not pm.group(1).startswith("data:")) else ""
            rm = re.search(r'class="public-list-prb[^"]*"[^>]*>([^<]*)', inner)
            remarks = self._safe(rm.group(1)) if rm else ""
            videos.append({
                "vod_id": href,
                "vod_name": title,
                "vod_pic": pic or self.DEFAULT_PIC,
                "vod_remarks": remarks,
            })
            if limit and len(videos) >= limit:
                break
        return videos

    # ---------- 分页页数（从 page-link 文本取最大数字，兼容路由格式变化） ----------
    @staticmethod
    def _page_count(html):
        # 从分页链接 href（含尾页）提取最大页码，兼容 /show/{tid}--------{N}---/ 格式
        nums = []
        for href in re.findall(r'class="[^"]*page-link[^"]*"[^>]*href="(/show/[^"#?]*)"', html):
            m = re.search(r'-+(\d+)-*/?$', href)
            if m:
                nums.append(int(m.group(1)))
        return max(nums) if nums else 1

    # ---------- 筛选 ----------
    @staticmethod
    def _filter_values():
        years = [{"n": "全部", "v": ""}]
        years.extend({"n": str(y), "v": str(y)} for y in range(2026, 2009, -1))
        return [
            {"key": "area", "name": "地区", "value": [
                {"n": "全部", "v": ""}, {"n": "大陆", "v": "大陆"}, {"n": "香港", "v": "香港"},
                {"n": "台湾", "v": "台湾"}, {"n": "美国", "v": "美国"}, {"n": "韩国", "v": "韩国"},
                {"n": "日本", "v": "日本"}, {"n": "英国", "v": "英国"}, {"n": "法国", "v": "法国"},
                {"n": "泰国", "v": "泰国"}, {"n": "其他", "v": "其他"},
            ]},
            {"key": "class", "name": "类型", "value": [
                {"n": "全部", "v": ""}, {"n": "喜剧", "v": "喜剧"}, {"n": "爱情", "v": "爱情"},
                {"n": "动作", "v": "动作"}, {"n": "科幻", "v": "科幻"}, {"n": "剧情", "v": "剧情"},
                {"n": "悬疑", "v": "悬疑"}, {"n": "犯罪", "v": "犯罪"}, {"n": "恐怖", "v": "恐怖"},
                {"n": "动画", "v": "动画"}, {"n": "战争", "v": "战争"}, {"n": "纪录", "v": "纪录"},
            ]},
            {"key": "lang", "name": "语言", "value": [
                {"n": "全部", "v": ""}, {"n": "国语", "v": "国语"}, {"n": "英语", "v": "英语"},
                {"n": "粤语", "v": "粤语"}, {"n": "韩语", "v": "韩语"}, {"n": "日语", "v": "日语"},
            ]},
            {"key": "year", "name": "年份", "value": years},
            {"key": "by", "name": "排序", "value": [
                {"n": "时间", "v": "time"}, {"n": "人气", "v": "hits"}, {"n": "评分", "v": "score"},
            ]},
        ]

    def _filters(self):
        return {tid: self._filter_values() for tid, _ in self.CATEGORIES}

    # ---------- 五接口 ----------
    def homeContent(self, filter=False):
        classes = [{"type_id": tid, "type_name": name} for tid, name in self.CATEGORIES]
        return {
            "class": classes,
            "filters": self._filters(),
            "list": self._parse_cards(self._fetch("/"), 40),
        }

    def homeVideoContent(self):
        return {"list": self._parse_cards(self._fetch("/"), 40)}

    @staticmethod
    def _extend_dict(extend):
        if isinstance(extend, dict):
            return extend
        try:
            data = json.loads(str(extend or "{}"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def categoryContent(self, tid, pg, filter=False, extend=None):
        try:
            page = max(1, int(pg or 1))
        except Exception:
            page = 1
        tid = str(tid or "")
        if tid not in [c[0] for c in self.CATEGORIES]:
            return {"list": [], "page": page, "pagecount": page, "limit": 40, "total": 0}
        opt = self._extend_dict(extend)
        # MacCMS /show/{tid}-{area}-{by}-{class}-{lang}-{letter}-{}-{}-{page}-{}-{}-{year}/
        fields = [tid, opt.get("area", ""), opt.get("by", ""), opt.get("class", ""),
                  opt.get("lang", ""), opt.get("letter", ""), "", "", str(page), "", "", opt.get("year", "")]
        route = "/show/{}/".format("-".join(quote(str(x), safe="") for x in fields))
        html = self._fetch(route)
        return {
            "list": self._parse_cards(html, 60),
            "page": page,
            "pagecount": self._page_count(html),
            "limit": 40,
            "total": self._page_count(html) * 40,
        }

    @staticmethod
    def _detail_path(value):
        raw = str(value or "").strip()
        m = re.search(r"(/detail/[^?#]+/)", raw, re.I)
        if m:
            return m.group(1)
        if raw and "/" not in raw:
            return "/detail/%s/" % raw.strip("/")
        return ""

    def _parse_detail(self, html, vod_id):
        if not html:
            return None
        # 标题
        tm = re.search(r'class="slide-info-title[^"]*"[^>]*>(.*?)</', html, re.S)
        title = self._safe(tm.group(1)) if tm else ""
        if not title:
            hm = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
            title = self._safe(hm.group(1)) if hm else ""
        if not title:
            return None
        # 年/地/类/状（slide-info-remarks 顺序）
        remarks = re.findall(r'class="slide-info-remarks[^"]*"[^>]*>(.*?)</', html, re.S)
        year = self._safe(remarks[0]) if len(remarks) > 0 else ""
        area = self._safe(remarks[1]) if len(remarks) > 1 else ""
        vod_type = self._safe(remarks[2]) if len(remarks) > 2 else ""
        remark = self._safe(remarks[3]) if len(remarks) > 3 else ""
        # 演员 / 导演：detail-info 内 strong 标签为字段名
        actor = director = ""
        for lab, key in (("演员", "actor"), ("主演", "actor"), ("导演", "director")):
            lm = re.search(r"<strong>[^<]*%s[^<]*</strong>\s*<[^>]*>(.*?)</" % lab, html, re.S)
            if lm:
                val = self._safe(lm.group(1))
                if key == "actor":
                    actor = val
                else:
                    director = val
        # 简介
        sm = re.search(r'class="switch-box"[^>]*>(.*?)</div>', html, re.S)
        content = self._safe(sm.group(1)) if sm else ""
        if not content:
            meta = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]*)"', html)
            content = self._safe(meta.group(1)) if meta else ""
        # 线路名（anthology-tab 内 swiper-slide 文本，保留圈号序号 蓝光③/极速①… 区分多线路）
        tabs = re.findall(r'class="[^"]*anthology-tab[^"]*"[^>]*>(.*?)</div>', html, re.S)
        tab_names = []
        for t in tabs:
            names = re.findall(r"&nbsp;([^<]+?)(?:<span|$)", t)
            if names:
                tab_names.extend(nm.strip() for nm in names)
            if not tab_names:
                tab_names = [self._safe(x) for x in re.findall(r"swiper-slide[^>]*>([^<]+)", t)]
        # 剧集：按 anthology-list-box 块位置切片（每块一条线路，避免 lookahead 误并块）
        # 实测顺序：box[0]=from4 / box[1]=from2 / box[2]=from1 / box[3]=from3，
        # 与 tab 顺序一致（box[i] ↔ tab[i]）。
        play_from, play_url = [], []
        box_starts = [m.start() for m in re.finditer(r'class="[^"]*anthology-list-box[^"]*"', html)]
        for idx, st in enumerate(box_starts):
            en = box_starts[idx + 1] if idx + 1 < len(box_starts) else len(html)
            inner = html[st:en]
            eps = []
            for am in re.finditer(r'<a\b[^>]*href="(/play/[^"?#]*)"[^>]*>(.*?)</a>', inner, re.S):
                name = self._safe(am.group(2)) or "第%d集" % (len(eps) + 1)
                eps.append("%s$%s" % (name, am.group(1)))
            if not eps:
                continue
            line = tab_names[idx] if idx < len(tab_names) else "线路%d" % (idx + 1)
            play_from.append(line)
            play_url.append("#".join(eps))
        return {
            "vod_id": vod_id,
            "vod_name": title,
            "vod_pic": self.DEFAULT_PIC,
            "vod_year": year,
            "vod_area": area,
            "vod_type": vod_type,
            "vod_remarks": remark,
            "vod_actor": actor,
            "vod_director": director,
            "vod_content": content,
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }

    def detailContent(self, ids):
        raw = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
        path = self._detail_path(raw)
        if not path:
            return {"list": []}
        vod = self._parse_detail(self._fetch(path), path)
        return {"list": [vod]} if vod else {"list": []}

    def searchContent(self, key, quick=False, pg="1"):
        try:
            page = max(1, int(pg or 1))
        except Exception:
            page = 1
        keyword = str(key or "").strip()
        if not keyword:
            return {"list": [], "page": page, "pagecount": page, "limit": 10, "total": 0}
        # 关键词走路径参数（已验证 /ss/{key}----------{page}---/，kw 与 page 后无多余斜杠）
        route = "/ss/{}----------{}---/".format(quote(keyword, safe=""), page)
        html = self._fetch(route)
        return {
            "list": self._parse_cards(html, 60),
            "page": page,
            "pagecount": self._page_count(html),
            "limit": 10,
            "total": self._page_count(html) * 10,
        }

    # ---------- 播放：提取 player_aaaa（emoji 加密 url） ----------
    @staticmethod
    def _extract_player(html):
        i = html.find("player_aaaa")
        if i < 0:
            return {}
        start = html.find("{", i)
        if start < 0:
            return {}
        depth = instr = esc = 0
        for j in range(start, len(html)):
            c = html[j]
            if esc:
                esc = False
                continue
            if c == "\\":
                esc = True
                continue
            if c == '"':
                instr = not instr
                continue
            if instr:
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(html[start:j + 1])
                    except Exception:
                        return {}
        return {}

    def playerContent(self, flag, id, vipFlags=None):
        raw = str(id or "").strip()
        base_header = {
            "User-Agent": self.HEADERS["User-Agent"],
            "Referer": self.host.rstrip("/") + "/",
        }
        # 若 id 本身就是直链（理论上不会出现，emoji 站均为加密）
        if self.DIRECT_RE.search(raw):
            url = raw if raw.startswith(("http://", "https://")) else self.host.rstrip("/") + "/" + raw.lstrip("/")
            return {"parse": 0, "url": url, "header": base_header}
        # 抓播放页，取 player_aaaa.url（emoji 加密串）
        html = self._fetch(raw)
        data = self._extract_player(html)
        emoji = (data.get("url") or "").replace("\\/", "/").strip()
        if not emoji:
            # 兜底：直接把播放路径交给解析服务
            url = self.host.rstrip("/") + "/" + raw.lstrip("/")
            return {"parse": 1, "url": url, "header": base_header}
        # emoji 交给 play.brovod.com 二次解析（parse:1）
        return {
            "parse": 1,
            "url": self.PARSER + quote(emoji, safe=""),
            "header": base_header,
        }

    # ---------- 其余接口 ----------
    def isVideoFormat(self, url):
        return bool(self.DIRECT_RE.search(str(url or "")))

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return None

    def liveContent(self, url):
        return {"list": []}

    def action(self, action):
        return {}

    def destroy(self):
        pass


if __name__ == "__main__":
    # 离线自检：直接用抓回的样本 HTML 验证解析逻辑（无需联网）
    import os
    BASE = os.path.dirname(os.path.abspath(__file__))
    s = Spider()

    def load(name):
        p = os.path.join(BASE, name)
        return open(p, encoding="utf-8", errors="ignore").read() if os.path.exists(p) else ""

    home = s._parse_cards(load("_probe_home.html"), 40)
    print("首页卡片:", len(home))
    if home:
        print("  示例:", home[0]["vod_name"], "|", home[0]["vod_remarks"], "|", home[0]["vod_id"])

    cat = s._parse_cards(load("_probe_cat_ok.html"), 60)
    print("分类卡片:", len(cat), "页数:", s._page_count(load("_probe_cat_ok.html")))

    search = s._parse_cards(load("_probe_search.html"), 60)
    print("搜索卡片:", len(search))

    detail = s._parse_detail(load("_probe_detail.html"), "/detail/benpaobatianlupian-165165/")
    if detail:
        lines = detail["vod_play_from"].split("$$$")
        print("详情:", detail["vod_name"], "| 线路数:", len(lines))
        print("  线路:", lines)
        print("  首线路首集:", detail["vod_play_url"].split("$$$")[0].split("#")[0])

    player = s._extract_player(load("_probe_play.html"))
    print("播放页 player_aaaa.encrypt:", player.get("encrypt"), "| url 长度:", len(player.get("url", "")))
    print("播放返回:", s.playerContent("", "/play/benpaobatianlupian-165165-1-1/", []))
