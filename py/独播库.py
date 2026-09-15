# -*- coding: utf-8 -*-
"""
独播库 (Duboku) TVBox / 影视仓 Python 接口源
============================================
由 CatVod T4(JS) 源「独播库.js」移植而来。

站点特征：
  - JSON API 源（非 HTML 解析），接口域名 https://api.dbokutv.com
  - 所有请求必须带签名：?sign=<60位随机>&token=<38位随机>&ssid=<Base64(随机数+时间戳交织)>
  - ID 混淆：DId/DuId/TnId/VId/HId 均为"每10字符反转 -> .替换= -> Base64"的混淆串，需解码还原
  - 分类：/vodshow/{tid}-{area}-{sort}-{class}-{lang}-{letter}-{scat}--{pg}--{year}
  - 详情：{host}{解码后的详情路径} 返回 Playlist（EpisodeName + 解码VId）
  - 播放：{host}{解码后的VId路径} 返回 HId，再解码得到真实直链
  - 搜索：/vodsearch?wd=关键词

铁律落实：header 一律 dict；禁用 self.post(json=)（本源全 GET）；
播放地址存相对/解码路径、playerContent 用 _sign_url 拼 Host（无双重 host）；
三层分隔符 # 正确（线路名 "独播库" 只放 vod_play_from）。
"""

import re
import json
import base64
import random
import time
from urllib.parse import quote

try:
    from base.spider import Spider
except Exception:
    # 独立调试时可缺省 base.spider，仅用于语法检查
    class Spider:
        def fetch(self, *a, **k):
            raise NotImplementedError("base.spider required in TVBox runtime")


# ---- 站点常量 ----
API_HOST = "https://api.dbokutv.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
HEADERS = {
    "User-Agent": UA,
    "Connection": "Keep-Alive",
    "Referer": "https://www.duboku.tv/",
}
PLAY_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept-Encoding": "gzip, deflate",
    "origin": "https://w.duboku.io",
    "referer": "https://w.duboku.io/",
    "priority": "u=1, i",
}

CLASSES = [
    {"type_id": "2", "type_name": "连续剧"},
    {"type_id": "3", "type_name": "综艺"},
    {"type_id": "1", "type_name": "电影"},
    {"type_id": "4", "type_name": "动漫"},
]

# JS 中 FilterList.Class -> 筛选 key 的映射
FILTER_KEY_MAP = {
    "剧情": "class", "地区": "area", "年份": "year", "语言": "lang",
    "字母": "letter", "排序": "sort", "类型": "scat",
}

_ALNUM = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


# ---------------- 通用工具（模块级，纯函数） ----------------

def _rand_str(n):
    """生成 n 位 [a-zA-Z0-9] 随机串（对应 JS 的 u()）。"""
    return "".join(random.choice(_ALNUM) for _ in range(n))


def _interleave(t, e):
    """交织两个字符串：先逐字符交替，再拼接各自剩余（对应 JS 的 f 内联函数）。"""
    o = min(len(t), len(e))
    parts = []
    for r in range(o):
        parts.append(t[r])
        parts.append(e[r])
    parts.append(t[o:])
    parts.append(e[o:])
    return "".join(parts)


def decode_id(e):
    """
    解码混淆 ID（对应 JS 的 l()）：
      1) 去掉引号  2) 每 10 字符为一个块整体反转  3) '.' 还原为 '='  4) Base64 解码为 UTF-8
    """
    if not e or not isinstance(e, str):
        return ""
    n = e.replace("'", "").replace('"', "")
    if not n:
        return ""
    o = ""
    for i in range(0, len(n), 10):
        o += n[i:i + 10][::-1]
    o = o.replace(".", "=")
    try:
        return base64.b64decode(o).decode("utf-8")
    except Exception:
        return ""


