#coding=utf-8
#!/usr/bin/python
import sys
sys.path.append('..') 
from base.spider import Spider
import json
import time
import base64
import re
from urllib import request, parse
import urllib
import urllib.request
import time

class Spider(Spider):
    def getName(self):
        return "中央电视台"
    def init(self,extend=""):
        print("============{0}============".format(extend))
        pass
    def isVideoFormat(self,url):
        pass
    def manualVideoCheck(self):
        pass
    def homeContent(self,filter):
        result = {}
        # 只保留三个分类
        cateManual = {
            "电视剧": "电视剧",
            "动画片": "动画片",
            "纪录片": "纪录片"
        }
        classes = []
        for k in cateManual:
            classes.append({
                'type_name': k,
                'type_id': cateManual[k]
            })
        result['class'] = classes
        if(filter):
            result['filters'] = self.config['filter']  # 此时 filter 中只包含三个分类
        return result
    def homeVideoContent(self):
        result = {'list': []}
        return result
    def categoryContent(self,tid,pg,filter,extend):
        result = {}
        month = ""  # 月
        year = ""   # 年
        area = ''   # 地区
        channel = '' # 频道
        datafl = '' # 类型
        letter = '' # 字母
        pagecount = 24

        # 仅保留三个分类的逻辑，其余分支已移除（但保留原代码结构以兼容未调用的情形）
        if tid == '动画片':
            id = urllib.parse.quote(tid)
            if 'datadq-area' in extend.keys():
                area = urllib.parse.quote(extend['datadq-area'])
            if 'dataszm-letter' in extend.keys():
                letter = extend['dataszm-letter']
            if 'datafl-sc' in extend.keys():
                datafl = urllib.parse.quote(extend['datafl-sc'])
            url = 'https://api.cntv.cn/list/getVideoAlbumList?channelid=CHAL1460955899450127&area={0}&sc={4}&fc={1}&letter={2}&p={3}&n=24&serviceId=tvcctv&topv=1&t=json'.format(area, id, letter, pg, datafl)
        elif tid == '纪录片':
            id = urllib.parse.quote(tid)
            if 'datapd-channel' in extend.keys():
                channel = urllib.parse.quote(extend['datapd-channel'])
            if 'datafl-sc' in extend.keys():
                datafl = urllib.parse.quote(extend['datafl-sc'])
            if 'datanf-year' in extend.keys():
                year = extend['datanf-year']
            if 'dataszm-letter' in extend.keys():
                letter = extend['dataszm-letter']
            url = 'https://api.cntv.cn/list/getVideoAlbumList?channelid=CHAL1460955924871139&fc={0}&channel={1}&sc={2}&year={3}&letter={4}&p={5}&n=24&serviceId=tvcctv&topv=1&t=json'.format(id, channel, datafl, year, letter, pg)
        elif tid == '电视剧':
            id = urllib.parse.quote(tid)
            if 'datafl-sc' in extend.keys():
                datafl = urllib.parse.quote(extend['datafl-sc'])
            if 'datanf-year' in extend.keys():
                year = extend['datanf-year']
            if 'dataszm-letter' in extend.keys():
                letter = extend['dataszm-letter']
            url = 'https://api.cntv.cn/list/getVideoAlbumList?channelid=CHAL1460955853485115&area={0}&sc={1}&fc={2}&year={3}&letter={4}&p={5}&n=24&serviceId=tvcctv&topv=1&t=json'.format(area, datafl, id, year, letter, pg)
        else:
            # 如果意外传入其他 tid，返回空列表
            result['list'] = []
            result['page'] = pg
            result['pagecount'] = 0
            result['limit'] = 90
            result['total'] = 0
            return result

        videos = []
        htmlText = self.webReadFile(urlStr=url, header=self.header)
        # 注意：节目大全分支已移除，故这里直接调用 get_list
        videos = self.get_list(html=htmlText, tid=tid)

        result['list'] = videos
        result['page'] = pg
        result['pagecount'] = 9999 if len(videos) >= pagecount else pg
        result['limit'] = 90
        result['total'] = 999999
        return result

    def detailContent(self,array):
        result={}
        aid = array[0].split('###')
        tid = aid[0]
        logo = aid[3]
        lastVideo = aid[2]
        title = aid[1]
        id = aid[4]
        
        vod_year = aid[5]
        actors = aid[6]
        brief = aid[7]
        fromId = 'CCTV'
        # 由于节目大全已移除，不再处理该分支，仅保留通用逻辑
        Url = 'https://api.cntv.cn/NewVideo/getVideoListByAlbumIdNew?id={0}&serviceId=tvcctv&p=1&n=100&mode=0&pub=1'.format(id)
        videoList = []
        try:
            if tid == "搜索":
                fromId = '中央台'
                videoList = [title + "$" + lastVideo]
            else:
                htmlTxt = self.webReadFile(urlStr=Url, header=self.header)
                jRoot = json.loads(htmlTxt)
                data = jRoot['data']
                jsonList = data['list']
                videoList = self.get_EpisodesList(jsonList=jsonList)
                if len(videoList) < 1:
                    htmlTxt = self.webReadFile(urlStr=lastVideo, header=self.header)
                    if tid == "电视剧" or tid == "纪录片":
                        patternTxt = r"'title':\s*'(?P<title>.+?)',\n{0,1}\s*'brief':\s*'(.+?)',\n{0,1}\s*'img':\s*'(.+?)',\n{0,1}\s*'url':\s*'(?P<url>.+?)'"
                    elif tid == "动画片":
                        patternTxt = r"'title':\s*'(?P<title>.+?)',\n{0,1}\s*'img':\s*'(.+?)',\n{0,1}\s*'brief':\s*'(.+?)',\n{0,1}\s*'url':\s*'(?P<url>.+?)'"
                    else:
                        patternTxt = r"'title':\s*'(?P<title>.+?)',\n{0,1}\s*'img':\s*'(.+?)',\n{0,1}\s*'brief':\s*'(.+?)',\n{0,1}\s*'url':\s*'(?P<url>.+?)'"
                    videoList = self.get_EpisodesList_re(htmlTxt=htmlTxt, patternTxt=patternTxt)
                    fromId = '央视'
        except:
            pass
        if len(videoList) == 0:
            return {}
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
            "vod_content": brief
        }
        vod['vod_play_from'] = fromId
        vod['vod_play_url'] = "#".join(videoList)
        result = {'list': [vod]}
        return result

    # 辅助函数（均未改动）
    def get_lineList(self,Txt,mark,after):
        circuit=[]
        origin=Txt.find(mark)
        while origin>8:
            end=Txt.find(after,origin)
            circuit.append(Txt[origin:end])
            origin=Txt.find(mark,end)
        return circuit    
    def get_RegexGetTextLine(self,Text,RegexText,Index):
        returnTxt=[]
        pattern = re.compile(RegexText, re.M|re.S)
        ListRe=pattern.findall(Text)
        if len(ListRe)<1:
            return returnTxt
        for value in ListRe:
            returnTxt.append(value)    
        return returnTxt

    def searchContent(self,key,quick):
        key=urllib.parse.quote(key)
        Url='https://search.cctv.com/ifsearch.php?page=1&qtext={0}&sort=relevance&pageSize=20&type=video&vtime=-1&datepid=1&channel=&pageflag=0&qtext_str={0}'.format(key)
        htmlTxt=self.webReadFile(urlStr=Url,header=self.header)
        videos=self.get_list_search(html=htmlTxt,tid='搜索')
        result = {'list': videos}
        return result

    # 修改 playerContent：直接返回 id，parse=0（保持去除解析）
    def playerContent(self, flag, id, vipFlags):
        result = {}
        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 9_1 like Mac OS X) AppleWebKit/601.1.46 (KHTML, like Gecko) Version/9.0 Mobile/13B143 Safari/601.1'
        }
        result["parse"] = 0
        result["playUrl"] = ''
        result["url"] = id
        result["header"] = headers
        return result

    # 配置文件：只保留三个分类的筛选
    config = {
        "player": {},
        "filter": {
            "电视剧": [
                {"key":"datafl-sc","name":"类型","value":[{"n":"全部","v":""},{"n":"谍战","v":"谍战"},{"n":"悬疑","v":"悬疑"},{"n":"刑侦","v":"刑侦"},{"n":"历史","v":"历史"},{"n":"古装","v":"古装"},{"n":"武侠","v":"武侠"},{"n":"军旅","v":"军旅"},{"n":"战争","v":"战争"},{"n":"喜剧","v":"喜剧"},{"n":"青春","v":"青春"},{"n":"言情","v":"言情"},{"n":"偶像","v":"偶像"},{"n":"家庭","v":"家庭"},{"n":"年代","v":"年代"},{"n":"革命","v":"革命"},{"n":"农村","v":"农村"},{"n":"都市","v":"都市"},{"n":"其他","v":"其他"}]},
                {"key":"datadq-area","name":"地区","value":[{"n":"全部","v":""},{"n":"中国大陆","v":"中国大陆"},{"n":"中国香港","v":"香港"},{"n":"美国","v":"美国"},{"n":"欧洲","v":"欧洲"},{"n":"泰国","v":"泰国"}]},
                {"key":"datanf-year","name":"年份","value":[{"n":"全部","v":""},{"n":"2023","v":"2023"},{"n":"2022","v":"2022"},{"n":"2021","v":"2021"},{"n":"2020","v":"2020"},{"n":"2019","v":"2019"},{"n":"2018","v":"2018"},{"n":"2017","v":"2017"},{"n":"2016","v":"2016"},{"n":"2015","v":"2015"},{"n":"2014","v":"2014"},{"n":"2013","v":"2013"},{"n":"2012","v":"2012"},{"n":"2011","v":"2011"},{"n":"2010","v":"2010"},{"n":"2009","v":"2009"},{"n":"2008","v":"2008"},{"n":"2007","v":"2007"},{"n":"2006","v":"2006"},{"n":"2005","v":"2005"},{"n":"2004","v":"2004"},{"n":"2003","v":"2003"},{"n":"2002","v":"2002"},{"n":"2001","v":"2001"},{"n":"2000","v":"2000"},{"n":"1999","v":"1999"},{"n":"1998","v":"1998"},{"n":"1997","v":"1997"}]},
                {"key":"dataszm-letter","name":"字母","value":[{"n":"全部","v":""},{"n":"A","v":"A"},{"n":"C","v":"C"},{"n":"E","v":"E"},{"n":"F","v":"F"},{"n":"G","v":"G"},{"n":"H","v":"H"},{"n":"I","v":"I"},{"n":"J","v":"J"},{"n":"K","v":"K"},{"n":"L","v":"L"},{"n":"M","v":"M"},{"n":"N","v":"N"},{"n":"O","v":"O"},{"n":"P","v":"P"},{"n":"Q","v":"Q"},{"n":"R","v":"R"},{"n":"S","v":"S"},{"n":"T","v":"T"},{"n":"U","v":"U"},{"n":"V","v":"V"},{"n":"W","v":"W"},{"n":"X","v":"X"},{"n":"Y","v":"Y"},{"n":"Z","v":"Z"},{"n":"0-9","v":"0-9"}]}
            ],
            "动画片": [
                {"key":"datafl-sc","name":"类型","value":[{"n":"全部","v":""},{"n":"亲子","v":"亲子"},{"n":"搞笑","v":"搞笑"},{"n":"冒险","v":"冒险"},{"n":"动作","v":"动作"},{"n":"宠物","v":"宠物"},{"n":"体育","v":"体育"},{"n":"益智","v":"益智"},{"n":"历史","v":"历史"},{"n":"教育","v":"教育"},{"n":"校园","v":"校园"},{"n":"言情","v":"言情"},{"n":"武侠","v":"武侠"},{"n":"经典","v":"经典"},{"n":"未来","v":"未来"},{"n":"古代","v":"古代"},{"n":"神话","v":"神话"},{"n":"真人","v":"真人"},{"n":"励志","v":"励志"},{"n":"热血","v":"热血"},{"n":"奇幻","v":"奇幻"},{"n":"童话","v":"童话"},{"n":"剧情","v":"剧情"},{"n":"夺宝","v":"夺宝"},{"n":"其他","v":"其他"}]},
                {"key":"datadq-area","name":"地区","value":[{"n":"全部","v":""},{"n":"中国大陆","v":"中国大陆"},{"n":"美国","v":"美国"},{"n":"欧洲","v":"欧洲"}]},
                {"key":"dataszm-letter","name":"字母","value":[{"n":"全部","v":""},{"n":"A","v":"A"},{"n":"C","v":"C"},{"n":"E","v":"E"},{"n":"F","v":"F"},{"n":"G","v":"G"},{"n":"H","v":"H"},{"n":"I","v":"I"},{"n":"J","v":"J"},{"n":"K","v":"K"},{"n":"L","v":"L"},{"n":"M","v":"M"},{"n":"N","v":"N"},{"n":"O","v":"O"},{"n":"P","v":"P"},{"n":"Q","v":"Q"},{"n":"R","v":"R"},{"n":"S","v":"S"},{"n":"T","v":"T"},{"n":"U","v":"U"},{"n":"V","v":"V"},{"n":"W","v":"W"},{"n":"X","v":"X"},{"n":"Y","v":"Y"},{"n":"Z","v":"Z"},{"n":"0-9","v":"0-9"}]}
            ],
            "纪录片": [
                {"key":"datapd-channel","name":"频道","value":[{"n":"全部","v":""},{"n":"CCTV{1 综合","v":"CCTV{1 综合"},{"n":"CCTV{2 财经","v":"CCTV{2 财经"},{"n":"CCTV{3 综艺","v":"CCTV{3 综艺"},{"n":"CCTV{4 中文国际","v":"CCTV{4 中文国际"},{"n":"CCTV{5 体育","v":"CCTV{5 体育"},{"n":"CCTV{6 电影","v":"CCTV{6 电影"},{"n":"CCTV{7 国防军事","v":"CCTV{7 国防军事"},{"n":"CCTV{8 电视剧","v":"CCTV{8 电视剧"},{"n":"CCTV{9 纪录","v":"CCTV{9 纪录"},{"n":"CCTV{10 科教","v":"CCTV{10 科教"},{"n":"CCTV{11 戏曲","v":"CCTV{11 戏曲"},{"n":"CCTV{12 社会与法","v":"CCTV{12 社会与法"},{"n":"CCTV{13 新闻","v":"CCTV{13 新闻"},{"n":"CCTV{14 少儿","v":"CCTV{14 少儿"},{"n":"CCTV{15 音乐","v":"CCTV{15 音乐"},{"n":"CCTV{17 农业农村","v":"CCTV{17 农业农村"}]},
                {"key":"datafl-sc","name":"类型","value":[{"n":"全部","v":""},{"n":"人文历史","v":"人文历史"},{"n":"人物","v":"人物"},{"n":"军事","v":"军事"},{"n":"探索","v":"探索"},{"n":"社会","v":"社会"},{"n":"时政","v":"时政"},{"n":"经济","v":"经济"},{"n":"科技","v":"科技"}]},
                {"key":"datanf-year","name":"年份","value":[{"n":"全部","v":""},{"n":"2023","v":"2023"},{"n":"2022","v":"2022"},{"n":"2021","v":"2021"},{"n":"2020","v":"2020"},{"n":"2019","v":"2019"},{"n":"2018","v":"2018"},{"n":"2017","v":"2017"},{"n":"2016","v":"2016"},{"n":"2015","v":"2015"},{"n":"2014","v":"2014"},{"n":"2013","v":"2013"},{"n":"2012","v":"2012"},{"n":"2011","v":"2011"},{"n":"2010","v":"2010"},{"n":"2009","v":"2009"},{"n":"2008","v":"2008"}]},
                {"key":"dataszm-letter","name":"字母","value":[{"n":"全部","v":""},{"n":"A","v":"A"},{"n":"C","v":"C"},{"n":"E","v":"E"},{"n":"F","v":"F"},{"n":"G","v":"G"},{"n":"H","v":"H"},{"n":"I","v":"I"},{"n":"J","v":"J"},{"n":"K","v":"K"},{"n":"L","v":"L"},{"n":"M","v":"M"},{"n":"N","v":"N"},{"n":"O","v":"O"},{"n":"P","v":"P"},{"n":"Q","v":"Q"},{"n":"R","v":"R"},{"n":"S","v":"S"},{"n":"T","v":"T"},{"n":"U","v":"U"},{"n":"V","v":"V"},{"n":"W","v":"W"},{"n":"X","v":"X"},{"n":"Y","v":"Y"},{"n":"Z","v":"Z"},{"n":"0-9","v":"0-9"}]}
            ]
        }
    }

    header = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.54 Safari/537.36",
        "Host": "tv.cctv.com",
        "Referer": "https://tv.cctv.com/"
    }
    
    def localProxy(self,param):
        return [200, "video/MP2T", action, ""]

    # ----------------------------------------------- 自定义函数 -----------------------------------------------
    def format_title(self, title):
        if not title:
            return title
        match = re.search(r'《(.+?)》', title)
        if match:
            return match.group(1)
        else:
            return title

    def webReadFile(self, urlStr, header):
        html = ''
        req = urllib.request.Request(url=urlStr)  # headers=header 可加可不加
        with urllib.request.urlopen(req) as response:
            html = response.read().decode('utf-8')
        return html

    def TestWebPage(self, urlStr, header):
        html = ''
        req = urllib.request.Request(url=urlStr, method='HEAD')
        with urllib.request.urlopen(req) as response:
            html = response.getcode()
        return html

    def get_RegexGetText(self, Text, RegexText, Index):
        returnTxt = ""
        Regex = re.search(RegexText, Text, re.M|re.S)
        if Regex is None:
            returnTxt = ""
        else:
            returnTxt = Regex.group(Index)
        return returnTxt

    def get_EpisodesList(self, jsonList):
        videos = []
        for vod in jsonList:
            url = vod['guid']
            title = vod['title']
            if len(url) == 0:
                continue
            videos.append(title + "$" + url)
        return videos

    def get_EpisodesList_re(self, htmlTxt, patternTxt):
        ListRe = re.finditer(patternTxt, htmlTxt, re.M|re.S)
        videos = []
        for vod in ListRe:
            url = vod.group('url')
            title = vod.group('title')
            if len(url) == 0:
                continue
            videos.append(title + "$" + url)
        return videos

    def get_lineList(self, Txt, mark, after):
        circuit = []
        origin = Txt.find(mark)
        while origin > 8:
            end = Txt.find(after, origin)
            circuit.append(Txt[origin:end])
            origin = Txt.find(mark, end)
        return circuit

    def get_RegexGetTextLine(self, Text, RegexText, Index):
        returnTxt = []
        pattern = re.compile(RegexText, re.M|re.S)
        ListRe = pattern.findall(Text)
        if len(ListRe) < 1:
            return returnTxt
        for value in ListRe:
            returnTxt.append(value)
        return returnTxt

    def removeHtml(self, txt):
        soup = re.compile(r'<[^>]+>', re.S)
        txt = soup.sub('', txt)
        return txt.replace("&nbsp;", " ")

    def get_m3u8(self, urlTxt):
        # 此方法已不再使用，保留以免依赖
        url = "https://vdn.apps.cntv.cn/api/getHttpVideoInfo.do?pid={0}".format(urlTxt)
        html = self.webReadFile(urlStr=url, header=self.header)
        jo = json.loads(html)
        link = jo['hls_url'].strip()
        html = self.webReadFile(urlStr=link, header=self.header)
        content = html.strip()
        arr = content.split('\n')
        urlPrefix = self.get_RegexGetText(Text=link, RegexText='(http[s]?://[a-zA-z0-9.]+)/', Index=1)
        subUrl = arr[-1].split('/')
        subUrl[3] = '1200'
        subUrl[-1] = '1200.m3u8'
        hdUrl = urlPrefix + '/'.join(subUrl)
        url = urlPrefix + arr[-1]
        hdRsp = self.TestWebPage(urlStr=hdUrl, header=self.header)
        if hdRsp == 200:
            url = hdUrl
        else:
            url = ''
        return url

    def get_list_search(self, html, tid):
        jRoot = json.loads(html)
        jsonList = jRoot['list']
        videos = []
        for vod in jsonList:
            url = vod['urllink']
            title = self.removeHtml(txt=vod['title'])
            title = self.format_title(title)
            img = vod['imglink']
            id = vod['id']
            brief = vod['channel']
            year = vod['uploadtime']
            if len(url) == 0:
                continue
            guid = "{0}###{1}###{2}###{3}###{4}###{5}###{6}###{7}".format(tid, title, url, img, id, year, '', brief)
            videos.append({
                "vod_id": guid,
                "vod_name": title,
                "vod_pic": img,
                "vod_remarks": year
            })
        return videos

    def get_list1(self, html, tid):
        # 此方法原用于节目大全，现保留但不会被调用
        jRoot = json.loads(html)
        videos = []
        data = jRoot['response']
        if data is None:
            return []
        jsonList = data['docs']
        for vod in jsonList:
            id = vod['lastVIDE']['videoSharedCode']
            title = vod['column_name']
            title = self.format_title(title)
            url = vod['column_website']
            img = vod['column_logo']
            year = vod['column_playdate']
            brief = vod['column_brief']
            actors = ''
            if len(url) == 0:
                continue
            guid = "{0}###{1}###{2}###{3}###{4}###{5}###{6}###{7}".format(tid, title, url, img, id, year, actors, brief)
            videos.append({
                "vod_id": guid,
                "vod_name": title,
                "vod_pic": img,
                "vod_remarks": ''
            })
        return videos

    def get_list(self, html, tid):
        jRoot = json.loads(html)
        videos = []
        data = jRoot['data']
        if data is None:
            return []
        jsonList = data['list']
        for vod in jsonList:
            url = vod['url']
            title = vod['title']
            title = self.format_title(title)
            img = vod['image']
            id = vod['id']
            try:
                brief = vod['brief']
            except:
                brief = ''
            try:
                year = vod['year']
            except:
                year = ''
            try:
                actors = vod['actors']
            except:
                actors = ''
            if len(url) == 0:
                continue
            guid = "{0}###{1}###{2}###{3}###{4}###{5}###{6}###{7}".format(tid, title, url, img, id, year, actors, brief)
            videos.append({
                "vod_id": guid,
                "vod_name": title,
                "vod_pic": img,
                "vod_remarks": ''
            })
        return videos