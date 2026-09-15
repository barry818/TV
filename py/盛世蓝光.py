# -*- coding: utf-8 -*-
# 盛世蓝光 (ApptoV5 API 源) TVBox / 影视仓 Python 接口源
# 由「盛世蓝光.py」重写修复：修正分类恒空、getName 返回 None、uuid 未写入 headers、
# 搜索/分类缺 pagecount、vod_pic 未防 None、extend 可能为字符串、各接口缺 key 守卫等问题。
#
# 铁律落实：header 一律 dict；POST 用 self.post(url, data=...)（非 json=）；
# 线路名 show 只放 vod_play_from；播放地址用 名称$线路@直链 编码，playerContent 按 @ 拆解。

import re
import sys
import uuid
from urllib.parse import quote

try:
    from base.spider import Spider
except Exception:
    class Spider:
        def fetch(self, *a, **k):
            raise NotImplementedError("base.spider required in TVBox runtime")

sys.path.append("..")

# 请求基础头（uuid 在 init 内生成并写入）
BASE_HEADERS = {
    "User-Agent": "Dart/2.19 (dart:io)",
    "Accept-Encoding": "gzip",
}


# 内置默认 API 域名（IP:PORT 直连）；如需切换可在 tv.json 的 ext 字段覆盖
DEFAULT_HOST = "http://43.248.117.123:4680"