class Spider(Spider):
    Host = API_HOST

    # ---------------- 初始化 ----------------

    def init(self, extend=""):
        if isinstance(extend, str) and re.match(r"^https?://", extend.strip()):
            self.Host = extend.strip().rstrip("/")
        self.headers = dict(HEADERS)
        self.headers["Referer"] = "https://www.duboku.tv/"

    def getName(self):
        return "独播库"

    # ---------------- 请求（带签名） ----------------

    def _sign_url(self, path):
        """给 API path 附加签名参数，返回完整 URL（对应 JS 的 f()）。"""
        n = random.randint(0, 800000000)
        s1 = f"{n + 100000000}{900000000 - n}"      # ${n+1e8}${9e8-n}
        s2 = str(int(time.time()))                  # 当前秒级时间戳
        inter = _interleave(s1, s2)
        ssid = base64.b64encode(inter.encode("utf-8")).decode("ascii").replace("=", ".")
        p = path if path.startswith("/") else "/" + path
        return (f"{self.Host}{p}?sign={_rand_str(60)}"
                f"&token={_rand_str(38)}&ssid={ssid}")

    def _get_json(self, url):
        """GET 并解析 JSON，兼容 .json() / .text / .content / 纯字符串。"""
        try:
            r = self.fetch(url, headers=self.headers)
            if r is None:
                return None
            if hasattr(r, "json"):
                try:
                    return r.json()
                except Exception:
                    pass
            if hasattr(r, "text") and isinstance(r.text, str):
                return json.loads(r.text)
            if hasattr(r, "content"):
                return json.loads(r.content.decode("utf-8", "ignore"))
            if isinstance(r, str):
                return json.loads(r)
        except Exception:
            return None
        return None

    # ---------------- 接口实现 ----------------

    def homeContent(self, filter):
        filters = self._build_filters()
        return {"class": CLASSES, "filters": filters}

    def homeVideoContent(self):
        data = self._get_json(self._sign_url("/home"))
        out = []
        if isinstance(data, list):
            for block in data:
                for v in (block.get("VodList") or []):
                    out.append(self._to_vod(v))
        return {"list": out}

    def categoryContent(self, tid, pg, filter, extend):
        tid = str(tid or "1")
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        ext = self._parse_extend(extend)
        # 12 段数组（与 JS 的 s[] 完全对应）
        s = [""] * 12
        s[0] = tid
        s[1] = ext.get("area", "") or ""
        s[2] = ext.get("sort", "") or "时间"
        s[3] = ext.get("class", "") or ""
        s[4] = ext.get("lang", "") or ""
        s[5] = ext.get("letter", "") or ""
        s[6] = ext.get("scat", "") or ""
        s[8] = "" if pg == 1 else str(pg)
        s[11] = ext.get("year", "") or ""
        url = self._sign_url("/vodshow/" + "-".join(s))
        data = self._get_json(url)
        out = []
        if data and data.get("VodList"):
            for v in data["VodList"]:
                out.append(self._to_vod(v))
        pagecount = self._page_count(data, pg)
        return {"page": pg, "pagecount": pagecount, "list": out}

    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, list) else ids
        # vid 已是解码后的详情路径（如 /vod/detail/xxx）
        url = self._sign_url(vid)
        data = self._get_json(url)
        if not data:
            return {"list": []}

        playlist = data.get("Playlist") or []
        eps = []
        for t in playlist:
            name = t.get("EpisodeName", "")
            path = decode_id(t.get("VId"))
            if path:
                eps.append(f"{name}${path}")

        actor = data.get("Actor")
        if isinstance(actor, list):
            actor = ",".join(actor)
        vod = {
            "vod_id": vid,
            "vod_name": data.get("Name", ""),
            "vod_pic": decode_id(data.get("TnId")),
            "vod_remarks": f"评分：{data.get('Rating', '')}",
            "vod_year": data.get("ReleaseYear", ""),
            "vod_area": data.get("Region", ""),
            "vod_actor": actor or "",
            "vod_director": data.get("Director", ""),
            "vod_content": data.get("Description", ""),
            "vod_play_from": "独播库",
            "vod_play_url": "#".join(eps),
            "type_name": ",".join(filter(None, [
                data.get("Genre"), data.get("Scenario"), data.get("Language")])),
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        # id 为解码后的 VId 路径（如 /vod/play/xxx）
        url = self._sign_url(id)
        data = self._get_json(url)
        if not data:
            return {"parse": 0, "url": "", "header": {}}
        hid = decode_id(data.get("HId"))
        if hid and re.match(r"^https?://", hid):
            return {"parse": 0, "url": hid, "header": dict(PLAY_HEADERS)}
        return {"parse": 0, "url": "", "header": {}, "msg": "未获取到播放地址，请稍后重试"}

    def searchContent(self, key, quick, pg):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        url = self._sign_url("/vodsearch") + "&wd=" + quote(str(key))
        data = self._get_json(url)
        out = []
        if isinstance(data, list):
            for v in data:
                out.append({
                    "vod_id": decode_id(v.get("DId") or v.get("DuId")),
                    "vod_name": v.get("Name", ""),
                    "vod_pic": decode_id(v.get("TnId")),
                    "vod_remarks": v.get("Tag", ""),
                    "vod_actor": v.get("Actor", ""),
                    "vod_score": v.get("Rating", ""),
                })
        pagecount = pg + 1 if out else pg
        return {"list": out, "page": pg, "pagecount": pagecount,
                "limit": len(out) or 18, "total": pagecount * 18}

    # ---------------- 解析辅助 ----------------

    def _to_vod(self, v):
        if not isinstance(v, dict):
            return {}
        return {
            "vod_id": decode_id(v.get("DId") or v.get("DuId")),
            "vod_name": v.get("Name", ""),
            "vod_pic": decode_id(v.get("TnId")),
            "vod_remarks": v.get("Tag", ""),
        }

    def _page_count(self, data, pg):
        if not data:
            return pg
        pc = 0
        try:
            for t in (data.get("PaginationList") or []):
                if t.get("Type") == "StartEnd":
                    pid = decode_id(t.get("PId") or t.get("PuId"))
                    parts = pid.split("-")
                    if len(parts) > 8:
                        x = int(parts[8])
                        if x:
                            pc = x
            if pc == 0:
                for t in (data.get("PaginationList") or []):
                    if t.get("Type") == "ShortPage":
                        parts = (t.get("Name") or "").split("/")
                        if len(parts) > 1:
                            x = int(parts[1])
                            if x:
                                pc = x
        except Exception:
            pc = 0
        if pc == 0:
            pc = 1
        return max(pg, pc)

    def _build_filters(self):
        filters = {}
        for c in CLASSES:
            tid = c["type_id"]
            # /vodshow/{tid}-----------  (tid + 11 个空段，共 12 段)
            url = self._sign_url("/vodshow/" + tid + "-" * 11)
            data = self._get_json(url)
            fl = []
            if data and data.get("FilterList"):
                for flt in data["FilterList"]:
                    key = FILTER_KEY_MAP.get(flt.get("Class", ""))
                    opts = flt.get("OptionList") or []
                    if not key or not opts:
                        continue
                    values = []
                    init = ""
                    if key == "sort":
                        for o in opts:
                            op = o.get("Option")
                            values.append({"n": op, "v": op})
                        init = "时间"
                    else:
                        values.append({"n": "全部", "v": ""})
                        for o in opts:
                            op = o.get("Option")
                            if op and op != "全部":
                                values.append({"n": op, "v": op})
                    fl.append({"key": key, "name": flt.get("Class"),
                               "value": values, "init": init})
            if fl:
                filters[tid] = fl
        return filters

    @staticmethod
    def _parse_extend(extend):
        if not extend:
            return {}
        if isinstance(extend, str):
            try:
                return json.loads(extend)
            except Exception:
                return {}
        return extend
