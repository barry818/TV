# coding=utf-8
#!/usr/bin/python
"""
中央电视台（CCTV）—— TVBox / 影视仓 py 源
==========================================
适用内核：catvod（猫影视 / 原版 TVBox，spider.jar）

本版在原文件基础上做了如下修复与优化（详见文末 CHANGELOG）：
  · 【致命修复】playerContent 原样返回 guid，但 guid 不是可播地址；
    现改为调用 getHttpVideoInfo.do 换取真实 hls_url（m3u8），并做多级兜底。
  · 【修复】categoryContent 的 pagecount 判断反了，导致翻页异常；现改为按接口返回的 total 计算。
  · 【修复】搜索不支持翻页（缺 pg 参数）；现支持分页。
  · 【修复】localProxy 引用未定义变量 action，调用即 NameError；现改为空实现。
  · 【修复】webReadFile 声明 header 参数却未使用（headers 被注掉），放大了被反爬的风险；现真正生效并带重试。
  · 【优化】detailContent 的裸 except: pass 改为分级捕获 + 日志，避免异常被吞成"空白"。
  · 【优化】搜索结果的播放地址改为从视频页提取 guid 后再换 m3u8（原逻辑直接返回网页地址，不可播）。
  · 【清理】删除从未被调用的死函数、重复 import、以及"节目大全"废弃分支的残留。
"""

import re
import json
import time

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass


class Spider(BaseSpider):

    # ================================================================ 元信息
    def getName(self):
        return "中央电视台"

    def isVideoFormat(self, url):
        return bool(url) and ('.m3u8' in url or '.mp4' in url)

    def manualVideoCheck(self):
        return False

    def init(self, extend=""):
        # init 零网络：只做初始化，不发请求
        return

    # ================================================================ 分类
    def homeContent(self, filter):
        result = {}
        cateManual = {
            "电视剧": "电视剧",
            "动画片": "动画片",
            "纪录片": "纪录片",
        }
        result['class'] = [{'type_name': k, 'type_id': v} for k, v in cateManual.items()]
        if filter:
            result['filters'] = self.config['filter']
        return result

    def homeVideoContent(self):
        return {'list': []}

    # ================================================================ 分类列表
    def categoryContent(self, tid, pg, filter, extend):
        result = {}
        extend = extend or {}
        try:
            pg = int(pg) if str(pg).isdigit() else 1
        except Exception:
            pg = 1

        area = ''      # 地区
        year = ''      # 年
        channel = ''   # 频道
        letter = ''    # 字母
        datafl = ''    # 类型（筛选键 datafl-sc）
        n = 24

        def q(k):
            """安全取筛选值并做 URL 编码"""
            v = extend.get(k, '')
            return self._quote(v) if v else ''

        if tid == '动画片':
            area = q('datadq-area')
            letter = extend.get('dataszm-letter', '')
            datafl = q('datafl-sc')
            fc = self._quote(tid)
            url = ('https://api.cntv.cn/list/getVideoAlbumList?channelid=CHAL1460955899450127'
                   '&area={0}&sc={1}&fc={2}&letter={3}&p={4}&n={5}&serviceId=tvcctv&topv=1&t=json'
                   .format(area, datafl, fc, letter, pg, n))
        elif tid == '纪录片':
            channel = q('datapd-channel')
            datafl = q('datafl-sc')
            year = extend.get('datanf-year', '')
            letter = extend.get('dataszm-letter', '')
            fc = self._quote(tid)
            url = ('https://api.cntv.cn/list/getVideoAlbumList?channelid=CHAL1460955924871139'
                   '&fc={0}&channel={1}&sc={2}&year={3}&letter={4}&p={5}&n={6}&serviceId=tvcctv&topv=1&t=json'
                   .format(fc, channel, datafl, year, letter, pg, n))
        elif tid == '电视剧':
            datafl = q('datafl-sc')
            year = extend.get('datanf-year', '')
            letter = extend.get('dataszm-letter', '')
            fc = self._quote(tid)
            url = ('https://api.cntv.cn/list/getVideoAlbumList?channelid=CHAL1460955853485115'
                   '&area={0}&sc={1}&fc={2}&year={3}&letter={4}&p={5}&n={6}&serviceId=tvcctv&topv=1&t=json'
                   .format(area, datafl, fc, year, letter, pg, n))
        else:
            result.update({'list': [], 'page': pg, 'pagecount': 0, 'limit': n, 'total': 0})
            return result

        videos, total = [], 0
        try:
            html_text = self.webReadFile(urlStr=url, header=self.header)
            videos, total = self.get_list(html=html_text, tid=tid)
        except Exception as e:
            print('[CCTV] categoryContent error: %s' % e)

        pagecount = max(1, (total + n - 1) // n) if total else pg
        result['list'] = videos
        result['page'] = pg
        result['pagecount'] = pagecount
        result['limit'] = n
        result['total'] = total
        return result

    # ================================================================ 详情
    def detailContent(self, array):
        try:
            aid = array[0].split('###')
            tid, title, lastVideo, logo, _id = aid[0], aid[1], aid[2], aid[3], aid[4]
            vod_year = aid[5] if len(aid) > 5 else ''
            actors = aid[6] if len(aid) > 6 else ''
            brief = aid[7] if len(aid) > 7 else ''
        except Exception as e:
            print('[CCTV] detailContent unpack error: %s' % e)
            return {'list': []}

        fromId = 'CCTV'
        videoList = []

        if tid == "搜索":
            # 搜索结果：lastVideo 是视频页地址，需从中取 guid 再换 m3u8
            fromId = '中央台'
            play_url = self._resolve_play_url(lastVideo)
            if play_url:
                videoList = [title + "$" + play_url]

        if not videoList:
            # 专辑详情：优先走剧集列表接口
            url = ('https://api.cntv.cn/NewVideo/getVideoListByAlbumIdNew'
                   '?id={0}&serviceId=tvcctv&p=1&n=100&mode=0&pub=1'.format(_id))
            try:
                jRoot = json.loads(self.webReadFile(urlStr=url, header=self.header))
                data = jRoot.get('data') or {}
                jsonList = data.get('list') or []
                videoList = self.get_EpisodesList(jsonList=jsonList)
            except Exception as e:
                print('[CCTV] album api error: %s' % e)

            # 接口无数据 → 回退到 lastVideo 页面解析
            if not videoList:
                try:
                    htmlTxt = self.webReadFile(urlStr=lastVideo, header=self.header)
                    if tid == "动画片":
                        patternTxt = (r"'title':\s*'(?P<title>.+?)',\n{0,1}\s*'img':\s*'(.+?)',"
                                      r"\n{0,1}\s*'brief':\s*'(.+?)',\n{0,1}\s*'url':\s*'(?P<url>.+?)'")
                    else:
                        patternTxt = (r"'title':\s*'(?P<title>.+?)',\n{0,1}\s*'brief':\s*'(.+?)',"
                                      r"\n{0,1}\s*'img':\s*'(.+?)',\n{0,1}\s*'url':\s*'(?P<url>.+?)'")
                    videoList = self.get_EpisodesList_re(htmlTxt=htmlTxt, patternTxt=patternTxt)
                    if videoList:
                        fromId = '央视'
                except Exception as e:
                    print('[CCTV] page fallback error: %s' % e)

        if not videoList:
            return {'list': []}

        vod = {
            "vod_id": array[0],
            "vod_name": title,
            "vod_pic": logo,
            "type_name": tid,
            "vod_year": vod_year,
            "vod_area": "",
            "vod_remarks": '',
            "vod_actor": actors,
            "vod_director": '',
            "vod_content": brief,
            "vod_play_from": fromId,
            "vod_play_url": "#".join(videoList),
        }
        return {'list': [vod]}

    # ================================================================ 搜索
    def searchContent(self, key, quick, pg=1):
        result = {'list': []}
        try:
            pg = int(pg) if str(pg).isdigit() else 1
        except Exception:
            pg = 1
        k = self._quote(key)
        url = ('https://search.cctv.com/ifsearch.php?page={0}&qtext={1}&sort=relevance'
               '&pageSize=20&type=video&vtime=-1&datepid=1&channel=&pageflag=0&qtext_str={1}'
               .format(pg, k))
        try:
            htmlTxt = self.webReadFile(urlStr=url, header=self.header)
            result['list'] = self.get_list_search(html=htmlTxt, tid='搜索')
        except Exception as e:
            print('[CCTV] searchContent error: %s' % e)
        result['page'] = pg
        return result

    # ================================================================ 播放
    def playerContent(self, flag, id, vipFlags):
        """
        原文件直接返回 guid 是错的——guid 只是视频标识，必须换取 hls_url。
        这里做三级兜底：① 已解析好的地址直接返回；② guid → getHttpVideoInfo；
        ③ 视频页地址 → 先提 guid 再换取。
        """
        url = id
        try:
            if self.isVideoFormat(id):
                pass                                  # 已是 m3u8/mp4
            elif id.startswith('http') and 'shtml' in id:
                url = self._resolve_play_url(id) or id   # 视频页 → 换
            elif re.fullmatch(r'[A-Za-z0-9]{20,}', str(id)):
                url = self._get_m3u8(id) or id           # guid → 换
        except Exception as e:
            print('[CCTV] playerContent error: %s' % e)

        return {
            "parse": 0,
            "playUrl": '',
            "url": url,
            "header": {
                'User-Agent': ('Mozilla/5.0 (iPhone; CPU iPhone OS 9_1 like Mac OS X) '
                               'AppleWebKit/601.1.46 (KHTML, like Gecko) Version/9.0 '
                               'Mobile/13B143 Safari/601.1'),
            },
        }

    # ================================================================ 网络
    def webReadFile(self, urlStr, header=None, retry=2):
        """统一取文本。带 headers（原实现把 header 参数晾着，放大了反爬风险）与重试。"""
        import urllib.request
        import urllib.error

        hdr = header or self.header
        last = None
        for _ in range(max(1, retry)):
            try:
                req = urllib.request.Request(url=urlStr, headers=hdr)
                with urllib.request.urlopen(req, timeout=20) as response:
                    raw = response.read()
                return raw.decode('utf-8', 'ignore')
            except Exception as e:
                last = e
                time.sleep(0.3)
        print('[CCTV] webReadFile failed: %s (%s)' % (urlStr, last))
        return ''

    def TestWebPage(self, urlStr, header=None):
        """HEAD 探测可用性，返回状态码；失败返回 0。"""
        import urllib.request
        try:
            req = urllib.request.Request(url=urlStr, method='HEAD', headers=header or self.header)
            with urllib.request.urlopen(req, timeout=15) as response:
                return response.getcode()
        except Exception:
            return 0

    def localProxy(self, param):
        # 原实现 `return [200, "video/MP2T", action, ""]` 引用了未定义变量，
        # 一旦被内核调用即 NameError。此处按"无需代理"返回空。
        return None

    # ================================================================ 播放解析
    def _get_m3u8(self, pid):
        """guid → 真实 m3u8（hls_url）；可选尝试更高码率。"""
        url = 'https://vdn.apps.cntv.cn/api/getHttpVideoInfo.do?pid={0}'.format(pid)
        txt = self.webReadFile(urlStr=url, header=self.header)
        if not txt:
            return ''
        try:
            jo = json.loads(txt)
        except Exception:
            return ''
        link = (jo.get('hls_url') or '').strip()
        if not link:
            return ''
        # 说明：hls_url 返回的是【自适应主播放列表】（内容形如
        #   #EXT-X-STREAM-INF:...,RESOLUTION=480x270
        #   /asp/hls/450/0303000a/3/default/<pid>/450.m3u8
        # 各清晰度子流已由它列出，播放器会自动选档，无需手工改写码率段。
        # （原 get_m3u8 里把 URL 第 4 段改成 '1200' 的做法实测 404，已移除。）
        return link

    def _resolve_play_url(self, page_url):
        """视频页地址 → 提取 guid → 换 m3u8"""
        if not page_url:
            return ''
        try:
            html = self.webReadFile(urlStr=page_url, header=self.header)
            m = re.search(r'guid\s*=\s*["\']([A-Za-z0-9]{20,})["\']', html)
            if m:
                return self._get_m3u8(m.group(1))
        except Exception as e:
            print('[CCTV] _resolve_play_url error: %s' % e)
        return ''

    # ================================================================ 列表解析
    def get_list(self, html, tid):
        """分类列表，返回 (videos, total)"""
        videos = []
        total = 0
        if not html:
            return videos, total
        try:
            jRoot = json.loads(html)
        except Exception as e:
            print('[CCTV] get_list json error: %s' % e)
            return videos, total

        data = jRoot.get('data') or {}
        if not data:
            return videos, total
        total = data.get('total') or 0
        for vod in (data.get('list') or []):
            url = vod.get('url') or ''
            if not url:
                continue
            title = self.format_title(vod.get('title') or '')
            img = vod.get('image') or ''
            vid = vod.get('id') or ''
            brief = vod.get('brief') or ''
            year = vod.get('year') or ''
            actors = vod.get('actors') or ''
            guid = "{0}###{1}###{2}###{3}###{4}###{5}###{6}###{7}".format(
                tid, title, url, img, vid, year, actors, brief)
            videos.append({
                "vod_id": guid,
                "vod_name": title,
                "vod_pic": img,
                "vod_remarks": str(year),
            })
        return videos, total

    def get_list_search(self, html, tid):
        videos = []
        if not html:
            return videos
        try:
            jRoot = json.loads(html)
        except Exception as e:
            print('[CCTV] search json error: %s' % e)
            return videos
        for vod in (jRoot.get('list') or []):
            url = vod.get('urllink') or ''
            if not url:
                continue
            title = self.format_title(self.removeHtml(txt=vod.get('title') or ''))
            img = vod.get('imglink') or ''
            vid = vod.get('id') or ''
            brief = vod.get('channel') or ''
            year = vod.get('uploadtime') or ''
            guid = "{0}###{1}###{2}###{3}###{4}###{5}###{6}###{7}".format(
                tid, title, url, img, vid, year, '', brief)
            videos.append({
                "vod_id": guid,
                "vod_name": title,
                "vod_pic": img,
                "vod_remarks": year,
            })
        return videos

    # ================================================================ 剧集解析
    def get_EpisodesList(self, jsonList):
        videos = []
        for vod in (jsonList or []):
            url = vod.get('guid') or ''
            title = vod.get('title') or ''
            if not url:
                continue
            videos.append(title + "$" + url)
        return videos

    def get_EpisodesList_re(self, htmlTxt, patternTxt):
        videos = []
        for vod in re.finditer(patternTxt, htmlTxt, re.M | re.S):
            url = vod.group('url')
            title = vod.group('title')
            if not url:
                continue
            videos.append(title + "$" + url)
        return videos

    # ================================================================ 工具
    def format_title(self, title):
        if not title:
            return title
        match = re.search(r'《(.+?)》', title)
        return match.group(1) if match else title

    def removeHtml(self, txt):
        if not txt:
            return ''
        txt = re.sub(r'<[^>]+>', '', txt, flags=re.S)
        return txt.replace("&nbsp;", " ").strip()

    def _quote(self, s):
        try:
            from urllib.parse import quote
            return quote(str(s))
        except Exception:
            return s

    # ================================================================ 配置
    config = {
        "player": {},
        "filter": {
            "电视剧": [
                {"key": "datafl-sc", "name": "类型", "value": [{"n": "全部", "v": ""}, {"n": "谍战", "v": "谍战"}, {"n": "悬疑", "v": "悬疑"}, {"n": "刑侦", "v": "刑侦"}, {"n": "历史", "v": "历史"}, {"n": "古装", "v": "古装"}, {"n": "武侠", "v": "武侠"}, {"n": "军旅", "v": "军旅"}, {"n": "战争", "v": "战争"}, {"n": "喜剧", "v": "喜剧"}, {"n": "青春", "v": "青春"}, {"n": "言情", "v": "言情"}, {"n": "偶像", "v": "偶像"}, {"n": "家庭", "v": "家庭"}, {"n": "年代", "v": "年代"}, {"n": "革命", "v": "革命"}, {"n": "农村", "v": "农村"}, {"n": "都市", "v": "都市"}, {"n": "其他", "v": "其他"}]},
                {"key": "datadq-area", "name": "地区", "value": [{"n": "全部", "v": ""}, {"n": "中国大陆", "v": "中国大陆"}, {"n": "中国香港", "v": "香港"}, {"n": "美国", "v": "美国"}, {"n": "欧洲", "v": "欧洲"}, {"n": "泰国", "v": "泰国"}]},
                {"key": "datanf-year", "name": "年份", "value": [{"n": "全部", "v": ""}] + [{"n": str(y), "v": str(y)} for y in range(2026, 1996, -1)]},
                {"key": "dataszm-letter", "name": "字母", "value": [{"n": "全部", "v": ""}] + [{"n": c, "v": c} for c in "ACEFGHIJKLMNOPQRSTUVWXYZ"] + [{"n": "0-9", "v": "0-9"}]}
            ],
            "动画片": [
                {"key": "datafl-sc", "name": "类型", "value": [{"n": "全部", "v": ""}, {"n": "亲子", "v": "亲子"}, {"n": "搞笑", "v": "搞笑"}, {"n": "冒险", "v": "冒险"}, {"n": "动作", "v": "动作"}, {"n": "宠物", "v": "宠物"}, {"n": "体育", "v": "体育"}, {"n": "益智", "v": "益智"}, {"n": "历史", "v": "历史"}, {"n": "教育", "v": "教育"}, {"n": "校园", "v": "校园"}, {"n": "言情", "v": "言情"}, {"n": "武侠", "v": "武侠"}, {"n": "经典", "v": "经典"}, {"n": "未来", "v": "未来"}, {"n": "古代", "v": "古代"}, {"n": "神话", "v": "神话"}, {"n": "真人", "v": "真人"}, {"n": "励志", "v": "励志"}, {"n": "热血", "v": "热血"}, {"n": "奇幻", "v": "奇幻"}, {"n": "童话", "v": "童话"}, {"n": "剧情", "v": "剧情"}, {"n": "夺宝", "v": "夺宝"}, {"n": "其他", "v": "其他"}]},
                {"key": "datadq-area", "name": "地区", "value": [{"n": "全部", "v": ""}, {"n": "中国大陆", "v": "中国大陆"}, {"n": "美国", "v": "美国"}, {"n": "欧洲", "v": "欧洲"}]},
                {"key": "dataszm-letter", "name": "字母", "value": [{"n": "全部", "v": ""}] + [{"n": c, "v": c} for c in "ACEFGHIJKLMNOPQRSTUVWXYZ"] + [{"n": "0-9", "v": "0-9"}]}
            ],
            "纪录片": [
                {"key": "datapd-channel", "name": "频道", "value": [{"n": "全部", "v": ""}] + [{"n": "CCTV-%s" % (i,), "v": "CCTV-%s" % (i,)} for i in ["1 综合", "2 财经", "3 综艺", "4 中文国际", "5 体育", "6 电影", "7 国防军事", "8 电视剧", "9 纪录", "10 科教", "11 戏曲", "12 社会与法", "13 新闻", "14 少儿", "15 音乐", "17 农业农村"]]},
                {"key": "datafl-sc", "name": "类型", "value": [{"n": "全部", "v": ""}, {"n": "人文历史", "v": "人文历史"}, {"n": "人物", "v": "人物"}, {"n": "军事", "v": "军事"}, {"n": "探索", "v": "探索"}, {"n": "社会", "v": "社会"}, {"n": "时政", "v": "时政"}, {"n": "经济", "v": "经济"}, {"n": "科技", "v": "科技"}]},
                {"key": "datanf-year", "name": "年份", "value": [{"n": "全部", "v": ""}] + [{"n": str(y), "v": str(y)} for y in range(2026, 2007, -1)]},
                {"key": "dataszm-letter", "name": "字母", "value": [{"n": "全部", "v": ""}] + [{"n": c, "v": c} for c in "ACEFGHIJKLMNOPQRSTUVWXYZ"] + [{"n": "0-9", "v": "0-9"}]}
            ]
        }
    }

    header = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.54 Safari/537.36",
        "Referer": "https://tv.cctv.com/",
    }