class Spider(Spider):
    host = DEFAULT_HOST
    config = {}
    local_uuid = ""
    parsing_config = {}

    def init(self, extend=""):
        host = (extend or "").strip()
        if not host:
            # 未通过 tv.json ext 传入域名时，回退到内置默认域名
            host = self.host or DEFAULT_HOST
        # 用户可通过 tv.json 的 ext 覆盖域名；不传则用内置默认域名
        if not host.startswith("http"):
            host = "http://" + host
        self.host = host.rstrip("/")

        # 生成并写入鉴权 uuid（原实现漏写回 headers，导致该头恒为空）
        self.local_uuid = str(uuid.uuid4())
        self.headers = dict(BASE_HEADERS)
        self.headers["appto-local-uuid"] = self.local_uuid

        self.config = {}
        self.parsing_config = {}
        try:
            resp = self.fetch(
                f"{self.host}/apptov5/v1/config/get?p=android&__platform=android",
                headers=self.headers,
            ).json()
            config = resp.get("data") or {}
            self.config = config

            parsing_conf = (config.get("get_parsing") or {}).get("lists", []) or []
            parsing_config = {}
            for i in parsing_conf:
                cfgs = i.get("config") or []
                if len(cfgs) != 0:
                    label = [j.get("label") for j in cfgs if j.get("type") == "json"]
                    label = [x for x in label if x]
                    parsing_config[i.get("key")] = label
            self.parsing_config = parsing_config
        except Exception as e:
            print(f"初始化异常：{e}")
        return None

    def getName(self):
        return "盛世蓝光"

    # ---------------- 接口实现 ----------------

    def homeContent(self, filter):
        config = self.config
        if not isinstance(config, dict):
            return {"class": [], "filters": {}}
        home_cate = config.get("get_home_cate") or []
        classes = []
        for i in home_cate:
            cate = i.get("cate") or i.get("id")
            title = i.get("title")
            if not cate or not title:
                continue
            if title == "首页":          # 首页为入口模块非真实分类，且 id 与"电影"重复，跳过避免 tab 冲突
                continue
            classes.append({"type_id": cate, "type_name": title})
        return {"class": classes, "filters": {}}

    def homeVideoContent(self):
        try:
            resp = self.fetch(
                f"{self.host}/apptov5/v1/home/data?id=1&mold=1&__platform=android",
                headers=self.headers,
            ).json()
        except Exception as e:
            print(f"首页数据异常：{e}")
            return {"list": []}
        data = resp.get("data") or {}
        vod_list = []
        for i in data.get("sections", []) or []:
            for j in i.get("items", []) or []:
                pic = j.get("vod_pic") or ""
                if pic.startswith("mac://"):
                    pic = pic.replace("mac://", "http://", 1)
                vod_list.append({
                    "vod_id": j.get("vod_id"),
                    "vod_name": j.get("vod_name"),
                    "vod_pic": pic,
                    "vod_remarks": j.get("vod_remarks"),
                })
        return {"list": vod_list}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        ext = self._parse_extend(extend)
        url = (
            f"{self.host}/apptov5/v1/vod/lists"
            f"?area={ext.get('area', '')}&lang={ext.get('lang', '')}"
            f"&year={ext.get('year', '')}&order={ext.get('sort', 'time')}"
            f"&type_id={tid}&type_name=&page={pg}&pageSize=21&__platform=android"
        )
        try:
            resp = self.fetch(url, headers=self.headers).json()
        except Exception as e:
            print(f"分类数据异常：{e}")
            return {"list": [], "page": pg, "pagecount": pg}
        data = resp.get("data") or {}
        items = data.get("data") or []
        for i in items:
            pic = i.get("vod_pic") or ""
            if pic.startswith("mac://"):
                i["vod_pic"] = pic.replace("mac://", "http://", 1)
        total = data.get("total") or 0
        try:
            total = int(total)
        except Exception:
            total = 0
        pagecount = (total // 21) + (1 if total % 21 else 0) if total else pg
        return {"list": items, "page": pg, "pagecount": pagecount, "total": total}

    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, list) else ids
        try:
            resp = self.fetch(
                f"{self.host}/apptov5/v1/vod/getVod?id={vid}",
                headers=self.headers,
            ).json()
        except Exception as e:
            print(f"详情异常：{e}")
            return {"list": []}

        data3 = resp.get("data") or {}
        vod_play_from = ""
        vod_play_url = ""
        for i in data3.get("vod_play_list", []) or []:
            pinfo = i.get("player_info") or {}
            fu = pinfo.get("from", "")
            show = pinfo.get("show", "")
            play_url = ""
            for j in i.get("urls", []) or []:
                # 编码：名称$线路@直链（@ 为线路/直链分隔，避免与 $ 冲突）
                play_url += f"{j.get('name', '')}${fu}@{j.get('url', '')}#"
            if play_url:
                vod_play_from += show + "$$$"
                vod_play_url += play_url.rstrip("#") + "$$$"

        vod_play_from = vod_play_from.rstrip("$$$")
        vod_play_url = vod_play_url.rstrip("$$$")

        return {"list": [{
            "vod_id": data3.get("vod_id"),
            "vod_name": data3.get("vod_name"),
            "vod_content": data3.get("vod_content"),
            "vod_remarks": data3.get("vod_remarks"),
            "vod_director": data3.get("vod_director"),
            "vod_actor": data3.get("vod_actor"),
            "vod_year": data3.get("vod_year"),
            "vod_area": data3.get("vod_area"),
            "vod_play_from": vod_play_from,
            "vod_play_url": vod_play_url,
        }]}

    def playerContent(self, flag, id, vipflags):
        default_ua = ("Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) "
                      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 "
                      "Mobile/15E148 Safari/604.1")
        parsing_config = self.parsing_config if isinstance(self.parsing_config, dict) else {}

        # id 形如 名称$线路@直链 -> 取 @ 后的 线路@直链
        parts = id.split("@")
        if len(parts) != 2:
            return {"parse": 0, "url": id, "header": {"User-Agent": default_ua}}
        playfrom, rawurl = parts

        label_list = parsing_config.get(playfrom)
        if not label_list:
            # 无解析配置，直接透传直链
            return {"parse": 0, "url": rawurl, "header": {"User-Agent": default_ua}}

        result = {"parse": 1, "url": rawurl, "header": {"User-Agent": default_ua}}
        for label in label_list:
            payload = {"play_url": rawurl, "label": label, "key": playfrom}
            try:
                # 标准 POST：data=dict（非 json=，避免 TypeError）
                resp = self.post(
                    f"{self.host}/apptov5/v1/parsing/proxy?__platform=android",
                    data=payload,
                    headers=self.headers,
                ).json()
            except Exception as e:
                print(f"解析请求异常: {e}")
                continue
            if not isinstance(resp, dict):
                continue
            if resp.get("code") == 422:
                continue
            d = resp.get("data")
            if not isinstance(d, dict):
                continue
            url = d.get("url")
            if not url:
                continue
            ua = d.get("UA") or d.get("UserAgent") or default_ua
            result = {"parse": 0, "url": url, "header": {"User-Agent": ua}}
            break
        return result

    def searchContent(self, key, quick, pg="1"):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        url = (f"{self.host}/apptov5/v1/search/lists"
               f"?wd={quote(str(key))}&page={pg}&type=&__platform=android")
        try:
            resp = self.fetch(url, headers=self.headers).json()
        except Exception as e:
            print(f"搜索异常：{e}")
            return {"list": [], "page": pg, "pagecount": pg}
        data = resp.get("data") or {}
        items = data.get("data") or []
        for i in items:
            pic = i.get("vod_pic") or ""
            if pic.startswith("mac://"):
                i["vod_pic"] = pic.replace("mac://", "http://", 1)
        total = data.get("total") or 0
        pagecount = pg + 1 if items else pg
        return {"list": items, "page": pg, "pagecount": pagecount, "total": total}

    # ---------------- 工具 ----------------

    @staticmethod
    def _parse_extend(extend):
        if not extend:
            return {}
        if isinstance(extend, dict):
            return extend
        if isinstance(extend, str):
            try:
                import json
                return json.loads(extend)
            except Exception:
                return {}
        return {}

    # 以下为框架可选钩子
    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    def localProxy(self, param):
        pass
