import hashlib
import hmac
import json
import re
import secrets
import time
import urllib.parse

from base.spider import Spider

"""
搜剧AI (ai.baipiaozhe.com) —— TVBox / 影视仓 Python 接口源
站点性质：AI 影视搜索聚合站（React SPA + OpenAI 风格 JSON API）。

==================== 反编译要点（重要） ====================
站点 API 全部带【请求签名】校验，无签名返回 401 "Missing request signature"。
签名算法（从前端 JS 逆向得到）：
  消息 = "{METHOD}\\n{path}{query}\\n{timestamp_ms}\\n{nonce}"
  签名 = HMAC-SHA256(SECRET, 消息).hexdigest()   # 小写 hex
  请求头需携带：
    x-ai-movie-timestamp  = timestamp(ms)
    x-ai-movie-nonce      = 32 位十六进制随机串
    x-ai-movie-signature  = 上述签名
    x-ai-movie-client-name / -client-version / -build-version / -protocol-version  = 客户端标识
  SECRET 内嵌于前端包（movie-card-runtime chunk），已提取：

搜索结论：
  - /v1/browse/catalog?query=xxx 的 query 参数【被服务端忽略】（任何关键词都返回同一批），
    所以列表/搜索不能直接用该接口做关键词检索。
  - 真正的检索走 /v1/suggest?q=关键词 → 返回精确片名 + target.variant_id（真实 catalog id），
    再用 /v1/catalog/{id} 取详情。这是 searchContent 采用的路径（相关度极佳）。
  - 分类浏览用 /v1/browse/catalog?intent=catalog_search&kind=movie|series|variety|short_drama
    （kind 合法值即此四项；无 anime/tv）。

播放结论：
  - catalog 详情里的 urls.yjm3u8 指向 zy.baipiaozhe.com，该域被 Cloudflare 拦（直连 301 死循环），
    TVBox 播放器无法过校验 → 不可用。
  - 但 /v1/playback/resolve/{episode_token} 返回的 line_options 内含【第三方 CDN 直链 m3u8】
    （如 hn.bfvvs.com / wsyzy 等，url_kind=m3u8 且 resolved=true），实测 200 可播。
    playerContent 即取这些直链，跳过 zy 域与需要二次解析的 ticket 线路。

铁律落实：全程 self.fetch()；不覆盖 __init__；header 为 dict；不使用 self.post(json=)。
"""

# ---- 签名密钥与客户端标识（来自前端包，可能随版本更新，若 401 请同步刷新） ----
SECRET = "f39d73aa7a6426203cdee1ef17b31d3b7ea8c23f4c59c62a3a8aa0f39ee5e79d"
CLIENT_NAME = "movie-search-frontend"
CLIENT_VERSION = "1.0.0"
BUILD_VERSION = "aimovie-v2026.09.15.3-774bcc0013f5-web"
PROTOCOL_VERSION = "2026-07-05.library-v2.playback-v1"

# 分类映射：type_id -> (intent, kind)
CATE_MAP = {
    "1": ("latest_catalog", None),
    "2": ("catalog_search", "movie"),
    "3": ("catalog_search", "series"),
    "4": ("catalog_search", "variety"),
    "5": ("catalog_search", "short_drama"),
}


