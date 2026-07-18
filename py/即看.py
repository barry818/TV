#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
jkan.app 爬虫 - TVBox/影视仓 Spider 插件
支持分类浏览、筛选、搜索、详情获取、播放链接解析
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
    """jkan.app 爬虫"""

    BASE_URL = "https://www.jkan.app"

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://www.jkan.app/",
    }

    CATEGORY_MAP = {
        "1": {"name": "电影", "url": "/tv/1.html"},
        "2": {"name": "电视剧", "url": "/tv/2.html"},
        "3": {"name": "综艺", "url": "/tv/3.html"},
        "4": {"name": "动漫", "url": "/tv/4.html"},
        "58": {"name": "儿童", "url": "/tv/58.html"},
        "53": {"name": "短剧", "url": "/tv/53.html"},
        "6": {"name": "动作片", "url": "/tv/6.html"},
        "7": {"name": "喜剧片", "url": "/tv/7.html"},
        "8": {"name": "爱情片", "url": "/tv/8.html"},
        "9": {"name": "科幻片", "url": "/tv/9.html"},
        "11": {"name": "剧情片", "url": "/tv/11.html"},
        "13": {"name": "国产剧", "url": "/tv/13.html"},
        "14": {"name": "港台剧", "url": "/tv/14.html"},
        "15": {"name": "日韩剧", "url": "/tv/15.html"},
    }

    def __init__(self):
        try:
            super().__init__()
        except Exception:
            pass
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update(self.HEADERS)
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=20, max_retries=Retry(total=1, backoff_factor=0.3))
        self.session.mount('https://', adapter)
        self.session.mount('http://', adapter)
        self._cache = {}
        self._cache_ttl = 300
        self._last_search_time = 0
        self._search_interval = 3.0
        self._init_session()

    def _init_session(self):
        try:
            self.session.get(f"{self.BASE_URL}/", timeout=10)
        except Exception:
            pass

    def init(self, extend):
        pass

    def getName(self):
        return "JKAN影视"

    def _parse_ext(self, ext):
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

    def homeContent(self, filter=False):
        try:
            url = f"{self.BASE_URL}/"
            resp = self._get(url)
            if not resp:
                return {}

            classes = [{"type_id": cid, "type_name": info["name"]}
                       for cid, info in list(self.CATEGORY_MAP.items())[:8]]

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

    def _get_filters(self):
        filters = {}

        area_values = [
            {"n": "全部", "v": ""},
            {"n": "中国大陆", "v": "中国大陆"},
            {"n": "中国香港", "v": "中国香港"},
            {"n": "中国台湾", "v": "中国台湾"},
            {"n": "美国", "v": "美国"},
            {"n": "韩国", "v": "韩国"},
            {"n": "日本", "v": "日本"},
            {"n": "泰国", "v": "泰国"},
            {"n": "印度", "v": "印度"},
            {"n": "法国", "v": "法国"},
            {"n": "英国", "v": "英国"},
            {"n": "其他", "v": "其他"},
        ]

        type_values_movie = [
            {"n": "全部", "v": ""},
            {"n": "动作", "v": "动作"}, {"n": "喜剧", "v": "喜剧"},
            {"n": "爱情", "v": "爱情"}, {"n": "科幻", "v": "科幻"},
            {"n": "剧情", "v": "剧情"}, {"n": "悬疑", "v": "悬疑"},
            {"n": "惊悚", "v": "惊悚"}, {"n": "恐怖", "v": "恐怖"},
            {"n": "犯罪", "v": "犯罪"}, {"n": "冒险", "v": "冒险"},
            {"n": "奇幻", "v": "奇幻"}, {"n": "战争", "v": "战争"},
        ]

        type_values_series = [
            {"n": "全部", "v": ""},
            {"n": "剧情", "v": "剧情"}, {"n": "古装", "v": "古装"},
            {"n": "战争", "v": "战争"}, {"n": "喜剧", "v": "喜剧"},
            {"n": "家庭", "v": "家庭"}, {"n": "犯罪", "v": "犯罪"},
            {"n": "动作", "v": "动作"}, {"n": "奇幻", "v": "奇幻"},
        ]

        type_values_anime = [
            {"n": "全部", "v": ""},
            {"n": "情感", "v": "情感"}, {"n": "科幻", "v": "科幻"},
            {"n": "热血", "v": "热血"}, {"n": "推理", "v": "推理"},
            {"n": "冒险", "v": "冒险"}, {"n": "搞笑", "v": "搞笑"},
            {"n": "校园", "v": "校园"}, {"n": "动作", "v": "动作"},
        ]

        type_values_variety = [
            {"n": "全部", "v": ""},
            {"n": "选秀", "v": "选秀"}, {"n": "情感", "v": "情感"},
            {"n": "访谈", "v": "访谈"}, {"n": "真人秀", "v": "真人秀"},
        ]

        year_values = [{"n": "全部", "v": ""}]
        for y in range(2026, 2009, -1):
            year_values.append({"n": str(y), "v": str(y)})
        year_values.append({"n": "更早", "v": "2009"})

        lang_values = [
            {"n": "全部", "v": ""},
            {"n": "汉语普通话", "v": "汉语普通话"},
            {"n": "粤语", "v": "粤语"},
            {"n": "韩语", "v": "韩语"},
            {"n": "日语", "v": "日语"},
            {"n": "英语", "v": "英语"},
        ]

        type_map = {
            "1": type_values_movie,
            "2": type_values_series,
            "3": type_values_variety,
            "4": type_values_anime,
            "58": type_values_anime,
            "53": type_values_series,
            "6": type_values_movie,
            "7": type_values_movie,
            "8": type_values_movie,
            "9": type_values_movie,
            "11": type_values_movie,
            "13": type_values_series,
            "14": type_values_series,
            "15": type_values_series,
        }

        for cate_id in self.CATEGORY_MAP:
            tv = type_map.get(cate_id, type_values_movie)
            filters[cate_id] = [
                {"key": "area", "name": "地区", "value": area_values},
                {"key": "type", "name": "类型", "value": tv},
                {"key": "lang", "name": "语言", "value": lang_values},
                {"key": "year", "name": "年份", "value": year_values},
            ]
        return filters

    def categoryContent(self, tid, pg, filter, ext):
        try:
            page = int(pg) if pg else 1
            type_id = str(tid)

            if type_id not in self.CATEGORY_MAP:
                return {"list": [], "page": page, "pagecount": 1, "limit": 20, "total": 0}

            ext_dict = self._parse_ext(ext)
            area_filter = ext_dict.get('area', '')
            type_filter = ext_dict.get('type', '')
            lang_filter = ext_dict.get('lang', '')
            year_filter = ext_dict.get('year', '')

            area_enc = urllib.parse.quote(area_filter) if area_filter else ''
            type_enc = urllib.parse.quote(type_filter) if type_filter else ''
            lang_enc = urllib.parse.quote(lang_filter) if lang_filter else ''
            year_val = year_filter or ''

            segs = [type_id, area_enc, '', type_enc, lang_enc, '', '', '', str(page), '', '', year_val]
            path = '-'.join(segs)
            url = f"{self.BASE_URL}/show/{path}.html"

            resp = self._get(url)
            if not resp:
                return {"list": [], "page": page, "pagecount": 1, "limit": 20, "total": 0}

            videos = self._parse_video_list(resp.text)
            pagecount = self._parse_total_pages(resp.text)
            total = self._parse_total_count(resp.text)

            if not total and pagecount > 0:
                total = pagecount * 60

            return {
                "list": videos,
                "page": page,
                "pagecount": pagecount if pagecount > 1 else 1,
                "limit": 60,
                "total": total,
            }
        except Exception as e:
            logger.error(f"获取分类内容失败: {e}")
            return {"list": [], "page": 1, "pagecount": 1, "limit": 20, "total": 0}

    def _parse_total_pages(self, html):
        tip_m = re.search(r'共\s*(\d+)\s*页', html)
        if tip_m:
            return int(tip_m.group(1))
        tail_match = re.search(r'/show/\d+.*?--------(\d+)---', html)
        if tail_match:
            return int(tail_match.group(1))
        tail_match2 = re.search(r'/search/[^"]*?----------(\d+)---', html)
        if tail_match2:
            return int(tail_match2.group(1))
        return 1

    def _parse_total_count(self, html):
        count_m = re.search(r'共有[*]?(\d+)[*]?个影片', html)
        if count_m:
            return int(count_m.group(1))
        return 0

    def _parse_video_list(self, html):
        videos = []
        soup = BeautifulSoup(html, 'html.parser')

        items = soup.find_all('li', class_=re.compile(r'vodlist_item'))
        
        if not items:
            all_links = soup.find_all('a', href=re.compile(r'/video/\d+\.html'))
            seen_ids = set()
            for a in all_links:
                href = a.get('href', '')
                vid_match = re.search(r'/video/(\d+)\.html', href)
                if not vid_match:
                    continue
                vid_id = vid_match.group(1)
                if vid_id in seen_ids:
                    continue
                
                card = a
                for _ in range(3):
                    parent = card.parent
                    if parent and len(parent.find_all('a', href=re.compile(r'/video/'))) <= 2:
                        card = parent
                    else:
                        break
                
                seen_ids.add(vid_id)
                
                title = a.get('title', '')
                if not title:
                    title = a.get_text(strip=True)
                
                if '在线观看' in title:
                    title = re.sub(r'[-]*\s*(?:免费)?在线观看.*$', '', title).strip()
                
                poster = self._extract_poster(str(card))
                
                remarks = ''
                card_text = card.get_text(' ', strip=True)
                remarks_m = re.search(r'(\d{4}\s*\|\s*[^|]*(?:集|完结|正片|更新))', card_text)
                if remarks_m:
                    remarks = remarks_m.group(1).strip()
                else:
                    remarks_m = re.search(r'(第?\d+集|全\d+集|正片|完结|更新至\d+集|连载中|已完结)', card_text)
                    if remarks_m:
                        remarks = remarks_m.group(1)
                
                if title and len(title) > 1:
                    videos.append({
                        "vod_id": vid_id,
                        "vod_name": title,
                        "vod_pic": poster,
                        "vod_remarks": remarks,
                    })
            return videos

        for item in items:
            link = item.find('a', href=re.compile(r'/video/\d+\.html'))
            if not link:
                continue
            
            href = link.get('href', '')
            vid_match = re.search(r'/video/(\d+)\.html', href)
            if not vid_match:
                continue
            vid_id = vid_match.group(1)
            
            title = link.get('title', '')
            if not title:
                title_link = item.find('p', class_='vodlist_title')
                if title_link:
                    a = title_link.find('a')
                    if a:
                        title = a.get('title', '') or a.get_text(strip=True)
            
            if not title:
                title = link.get_text(strip=True)
            
            if '在线观看' in title:
                title = re.sub(r'[-]*\s*(?:免费)?在线观看.*$', '', title).strip()
            
            poster = ''
            thumb = item.find(class_=re.compile(r'vodlist_thumb'))
            if thumb:
                data_bg = thumb.get('data-background-image', '')
                if data_bg and data_bg.startswith('http'):
                    poster = data_bg
                
                if not poster:
                    poster = self._extract_poster(str(thumb))
            
            if not poster:
                poster = self._extract_poster(str(item))
            
            remarks = ''
            xszxj = item.find(class_=re.compile(r'xszxj'))
            if xszxj:
                remarks = xszxj.get_text(strip=True)
            
            if not remarks:
                item_text = item.get_text(' ', strip=True)
                remarks_m = re.search(r'(\d{4}\s*\|\s*[^|]*(?:集|完结|正片|更新))', item_text)
                if remarks_m:
                    remarks = remarks_m.group(1).strip()
                else:
                    remarks_m = re.search(r'(第?\d+集|全\d+集|正片|完结|更新至\d+集|连载中|已完结)', item_text)
                    if remarks_m:
                        remarks = remarks_m.group(1)
            
            if title and len(title) > 1:
                videos.append({
                    "vod_id": vid_id,
                    "vod_name": title,
                    "vod_pic": poster,
                    "vod_remarks": remarks,
                })
        
        return videos

    def _extract_poster(self, html):
        data_bg_m = re.search(r'data-background-image=["\'](https?://[^"\']+)["\']', html, re.IGNORECASE)
        if data_bg_m:
            return data_bg_m.group(1)
        
        data_src_m = re.search(r'data-(?:src|original)=["\'](https?://[^"\']+\.(?:jpg|jpeg|png|webp))["\']', html, re.IGNORECASE)
        if data_src_m:
            return data_src_m.group(1)
        
        poster_m = re.search(
            r'https?://[^\s"\'<>]*\.(?:hitv\.app|alicdn\.com|qpic\.cn|qcloud\.com|myqcloud\.com)[^\s"\'<>]*'
            r'[^\s"\'<>]+\.(?:jpg|jpeg|png|webp)',
            html, re.IGNORECASE
        )
        if poster_m:
            return poster_m.group(0)
        
        img_urls = re.findall(r'https?://[^\s"\'<>]+\.(?:jpg|jpeg|png|gif|webp)', html, re.IGNORECASE)
        for u in img_urls:
            ul = u.lower()
            if any(kw in ul for kw in ['logo', 'icon', 'douban', 'avatar', 'user', 'default']):
                continue
            if any(kw in ul for kw in ['vod', 'upload', 'cover', 'poster', 'video']):
                return u
            if len(u) > 50:
                return u
        
        return ''

    def _extract_intro(self, soup, html):
        pannels = soup.find_all('div', class_='pannel')
        for pannel in pannels:
            pannel_text = pannel.get_text(' ', strip=True)
            if '剧情介绍' not in pannel_text:
                continue
            
            first_idx = pannel_text.find('剧情介绍')
            second_idx = pannel_text.find('剧情介绍', first_idx + 4)
            
            if second_idx >= 0:
                snippet = pannel_text[second_idx:]
                snippet = re.sub(r'^剧情介绍[：:]?\s*', '', snippet)
                snippet = re.split(r'(观看全集|收起全集|豆瓣TMBD评分|||我要评分|相关推荐|更多|保存到浏览器)', snippet)[0]
                snippet = snippet.strip()
                if 'var ' not in snippet and 'function' not in snippet and '<script' not in snippet:
                    if len(snippet) > 20:
                        return snippet[:500]
            
            if first_idx >= 0:
                snippet = pannel_text[first_idx:]
                after_tabs = re.sub(r'^.*?豆瓣TMBD评分\s*', '', snippet)
                if after_tabs != snippet:
                    after_tabs = re.sub(r'^剧情介绍[：:]?\s*', '', after_tabs)
                    after_tabs = re.split(r'(观看全集|收起全集|||我要评分|相关推荐|更多)', after_tabs)[0]
                    after_tabs = after_tabs.strip()
                    if len(after_tabs) > 20 and 'var ' not in after_tabs:
                        return after_tabs[:500]

        og_desc = soup.find('meta', property='og:description')
        if og_desc:
            desc = og_desc.get('content', '')
            desc = re.sub(r'^.*?剧情介绍[：:]?\s*', '', desc)
            desc = re.sub(r'<[^>]+>', '', desc)
            desc = re.sub(r'&[a-zA-Z]+;', ' ', desc)
            desc = re.sub(r'\s+', ' ', desc).strip()
            if len(desc) > 20 and 'var ' not in desc and 'function' not in desc:
                return desc[:500]

        content_div = soup.find('div', class_=re.compile(r'content_detail'))
        if content_div:
            ps = content_div.find_all('p')
            for p in ps:
                p_text = p.get_text(strip=True)
                if len(p_text) > 50 and '看点' not in p_text[:10]:
                    return p_text[:500]

        intro_m = re.search(
            r'剧情介绍[：:]?\s*([^<]{30,500}?)(?:<br\s*/?>|</p>|</div>|<div[^>]*class="|[^>]*观看全集|[^>]*收起)',
            html
        )
        if intro_m:
            text = intro_m.group(1).strip()
            text = re.sub(r'&[a-zA-Z]+;', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            if len(text) > 20 and 'var ' not in text and 'function' not in text:
                return text[:500]
        
        return ''

    def detailContent(self, ids):
        try:
            vod_id = ids[0] if isinstance(ids, list) else str(ids)
            url = f"{self.BASE_URL}/video/{vod_id}.html"
            resp = self._get(url)
            if not resp:
                return {"list": []}

            html = resp.text
            soup = BeautifulSoup(html, 'html.parser')

            title = ''
            h1 = soup.find('h1') or soup.find('h2')
            if h1:
                title = h1.get_text(strip=True)
                for suffix in ['-电影免费在线观看', '-动漫免费在线观看', '-剧集免费在线观看', '-综艺免费在线观看', '-电视剧免费在线观看']:
                    title = title.replace(suffix, '')
            
            if not title:
                meta_title = soup.find('meta', property='og:title')
                if meta_title:
                    title = meta_title.get('content', '')

            poster = ''
            og_image = soup.find('meta', property='og:image')
            if og_image:
                poster = og_image.get('content', '')
            
            if not poster:
                content_thumb = soup.find('div', class_=re.compile(r'content_thumb'))
                if content_thumb:
                    poster = self._extract_poster(str(content_thumb))
            
            if not poster:
                poster = self._extract_poster(html)

            year = area = type_name = lang = actor = director = remarks = content = ''

            data_lis = soup.find_all('li', class_='data')
            for li in data_lis:
                li_text = li.get_text(' ', strip=True)
                li_html = str(li)
                
                if '导演' in li_text:
                    names = re.findall(r'<a[^>]*>([^<]+)</a>', li_html)
                    if names:
                        director = ','.join(names[:5])
                    else:
                        m = re.search(r'导演[：:]\s*([^\n<]+)', li_text)
                        if m:
                            director = m.group(1).strip()
                
                if '主演' in li_text:
                    names = re.findall(r'<a[^>]*>([^<]+)</a>', li_html)
                    if names:
                        actor = ','.join(names[:15])
                    else:
                        m = re.search(r'主演[：:]\s*([^\n<]+)', li_text)
                        if m:
                            actor = m.group(1).strip()
                
                if '地区' in li_text:
                    m = re.search(r'地区[：:]\s*([^\s<]+)', li_text)
                    if m:
                        area = m.group(1).strip()
                    else:
                        area_links = re.findall(r'<a[^>]*>([^<]+)</a>', li_html)
                        if area_links:
                            area = area_links[0].strip()
                
                if '上映' in li_text or '年份' in li_text:
                    m = re.search(r'(\d{4})', li_text)
                    if m:
                        year = m.group(1)
                
                if '语言' in li_text:
                    m = re.search(r'语言[：:]\s*([^\s<]+)', li_text)
                    if m:
                        lang = m.group(1).strip()
                
                type_links = re.findall(r'<a[^>]*href="/tv/\d+\.html"[^>]*>([^<]+)</a>', li_html)
                if type_links and not type_name:
                    type_name = ','.join(type_links[:3])
                
                update_m = re.search(r'(更新至第?\d+集|第?\d+集|全\d+集|正片|完结|更新至\d+[期集]|连载中|已完结)', li_text)
                if update_m and not remarks:
                    remarks = update_m.group(1)

            if not type_name:
                type_matches = re.findall(r'<a[^>]*href="/search/[^"]*"[^>]*>([^<]+)</a>', html)
                filtered = [t for t in type_matches if t and len(t) < 10 and t not in [title, area, year, lang]]
                if filtered:
                    type_name = ','.join(filtered[:4])

            if not remarks:
                data_style = soup.find(class_=re.compile(r'data_style'))
                if data_style:
                    remarks = data_style.get_text(strip=True)
            
            if not remarks:
                remarks_m = re.search(r'(更新至第?\d+[集期]|第?\d+集|全\d+集|正片|完结|连载中|已完结)', html)
                if remarks_m:
                    remarks = remarks_m.group(1)

            content = self._extract_intro(soup, html)

            if not content:
                og_desc = soup.find('meta', property='og:description')
                if og_desc:
                    desc = og_desc.get('content', '')
                    desc = re.sub(r'^.*?剧情介绍[：:]?\s*', '', desc)
                    if len(desc) > 20:
                        content = desc

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
        play_from_list = []
        play_url_list = []

        soup = BeautifulSoup(html, 'html.parser')
        source_tabs = soup.find_all('a', href=re.compile(r'/play/\d+-\d+-\d+\.html'))

        sources = {}
        for tab in source_tabs:
            href = tab.get('href', '')
            m = re.search(r'/play/\d+-(\d+)-(\d+)\.html', href)
            if not m:
                continue

            sid = int(m.group(1))
            epid = int(m.group(2))
            ep_name = tab.get_text(strip=True)

            if not ep_name or '立即播放' in ep_name or 'APP' in ep_name:
                continue

            if sid not in sources:
                sources[sid] = {}

            if epid not in sources[sid]:
                sources[sid][epid] = (ep_name, href)

        source_names = {}
        name_matches = re.findall(r'(1080\s*\w+|4K\s*\w+|在线观看|高清)', html)
        seen_names = []
        for name in name_matches:
            name = name.strip()
            if name not in seen_names and len(name) < 20:
                seen_names.append(name)

        for i, name in enumerate(seen_names[:len(sources)]):
            source_names[i + 1] = name

        for idx, sid in enumerate(sorted(sources.keys())):
            episodes_dict = sources[sid]
            episodes = sorted(episodes_dict.items(), key=lambda x: x[0])

            if not episodes:
                continue

            from_name = source_names.get(idx + 1, f"线路{sid}")
            play_from_list.append(from_name)

            urls = [f"{ep_name}${self.BASE_URL}{href}" for epid, (ep_name, href) in episodes]
            play_url_list.append('#'.join(urls))

        return play_from_list, play_url_list

    def playerContent(self, flag, id, vipFlags):
        try:
            url = id
            if url.startswith('/'):
                url = self.BASE_URL + url
            elif not url.startswith('http'):
                url = self.BASE_URL + '/play/' + url

            resp = self._get(url, use_cache=False)
            if not resp:
                return {}

            html = resp.text

            player_m = re.search(r'player_aaaa\s*=\s*({[^<]+})', html)
            if player_m:
                try:
                    pdata = json.loads(player_m.group(1))
                    play_url = pdata.get('url', '')
                    encrypt = pdata.get('encrypt', 0)

                    if encrypt == 1:
                        play_url = urllib.parse.unquote(play_url)
                    elif encrypt == 2:
                        import base64
                        try:
                            padded = play_url + '=' * (4 - len(play_url) % 4)
                            play_url = urllib.parse.unquote(base64.urlsafe_b64decode(padded).decode('utf-8'))
                        except Exception:
                            pass

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

                    if play_url:
                        return {
                            "parse": 1,
                            "playUrl": "",
                            "url": play_url,
                            "header": json.dumps({
                                "User-Agent": self.HEADERS["User-Agent"],
                                "Referer": self.BASE_URL + "/",
                            }),
                        }
                except Exception as e:
                    logger.error(f"解析player_aaaa失败: {e}")

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

    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg) if pg else 1
            encoded_key = urllib.parse.quote(key)

            if page <= 1:
                url = f"{self.BASE_URL}/search/{encoded_key}-------------.html"
            else:
                url = f"{self.BASE_URL}/search/{encoded_key}----------{page}---.html"

            now = time.time()
            if now - self._last_search_time < self._search_interval:
                time.sleep(self._search_interval - (now - self._last_search_time))

            resp = self._get(url, use_cache=False)
            
            if resp and "请不要频繁操作" in resp.text:
                time.sleep(self._search_interval)
                resp = self._get(url, use_cache=False)

            if not resp:
                return {"list": [], "page": 1, "pagecount": 1, "limit": 20, "total": 0}

            self._last_search_time = time.time()

            videos = self._parse_video_list(resp.text)
            
            if page <= 1 and videos:
                videos = self._reorder_search_results(videos, key)

            pagecount = self._parse_total_pages(resp.text)

            return {
                "list": videos,
                "page": page,
                "pagecount": pagecount if pagecount > 1 else 1,
                "limit": 30,
                "total": pagecount * 30 if pagecount > 1 else len(videos),
            }
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return {"list": [], "page": 1, "pagecount": 1, "limit": 20, "total": 0}

    def _reorder_search_results(self, videos, key):
        if not videos or not key:
            return videos

        def match_score(video):
            name = video.get("vod_name", "")
            score = 0
            if name == key:
                score += 100
            elif name.startswith(key + " "):
                score += 90
            elif name.startswith(key):
                score += 80
            elif key in name:
                score += 50
            else:
                score += 0
            return score

        return sorted(videos, key=lambda x: -match_score(x))


