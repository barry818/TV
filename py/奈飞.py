# -*- coding: utf-8 -*-
# 奈飞丨4K (wsyzy.net 苹果CMS API) → TVBox / 影视仓 Python 接口源
#
# 站点类型：苹果CMS VOD API（原 type=1 资源站），此处封装为 type=3 Python 源。
# 接口基址：https://api.wsyzy.net/api.php/provide/vod
# 用户指定分类：4K电影=62 / Netflix电影=71 / Netflix自制剧=72
#
# 【搜索修复说明】
#   官方 API 的 wd 搜索参数被站点硬编码禁用（ac=list / ac=detail 带 wd 均返回
#   "暂不支持搜索"），调参无法绕过。因此本源改用「本地索引搜索」：
#   后台线程把三个分类的全量列表抓进内存，searchContent 在内存里做关键词
#   子串匹配并分页返回。源加载后后台静默建索引，首次搜索会等待冷启动
#   （每类前 2 页，约 5~8 秒）后再匹配；全站索引建完后搜索秒回。
#
# 铁律：不覆盖 __init__（属性在 init 设置）；header 一律 dict；
#      主流接口全程 GET、URL 参数手动拼接（兼容 TVBox fetch 仅收 url/headers）；
#      苹果CMS 自带三层分隔符($$$/#/$)，vod_play_from / vod_play_url 直接透传；
#      搜索索引抓取使用独立 requests 直连（不走 self.fetch），规避子线程桥接隐患。

import json
import re
import threading
import time
from urllib.parse import quote

import requests

try:
    from base.spider import Spider
except Exception:
    class Spider:
        def fetch(self, *a, **k):
            raise NotImplementedError("base.spider required in TVBox runtime")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

API = "https://api.wsyzy.net/api.php/provide/vod"

# 用户指定的 3 个分类（type_name → type_id），homeContent 只展示这些
WANT_CATS = [
    {"type_id": 62, "type_name": "4K电影"},
    {"type_id": 71, "type_name": "Netflix电影"},
    {"type_id": 72, "type_name": "Netflix自制剧"},
]

# 搜索索引覆盖的分类（与 WANT_CATS 一致，元组形式便于迭代）
SEARCH_CATS = [(62, "4K电影"), (71, "Netflix电影"), (72, "Netflix自制剧")]

# 冷启动抓取：每类抓前 N 页即视为「可用」，搜索先等冷启动再匹配
COLD_PAGES_PER_CAT = 2


