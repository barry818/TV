#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wbbb1.com 爬虫 - TVBox/影视仓 Spider 插件
支持分类浏览、筛选（类型/地区/语言/年份/字母）、搜索、详情获取、播放链接解析
选集正序排列，海报封面补充
"""

import re
import json
import logging
import urllib.parse
import os
import sys
import time
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from base.spider import Spider as BaseSpider
except ImportError:
    BaseSpider = object

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Spider(BaseSpider):
    """wbbb1.com（歪比巴卜）爬虫"""

    BASE_URL = "https://wbbb1.com"

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://wbbb1.com/",
    }

    # 解析接口域名（从 /static/player/parse.js 获取）
    PARSE_HOST = "https://xn--qvr2v.850088.xyz"

    # 分类映射 - 使用show路径（有完整分页和更多内容）
    CATEGORY_MAP = {
        "1": {"name": "电影", "url": "/show/1-----------.html"},
        "2": {"name": "剧集", "url": "/show/2-----------.html"},
        "3": {"name": "动漫", "url": "/show/3-----------.html"},
        "4": {"name": "综艺", "url": "/show/4-----------.html"},
    }

    # 播放源名称映射（从 /static/js/playerconfig.js 获取）
    # 键: 播放器代码, 值: 显示名称
    PLAYER_MAP = {
        "abc": "推荐",
        "wbbf": "蓝光4K",
        "wbba": "蓝光A",
        "wbbc": "蓝光C",
        "wbbd": "蓝光D",
        "wbbb": "蓝光B",
        "wbbe": "蓝光E",
        "bfzym3u8": "BF有广",
        "lzm3u8": "LZ有广",
    }

    # 反向映射：显示名称 -> 播放器代码（用于补全缺失线路）
    PLAYER_MAP_REVERSE = {v: k for k, v in PLAYER_MAP.items()}

    def __init__(self):
        try:
            super().__init__()
        except Exception:
            pass
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update(self.HEADERS)
        # 连接池优化：复用TCP连接，减少握手开销
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=20, max_retries=Retry(total=1, backoff_factor=0.3))
        self.session.mount('https://', adapter)
        self.session.mount('http://', adapter)
        # 简单缓存：避免短时间内重复请求同一URL
        self._cache = {}
        self._cache_ttl = 300  # 5分钟缓存
        self._init_session()

    def _init_session(self):
        """初始化会话：先访问首页获取Cookie，后续请求不会返回520"""
        try:
            self.session.get(f"{self.BASE_URL}/", timeout=10)
        except Exception:
            pass

    def init(self, extend):
        pass

    def getName(self):
        return "歪比巴卜影视"

    def _parse_ext(self, ext):
        """解析ext参数，兼容dict和JSON字符串"""
        if not ext:
            return {}
        if isinstance(ext, dict):
            return ext
        if isinstance(ext, str):
            try:
                return json.loads(ext)
            except Exception:
                return {}
        return {}

    def _get(self, url, use_cache=True):
        """带缓存的GET请求
        缓存详情页和分类页，播放页不缓存（内容会变）
        """
        if use_cache:
            cached = self._cache.get(url)
            if cached and (time.time() - cached[0] < self._cache_ttl):
                return cached[1]
        try:
            resp = self.session.get(url, timeout=15)
            resp.encoding = "utf-8"
            if use_cache and resp.status_code == 200:
                self._cache[url] = (time.time(), resp)
            return resp
        except Exception as e:
            logger.error(f"请求失败 {url}: {e}")
            return None

    # ==================== 首页 ====================
    def homeContent(self, filter=False):
        try:
            url = f"{self.BASE_URL}/"
            resp = self._get(url)
            if not resp:
                return {}

            classes = [{"type_id": cid, "type_name": info["name"]}
                       for cid, info in self.CATEGORY_MAP.items()]

            home_list = self._parse_video_list(resp.text)

            return {
                "class": classes,
                "filters": self._get_filters(),
                "list": home_list,
            }
        except Exception as e:
            logger.error(f"获取首页失败: {e}")
            return {}

    def homeVideoContent(self):
        home = self.homeContent()
        return {"list": home.get("list", [])}

    # ==================== 筛选 ====================
    def _get_filters(self):
        """筛选配置：类型/地区/语言/年份/字母
        URL格式: /show/{分类ID}-{地区}-{类型}-{语言}-{年份}-{字母}------.html
        筛选value使用URL编码的中文
        """
        filters = {}

        type_values_movie = [
            {"n": "全部", "v": ""},
            {"n": "喜剧", "v": "喜剧"}, {"n": "爱情", "v": "爱情"},
            {"n": "恐怖", "v": "恐怖"}, {"n": "动作", "v": "动作"},
            {"n": "科幻", "v": "科幻"}, {"n": "剧情", "v": "剧情"},
            {"n": "战争", "v": "战争"}, {"n": "警匪", "v": "警匪"},
            {"n": "犯罪", "v": "犯罪"}, {"n": "动画", "v": "动画"},
            {"n": "奇幻", "v": "奇幻"}, {"n": "武侠", "v": "武侠"},
            {"n": "冒险", "v": "冒险"},
        ]

        type_values_series = [
            {"n": "全部", "v": ""},
            {"n": "古装", "v": "古装"}, {"n": "战争", "v": "战争"},
            {"n": "青春偶像", "v": "青春偶像"}, {"n": "喜剧", "v": "喜剧"},
            {"n": "家庭", "v": "家庭"}, {"n": "犯罪", "v": "犯罪"},
            {"n": "动作", "v": "动作"}, {"n": "奇幻", "v": "奇幻"},
            {"n": "剧情", "v": "剧情"}, {"n": "历史", "v": "历史"},
            {"n": "网剧", "v": "网剧"},
        ]

        type_values_anime = [
            {"n": "全部", "v": ""},
            {"n": "情感", "v": "情感"}, {"n": "科幻", "v": "科幻"},
            {"n": "热血", "v": "热血"}, {"n": "推理", "v": "推理"},
            {"n": "冒险", "v": "冒险"}, {"n": "搞笑", "v": "搞笑"},
            {"n": "机战", "v": "机战"}, {"n": "校园", "v": "校园"},
            {"n": "动作", "v": "动作"}, {"n": "运动", "v": "运动"},
            {"n": "战争", "v": "战争"}, {"n": "少女", "v": "少女"},
            {"n": "社会", "v": "社会"}, {"n": "原创", "v": "原创"},
        ]

        type_values_variety = [
            {"n": "全部", "v": ""},
            {"n": "选秀", "v": "选秀"}, {"n": "情感", "v": "情感"},
            {"n": "访谈", "v": "访谈"}, {"n": "播报", "v": "播报"},
            {"n": "旅游", "v": "旅游"}, {"n": "音乐", "v": "音乐"},
            {"n": "美食", "v": "美食"}, {"n": "纪实", "v": "纪实"},
            {"n": "曲艺", "v": "曲艺"}, {"n": "生活", "v": "生活"},
            {"n": "游戏", "v": "游戏"}, {"n": "真人秀", "v": "真人秀"},
        ]

        area_values = [
            {"n": "全部", "v": ""},
            {"n": "大陆", "v": "大陆"}, {"n": "港台", "v": "港台"},
            {"n": "美国", "v": "美国"}, {"n": "韩国", "v": "韩国"},
            {"n": "日本", "v": "日本"}, {"n": "泰国", "v": "泰国"},
            {"n": "印度", "v": "印度"}, {"n": "法国", "v": "法国"},
            {"n": "英国", "v": "英国"}, {"n": "其他", "v": "其他"},
        ]

        lang_values = [
            {"n": "全部", "v": ""},
            {"n": "国语", "v": "国语"}, {"n": "粤语", "v": "粤语"},
            {"n": "韩语", "v": "韩语"}, {"n": "日语", "v": "日语"},
            {"n": "英语", "v": "英语"}, {"n": "泰语", "v": "泰语"},
            {"n": "其它", "v": "其它"},
        ]

        year_values = [{"n": "全部", "v": ""}]
        for y in range(2026, 2009, -1):
            year_values.append({"n": str(y), "v": str(y)})
        year_values.append({"n": "更早", "v": "2009"})

        letter_values = [{"n": "全部", "v": ""}]
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            letter_values.append({"n": letter, "v": letter})
        letter_values.append({"n": "0-9", "v": "0-9"})

        type_map = {
            "1": type_values_movie,
            "2": type_values_series,
            "3": type_values_anime,
            "4": type_values_variety,
        }

        for cate_id in self.CATEGORY_MAP:
            tv = type_map.get(cate_id, type_values_movie)
            filters[cate_id] = [
                {"key": "area", "name": "地区", "value": area_values},
                {"key": "type", "name": "类型", "value": tv},
                {"key": "lang", "name": "语言", "value": lang_values},
                {"key": "year", "name": "年份", "value": year_values},
                {"key": "letter", "name": "字母", "value": letter_values},
            ]
        return filters

    # ==================== 分类 ====================
    def categoryContent(self, tid, pg, filter, ext):
        try:
            page = int(pg) if pg else 1
            type_id = str(tid)

            cate_info = self.CATEGORY_MAP.get(type_id)
            if not cate_info:
                return {"list": [], "page": page, "pagecount": 1, "limit": 20, "total": 0}

            ext_dict = self._parse_ext(ext)
            area_filter = ext_dict.get('area', '')
            type_filter = ext_dict.get('type', '')
            lang_filter = ext_dict.get('lang', '')
            year_filter = ext_dict.get('year', '')
            letter_filter = ext_dict.get('letter', '')

            # show路径12段格式（含catid共12段，第9段是页码）:
            # [catid, area, by, class, lang, letter, x, x, page, x, x, year]
            # 索引:   0     1    2   3      4     5      6  7    8    9  10   11
            area_enc = urllib.parse.quote(area_filter) if area_filter else ''
            type_enc = urllib.parse.quote(type_filter) if type_filter else ''
            lang_enc = urllib.parse.quote(lang_filter) if lang_filter else ''
            year_val = year_filter or ''
            letter_val = letter_filter or ''
            page_val = str(page) if page > 1 else ''

            segs = [
                type_id,   # 0: catid
                area_enc,  # 1: area
                '',        # 2: by
                type_enc,  # 3: class(type)
                lang_enc,  # 4: lang
                letter_val,# 5: letter
                '',        # 6: x
                '',        # 7: x
                page_val,  # 8: page (第9段)
                '',        # 9: x
                '',        # 10: x
                year_val,  # 11: year
            ]
            path = '-'.join(segs)
            url = f"{self.BASE_URL}/show/{path}.html"

            resp = self._get(url)
            if not resp:
                return {"list": [], "page": page, "pagecount": 1, "limit": 20, "total": 0}

            videos = self._parse_video_list(resp.text)
            pagecount = self._parse_total_pages(resp.text)
            total = self._parse_total_count(resp.text)

            return {
                "list": videos,
                "page": page,
                "pagecount": pagecount,
                "limit": 72,
                "total": total if total else len(videos) * pagecount,
            }
        except Exception as e:
            logger.error(f"获取分类内容失败: {e}")
            return {"list": [], "page": 1, "pagecount": 1, "limit": 20, "total": 0}

    def _parse_total_pages(self, html):
        """解析总页数 - 从page-number和尾页链接提取"""
        soup = BeautifulSoup(html, 'html.parser')

        # 方法1: 从page-number类获取最大页码
        page_numbers = soup.find_all('a', class_=re.compile(r'page-number'))
        max_page = 1
        for a in page_numbers:
            text = a.get_text(strip=True)
            if re.match(r'^\d+$', text):
                p = int(text)
                if p > max_page:
                    max_page = p
        if max_page > 1:
            return max_page

        # 方法2: 从尾页链接获取
        patterns = [
            r'/show/\d+[^"]*--------(\d+)---\.html["\'][^>]*>尾页',
            r'/show/\d+[^"]*--------(\d+)---\.html["\'][^>]*>末页',
            r'/show/\d+[^"]*--------(\d+)---\.html["\'][^>]*>最后一页',
            r'href="/show/\d+[^"]*--------(\d+)---\.html"',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, html)
            if matches:
                try:
                    return max(int(m) for m in matches)
                except (ValueError, IndexError):
                    pass

        return 1

    def _parse_total_count(self, html):
        """解析总数量"""
        patterns = [
            r'共\s*(\d+)\s*[条部个]',
            r'总数[：:]\s*(\d+)',
            r'total[：:]\s*(\d+)',
            r'count[：:]\s*(\d+)',
            r'(\d+)\s*条数据',
        ]
        for pattern in patterns:
            m = re.search(pattern, html)
            if m:
                try:
                    return int(m.group(1))
                except ValueError:
                    pass
        return 0

    def _parse_video_list(self, html):
        """解析视频列表
        卡片: a.module-poster-item > href="/detail/ID.html", title, img[data-original], div.module-item-note
        """
        videos = []
        soup = BeautifulSoup(html, 'html.parser')

        items = soup.find_all('a', class_=re.compile(r'module-poster-item'))
        if not items:
            # 回退：查找所有包含 /detail/ 的链接
            items = soup.find_all('a', href=re.compile(r'/detail/\d+\.html'))

        seen_ids = set()
        for item in items:
            href = item.get('href', '')
            vid_match = re.search(r'/detail/(\d+)\.html', href)
            if not vid_match:
                continue
            vid_id = vid_match.group(1)
            if vid_id in seen_ids:
                continue
            seen_ids.add(vid_id)

            title = item.get('title', '')
            if not title:
                img_tag = item.find('img')
                if img_tag:
                    title = img_tag.get('alt', '')

            poster = ''
            img_tag = item.find('img')
            if img_tag:
                poster = img_tag.get('data-original', '') or img_tag.get('src', '')
                # 过滤加载占位图
                if poster and ('load.gif' in poster or 'errorpic' in poster):
                    poster = img_tag.get('data-original', '') or ''

            remarks = ''
            note_tag = item.find('div', class_=re.compile(r'module-item-note'))
            if note_tag:
                remarks = note_tag.get_text(strip=True)

            if title:
                videos.append({
                    "vod_id": vid_id,
                    "vod_name": title,
                    "vod_pic": poster,
                    "vod_remarks": remarks,
                })
        return videos

    # ==================== 详情 ====================
    def detailContent(self, ids):
        try:
            vod_id = ids[0] if isinstance(ids, list) else str(ids)
            url = f"{self.BASE_URL}/detail/{vod_id}.html"
            resp = self._get(url)
            if not resp:
                return {"list": []}

            html = resp.text
            soup = BeautifulSoup(html, 'html.parser')

            # 标题
            title = ''
            h1 = soup.find('h1')
            if h1:
                title = h1.get_text(strip=True)

            # 海报
            poster = ''
            info_cover = soup.find('div', class_=re.compile(r'module-item-cover|module-poster-bg'))
            if info_cover:
                img = info_cover.find('img')
                if img:
                    poster = img.get('data-original', '') or img.get('src', '')
                    if 'load.gif' in poster or 'errorpic' in poster:
                        poster = img.get('data-original', '')

            # 年份/地区/类型 - 从 module-info-tag-link 提取
            # URL格式: /show/{catid}-{area}-{by}-{class}-{lang}-{letter}-...-{year}.html
            # 去掉catid后segments: [0]=area, [2]=class(类型), [4]=lang, [5]=letter, [10]=year
            year = area = type_name = ''
            tag_links = soup.find_all('div', class_=re.compile(r'module-info-tag-link'))
            for tag in tag_links:
                a_tag = tag.find('a')
                if not a_tag:
                    continue
                href = urllib.parse.unquote(a_tag.get('href', ''))
                text = a_tag.get_text(strip=True)
                m = re.match(r'/show/\d+-(.+?)\.html', href)
                if m:
                    segments = m.group(1).split('-')
                    if len(segments) >= 11:
                        if segments[0]:  # area at position 0
                            area = text
                        elif segments[2]:  # type at position 2
                            type_name = text
                        elif segments[10]:  # year at position 10
                            year = text

            # 如果没从tag-link提取到年份，尝试从正则提取
            if not year:
                year_m = re.search(r'-----------(\d{4})', html)
                if year_m:
                    year = year_m.group(1)

            # 导演/主演/备注等 - 从 module-info-item 提取
            actor = director = remarks = content = ''
            info_items = soup.find_all('div', class_=re.compile(r'module-info-item'))
            for item in info_items:
                title_tag = item.find('span', class_=re.compile(r'module-info-item-title'))
                content_tag = item.find('div', class_=re.compile(r'module-info-item-content'))
                if not title_tag:
                    continue
                label = title_tag.get_text(strip=True)
                if not content_tag:
                    continue
                value = content_tag.get_text(strip=True)
                value = re.sub(r'/', '', value).strip()

                if label.startswith('导演'):
                    director = value
                elif label.startswith('主演'):
                    actor = value
                elif label.startswith('备注'):
                    remarks = value
                elif label.startswith('更新'):
                    remarks = value

            # 简介
            desc_tag = soup.find('div', class_=re.compile(r'module-info-introduction-content'))
            if desc_tag:
                p = desc_tag.find('p')
                if p:
                    content = p.get_text(strip=True)

            # 播放源和集数（正序）
            play_from_list, play_url_list = self._parse_play_sources(html, vod_id)

            vod_item = {
                "vod_id": vod_id,
                "vod_name": title,
                "vod_pic": poster,
                "type_name": type_name,
                "vod_year": year,
                "vod_area": area,
                "vod_remarks": remarks,
                "vod_actor": actor,
                "vod_director": director,
                "vod_content": content,
                "vod_play_from": '$$$'.join(play_from_list),
                "vod_play_url": '$$$'.join(play_url_list),
            }
            return {"list": [vod_item]}
        except Exception as e:
            logger.error(f"获取详情失败: {e}")
            return {"list": []}

    def _parse_play_sources(self, html, vod_id):
        """解析播放源和集数 - 正序排列
        策略：tab-item(data-dropdown-value)与module-list(sort-list)按索引一一对应
        data-dropdown-value直接就是显示名称（如"蓝光4K"），无需请求播放页
        """
        play_from_list = []
        play_url_list = []

        soup = BeautifulSoup(html, 'html.parser')

        # 获取tab-item中的线路名称（已按显示顺序排列）
        source_tabs = soup.find_all('div', class_=re.compile(r'tab-item'), attrs={'data-dropdown-value': True})
        tab_names = [tab.get('data-dropdown-value', '') for tab in source_tabs]

        # 获取module-list（与tab-item一一对应）
        module_lists = soup.find_all('div', class_=re.compile(r'module-list\s+sort-list'))

        # 按索引匹配tab名称和集数列表
        for idx, ml in enumerate(module_lists):
            links = ml.find_all('a', href=re.compile(r'/vplay/'))
            if not links:
                continue

            seen_nid = set()
            episodes = {}

            for a in links:
                href = a.get('href', '')
                m = re.search(r'/vplay/(\d+)-(\d+)-(\d+)\.html', href)
                if not m:
                    continue
                nid = int(m.group(3))

                if nid in seen_nid:
                    continue
                seen_nid.add(nid)

                ep_name = a.get_text(strip=True) or f"第{nid}集"
                play_url = f"{self.BASE_URL}{href}"
                episodes[nid] = (ep_name, play_url)

            if episodes:
                from_name = tab_names[idx] if idx < len(tab_names) else f"线路{idx + 1}"
                play_from_list.append(from_name)
                urls = [f"{name}${u}" for nid, (name, u) in sorted(episodes.items())]
                play_url_list.append('#'.join(urls))

        # 如果没解析到任何播放源，使用兜底方法
        if not play_from_list:
            return self._parse_play_sources_fallback(html, vod_id)

        return play_from_list, play_url_list

    def _parse_play_sources_fallback(self, html, vod_id):
        """兜底：从所有 vplay 链接按 sid 分组"""
        play_from_list = []
        play_url_list = []
        links = re.findall(r'/vplay/(\d+)-(\d+)-(\d+)\.html', html)
        sources = {}
        for link in links:
            vid, sid, nid = int(link[0]), int(link[1]), int(link[2])
            sources.setdefault(sid, {})[nid] = link

        for sid in sorted(sources.keys()):
            eps = sources[sid]
            episodes = sorted(eps.items())
            from_name = self.PLAYER_MAP.get(str(sid), f"线路{sid}")
            play_from_list.append(from_name)
            urls = [f"第{nid}集${self.BASE_URL}/vplay/{vid}-{sid}-{nid}.html" for nid, (vid, _, _) in episodes]
            play_url_list.append('#'.join(urls))
        return play_from_list, play_url_list

    # ==================== 播放 ====================
    def playerContent(self, flag, id, vipFlags):
        """解析播放页获取播放链接
        策略：
        1. 如果player_aaaa.url是直接的m3u8链接，返回parse=0直接播放
        2. 如果是加密URL（蓝光系列），返回解析接口URL + parse=1
           解析接口页面(https://xn--qvr2v.850088.xyz/player/?url=xxx)包含danmaya.js
           会自动执行CryptoJS AES解密获取m3u8并播放
        3. 同时传递next和title参数，与原站parse.js逻辑一致
        """
        try:
            url = id
            if url.startswith('/'):
                url = self.BASE_URL + url
            elif not url.startswith('http'):
                url = self.BASE_URL + '/vplay/' + url

            resp = self._get(url, use_cache=False)
            if not resp:
                return {}

            html = resp.text

            # 从player_aaaa提取URL
            player_m = re.search(r'player_aaaa\s*=\s*({[^<]+})', html)
            if player_m:
                try:
                    pdata = json.loads(player_m.group(1))
                    play_url = pdata.get('url', '')
                    encrypt = pdata.get('encrypt', 0)
                    play_from = pdata.get('from', '')
                    link_next = pdata.get('link_next', '')
                    title = pdata.get('title', '')

                    if encrypt == 1:
                        play_url = urllib.parse.unquote(play_url)
                    elif encrypt == 2:
                        import base64
                        try:
                            padded = play_url + '=' * (4 - len(play_url) % 4)
                            play_url = urllib.parse.unquote(base64.urlsafe_b64decode(padded).decode('utf-8'))
                        except Exception:
                            pass

                    # 如果是直接的m3u8链接，直接返回parse=0
                    if play_url and '.m3u8' in play_url and play_url.startswith('http'):
                        return {
                            "parse": 0,
                            "playUrl": "",
                            "url": play_url,
                            "header": json.dumps({
                                "User-Agent": self.HEADERS["User-Agent"],
                                "Referer": self.BASE_URL + "/",
                            }),
                        }

                    # 如果是加密URL（蓝光系列），构建解析接口URL
                    # 与原站parse.js的iframe src格式一致：
                    # https://xn--qvr2v.850088.xyz/player/?url={加密URL}&next=//域名+link_next&title=标题
                    if play_url:
                        next_param = ''
                        if link_next:
                            next_param = f'&next=//{self.BASE_URL.replace("https://", "")}{link_next}'
                        title_param = f'&title={urllib.parse.quote(title)}' if title else ''

                        parse_url = f"{self.PARSE_HOST}/player/?url={play_url}{next_param}{title_param}"

                        return {
                            "parse": 1,
                            "playUrl": "",
                            "url": parse_url,
                            "header": json.dumps({
                                "User-Agent": self.HEADERS["User-Agent"],
                                "Referer": self.BASE_URL + "/",
                            }),
                        }
                except Exception as e:
                    logger.error(f"解析player_aaaa失败: {e}")

            # 兜底：直接匹配m3u8链接
            m = re.search(r'(https?://[^"\'\\s]+\.m3u8[^"\'\\s]*)', html)
            if m:
                return {
                    "parse": 0,
                    "playUrl": "",
                    "url": m.group(1),
                    "header": json.dumps({
                        "User-Agent": self.HEADERS["User-Agent"],
                        "Referer": self.BASE_URL + "/",
                    }),
                }

            # 最终兜底：返回解析接口URL
            return {
                "parse": 1,
                "playUrl": "",
                "url": url,
                "header": json.dumps({
                    "User-Agent": self.HEADERS["User-Agent"],
                    "Referer": self.BASE_URL + "/",
                }),
            }
        except Exception as e:
            logger.error(f"解析播放失败: {e}")
            return {}

    # ==================== 搜索 ====================
    def searchContent(self, key, quick, pg="1"):
        """搜索内容"""
        try:
            page = int(pg) if pg else 1
            encoded_key = urllib.parse.quote(key)

            # HTML搜索页
            url = f"{self.BASE_URL}/search/-------------.html?wd={encoded_key}"
            if page > 1:
                url += f"&page={page}"

            resp = self._get(url)
            if not resp:
                return {"list": [], "page": page, "pagecount": 1, "limit": 20, "total": 0}

            if any(k in resp.text for k in ['验证码', '人机验证', '安全验证', 'just_a_test']):
                logger.warning("搜索被安全验证拦截")
                return {"list": [], "page": page, "pagecount": 1, "limit": 20, "total": 0}

            videos = self._parse_video_list(resp.text)
            pagecount = self._parse_total_pages(resp.text)

            return {
                "list": videos,
                "page": page,
                "pagecount": pagecount if pagecount > 1 else 1,
                "limit": 72,
                "total": len(videos) * pagecount if pagecount > 1 else len(videos),
            }
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return {"list": [], "page": 1, "pagecount": 1, "limit": 20, "total": 0}


if __name__ == "__main__":
    spider = Spider()
    # 基础自测
    print("=== 首页 ===")
    home = spider.homeContent()
    print("分类:", [c["type_name"] for c in home.get("class", [])])
    print("首页视频数:", len(home.get("list", [])))
    if home.get("list"):
        print("示例:", home["list"][0])

    print("\n=== 分类(电影) ===")
    cate = spider.categoryContent("1", 1, 0, {})
    print("视频数:", len(cate.get("list", [])), "总页数:", cate.get("pagecount"))
    if cate.get("list"):
        print("示例:", cate["list"][0])

    print("\n=== 筛选(电影-动作-2026) ===")
    filt = spider.categoryContent("1", 1, 1, {"type": "动作", "year": "2026"})
    print("视频数:", len(filt.get("list", [])))
    if filt.get("list"):
        print("示例:", filt["list"][0])

    if cate.get("list"):
        vid = cate["list"][0]["vod_id"]
        print(f"\n=== 详情({vid}) ===")
        detail = spider.detailContent([vid])
        if detail.get("list"):
            d = detail["list"][0]
            print("片名:", d["vod_name"], "| 年份:", d["vod_year"], "| 地区:", d["vod_area"])
            print("导演:", d["vod_director"][:40])
            print("播放源:", d["vod_play_from"][:80])
            print("播放URL:", d["vod_play_url"][:100])

        print(f"\n=== 播放({vid}) ===")
        play = spider.playerContent("蓝光C", f"https://wbbb1.com/vplay/{vid}-6-1.html", "")
        print("播放:", play.get("url", "")[:100])

    print("\n=== 搜索(变形金刚) ===")
    res = spider.searchContent("变形金刚", False, "1")
    print("搜索结果数:", len(res.get("list", [])))
    if res.get("list"):
        print("示例:", res["list"][0])
