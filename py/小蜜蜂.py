# -*- coding: utf-8 -*-
"""
小蜜蜂影院 (xmfyy.vip)
苹果CMS - Conch模板
站点: https://www.xmfyy.vip@猪猪
"""

import sys
import re
import json
import requests
from urllib.parse import quote, urljoin

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    # ==================== 站点配置 ====================
    SITE_URL = "https://www.xmfyy.vip"

    # 分类映射（从首页导航获取）
    CATEGORIES = [
        {"type_id": "1", "type_name": "电影"},
        {"type_id": "2", "type_name": "连续剧"},
        {"type_id": "3", "type_name": "综艺"},
        {"type_id": "4", "type_name": "动漫"},
        {"type_id": "6", "type_name": "动作片"},
        {"type_id": "7", "type_name": "喜剧片"},
        {"type_id": "8", "type_name": "爱情片"},
        {"type_id": "9", "type_name": "科幻片"},
        {"type_id": "10", "type_name": "恐怖片"},
        {"type_id": "11", "type_name": "剧情片"},
        {"type_id": "12", "type_name": "战争片"},
        {"type_id": "13", "type_name": "国产剧"},
        {"type_id": "14", "type_name": "港台剧"},
        {"type_id": "15", "type_name": "日韩剧"},
        {"type_id": "16", "type_name": "欧美剧"},
        {"type_id": "19", "type_name": "动画片"},
        {"type_id": "28", "type_name": "动漫"},
        {"type_id": "37", "type_name": "其他剧"},
        {"type_id": "38", "type_name": "纪录片"},
        {"type_id": "39", "type_name": "番剧"},
    ]

    def init(self, extend=""):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': self.SITE_URL + '/',
        }

    def getName(self):
        return "小蜜蜂影院"

    def _fetch(self, url, retries=3):
        for attempt in range(retries):
            try:
                resp = requests.get(url, headers=self.headers, timeout=15)
                resp.encoding = 'utf-8'
                if resp.status_code == 200:
                    return resp.text
            except:
                if attempt < retries - 1:
                    import time
                    time.sleep(1)
                    continue
        return None

    def _fix_url(self, url):
        if not url:
            return ""
        if url.startswith('http'):
            return url
        if url.startswith('//'):
            return 'https:' + url
        if url.startswith('/'):
            return self.SITE_URL + url
        return self.SITE_URL + '/' + url

    def _clean(self, text):
        return re.sub(r'<[^>]+>', '', text or '').strip()

    # ==================== 解析视频列表 ====================
    def _parse_list(self, html):
        """解析视频列表（首页/分类/搜索）"""
        videos = []
        if not html:
            return videos

        # 匹配视频卡片：<li class="hl-list-item ...">
        pattern = r'<li\s+class="[^"]*hl-list-item[^"]*">(.*?)</li>'
        for li in re.finditer(pattern, html, re.DOTALL | re.IGNORECASE):
            content = li.group(1)

            # 提取链接和标题
            a_match = re.search(r'<a\s+[^>]*href="([^"]+)"[^>]*title="([^"]+)"[^>]*>', content)
            if not a_match:
                continue
            href = a_match.group(1)
            title = a_match.group(2)

            if '/vod/detail/' not in href:
                continue

            # 提取视频ID
            vid_match = re.search(r'/vod/detail/id/(\d+)\.html', href)
            if not vid_match:
                continue
            vid = vid_match.group(1)

            # 提取图片
            pic = ''
            pic_match = re.search(r'data-original="([^"]+)"', content)
            if pic_match:
                pic = pic_match.group(1)

            # 提取备注（集数/状态）
            remark = ''
            remark_match = re.search(r'<span\s+class="[^"]*remarks[^"]*">([^<]+)</span>', content)
            if remark_match:
                remark = remark_match.group(1).strip()

            if not remark:
                remark_match = re.search(r'<div\s+class="[^"]*hl-pic-text[^"]*">.*?<span[^>]*>([^<]+)</span>', content)
                if remark_match:
                    remark = remark_match.group(1).strip()

            if pic and not pic.startswith('http'):
                pic = self._fix_url(pic)

            videos.append({
                'vod_id': vid,
                'vod_name': title,
                'vod_pic': pic,
                'vod_remarks': remark,
            })

        return videos

    # ==================== 解析剧集 ====================
    def _parse_episodes(self, html):
        """解析剧集列表"""
        eps = []
        if not html:
            return eps

        # 匹配播放链接：<a href="/vod/play/id/xxx/sid/xxx/nid/xxx.html">第x集</a>
        pattern = r'<a\s+href="(/index\.php/vod/play/id/\d+/sid/\d+/nid/\d+\.html)"[^>]*>([^<]+)</a>'
        for m in re.finditer(pattern, html, re.IGNORECASE):
            href = m.group(1)
            name = self._clean(m.group(2))
            if href and name:
                if any(k in name for k in ['集', '话', 'EP', 'ep', '正片', '第', '期']):
                    eps.append(f"{name}${self._fix_url(href)}")

        return eps

    # ==================== 首页 ====================
    def homeContent(self, filter):
        result = {
            'class': self.CATEGORIES,
            'list': [],
            'filters': {}
        }
        try:
            html = self._fetch(self.SITE_URL + '/')
            if html:
                result['list'] = self._parse_list(html)[:30]
        except:
            pass
        return result

    def homeVideoContent(self):
        try:
            html = self._fetch(self.SITE_URL + '/')
            if html:
                return {'list': self._parse_list(html)[:30]}
        except:
            pass
        return {'list': []}

    # ==================== 分类 ====================
    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if str(pg).isdigit() else 1
        if pg == 1:
            url = f"{self.SITE_URL}/index.php/vod/type/id/{tid}.html"
        else:
            url = f"{self.SITE_URL}/index.php/vod/type/id/{tid}-{pg}.html"

        result = {'list': [], 'page': pg, 'pagecount': 1, 'limit': 24, 'total': 0}
        try:
            html = self._fetch(url)
            if html:
                items = self._parse_list(html)
                result['list'] = items
                result['limit'] = max(len(items), 1)
                result['total'] = len(items) * 10

                # 计算总页数
                page_matches = re.findall(r'/type/id/' + str(tid) + r'-(\d+)\.html', html)
                if page_matches:
                    nums = [int(p) for p in page_matches if p.isdigit()]
                    if nums:
                        result['pagecount'] = max(nums) + 1
                else:
                    result['pagecount'] = pg + 1
        except:
            pass
        return result

    # ==================== 详情 ====================
    def detailContent(self, ids):
        result = {'list': []}
        try:
            vid = str(ids[0])
            url = f"{self.SITE_URL}/index.php/vod/detail/id/{vid}.html"
            html = self._fetch(url)
            if not html:
                return result

            # 标题
            name = ''
            m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
            if m:
                name = self._clean(m.group(1))
            if not name:
                m = re.search(r'<title>([^<]+)</title>', html)
                if m:
                    name = m.group(1).split('-')[0].strip()

            # 海报
            pic = ''
            m = re.search(r'data-original="([^"]+)"', html)
            if m:
                pic = self._fix_url(m.group(1))
            if not pic:
                m = re.search(r'<img[^>]*class="[^"]*vod-img[^"]*"[^>]*src="([^"]+)"', html)
                if m:
                    pic = self._fix_url(m.group(1))

            # 简介
            content = ''
            m = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]*)"', html)
            if m:
                content = m.group(1).strip()
            if not content:
                m = re.search(r'<div[^>]*class="[^"]*vod-content[^"]*"[^>]*>([\s\S]*?)</div>', html)
                if m:
                    content = self._clean(m.group(1))[:500]

            # 演员、导演、年份、状态
            actor = ''
            director = ''
            year = ''
            remarks = ''
            m = re.search(r'主演[：:]\s*([^<\n]+)', html)
            if m:
                actor = m.group(1).strip()
            m = re.search(r'导演[：:]\s*([^<\n]+)', html)
            if m:
                director = m.group(1).strip()
            m = re.search(r'年份[：:]\s*(\d{4})', html)
            if m:
                year = m.group(1)
            m = re.search(r'状态[：:]\s*([^<\n]+)', html)
            if m:
                remarks = m.group(1).strip()

            vod = {
                'vod_id': vid,
                'vod_name': name,
                'vod_pic': pic,
                'vod_content': content,
                'vod_year': year,
                'vod_actor': actor,
                'vod_director': director,
                'vod_remarks': remarks,
                'vod_play_from': '',
                'vod_play_url': '',
            }

            # 剧集
            eps = self._parse_episodes(html)
            if eps:
                vod['vod_play_from'] = '云播'
                vod['vod_play_url'] = '#'.join(eps)

            result['list'] = [vod]
        except:
            pass
        return result

    # ==================== 搜索 ====================
    def searchContent(self, key, quick, pg="1"):
        pg = int(pg) if str(pg).isdigit() else 1
        url = f"{self.SITE_URL}/index.php/vod/search.html?wd={quote(key)}"
        if pg > 1:
            url += f"&page={pg}"

        result = {'list': [], 'page': pg, 'pagecount': 1, 'limit': 24, 'total': 0}
        try:
            html = self._fetch(url)
            if html:
                items = self._parse_list(html)
                result['list'] = items
                if items:
                    result['pagecount'] = 9999
                    result['total'] = 999999
        except:
            pass
        return result

    # ==================== 播放 ====================
    def playerContent(self, flag, id, vipFlags):
        try:
            url = id
            if not url.startswith('http'):
                url = self._fix_url(url)

            # 如果是直链
            if re.search(r'\.(m3u8|mp4|flv)(\?|$)', url, re.I):
                return {
                    'parse': 0,
                    'url': url,
                    'header': json.dumps({'Referer': self.SITE_URL + '/', 'User-Agent': self.headers['User-Agent']})
                }

            # 获取播放页
            html = self._fetch(url)
            if html:
                # 查找 iframe
                m = re.search(r'<iframe[^>]*src="([^"]+)"', html, re.IGNORECASE)
                if m:
                    video_url = self._fix_url(m.group(1))
                    return {
                        'parse': 0,
                        'url': video_url,
                        'header': json.dumps({'Referer': self.SITE_URL + '/', 'User-Agent': self.headers['User-Agent']})
                    }

                # 查找 M3U8
                m = re.search(r'(https?://[^"\'\s<>]+\.m3u8[^"\'\s<>]*)', html, re.IGNORECASE)
                if m:
                    return {
                        'parse': 0,
                        'url': m.group(1),
                        'header': json.dumps({'Referer': self.SITE_URL + '/', 'User-Agent': self.headers['User-Agent']})
                    }

                # 查找 video 标签
                m = re.search(r'<video[^>]*src="([^"]+)"', html, re.IGNORECASE)
                if m:
                    video_url = self._fix_url(m.group(1))
                    return {
                        'parse': 0,
                        'url': video_url,
                        'header': json.dumps({'Referer': self.SITE_URL + '/', 'User-Agent': self.headers['User-Agent']})
                    }

            # 让播放器自行处理
            return {
                'parse': 1,
                'url': url,
                'header': json.dumps({'Referer': self.SITE_URL + '/', 'User-Agent': self.headers['User-Agent']})
            }
        except:
            return {'parse': 1, 'url': id, 'header': '{}'}

    def localProxy(self, param):
        return [200, {}, '']