class Spider(Spider):
    def init(self, extend=""):
        self.host = API
        self.headers = {
            "User-Agent": UA,
            "Referer": "https://api.wsyzy.net/",
            "Accept": "application/json,text/plain,*/*",
        }
        # 搜索本地索引相关
        self._idx = []                 # list[dict]: vod_id/name/pic/remarks
        self._idx_lock = threading.Lock()
        self._idx_started = False
        self._cold_done = False
        self._http_headers = {
            "User-Agent": UA,
            "Referer": "https://api.wsyzy.net/",
            "Accept": "application/json,text/plain,*/*",
        }
        self._start_index()
        return None

    def getName(self):
        return "🪼奈飞丨4K"

    # ---------------- 工具 ----------------

    def _get_json(self, params):
        """拼接 URL 后用 self.fetch 取 JSON（主流接口用，走框架 fetch）。"""
        try:
            qs = "&".join("%s=%s" % (k, quote(str(v), safe="")) for k, v in params.items())
            url = self.host + "?" + qs
            resp = self.fetch(url, headers=self.headers)
            text = resp.text if hasattr(resp, "text") else resp.content.decode("utf-8", "ignore")
            if not text or "暂不支持搜索" in text:
                return None
            return json.loads(text)
        except Exception as e:
            print("请求异常：%s" % e)
            return None

    def _http_get(self, params):
        """独立直连取 JSON（搜索索引用，走 requests 不依赖框架 fetch，子线程安全）。"""
        try:
            qs = "&".join("%s=%s" % (k, quote(str(v), safe="")) for k, v in params.items())
            r = requests.get(self.host + "?" + qs, headers=self._http_headers, timeout=20)
            if not r.text or "暂不支持搜索" in r.text:
                return None
            return r.json()
        except Exception as e:
            print("索引请求异常：%s" % e)
            return None

    @staticmethod
    def _item(v):
        return {
            "vod_id": str(v.get("vod_id", "")),
            "vod_name": v.get("vod_name", ""),
            "vod_pic": v.get("vod_pic", "") or "",
            "vod_remarks": v.get("vod_remarks", "") or "",
            "type_id": v.get("type_id", ""),
        }

    # 分类名别名：用户搜「奈飞/网飞」时映射到 Netflix 分类
    CAT_ALIAS = {"奈飞": "netflix", "网飞": "netflix", "netflix": "netflix"}

    # ---------------- 搜索本地索引 ----------------

    def _start_index(self):
        if self._idx_started:
            return
        self._idx_started = True
        t = threading.Thread(target=self._build_index, daemon=True)
        t.start()

    def _build_index(self):
        """后台线程：两阶段建立搜索索引。
        阶段1（冷启动）：每类抓前 COLD_PAGES_PER_CAT 页，三类都到位后置 cold_done；
        阶段2（全站补齐）：继续抓每类剩余页，索引逐渐覆盖全站。
        """
        pagecounts = {}
        # 阶段1：冷启动
        for tid, _ in SEARCH_CATS:
            for pg in range(1, COLD_PAGES_PER_CAT + 1):
                data = self._http_get({"ac": "detail", "t": tid, "pg": pg})
                if not data:
                    break
                lst = data.get("list", [])
                if not lst:
                    break
                try:
                    pagecounts[tid] = int(data.get("pagecount", 1) or 1)
                except Exception:
                    pagecounts[tid] = 1
                with self._idx_lock:
                    for v in lst:
                        it = self._item(v)
                        it["type_id"] = tid   # 用抓取时的分类ID，最可靠（接口字段可能缺）
                        self._idx.append(it)
        with self._idx_lock:
            self._cold_done = True
        # 阶段2：全站补齐
        for tid, _ in SEARCH_CATS:
            pc = pagecounts.get(tid, 1)
            for pg in range(COLD_PAGES_PER_CAT + 1, pc + 1):
                data = self._http_get({"ac": "detail", "t": tid, "pg": pg})
                if not data:
                    break
                lst = data.get("list", [])
                if not lst:
                    break
                with self._idx_lock:
                    for v in lst:
                        it = self._item(v)
                        it["type_id"] = tid
                        self._idx.append(it)

    # ---------------- 接口实现 ----------------

    def homeContent(self, filter):
        data = self._get_json({"ac": "class"})
        classes = []
        if data:
            cls = data.get("class", [])
            name2id = {str(c.get("type_name")): c.get("type_id") for c in cls}
            for c in WANT_CATS:
                if c["type_name"] in name2id:
                    classes.append({"type_id": name2id[c["type_name"]], "type_name": c["type_name"]})
        # 兜底：若站点分类名变动导致匹配不到，则回退全部分类
        if not classes and data:
            classes = [{"type_id": c.get("type_id"), "type_name": c.get("type_name")} for c in data.get("class", [])]
        return {"class": classes or WANT_CATS, "filters": {}}

    def categoryContent(self, tid, pg, filter, extend):
        # 用 ac=detail 拿列表：该站 ac=list 不含 vod_pic，detail 接口才含海报与播放地址
        params = {"ac": "detail", "t": tid, "pg": pg}
        if isinstance(extend, dict):
            for k, val in extend.items():
                if val not in (None, ""):
                    params[str(k)] = val
        data = self._get_json(params)
        items, pagecount, total = [], 1, 0
        if data:
            items = [self._item(v) for v in data.get("list", [])]
            try:
                pagecount = int(data.get("pagecount", 1))
            except Exception:
                pagecount = 1
            try:
                total = int(data.get("total", 0))
            except Exception:
                total = 0
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        return {"list": items, "page": pg, "pagecount": pagecount, "limit": 20, "total": total}

    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, list) else ids
        m = re.search(r"(\d+)", str(vid))
        vod_id = m.group(1) if m else str(vid)
        data = self._get_json({"ac": "detail", "ids": vod_id})
        lst = data.get("list", []) if data else []
        if not lst:
            return {"list": []}
        v = lst[0]
        return {"list": [{
            "vod_id": str(v.get("vod_id", "")),
            "vod_name": v.get("vod_name", ""),
            "vod_pic": v.get("vod_pic", "") or "",
            "vod_remarks": v.get("vod_remarks", "") or "",
            "vod_content": v.get("vod_content", "") or "",
            "vod_play_from": v.get("vod_play_from", "") or "",
            "vod_play_url": v.get("vod_play_url", "") or "",
        }]}

    def searchContent(self, key, quick, pg="1"):
        # 本地索引搜索：内存子串匹配 + 分页
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        key_l = (key or "").strip().lower()
        if not key_l:
            return {"list": [], "page": pg, "pagecount": 1, "total": 0}

        # 等待冷启动（后台线程把每类前 2 页抓完）；超时也不阻塞
        deadline = time.time() + 12
        while not self._cold_done and time.time() < deadline:
            time.sleep(0.2)

        # 兜底：若索引仍为空（后台线程未运行/被环境限制），同步补抓冷启动页
        with self._idx_lock:
            empty = (len(self._idx) == 0)
        if empty:
            for tid, _ in SEARCH_CATS:
                for p in range(1, COLD_PAGES_PER_CAT + 1):
                    data = self._http_get({"ac": "detail", "t": tid, "pg": p})
                    if data:
                        with self._idx_lock:
                            for v in data.get("list", []):
                                self._idx.append(self._item(v))

        with self._idx_lock:
            idx = list(self._idx)

        # 1) 片名子串匹配
        hits = [it for it in idx if key_l in str(it.get("vod_name", "")).lower()]

        # 2) 分类名兜底：关键词命中分类名（含别名映射）时，并入该分类全部影片
        kw_norm = self.CAT_ALIAS.get(key_l, key_l)
        matched_tids = set()
        for c in WANT_CATS:
            cn = str(c.get("type_name", "")).lower()
            if kw_norm in cn or key_l in cn:
                matched_tids.add(str(c.get("type_id")))
        if matched_tids:
            seen = {it["vod_id"] for it in hits}
            for it in idx:
                if str(it.get("type_id")) in matched_tids and it["vod_id"] not in seen:
                    hits.append(it)
                    seen.add(it["vod_id"])

        limit = 20
        total = len(hits)
        pagecount = max(1, (total + limit - 1) // limit)
        start = (pg - 1) * limit
        return {
            "list": hits[start:start + limit],
            "page": pg,
            "pagecount": pagecount,
            "total": total,
        }

    def playerContent(self, flag, id, vipflags):
        # 苹果CMS 播放地址即 m3u8 直链（已是完整 https URL），直接返回即可
        url = id if (isinstance(id, str) and id.startswith("http")) else str(id)
        return {
            "parse": 0,
            "url": url,
            "header": {"User-Agent": UA, "Referer": "https://api.wsyzy.net/"},
        }

    # ---------------- 框架可选钩子 ----------------

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    def localProxy(self, param):
        pass



