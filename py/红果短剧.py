# -*- coding: utf-8 -*-
"""
红果短剧 (hongguoduanju.com) TVBox / 影视仓 Python 爬虫源

数据全部由服务端 SSR 内嵌在 HTML 的 window._ROUTER_DATA 中，无任何签名/加密，
无需 Referer 之外的特殊头。已逐一验证五个接口可用：

  homeContent    -> GET /                                  (homeSections 精选)
  categoryContent-> GET /category/{tid}?page={pg}          (recommendList)
  detailContent  -> GET /detail?series_id={id}             (seriesDetail + HTML 内嵌 vid_list 有序播放id)
  searchContent  -> GET /search/{keyword}                  (loaderData 内 searchList，keyword 走路径参数)
  playerContent  -> GET /player/{series_id}/{play_vid}     (video_player_info.main_url 直链 mp4)

分类 type_id：
  real-drama 真人剧 | comic-drama 漫剧 | ai-drama AI剧 | comic 漫画

字段契约（遵循 base.spider）：
  线路分隔 $$$ / 集分隔 # / 集名与地址 $
  detailContent 中每集 id 编码为  series_id__play_vid ，playerContent 再拆出。
"""

import re
import json
from urllib.parse import quote

from base.spider import Spider


class Spider(Spider):
    host = "https://hongguoduanju.com"

    def init(self, extend=""):
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": self.host + "/",
        }
        self.classes = [
            {"type_id": "real-drama", "type_name": "真人剧"},
            {"type_id": "comic-drama", "type_name": "漫剧"},
            {"type_id": "ai-drama", "type_name": "AI剧"},
            {"type_id": "comic", "type_name": "漫画"},
        ]

    # ------------------------------------------------------------------ #
    #  元信息
    # ------------------------------------------------------------------ #
    def getName(self):
        return "红果短剧"

    def isHome(self):
        return True

    # ------------------------------------------------------------------ #
    #  首页
    # ------------------------------------------------------------------ #
    def homeContent(self, filter):
        return {"class": self.classes, "filters": {}}

    def homeVideoContent(self):
        html = self._fetch("/")
        sections = (
            self._router(html).get("loaderData", {}).get("page", {}).get("homeSections", [])
        )
        videos = []
        for sec in sections:
            for v in sec.get("video_list", []):
                videos.append(self._card(v))
        return {"list": videos}

    # ------------------------------------------------------------------ #
    #  分类
    # ------------------------------------------------------------------ #
    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if str(pg).isdigit() else 1
        html = self._fetch("/category/%s?page=%d" % (tid, page))
        data = self._router(html).get("loaderData", {})
        page_data = {}
        for d in data.values():
            if isinstance(d, dict) and "recommendList" in d:
                page_data = d
                break
        if not page_data:
            return {"list": [], "page": page, "pagecount": 1, "limit": 0, "total": 0}
        items = page_data.get("recommendList", [])
        videos = [self._card(v) for v in items]
        pg_info = page_data.get("pagination", {})
        total_pages = int(pg_info.get("totalPages", 1) or 1)
        return {
            "list": videos,
            "page": page,
            "pagecount": total_pages,
            "limit": len(videos),
            "total": int(pg_info.get("total", 0) or 0),
        }

    # ------------------------------------------------------------------ #
    #  详情
    # ------------------------------------------------------------------ #
    def detailContent(self, ids):
        sid = ids[0] if isinstance(ids, list) else ids
        html = self._fetch("/detail?series_id=%s" % sid)
        data = self._router(html).get("loaderData", {})
        page = data.get("detail_page", {})
        info = page.get("seriesDetail", {})
        title = info.get("series_name") or info.get("series_title") or ""
        pic = info.get("series_cover") or ""
        intro = info.get("series_intro") or ""
        total = int(info.get("episode_cnt") or 0)
        # 网页版为"试看站"：每剧仅前 N 集免费可播，第 N+1 集起服务端直接 404。
        # 只列出可播放的集数，避免点开黑屏/"没有解析"。
        free = int(info.get("accessible_episode_cnt") or 0)

        play_vids = self._extract_play_vids(html, sid)
        if not play_vids:
            play_vids = [sid]  # 兜底，保证至少一集
        if 0 < free < len(play_vids):
            play_vids = play_vids[:free]

        episodes = []
        for idx, pv in enumerate(play_vids):
            episodes.append("第%d集$%s__%s" % (idx + 1, sid, pv))
        play_url = "#".join(episodes)

        if 0 < free < total:
            mark = "试看%d/%d集" % (free, total)
        else:
            mark = info.get("episode_right_text") or ""

        vod = {
            "vod_id": sid,
            "vod_name": title,
            "vod_pic": pic,
            "vod_content": intro,
            "vod_remarks": mark,
            "vod_play_from": "红果",
            "vod_play_url": play_url,
        }
        return {"list": [vod]}

    # ------------------------------------------------------------------ #
    #  搜索（keyword 走路径参数，SSR 直接返回）
    # ------------------------------------------------------------------ #
    def searchContent(self, key, quick, pg=1):
        page = int(pg) if str(pg).isdigit() else 1
        url = "/search/%s" % quote(key)
        if page > 1:
            url += "?page=%d" % page
        html = self._fetch(url)
        data = self._router(html).get("loaderData", {})
        sl = []
        for d in data.values():
            if isinstance(d, dict) and "searchList" in d:
                sl = d["searchList"]
                break
        videos = []
        for item in sl:
            vd = item.get("video_data", {}) or {}
            videos.append(
                {
                    "vod_id": vd.get("series_id") or item.get("keyword", ""),
                    "vod_name": vd.get("series_title") or item.get("name", ""),
                    "vod_pic": vd.get("series_cover", ""),
                    "vod_remarks": vd.get("episode_right_text", ""),
                }
            )
        return {
            "list": videos,
            "page": page,
            "pagecount": 1,
            "limit": len(videos),
            "total": len(videos),
        }

    # ------------------------------------------------------------------ #
    #  播放：取直链 mp4
    # ------------------------------------------------------------------ #
    def playerContent(self, flag, id, vipFlags):
        # 兼容不同壳：附 jx/playUrl 字段
        out = {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": dict(self.headers)}
        if "__" not in id:
            return out
        sid, pv = id.split("__", 1)
        try:
            html = self._fetch("/player/%s/%s" % (sid, pv))
        except Exception:
            html = ""
        mp4 = ""
        if html:
            data = self._router(html).get("loaderData", {})
            pk = [k for k in data if k.endswith("/page")]
            if pk:
                vpi = data[pk[0]].get("video_player_info", {}) or {}
                mp4 = vpi.get("main_url", "") or vpi.get("backup_url", "")
            if not mp4:
                m = re.search(r'"main_url"\s*:\s*"([^"]+)"', html)
                if m:
                    mp4 = m.group(1).replace("\\u002F", "/").replace("\\/", "/")
        out["url"] = mp4
        return out

    # ------------------------------------------------------------------ #
    #  工具
    # ------------------------------------------------------------------ #
    def _fetch(self, path, accept="text/html"):
        url = self.host + path
        headers = dict(self.headers)
        headers["Accept"] = accept
        # 兼容不同壳的 fetch 返回值：requests.Response(.text/.content) / urllib(.read())
        for fn in ("fetch", "get"):
            f = getattr(self, fn, None)
            if not f:
                continue
            try:
                r = f(url, headers=headers)
                for attr in ("text", "content", "body"):
                    v = getattr(r, attr, None)
                    if v is not None:
                        return v.decode("utf-8", "ignore") if isinstance(v, (bytes, bytearray)) else str(v)
                rd = getattr(r, "read", None)
                if callable(rd):
                    v = rd()
                    return v.decode("utf-8", "ignore") if isinstance(v, (bytes, bytearray)) else str(v)
                if isinstance(r, (str, bytes)):
                    return r.decode("utf-8", "ignore") if isinstance(r, bytes) else r
            except Exception:
                continue
        import urllib.request

        req = urllib.request.Request(url, headers=headers)
        return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")

    def _router(self, html):
        i = html.find("_ROUTER_DATA = ")
        if i < 0:
            return {}
        start = html.find("{", i)
        depth = 0
        instr = False
        esc = False
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
                        return json.loads(html[start : j + 1])
                    except Exception:
                        return {}
        return {}

    def _card(self, v):
        return {
            "vod_id": v.get("series_id", ""),
            "vod_name": v.get("series_title") or v.get("series_name", ""),
            "vod_pic": v.get("series_cover", ""),
            "vod_remarks": v.get("episode_right_text", ""),
        }

    def _extract_play_vids(self, html, sid):
        """从详情页 HTML 提取当前剧集的有序 play_vid 列表。

        播放 id 只出现在 /player/{sid}/{vid} 链接与 video_player_info 中；
        详情页 video 容器内的 vid_list 数组按集序内嵌全部 play_vid（含第1集）。
        通过「数组元素集合是否包含 /player/{sid}/ 链接中的 vid」来精确定位当前剧，
        避免混入相关推荐剧的 vid_list。
        """
        hrefs = set(re.findall(r"/player/%s/(\d+)" % re.escape(sid), html))
        best = []
        for m in re.finditer(r'"vid_list"\s*:\s*\[', html):
            arr_start = m.end() - 1
            depth = 0
            instr = False
            esc = False
            end = None
            for j in range(arr_start, min(arr_start + 60000, len(html))):
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
                if c == "[":
                    depth += 1
                elif c == "]":
                    depth -= 1
                    if depth == 0:
                        end = j
                        break
            if end is None:
                continue
            seg = html[arr_start : end + 1]
            try:
                arr = json.loads(seg)
            except Exception:
                continue
            if not arr:
                continue
            arrset = set(arr)
            if hrefs and hrefs.issubset(arrset):
                return arr
            if len(arr) > len(best):
                best = arr
        return best
