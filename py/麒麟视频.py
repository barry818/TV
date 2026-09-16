# OK影视专用爬虫插件 | 麒麟影视 qlys.cc | 基于base.spider
# 站点：https://www.qlys.cc（苹果CMS + hl090模板）
# 列表：网页端 /index.php/vod/type/id/{tid}[/year/{y}[/area/{a}]]/page/{pg}.html
# 详情/搜索：API /api.php/provide/vod/?ac=detail（线路与地址一一对应，$$$分隔）
import re
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
requests.packages.urllib3.disable_warnings()

# 核心：继承OK影视内置base.spider.Spider类（必须保留）
from base.spider import Spider

class Spider(Spider):
    # ========== 插件基础配置 ==========
    def getName(self):
        """插件名称：OK影视插件列表中显示的名称"""
        return "麒麟影视"

    # ========== 初始化全局配置 ==========
    def init(self, extend=""):
        """
        初始化方法：配置站点地址、请求头、会话、全局变量
        """
        # 继承父类初始化（必须保留，不可删除）
        super().init(extend)

        # 1. 目标站点基础地址
        self.site_url = "https://www.qlys.cc"
        # 2. 苹果CMS数据API（详情/搜索统一走此接口，返回完整播放线路）
        self.api_url = "https://www.qlys.cc/api.php/provide/vod/"
        # 3. 请求头（移动端UA适配）
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Mobile Safari/537.36",
            "Referer": self.site_url + "/",
            "Accept-Language": "zh-CN,zh;q=0.9"
        }
        # 4. 会话保持+请求重试
        self.sess = requests.Session()
        self.sess.mount("https://", HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])))
        self.sess.mount("http://", HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])))
        # 5. 自定义全局参数
        self.page_size = 30   # 站点每页30条
        self.total = 9999

    # ========== 通用请求方法 ==========
    def fetch(self, url, timeout=10):
        """
        通用GET请求方法：全局复用，处理请求异常
        """
        try:
            res = self.sess.get(url, headers=self.headers, timeout=timeout, verify=False)
            return res
        except Exception:
            return None

    # ========== 首页分类接口（24个分类，全部有数据）==========
    def homeContent(self, filter):
        """
        首页分类：返回站点全部分类，并附带年份/地区筛选配置
        """
        cate_list = [
            {"type_name": "电影", "type_id": "1"},
            {"type_name": "电视剧", "type_id": "2"},
            {"type_name": "短剧", "type_id": "3"},
            {"type_name": "动漫", "type_id": "4"},
            {"type_name": "综艺", "type_id": "5"},
            {"type_name": "内地剧", "type_id": "6"},
            {"type_name": "港台剧", "type_id": "7"},
            {"type_name": "日韩剧", "type_id": "8"},
            {"type_name": "欧美剧", "type_id": "9"},
            {"type_name": "动作片", "type_id": "10"},
            {"type_name": "恐怖片", "type_id": "11"},
            {"type_name": "科幻片", "type_id": "12"},
            {"type_name": "战争片", "type_id": "13"},
            {"type_name": "爱情片", "type_id": "14"},
            {"type_name": "喜剧片", "type_id": "15"},
            {"type_name": "剧情片", "type_id": "16"},
            {"type_name": "记录片", "type_id": "17"},
            {"type_name": "内地番", "type_id": "18"},
            {"type_name": "日韩番", "type_id": "19"},
            {"type_name": "港台番", "type_id": "20"},
            {"type_name": "欧美番", "type_id": "21"},
            {"type_name": "泰剧", "type_id": "22"},
            {"type_name": "漫剧", "type_id": "23"},
            {"type_name": "有声漫剧", "type_id": "24"}
        ]
        result = {"class": cate_list}
        # filter为True时附加筛选配置（年份+地区）
        if filter:
            # 年份：2026-2000（各年份均已验证有数据）
            year_value = [{"n": "全部", "v": ""}]
            for y in range(2026, 1999, -1):
                year_value.append({"n": str(y), "v": str(y)})
            # 地区：均为已验证有数据的地区
            area_list = ["大陆", "香港", "台湾", "美国", "日本", "韩国", "英国", "法国",
                         "德国", "泰国", "印度", "俄罗斯", "加拿大", "澳大利亚", "新加坡"]
            area_value = [{"n": "全部", "v": ""}] + [{"n": a, "v": a} for a in area_list]
            # 每个分类都配置相同的年份+地区筛选
            filters = {}
            for c in cate_list:
                filters[c["type_id"]] = [
                    {"key": "year", "name": "年份", "value": year_value},
                    {"key": "area", "name": "地区", "value": area_value}
                ]
            result["filters"] = filters
        return result

    # ========== 分类列表接口（支持年份/地区筛选+分页）==========
    def categoryContent(self, tid, pg, filter, extend):
        """
        分类列表：根据分类ID+页码+筛选参数，返回对应视频列表
        """
        pg = int(pg) if str(pg).isdigit() else 1
        # 1. 构造筛选路径：可选 /year/2024/area/大陆
        filter_path = ""
        if extend:
            year = extend.get("year")
            area = extend.get("area")
            if year:
                filter_path += "/year/%s" % year
            if area:
                filter_path += "/area/%s" % requests.utils.quote(str(area))
        # 2. 构造列表请求地址
        list_url = "%s/index.php/vod/type/id/%s%s/page/%d.html" % (self.site_url, tid, filter_path, pg)
        # 3. 请求页面
        res = self.fetch(list_url)
        # 4. 初始化视频列表
        video_list = []
        # 5. 解析页面
        if res and res.ok:
            html = res.text
            for match in re.finditer(r'<div class="vod-item">(.*?)</a>\s*</div>', html, re.S):
                item_html = match.group(1)
                vod_id = re.search(r'href="/index.php/vod/detail/id/(\d+)\.html"', item_html)
                vod_name = re.search(r'title="([^"]+)"', item_html)
                vod_pic = re.search(r'<img src="([^"]+)"', item_html)
                vod_remarks = re.search(r'<span class="remarks">([^<]+)</span>', item_html)
                if vod_id and vod_name and vod_pic:
                    pic_url = vod_pic.group(1)
                    if pic_url.startswith("//"):
                        pic_url = "https:" + pic_url
                    elif not pic_url.startswith(("http://", "https://")):
                        pic_url = self.site_url + (pic_url if pic_url.startswith("/") else "/" + pic_url)
                    video_list.append({
                        "vod_id": vod_id.group(1),           # 数字ID，详情走API
                        "vod_name": vod_name.group(1).strip(),
                        "vod_pic": pic_url,
                        "vod_remarks": vod_remarks.group(1).strip() if vod_remarks else "",
                        "style": {"type": "rect", "ratio": 0.67}   # 竖版海报图
                    })
        # 6. 计算总页数：优先取页面"尾页"链接的页码（筛选后真实页数）
        pagecount = pg
        if res and res.ok:
            tail = re.search(r'<a class="page_link"[^>]*href="[^"]*/page/(\d+)\.html"[^>]*title="尾页"', res.text) \
                or re.search(r'<a class="page_link"[^>]*title="尾页"[^>]*href="[^"]*/page/(\d+)\.html"', res.text)
            if tail:
                pagecount = int(tail.group(1))
        # 7. 固定返回格式
        return {
            "list": video_list,
            "page": pg,
            "pagecount": pagecount,
            "limit": self.page_size,
            "total": self.total
        }

    # ========== 视频详情接口（走API，全线路播放地址）==========
    def detailContent(self, ids):
        """
        视频详情：根据vod_id（数字ID），调用站点API返回完整播放线路
        站点API返回的 vod_play_from / vod_play_url 即为OK影视标准格式：
        - 线路名用 $$$ 分隔
        - 播放地址用 $$$ 分隔线路、# 分隔集数、$ 分隔集名与地址
        """
        vod_id = ids[0] if ids else ""
        if not vod_id:
            return {"list": [{"vod_name": "视频ID为空"}]}
        # 1. 构造详情API请求
        detail_url = "%s?ac=detail&ids=%s" % (self.api_url, vod_id)
        # 2. 请求
        res = self.fetch(detail_url)
        # 3. 解析
        if res and res.ok:
            try:
                data = res.json()
            except Exception:
                data = None
            if data and data.get("list"):
                it = data["list"][0]
                play_from = it.get("vod_play_from", "") or ""
                play_url = it.get("vod_play_url", "") or ""
                # 过滤空线路，保证线路名与播放地址一一对应
                play_from, play_url = self._align_play_lines(play_from, play_url)
                # 简介清洗HTML标签
                content = it.get("vod_content", "") or ""
                content = re.sub(r'<[^>]+>', '', content).strip()
                detail_info = {
                    "vod_id": vod_id,
                    "vod_name": it.get("vod_name", "") or "未知名称",
                    "vod_pic": it.get("vod_pic", "") or "",
                    "vod_remarks": it.get("vod_remarks", "") or "",
                    "type_name": it.get("type_name", "") or "",
                    "vod_year": str(it.get("vod_year", "")) or "",
                    "vod_area": it.get("vod_area", "") or "",
                    "vod_actor": it.get("vod_actor", "") or "",
                    "vod_director": it.get("vod_director", "") or "",
                    "vod_content": content,
                    "vod_play_from": play_from,   # 必选：播放线路
                    "vod_play_url": play_url      # 必选：播放地址
                }
                return {"list": [detail_info]}
        # 解析失败返回提示
        return {"list": [{"vod_id": vod_id, "vod_name": "视频详情解析失败"}]}

    # ========== 搜索接口（走API，支持分页）==========
    def searchContent(self, key, quick, pg=1):
        """
        搜索接口：根据关键词，调用站点API返回搜索结果（支持分页）
        """
        pg = int(pg) if str(pg).isdigit() else 1
        # 1. 构造搜索URL
        search_url = "%s?ac=detail&wd=%s&pg=%d" % (self.api_url, requests.utils.quote(key), pg)
        # 2. 请求
        res = self.fetch(search_url)
        # 3. 初始化视频列表
        video_list = []
        total = 0
        pagecount = pg
        if res and res.ok:
            try:
                data = res.json()
            except Exception:
                data = None
            if data and data.get("list"):
                for it in data["list"]:
                    pic = it.get("vod_pic", "") or ""
                    if pic.startswith("//"):
                        pic = "https:" + pic
                    video_list.append({
                        "vod_id": str(it.get("vod_id", "")),
                        "vod_name": it.get("vod_name", "") or "",
                        "vod_pic": pic,
                        "vod_remarks": it.get("vod_remarks", "") or "",
                        "style": {"type": "rect", "ratio": 0.67}
                    })
                total = int(data.get("total") or 0)
                pagecount = int(data.get("pagecount") or pg)
        # 4. 固定返回格式
        return {
            "list": video_list,
            "page": pg,
            "pagecount": pagecount,
            "limit": self.page_size,
            "total": total if total else len(video_list)
        }

    # ========== 播放解析接口（m3u8直链，无需二次解析）==========
    def playerContent(self, flag, id, vipFlags):
        """
        播放解析：站点API返回的即为可直接播放的m3u8直链
        """
        # 1. 解析原始播放地址（拆分「节点名$地址」）
        play_url = id.split("$")[1] if "$" in id else id
        if not play_url:
            return {"parse": 0, "url": "", "header": self.headers}
        # 2. m3u8直链直接返回，parse=0
        return {
            "parse": 0,
            "url": play_url,
            "header": self.headers
        }

    # ========== 工具方法：对齐线路名与播放地址，剔除空线路 ==========
    def _align_play_lines(self, play_from, play_url):
        if not play_from or not play_url:
            return play_from, play_url
        froms = play_from.split("$$$")
        urls = play_url.split("$$$")
        # 两边数量不一致时，按地址数量对齐（保证线路-地址一一对应）
        if len(froms) != len(urls):
            n = min(len(froms), len(urls))
            froms = froms[:n]
            urls = urls[:n]
        keep_from, keep_url = [], []
        for f, u in zip(froms, urls):
            # 剔除无地址的线路，避免播放空线路
            if u and "$" in u:
                keep_from.append(f)
                keep_url.append(u)
        return "$$$".join(keep_from), "$$$".join(keep_url)

# ========== 无额外入口（OK影视自动识别Spider类，无需添加main函数）==========