class Spider(Spider):
    def init(self, extend=""):
        self.host = "https://ai.baipiaozhe.com"
        self.header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": self.host + "/",
            "Accept": "application/json",
        }
        if isinstance(extend, str) and extend.strip() and re.match(r"^https?://", extend.strip()):
            self.host = extend.strip().rstrip("/")
            self.header["Referer"] = self.host + "/"
        self._ua = self.header["User-Agent"]

    def getName(self):
        return "搜剧AI"

    # ---------- 签名 + 请求 ----------
    def _sign_headers(self, method, path):
        ts = str(int(time.time() * 1000))
        nonce = secrets.token_hex(16)
        msg = "%s\n%s\n%s\n%s" % (method, path, ts, nonce)
        sig = hmac.new(SECRET.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()
        h = dict(self.header)
        h["x-ai-movie-timestamp"] = ts
        h["x-ai-movie-nonce"] = nonce
        h["x-ai-movie-signature"] = sig
        h["x-ai-movie-client-name"] = CLIENT_NAME
        h["x-ai-movie-client-version"] = CLIENT_VERSION
        h["x-ai-movie-build-version"] = BUILD_VERSION
        h["x-ai-movie-protocol-version"] = PROTOCOL_VERSION
        return h

    def _api(self, path, method="GET"):
        """path 为相对路径(含 query)；签名与请求使用同一 path 字符串。返回解析后的 JSON 或原始文本。"""
        h = self._sign_headers(method, path)
        url = self.host + path
        resp = self.fetch(url, headers=h)
        if resp is None:
            return None
        if hasattr(resp, "text"):
            text = resp.text
        else:
            try:
                text = resp.content.decode("utf-8", errors="ignore")
            except Exception:
                text = ""
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            return text

    # ---------- 字段映射 ----------
    @staticmethod
    def _card_to_vod(card):
        cid = card.get("id") or card.get("variant_id")
        if not cid:
            return None
        title = card.get("title") or card.get("normalized_title") or ""
        pic = card.get("poster_url") or ""
        if pic and not pic.startswith("http"):
            pic = ""
        remarks = card.get("remarks") or ""
        if not remarks and card.get("year"):
            remarks = str(card.get("year"))
        if not remarks and card.get("area"):
            remarks = card.get("area")
        if not remarks and (card.get("genres") or []):
            remarks = (card.get("genres") or [])[0]
        return {
            "vod_id": cid,
            "vod_name": title,
            "vod_pic": pic,
            "vod_remarks": remarks,
        }

    # ---------- homeContent ----------
    def homeContent(self, filter):
        class_list = [
            {"type_id": "1", "type_name": "最新"},
            {"type_id": "2", "type_name": "电影"},
            {"type_id": "3", "type_name": "电视剧"},
            {"type_id": "4", "type_name": "综艺"},
            {"type_id": "5", "type_name": "短剧"},
        ]
        return {"class": class_list, "filters": {}}

    # ---------- categoryContent ----------
    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        intent, kind = CATE_MAP.get(str(tid), ("latest_catalog", None))
        params = "intent=%s&page=%d&limit=20" % (intent, pg)
        if kind:
            params += "&kind=%s" % kind
        data = self._api("/v1/browse/catalog?%s" % params)
        if not data or not isinstance(data, dict):
            return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}
        cards = data.get("cards") or []
        items = [self._card_to_vod(c) for c in cards]
        items = [x for x in items if x]
        pag = data.get("pagination") or {}
        total = pag.get("total")
        limit = pag.get("limit") or 20
        if not total:
            total = len(items)
        pagecount = (int(total) + limit - 1) // limit if total else 1
        return {
            "list": items,
            "page": pg,
            "pagecount": pagecount,
            "limit": limit,
            "total": int(total),
        }

    # ---------- searchContent（suggest -> variant_id -> catalog 详情） ----------
    def searchContent(self, key, quick, pg="1"):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if pg >= 2:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}
        q = urllib.parse.quote(key)
        s = self._api("/v1/suggest?q=%s" % q)
        if not s or not isinstance(s, dict):
            return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}
        sugs = s.get("suggestions") or []
        vids = []
        for sg in sugs:
            tgt = sg.get("target") or {}
            vid = tgt.get("variant_id")
            if vid and vid not in vids:
                vids.append(vid)
        items = []
        for vid in vids[:10]:
            d = self._api("/v1/catalog/%s" % urllib.parse.quote(vid, safe=""))
            if d and isinstance(d, dict) and d.get("title"):
                v = self._card_to_vod(d)
                if v:
                    items.append(v)
        return {
            "list": items,
            "page": pg,
            "pagecount": 1,
            "limit": 20,
            "total": len(items),
        }

    # ---------- detailContent ----------
    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vid = ids[0]
        d = self._api("/v1/catalog/%s" % urllib.parse.quote(vid, safe=""))
        if not d or not isinstance(d, dict) or not d.get("title"):
            return {"list": []}
        eps = d.get("episodes") or []
        if not eps:
            return {"list": []}
        # 解析首集 token 以发现"直链 m3u8"线路名（同一作品各集线路一致）
        lines = self._direct_lines(eps[0].get("token"))
        if not lines:
            lines = [{"disp": "云剧线路"}]
        play_from = "$$$".join(ln["disp"] for ln in lines)
        pools = []
        for ln in lines:
            pool = []
            for ep in eps:
                name = ep.get("title") or ("第%d集" % (ep.get("sequence_index") or 0))
                pool.append("%s$%s" % (name, ep.get("token")))
            pools.append("#".join(pool))
        play_url = "$$$".join(pools)
        vod = {
            "vod_id": vid,
            "vod_name": d.get("title", ""),
            "vod_pic": d.get("poster_url", ""),
            "vod_actor": ",".join(d.get("actors") or []),
            "vod_director": ",".join(d.get("directors") or []),
            "vod_remarks": d.get("remarks") or str(d.get("year") or ""),
            "vod_year": str(d.get("year") or ""),
            "vod_area": d.get("area") or "",
            "vod_content": d.get("description") or "",
            "vod_play_from": play_from,
            "vod_play_url": play_url,
        }
        return {"list": [vod]}

    # ---------- 播放解析：取直链 m3u8 线路 ----------
    def _resolve(self, token):
        if not token:
            return None
        return self._api("/v1/playback/resolve/%s" % urllib.parse.quote(token, safe=""))

    def _direct_lines(self, token):
        """返回该集可用的【直链 m3u8】线路列表 [{disp, weight}]（跳过 zy 域与 ticket 线路）。"""
        d = self._resolve(token)
        if not d or not isinstance(d, dict):
            return []
        out = []
        for ln in d.get("line_options", []):
            url = ln.get("url", "")
            if ln.get("url_kind") == "m3u8" and ln.get("resolved") and url.startswith("http") \
                    and "zy.baipiaozhe.com" not in url:
                disp = ln.get("label") or ln.get("provider_name") or ln.get("play_from") or "线路"
                out.append({"disp": disp, "weight": ln.get("preference_weight") or 0})
        # 去重保序
        seen, res = set(), []
        for x in out:
            if x["disp"] not in seen:
                seen.add(x["disp"])
                res.append(x)
        return res

    # ---------- playerContent ----------
    def playerContent(self, flag, id, vipFlags):
        # id = 某一集的 episode token
        d = self._resolve(id)
        if not d or not isinstance(d, dict):
            return {"parse": 0, "url": ""}
        lines = []
        for ln in d.get("line_options", []):
            url = ln.get("url", "")
            if ln.get("url_kind") == "m3u8" and ln.get("resolved") and url.startswith("http") \
                    and "zy.baipiaozhe.com" not in url:
                disp = ln.get("label") or ln.get("provider_name") or ln.get("play_from") or ""
                lines.append((disp, url, ln.get("preference_weight") or 0))
        if not lines:
            return {"parse": 0, "url": ""}
        # 优先匹配用户所选线路名(flag)，否则取权重最高者
        chosen = None
        for disp, url, w in lines:
            if flag and disp and disp == flag:
                chosen = url
                break
        if not chosen:
            lines.sort(key=lambda x: -x[2])
            chosen = lines[0][1]
        h = {"User-Agent": self._ua, "Referer": self.host + "/"}
        return {"parse": 0, "url": chosen, "header": h}


"""
==============================================================================
部署 tv.json 示例：
{
  "key": "搜剧AI",
  "name": "搜剧AI",
  "type": 3,
  "api": "./py/搜剧AI.py",
  "searchable": 1,
  "filterable": 0,
  "changeable": 1,
  "playerType": 2
}

说明：
- 本源为 AI 影视搜索站，核心用途是【搜索】与【分类浏览】，播放走第三方 CDN 直链 m3u8。
- 站点 API 带 HMAC 请求签名（已逆向实现），无需登录/会话即可调用。
- 搜索质量极佳：/v1/suggest 返回精确片名，再拉取详情，相关度远超站内的关键词列表检索。
- 分类：最新/电影/电视剧/综艺/短剧（kind 合法值仅此四项，故未放动漫）。
- 播放：取 playback/resolve 中的第三方 CDN 直链 m3u8（已验证 200 可播）；
  zy.baipiaozhe.com 的 m3u8 被 Cloudflare 拦截，已主动跳过。
- 注意：SECRET / build-version 等内嵌于前端包，若日后站点改版导致 401，
  需重新从前端 JS 提取 SECRET 并刷新本文件顶部常量。
==============================================================================
"""
