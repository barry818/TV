# -*- coding: utf-8 -*-
"""
=================================================
  袋鼠影视 TVBox / OK影视 / 影视仓 标准 Python 源
  站点: https://dsystv.com (袋鼠影视)
  仅供测试，测试完毕请于24小时删除。
=================================================

  修复说明（v2）：
  1. 播放列表改为按"线路"解析（苹果CMS·海螺模板）：
     详情页每个 <div class="panel" data-playlist-name=... data-playlist-line=...>
     内有该线路的分集 <li><a href="/play/xxx.html">集名</a></li>；
     详情页未预载分集时，请求 /playlist.php?id=&line= 接口兜底。
     修复前会把线路入口/按钮误当分集，导致播放列表错乱、播几秒被切走。
  2. playerContent 改为优先从播放页提取真实 m3u8 直链 (var now="...")，
     以 parse:0 直接播放，绕开播放页的 web-player-auto-switch.js 自动跳集脚本。
"""

import sys
import json
import re
import time
from urllib.parse import quote, urlencode

sys.path.append('..')

try:
    from base.spider import Spider
except ImportError:
    import requests as rq
    class Spider:
        def fetch(self, url, headers=None, **kw):
            kw.pop('timeout', None)
            r = rq.get(url, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r


class Spider(Spider):
    """袋鼠影视 Spider - 苹果CMS架构 HTML解析"""

    host = 'https://dsystv.com'

    header = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': 'https://dsystv.com/',
    }

    # 分类列表（根据导航栏 /frim/index1.html 等推断）
    classes = [
        {'type_name': '电影', 'type_id': '1'},
        {'type_name': '电视剧', 'type_id': '2'},
        {'type_name': '动漫', 'type_id': '3'},
        {'type_name': '综艺', 'type_id': '4'},
    ]

    # ===================================================================
    #  基础方法
    # ===================================================================

    def getName(self):
        return '袋鼠影视'

    def init(self, extend=''):
        self.extend = extend or ''
        self._url_cache = {}

    def isVideoFormat(self, url):
        return any(x in url for x in ['.m3u8', '.mp4', '.flv'])

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    # ===================================================================
    #  请求封装
    # ===================================================================

    def _fetch_html(self, path):
        """获取页面 HTML"""
        url = path if path.startswith('http') else self.host + path
        try:
            r = self.fetch(url, headers=self.header, timeout=15)
            return r.text if hasattr(r, 'text') else r.content.decode('utf-8', errors='ignore')
        except Exception as e:
            return ''

    # ===================================================================
    #  图片处理
    # ===================================================================

    def _wrap_pic(self, pic_url):
        """处理图片URL，补全协议，并解码 HTML 实体 (&amp; 等)"""
        if not pic_url:
            return ''
        pic_url = pic_url.strip().replace('&amp;', '&').replace('&#38;', '&')
        if pic_url.startswith('//'):
            pic_url = 'https:' + pic_url
        elif pic_url.startswith('/'):
            pic_url = self.host + pic_url
        return pic_url

    # 占位/加载图关键词：命中则视为无效图，需回退到 data-original / data-src
    _PLACEHOLDERS = ('load.gif', 'loading.gif', 'placeholder', 'blank.gif',
                     'blank.png', 'noimage', 'nopic', 'spinner',
                     '/load.', 'lazyload', 'data:image')

    def _is_placeholder(self, u):
        u = (u or '').lower()
        if not u or u.startswith('data:image'):
            return True
        return any(p in u for p in self._PLACEHOLDERS)

    def _extract_pic(self, frag):
        """从 HTML 片段提取真实图片URL。
        袋鼠影视列表卡片为懒加载(<img class="lazy" src="load.gif" data-original="真实图">)，
        若直接取 src 会拿到占位图 load.gif，导致图形显示不全。
        故优先 data-original → data-src → src，并过滤占位图。"""
        if not frag:
            return ''
        m = re.search(r'data-original="([^"]+)"', frag)
        if m and not self._is_placeholder(m.group(1)):
            return m.group(1)
        m = re.search(r'data-src="([^"]+)"', frag)
        if m and not self._is_placeholder(m.group(1)):
            return m.group(1)
        m = re.search(r'src="([^"]+)"', frag)
        if m and not self._is_placeholder(m.group(1)):
            return m.group(1)
        return ''

    # ===================================================================
    #  首页 & 分类
    # ===================================================================

    def homeContent(self, filter):
        """首页：返回分类和筛选器（本站无筛选器，返回空）"""
        return {'class': self.classes, 'filters': {}}

    def homeVideoContent(self):
        """首页推荐视频"""
        try:
            html = self._fetch_html('/')
            vod_list = self._parse_video_list(html)
            return {'list': vod_list[:30]}
        except Exception:
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        """分类内容：/frim/index{tid}.html?page={pg}"""
        try:
            pg = int(pg or 1)
            # 袋鼠影视分类页格式: /frim/index1.html (电影), index2.html (电视剧) ...
            url = f'/frim/index{tid}.html'
            if pg > 1:
                url += f'?page={pg}'
            html = self._fetch_html(url)
            vod_list = self._parse_video_list(html)
            pagecount = self._parse_pagecount(html)
            return {
                'page': pg,
                'pagecount': pagecount,
                'limit': len(vod_list),
                'total': pagecount * 24 if pagecount < 999 else 99999,
                'list': vod_list,
            }
        except Exception:
            return {'page': pg, 'pagecount': 1, 'limit': 0, 'total': 0, 'list': []}

    # ===================================================================
    #  搜索
    # ===================================================================

    def searchContent(self, key, quick, pg=1):
        """搜索：/search.php?searchword={key}&page={pg}"""
        try:
            pg = int(pg or 1)
            params = {'searchword': key}
            if pg > 1:
                params['page'] = pg
            url = '/search.php?' + urlencode(params)
            html = self._fetch_html(url)
            vod_list = self._parse_search_results(html)
            return {'list': vod_list[:30], 'page': pg}
        except Exception:
            return {'list': [], 'page': 1}

    def searchContentPage(self, key, quick, pg=1):
        return self.searchContent(key, quick, pg)

    # ===================================================================
    #  详情页
    # ===================================================================

    def detailContent(self, ids):
        """详情页：/movie/index{id}.html"""
        try:
            vod_id = ids[0] if isinstance(ids, list) else str(ids)
            html = self._fetch_html(f'/movie/index{vod_id}.html')

            # 标题
            vod_name = ''
            title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
            if title_match:
                vod_name = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
            if not vod_name:
                title_match = re.search(r'<title>(.*?)</title>', html, re.S)
                if title_match:
                    vod_name = title_match.group(1).strip()
                    # 《剧名》全集在线观看 - 类型 | 袋鼠影视  -> 剧名
                    m = re.search(r'《([^》]+)》', vod_name)
                    if m:
                        vod_name = m.group(1)
                    else:
                        vod_name = re.split(r'\s*[-|]\s*', vod_name)[0]
                        vod_name = vod_name.replace('全集在线观看', '').strip()

            # 封面：优先 data-original(懒加载真实图) → video-pic 的 src → 全局兜底
            vod_pic = ''
            pic_match = re.search(r'<img[^>]*class="[^"]*video-pic[^"]*"[^>]*data-original="([^"]+)"', html)
            if pic_match and not self._is_placeholder(pic_match.group(1)):
                vod_pic = pic_match.group(1)
            if not vod_pic:
                pic_match = re.search(r'<img[^>]*class="[^"]*video-pic[^"]*"[^>]*src="([^"]+)"', html)
                if pic_match and not self._is_placeholder(pic_match.group(1)):
                    vod_pic = pic_match.group(1)
            if not vod_pic:
                vod_pic = self._extract_pic(html)
            vod_pic = self._wrap_pic(vod_pic)

            # 详情信息 (苹果CMS常见结构)
            vod_year = ''
            vod_area = ''
            vod_class = ''
            vod_director = ''
            vod_actor = ''
            vod_content = ''

            # 提取详情列表
            info_items = re.findall(
                r'<li[^>]*>(?:<span[^>]*>)?(?:<i[^>]*>)?(.*?)(?:</i>)?(?:</span>)?：?\s*(.*?)</li>',
                html, re.S
            )
            for label, value in info_items:
                label = re.sub(r'<[^>]+>', '', label).strip()
                value = re.sub(r'<[^>]+>', '', value).strip()
                if '导演' in label:
                    vod_director = value
                elif '主演' in label:
                    vod_actor = value
                elif '类型' in label:
                    vod_class = value
                elif '地区' in label:
                    vod_area = value
                elif '年份' in label or '上映' in label:
                    year_m = re.search(r'(20\d{2})', value)
                    if year_m:
                        vod_year = year_m.group(1)

            # 简介
            desc_match = re.search(r'<div[^>]*data-video-plot\s*>(.*?)</div>', html, re.S)
            if desc_match:
                vod_content = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip()
            if not vod_content:
                desc_match = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html)
                if desc_match:
                    vod_content = desc_match.group(1)

            # 播放地址 - 按"线路"解析分集列表
            play_from_list, play_url_list = self._parse_play_sources(html, vod_id)

            # 如果还没有，用当前页面兜底
            if not play_from_list:
                play_from_list.append('袋鼠影视')
                play_url_list.append(f'播放$/movie/index{vod_id}.html')

            vod = {
                'vod_id': vod_id,
                'vod_name': vod_name,
                'vod_pic': vod_pic,
                'type_name': vod_class or '袋鼠影视',
                'vod_year': vod_year,
                'vod_area': vod_area,
                'vod_actor': vod_actor,
                'vod_director': vod_director,
                'vod_content': vod_content,
                'vod_remarks': '',
                'vod_play_from': '$$$'.join(play_from_list),
                'vod_play_url': '$$$'.join(play_url_list),
            }
            return {'list': [vod]}
        except Exception:
            return {'list': []}

    # ===================================================================
    #  播放
    # ===================================================================

    def playerContent(self, flag, id, vipFlags):
        """播放：优先从播放页提取真实 m3u8 直链，避免网页解析器自动跳集"""
        try:
            play_url = str(id or '')
            # 补全播放页 URL
            if play_url.startswith('/'):
                page_url = self.host + play_url
            elif play_url.startswith('http'):
                page_url = play_url
            else:
                # 可能是纯ID，构造播放页
                page_url = self.host + f'/movie/index{play_url}.html'

            # 直链优先：播放页里 var now="...m3u8" 即本集真实地址
            m3u8 = self._get_direct_url(page_url)
            if m3u8:
                return {
                    'parse': 0,  # 直接播放直链，不经过网页解析器
                    'url': m3u8,
                    'header': {
                        'User-Agent': self.header['User-Agent'],
                        'Referer': self.host + '/',
                    },
                }

            # 兜底：使用播放器内置解析
            return {
                'parse': 1,
                'url': page_url,
                'header': {
                    'User-Agent': self.header['User-Agent'],
                    'Referer': self.host + '/',
                },
            }
        except Exception:
            return {}

    # ===================================================================
    #  本地代理 (图片代理 - 备用)
    # ===================================================================

    def localProxy(self, param):
        try:
            if isinstance(param, str):
                from urllib.parse import parse_qs
                param_dict = parse_qs(param)
            else:
                param_dict = param

            do = param_dict.get('do', '')
            if isinstance(do, list):
                do = do[0] if do else ''

            if do == 'img':
                url = param_dict.get('url', '')
                if isinstance(url, list):
                    url = url[0] if url else ''
                if url:
                    import base64
                    try:
                        url = base64.urlsafe_b64decode(url).decode('utf-8')
                    except Exception:
                        pass
                    if url:
                        headers = {
                            'User-Agent': self.header['User-Agent'],
                            'Referer': self.host + '/',
                        }
                        r = self.fetch(url, headers=headers, timeout=15)
                        content_type = 'image/jpeg'
                        if '.png' in url:
                            content_type = 'image/png'
                        elif '.webp' in url:
                            content_type = 'image/webp'
                        content = r.content if hasattr(r, 'content') else r.text.encode('utf-8')
                        return [200, content_type, content, {}]
        except Exception:
            pass
        return [404, 'text/plain', '', {}]

    # ===================================================================
    #  解析辅助方法
    # ===================================================================

    def _parse_play_sources(self, html, vod_id):
        """解析苹果CMS(海螺模板)多线路分集列表。

        详情页中每个线路是一个：
            <div class="panel clearfix" data-playlist-name="蓝光专线1" data-playlist-line="0" ...>
              <ul ...><li id="00"><a href="/play/{id}-{line}-{part}.html">第1集</a></li>...</ul>
            </div>
        返回 (from_list, url_list)，对应 vod_play_from / vod_play_url。
        """
        from_list, url_list = [], []

        panel_re = re.compile(
            r'<div[^>]*data-playlist-name="([^"]+)"[^>]*data-playlist-line="(\d+)"',
            re.S
        )
        hits = list(panel_re.finditer(html))

        for i, m in enumerate(hits):
            line_name = m.group(1).strip()
            line = m.group(2)
            seg_start = m.end()
            seg_end = hits[i + 1].start() if i + 1 < len(hits) else len(html)
            seg = html[seg_start:seg_end]

            eps = self._parse_episodes(seg)
            if not eps:
                # 详情页未预载该线路分集时，请求分集接口兜底
                eps = self._parse_episodes_from_api(vod_id, line)
            if not eps:
                continue

            from_list.append(line_name or f'线路{line}')
            url_list.append('#'.join(f'{name}${href}' for name, href in eps))

        return from_list, url_list

    def _parse_episodes(self, frag):
        """从分集片段中解析 (集名, 播放地址) 列表，去重保序"""
        if not frag:
            return []
        eps = []
        ep_re = re.compile(
            r'<li[^>]*>\s*<a[^>]*href="(/play/[^"]+\.html)"[^>]*>(.*?)</a>',
            re.S
        )
        for href, name in ep_re.findall(frag):
            clean_name = re.sub(r'<[^>]+>', '', name).strip()
            if not clean_name:
                clean_name = '播放'
            eps.append((clean_name, href))

        seen = set()
        out = []
        for name, href in eps:
            key = (name, href)
            if key in seen:
                continue
            seen.add(key)
            out.append((name, href))
        return out

    def _parse_episodes_from_api(self, vod_id, line):
        """通过分集接口 /playlist.php?id=&line= 获取分集（详情页未预载时兜底）"""
        try:
            url = '/playlist.php?' + urlencode({'id': vod_id, 'line': line})
            return self._parse_episodes(self._fetch_html(url))
        except Exception:
            return []

    def _get_direct_url(self, page_url):
        """带缓存的播放页直链提取，缓存 30 分钟"""
        now_t = time.time()
        cached = self._url_cache.get(page_url)
        if cached and now_t - cached[0] < 1800:
            return cached[1]
        html = self._fetch_html(page_url)
        m3u8 = self._find_m3u8(html)
        if m3u8:
            self._url_cache[page_url] = (now_t, m3u8)
        return m3u8

    def _find_m3u8(self, html):
        """从播放页中提取真实视频地址：优先 var now="..."，其次 player JSON，最后页面任意 m3u8"""
        if not html:
            return ''
        m = re.search(r'var\s+now\s*=\s*"([^"]+)"', html)
        if m:
            u = m.group(1).strip()
            if u.startswith('http'):
                return u
        m = re.search(r'var\s+player_[a-zA-Z0-9_]+\s*=\s*(\{.*?\})\s*;', html, re.S)
        if m:
            try:
                j = json.loads(m.group(1))
                u = str(j.get('url', '') or '')
                if u.startswith('http'):
                    return u
            except Exception:
                pass
        m = re.search(r'https?://[^"\'\s<>]+\.m3u8[^"\'\s<>]*', html)
        if m:
            return m.group(0)
        return ''

    def _parse_pagecount(self, html):
        """解析总页数"""
        try:
            # 匹配 "共X页" 或 "1/10" 格式
            m = re.search(r'共\s*(\d+)\s*页', html)
            if m:
                return int(m.group(1))
            m = re.search(r'/(\d+)\s*页', html)
            if m:
                return int(m.group(1))
            # 找最大页码
            nums = re.findall(r'[?&]page=(\d+)', html)
            if nums:
                return max(int(n) for n in nums)
            if '下一页' in html:
                return 999
        except Exception:
            pass
        return 1

    def _parse_video_list(self, html):
        """解析视频卡片列表（首页/分类页）。
        关键修复：用 finditer 拿到每个卡片 <a> 的精确位置，取『本卡片到下一个卡片之间』的
        片段提取图片，避免 href 重复出现时 re.search 命中空 <a> 导致图片丢失（图形显示不全）。"""
        vod_list = []
        seen = set()

        pattern = re.compile(
            r'<a[^>]*class="[^"]*videopic[^"]*"[^>]*href="(/movie/index(\d+)\.html)"[^>]*title="([^"]*)"',
            re.S
        )
        matches = list(pattern.finditer(html))

        for i, mt in enumerate(matches):
            href, vid, title = mt.group(1), mt.group(2), mt.group(3)
            if vid in seen:
                continue
            seen.add(vid)

            # 片段 = 本卡片 <a> 起点 → 下一个卡片 <a> 起点（必含本卡片的 img，无论其在 a 内或紧邻 a 后）
            start = mt.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(html)
            frag = html[start:end]

            pic_url = self._wrap_pic(self._extract_pic(frag))

            # 备注（评分/年份/集数）
            remark = ''
            rm = re.search(r'class="[^"]*remark[^"]*"[^>]*>(.*?)</span>', frag, re.S)
            if rm:
                remark = re.sub(r'<[^>]+>', '', rm.group(1)).strip()
            if not remark:
                ym = re.search(r'(20\d{2})', frag)
                if ym:
                    remark = ym.group(1)

            vod_list.append({
                'vod_id': vid,
                'vod_name': title,
                'vod_pic': pic_url,
                'vod_remarks': remark,
            })

        return vod_list

    def _parse_search_results(self, html):
        """解析搜索结果。
        同样用 finditer 精确定位卡片片段，避免 href 重复导致图片错位/丢失。"""
        vod_list = []
        seen = set()

        pattern = re.compile(
            r'<a[^>]*href="(/movie/index(\d+)\.html)"[^>]*title="([^"]*)"',
            re.S
        )
        matches = list(pattern.finditer(html))

        for i, mt in enumerate(matches):
            href, vid, title = mt.group(1), mt.group(2), mt.group(3)
            if vid in seen:
                continue
            seen.add(vid)

            start = mt.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(html)
            frag = html[start:end]
            pic_url = self._wrap_pic(self._extract_pic(frag))

            vod_list.append({
                'vod_id': vid,
                'vod_name': title,
                'vod_pic': pic_url,
                'vod_remarks': '',
            })

        return vod_list