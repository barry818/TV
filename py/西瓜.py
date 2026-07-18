#!/usr/bin/python
# -*- coding: utf-8 -*-
import html
import re
from urllib.parse import quote, urljoin

import requests
from lxml import etree
from base.spider import Spider


class Spider(Spider):
    def getName(self):
        return "西瓜在线"

    def init(self, extend=""):
        self.host = "https://www.xiguazx.cc"
        self.api = self.host + "/api.php/provide/vod/"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Referer": self.host + "/",
        }

    def _get(self, params):
        try:
            response = requests.get(self.api, params=params, headers=self.headers, timeout=15)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            return {}

    def _web_get(self, url):
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or "utf-8"
            return response.text
        except requests.RequestException:
            return ""

    def _text(self, value):
        return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", value or ""))).strip()

    def _item(self, vod):
        return {
            "vod_id": str(vod.get("vod_id", "")),
            "vod_name": vod.get("vod_name", ""),
            "vod_pic": vod.get("vod_pic", ""),
            "vod_remarks": vod.get("vod_remarks", ""),
        }

    def _filters(self, classes):
        years = [str(year) for year in range(2026, 1979, -1)]
        values = [
            {"key": "area", "name": "地区", "value": [{"n": name, "v": value} for name, value in [
                ("全部", ""), ("中国", "中国"), ("中国大陆", "中国大陆"), ("中国香港", "中国香港"), ("中国台湾", "中国台湾"),
                ("美国", "美国"), ("韩国", "韩国"), ("日本", "日本"), ("英国", "英国"), ("法国", "法国"),
                ("德国", "德国"), ("印度", "印度"), ("泰国", "泰国"), ("其他", "其他")]]},
            {"key": "year", "name": "年份", "value": [{"n": "全部", "v": ""}] + [{"n": year, "v": year} for year in years]},
            {"key": "by", "name": "排序", "value": [{"n": "时间", "v": "time"}, {"n": "人气", "v": "hits"}, {"n": "评分", "v": "score"}]},
        ]
        return {item["type_id"]: values for item in classes}

    def _category_url(self, tid, pg, extend):
        parts = []
        for key in ("area", "by", "year"):
            value = str((extend or {}).get(key, "")).strip()
            if value:
                parts.extend((key, quote(value, safe="")))
        parts.extend(("id", quote(str(tid), safe=""), "page", str(pg)))
        return self.host + "/index.php/vod/show/" + "/".join(parts) + ".html"

    def _parse_category(self, page):
        source = self._web_get(page)
        if not source:
            return [], 1
        tree = etree.HTML(source)
        items = []
        seen = set()
        for node in tree.xpath('//a[contains(@class,"stui-vodlist__thumb") and contains(@href,"/vod/detail/")]'):
            match = re.search(r"/id/(\d+)", node.get("href", ""))
            if not match or match.group(1) in seen:
                continue
            seen.add(match.group(1))
            items.append({
                "vod_id": match.group(1),
                "vod_name": node.get("title", "").strip(),
                "vod_pic": urljoin(self.host, node.get("data-original") or node.get("data-src") or node.get("src") or ""),
                "vod_remarks": "".join(node.xpath('.//span[contains(@class,"pic-text")]/b/text()')).strip(),
            })
        page_text = "".join(tree.xpath('//li[contains(@class,"num")]/a/text()'))
        match = re.search(r"/\s*(\d+)", page_text)
        return items, int(match.group(1)) if match else 1

    def homeContent(self, filter):
        data = self._get({"ac": "list"})
        classes = [
            {"type_id": str(item.get("type_id", "")), "type_name": item.get("type_name", "")}
            for item in data.get("class", [])
            if item.get("type_id") and item.get("type_name")
        ]
        return {"class": classes, "list": [], "filters": self._filters(classes)}

    def categoryContent(self, tid, pg, filter, extend):
        items, pagecount = self._parse_category(self._category_url(tid, pg, extend))
        return {
            "page": int(pg),
            "pagecount": pagecount,
            "limit": len(items),
            "total": pagecount * len(items),
            "list": items,
        }

    def detailContent(self, ids):
        data = self._get({"ac": "detail", "ids": ",".join(str(vod_id) for vod_id in ids)})
        result = []
        for vod in data.get("list", []):
            result.append({
                "vod_id": str(vod.get("vod_id", "")),
                "vod_name": vod.get("vod_name", ""),
                "vod_pic": vod.get("vod_pic", ""),
                "type_name": vod.get("type_name", ""),
                "vod_year": str(vod.get("vod_year", "")),
                "vod_area": vod.get("vod_area", ""),
                "vod_remarks": vod.get("vod_remarks", ""),
                "vod_actor": vod.get("vod_actor", ""),
                "vod_director": vod.get("vod_director", ""),
                "vod_content": self._text(vod.get("vod_content", "")),
                "vod_play_from": vod.get("vod_play_from", ""),
                "vod_play_url": vod.get("vod_play_url", ""),
            })
        return {"list": result}

    def searchContent(self, key, quick, pg="1"):
        data = self._get({"ac": "detail", "wd": key, "pg": pg})
        return {
            "page": int(data.get("page") or pg),
            "pagecount": int(data.get("pagecount") or 1),
            "limit": int(data.get("limit") or 20),
            "total": int(data.get("total") or 0),
            "list": [self._item(vod) for vod in data.get("list", [])],
        }

    def playerContent(self, flag, id, vipFlags):
        url = id.strip()
        direct = re.search(r"\.(?:m3u8|mp4|flv|mp3)(?:\?|$)", url, re.I) is not None
        return {"parse": 0 if direct else 1, "url": url, "header": self.headers}