if __name__ == "__main__":
    spider = Spider()
    print("=== 首页 ===")
    home = spider.homeContent()
    print("分类:", [c["type_name"] for c in home.get("class", [])])
    print("首页视频数:", len(home.get("list", [])))
    if home.get("list"):
        v = home["list"][0]
        print(f"示例: {v['vod_name']} | 海报: {bool(v['vod_pic'])}")

    print("\n=== 分类(电影) ===")
    cate = spider.categoryContent("1", 1, 0, {})
    print(f"视频数: {len(cate.get('list', []))}, 总页数: {cate.get('pagecount')}, 总数: {cate.get('total')}")
    if cate.get("list"):
        v = cate["list"][0]
        print(f"示例: {v['vod_name']} | 海报: {bool(v['vod_pic'])}")

    print("\n=== 分类(动漫) ===")
    cate2 = spider.categoryContent("4", 1, 0, {})
    print(f"视频数: {len(cate2.get('list', []))}")
    if cate2.get("list"):
        for v in cate2["list"][:3]:
            print(f"  {v['vod_name']}")

    print("\n=== 分类(综艺) ===")
    cate3 = spider.categoryContent("3", 1, 0, {})
    print(f"视频数: {len(cate3.get('list', []))}")
    if cate3.get("list"):
        for v in cate3["list"][:3]:
            print(f"  {v['vod_name']}")

    if cate.get("list"):
        vid = cate["list"][0]["vod_id"]
        print(f"\n=== 详情({vid}) ===")
        detail = spider.detailContent([vid])
        if detail.get("list"):
            d = detail["list"][0]
            print(f"片名: {d['vod_name']}")
            print(f"海报: {'有' if d['vod_pic'] else '无'}")
            print(f"年份: {d['vod_year']}")
            print(f"地区: {d['vod_area']}")
            print(f"导演: {d['vod_director']}")
            print(f"主演: {d['vod_actor'][:80] if d['vod_actor'] else '无'}")
            print(f"类型: {d['type_name']}")
            print(f"简介: {d['vod_content'][:100] if d['vod_content'] else '无'}")
            print(f"播放源: {d['vod_play_from'][:80]}")

    print("\n=== 搜索(完美世界) ===")
    res = spider.searchContent("完美世界", False, "1")
    print(f"搜索结果数: {len(res.get('list', []))}")
    if res.get("list"):
        v = res["list"][0]
        print(f"示例: {v['vod_name']} | 海报: {bool(v['vod_pic'])}")
