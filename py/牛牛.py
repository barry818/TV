# -*- coding: utf-8 -*-
# 本资源来源于互联网公开渠道，仅可用于个人学习爬虫技术。
# 严禁将其用于任何商业用途，下载后请于 24 小时内删除，搜索结果均来自源站，本人不承担任何责任。

from base.spider import Spider
from Crypto.Cipher import AES, DES3
from Crypto.Util.Padding import unpad
from urllib.parse import quote, unquote, urljoin, urlparse
import re, sys, time, json, random, base64, hashlib, urllib3, uuid
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
sys.path.append('..')

class Spider(Spider):
    headers, player_src, host, proxyurl, parser, src, device_ids = {
        'User-Agent': 'Dart/3.9 (dart:io)',
        'Connection': 'Keep-Alive',
        'Accept-Encoding': 'gzip',
        'p': 'android',
        'product': 'M973Q',
        'content-type': 'application/json',                
        't': '',
        'd': 'c804d515-76a5-58b3-a5f9-4658558dd34c',
        'os': '9',
        'v': '1.5.8',
        'y': '1',
        'pkg': 'com.tencent.tmgp.cn.jj.chess2.hd.sh'
    }, {'src2': {'map_list': {}}, 'src1': {'vod_collection': {}}, 'src7': {'vod_collection': {}}}, '', '', [], {}, {}
    play_headers = {'User-Agent': 'Mozi', 'Connection': 'Keep-Alive', 'Accept-Encoding': 'gzip'}

    def init(self, extend=''):
        try:
            if isinstance(extend, dict):
                host = extend.get('host') or extend.get('url') or ''
            else:
                host = (extend or '').strip()
                try:
                    if host.startswith('{'):
                        host = json.loads(host).get('host') or json.loads(host).get('url') or ''
                except Exception:
                    pass
            if not host.startswith('http'):
                host = 'https://hdal.oss-cn-beijing.aliyuncs.com/xg.php'
            
            host_list = []
            self.init_error = '' # 初始化错误收集器
            
            # 加入时间戳，防止某些接口需要动态校验
            self.headers['t'] = str(int(time.time() * 1000))
            
            if not re.match(r'^https?://[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)*(:\d+)?/?$', host):
                try:
                    response = self.fetch(host, headers=self.headers, verify=False).text
                    if response:
                        host_data = self.decrypt(response.strip(), '@@bull!!!video$$')
                        addresses = host_data.split('\n')
                        host_list = [addr.strip() for addr in addresses if addr.strip()]
                    else:
                        self.init_error = 'xg.php returned empty'
                except Exception as e:
                    self.init_error = f'xg_err: {str(e)[:25]}'
            else:
                host_list = [host]

            if not host_list: 
                return None

            self.proxyurl = f'{self.getProxyUrl(True)}&type=niuniusp'
            self.device_ids['hema'] = '1a9591d8d9ba8feb'
            self.device_ids['xm3u8'] = 'nocache'
            self.device_ids['xiaocao'] = '57a94504c76d7143'
            
            path = '/config'
            config_success = False
            
            for current_host in host_list:
                try:
                    self.host = current_host.rstrip('/')
                    response = self.fetch(self.host + path, headers=self.headers, verify=False).text
                    if not response:
                        self.init_error = 'config returned empty'
                        continue
                    data_ = self.decrypt(response.strip(), path)
                    data = json.loads(data_)['data']
                    self.parser = data['parser']
                    self.src['src1'] = data['src1']
                    self.src['src2'] = data['src2']
                    self.src['src7'] = data['src7']
                    for _s in ('src3', 'src4', 'src5'):
                        self.src[_s] = data.get(_s, {})
                    config_success = True
                    self.init_error = ''
                    break
                except Exception as e:
                    self.init_error = f'cfg_err: {str(e)[:25]}'
                    continue
            
            if not config_success:
                self.host = '' # 失败清空 host
            return None
        except Exception as e:
            self.init_error = f'init_fatal: {str(e)[:25]}'
            return None

    # ==================== 筛选逻辑已完全套用牛牛视频 ====================
    def homeContent(self, filter):
        # 错误可视化拦截
        if not getattr(self, 'host', ''):
            err = getattr(self, 'init_error', 'Host Empty')
            return {'class': [{'type_id': 'err', 'type_name': f'InitErr: {err}'}]}
        
        try:
            path = '/types'
            response = self.fetch(self.host + path, headers=self.headers, verify=False).text
            data_ = self.decrypt(response.strip(), path)
            data = json.loads(data_)['data']
            classes = []
            # 需要过滤的分类名称（增加“直播”）
            exclude_names = ['热舞', '传媒', '吃瓜', '福利', '午夜', '直播']
            for i in data:
                if isinstance(i, dict):
                    type_name = i.get('type_name', '')
                    if type_name not in exclude_names:
                        classes.append({'type_id': i['type_id'], 'type_name': type_name})
            
            if not classes:
                return {'class': [{'type_id': 'err', 'type_name': 'Api returned no classes'}]}
            
            # 增加全局筛选参数（完全采用牛牛视频的筛选配置）
            filter_dict = {}
            for cls in classes:
                filter_dict[cls['type_id']] = [
                    {"key": "class", "name": "类型", "value": [{"n": "全部", "v": ""}, {"n": "喜剧", "v": "喜剧"}, {"n": "爱情", "v": "爱情"}, {"n": "动作", "v": "动作"}, {"n": "科幻", "v": "科幻"}, {"n": "剧情", "v": "剧情"}, {"n": "战争", "v": "战争"}, {"n": "警匪", "v": "警匪"}, {"n": "犯罪", "v": "犯罪"}, {"n": "动画", "v": "动画"}, {"n": "奇幻", "v": "奇幻"}, {"n": "武侠", "v": "武侠"}, {"n": "冒险", "v": "冒险"}, {"n": "恐怖", "v": "恐怖"}, {"n": "悬疑", "v": "悬疑"}]},
                    {"key": "area", "name": "地区", "value": [{"n": "全部", "v": ""}, {"n": "大陆", "v": "大陆"}, {"n": "香港", "v": "香港"}, {"n": "台湾", "v": "台湾"}, {"n": "美国", "v": "美国"}, {"n": "法国", "v": "法国"}, {"n": "英国", "v": "英国"}, {"n": "日本", "v": "日本"}, {"n": "韩国", "v": "韩国"}, {"n": "泰国", "v": "泰国"}, {"n": "印度", "v": "印度"}, {"n": "其他", "v": "其他"}]},
                    {"key": "year", "name": "年份", "value": [{"n": "全部", "v": ""}, {"n": "2024", "v": "2024"}, {"n": "2023", "v": "2023"}, {"n": "2022", "v": "2022"}, {"n": "2021", "v": "2021"}, {"n": "2020", "v": "2020"}, {"n": "2019", "v": "2019"}, {"n": "2018", "v": "2018"}, {"n": "2017", "v": "2017"}, {"n": "2016", "v": "2016"}, {"n": "2015", "v": "2015"}, {"n": "2014", "v": "2014"}, {"n": "2013", "v": "2013"}, {"n": "2012", "v": "2012"}, {"n": "2011", "v": "2011"}, {"n": "2010", "v": "2010"}]},
                    {"key": "order", "name": "排序", "value": [{"n": "最新", "v": "最新"}, {"n": "最热", "v": "最热"}, {"n": "评分", "v": "评分"}]}
                ]
            
            return {'class': classes, 'filters': filter_dict}
        except Exception as e:
            return {'class': [{'type_id': 'err', 'type_name': f'HomeErr: {str(e)[:25]}'}]}
    # ==================== 筛选逻辑套用结束 ====================

    def homeVideoContent(self):
        if not getattr(self, 'host', ''): return {'list': []}
        try:
            path = '/main'
            response = self.fetch(self.host + path, headers=self.headers, verify=False).text
            data_ = self.decrypt(response.strip(), path)
            data = json.loads(data_)['data']
            videos = []
            for i in data:
                for j in i.get('list', []):
                    videos.append({
                        'vod_id': j.get('vod_id', ''),
                        'vod_name': j.get('vod_name', ''),
                        'vod_pic': j.get('vod_pic', ''),
                        'vod_remarks': j.get('vod_remarks', ''),
                        'vod_year': j.get('vod_year', '')
                    })
            return {'list': videos}
        except Exception:
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        if not getattr(self, 'host', ''): return None
        # 如果是点击了报错信息的分类，拦截防止闪退
        if tid == 'err': return {'list': [], 'page': pg}
        
        # 提取筛选器传入的多选参数
        extend = extend or {}
        cls = extend.get('class', '')
        order = extend.get('order', '最新')
        area = extend.get('area', '')
        year = extend.get('year', '')
        state = extend.get('state', '')
        
        path = f'/list?class={quote(cls)}&order={quote(order)}&type_id={tid}&area={quote(area)}&year={quote(year)}&state={quote(state)}&wd=&page={pg}'
        try:
            response = self.fetch(self.host + path, headers=self.headers, verify=False).text
            data_ = self.decrypt(response.strip(), path)
            data = json.loads(data_)['data']
            if not data:
                return {'list': [], 'page': pg, 'pagecount': pg}
            return {'list': data, 'page': pg, 'pagecount': int(pg) + 1, 'limit': len(data), 'total': len(data) * int(pg)}
        except Exception:
            return {'list': [], 'page': pg, 'pagecount': pg}

    def searchContent(self, key, quick, pg='1'):
        if not getattr(self, 'host', ''): return None
        path = f'/list?class=&order=&type_id=&area=&year=&state=&wd={quote(key)}&page={pg}'
        try:
            response = self.fetch(self.host + path, headers=self.headers, verify=False).text
            data_ = self.decrypt(response.strip(), path)
            data = json.loads(data_)['data']
            for i in data:
                vod_content = i.get('vod_content')
                vod_blurb = i.get('vod_blurb')
                if not vod_content and vod_blurb:
                    i['vod_content'] = vod_blurb
            return {'list': data, 'page': pg}
        except Exception:
            return {'list': [], 'page': pg}

    def detailContent(self, ids):
        if not getattr(self, 'host', ''): return None
        path = f'/detail?vod_id={ids[0]}'
        try:
            response = self.fetch(self.host + path, headers=self.headers, verify=False).text
            data_ = self.decrypt(response.strip(), path)
            data = json.loads(data_)['data']
        except Exception:
            return {'list': []}
        
        play_from, play_urls = [], []
        for i in data['sources']:
            player_id = i['player_id']
            if player_id in ('xiaocao', 'shizi', 'hema'):
                continue
            found = False
            for i2 in self.parser:
                if i2['player_id'] == player_id:
                    if i2['player_name'].endswith('）'):
                        show = f"{i2['player_name']}({player_id})"
                    else:
                        show = f"{i2['player_name']}\u2005({player_id})"
                    play_from.append(show)
                    found = True
                    break
            if not found:
                play_from.append(player_id)
            play_url = []
            for j in i['episodes']:
                url = j['url']
                play_url.append(f"{j['name']}${player_id},{url}")
            play_urls.append('#'.join(play_url))
        video = {
            'vod_id': data['vod_id'],
            'vod_name': data['vod_name'],
            'vod_pic': data['vod_pic'],
            'vod_remarks': data['vod_remarks'],
            'vod_year': data['vod_year'],
            'vod_area': data['vod_area'],
            'vod_actor': data['vod_actor'],
            'vod_director': data['vod_director'],
            'vod_content': data['vod_content'],
            'vod_play_from': '$$$'.join(play_from),
            'vod_play_url': '$$$'.join(play_urls)
        }
        return {'list': [video]}

    def playerContent(self, flag, id, vipflags):
        play_from, raw_url = id.split(',', 1)
        url, headers = '', {}

        # 处理 MacCMS 常见的 url 编码或 Base64 加密
        try:
            if '%' in raw_url and not raw_url.startswith('http'):
                raw_url = unquote(raw_url)
            if not raw_url.startswith('http') and re.match(r'^[A-Za-z0-9+/=]+$', raw_url):
                decoded = base64.b64decode(raw_url).decode('utf-8')
                raw_url = unquote(decoded)
        except Exception:
            pass

        if play_from == 'hema':
            res = self.src2(raw_url)
            if not isinstance(res, dict):
                return {'jx': '0', 'parse': '0', 'url': '', 'header': self.play_headers}
            url, headers = res['url'], res.get('headers', {})
        elif play_from in ('xm3u8', 'xiaocao'):
            res = self.src1(play_from, raw_url)
            if not isinstance(res, dict):
                return {'jx': '0', 'parse': '0', 'url': '', 'header': self.play_headers}
            url, headers = res['url'], res.get('headers', {})
        else:
            is_direct_video = re.search(r'\.(m3u8|mp4|mkv|flv|avi|mov|wmv|webm)(\?.*)?$', raw_url, re.I)
            
            if is_direct_video:
                url = raw_url
                headers = self.play_headers
            else:
                parser = next((p for p in self.parser if p['player_id'] == play_from), None)
                if parser and parser.get('url'):
                    try:
                        headers = {item["key"]: item["value"] for item in parser.get('headers', [])}
                        no_parse_rule = parser.get('no_parse_rule')
                        if not(no_parse_rule and any(rule in raw_url for rule in no_parse_rule.split(','))):
                            if 'jz2' in parser['url'] or 'jz3' in parser['url'] or '高端' in parser.get('player_name', '') or play_from == 'yynb':
                                api_url = parser['url'].split('?')[0]
                                payload = {"nndata": raw_url}
                                b64_data = base64.b64encode(json.dumps(payload).encode('utf-8')).decode('utf-8')
                                post_headers = self.headers.copy()
                                post_headers['Content-Type'] = 'application/json; charset=UTF-8'
                                response = self.post(api_url, data=b64_data, headers=post_headers, verify=False).json()
                                url = response.get('url', '')
                                jx_headers = response.get('headers', '')
                            else:
                                api_url = parser['url'].replace('%s', raw_url)
                                response = self.fetch(api_url, headers=self.headers, verify=False).json()
                                url = response.get('url', '')
                                jx_headers = response.get('headers', '')

                            if jx_headers and isinstance(jx_headers, str):
                                headers = {}
                                for line in jx_headers.splitlines():
                                    if ':' in line:
                                        key, val = line.split(':', 1)
                                        headers[key.strip()] = val.strip()
                    except Exception:
                        url = ''

                if not url and raw_url.startswith('http'):
                    try:
                        parser_url = f"https://svip.qlplayer.cyou/?url={quote(raw_url)}"
                        parser_res = self.fetch(parser_url, headers=self.headers, verify=False).text
                        token_match = re.search(r'apiToken:\s*"([^"]+)"', parser_res)
                        if token_match:
                            api_token = token_match.group(1)
                            resolve_url = f"https://svip.qlplayer.cyou/api/resolve.php?token={quote(api_token)}"
                            resolve_res = self.fetch(resolve_url, headers=self.headers, verify=False).json()
                            if resolve_res.get('code') == 200 and resolve_res.get('url'):
                                url = resolve_res.get('url').replace('\\/', '/')
                                headers = self.play_headers
                    except Exception:
                        pass

                if not url:
                    url = self.src3_parse(raw_url)
                    if url:
                        headers = self.play_headers

        return {'jx': '0', 'parse': '0', 'url': url, 'header': headers or self.play_headers}

    def localProxy(self, params):
        if params['type'] == "niuniusp":
            return self.niuniu_m3u8_proxy(params)
        return None

    def src1(self, play_from, video_url):
        video_id, collection = video_url.split('@', 1)
        device_id = ''
        if play_from == 'xm3u8':
            src_type = 'src1'
            device_id = self.device_ids.get(play_from)
        elif play_from == 'xiaocao':
            src_type = 'src7'
            device_id = self.device_ids.get(play_from)
        nocache = 1 if device_id == 'nocache' else 0
        if not(bool(device_id) and len(device_id) == 16):
            device_id = self.random_device_id()
        tokenUrl = self.src[src_type]['tokenUrl']
        listUrl = self.src[src_type]['listUrl']
        detailUrl = self.src[src_type]['detailUrl']
        playerHeaders = {item["key"]: item["value"] for item in self.src[src_type]['playerHeaders']}
        main_header = {item["key"]: item["value"] for item in self.src[src_type]['headers']}
        headers2 = main_header.copy()
        cur_time = str(int(time.time() * 1000))
        sign = self.md5(f"{self.src[src_type]['salt']}{device_id}{cur_time}").upper()
        headers2.update({
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
            'sys_platform': "2",
            'device_id': device_id,
            'sign': sign,
            'cur_time': cur_time,
            'mobmodel': "xiaomi",
            'token': "",
            'log-header': "I am the log request header.",
            'mob_mfr': "xiaomi",
        })
        token = self.player_src.get(src_type, {}).get('token')
        if not token or nocache:
            response = self.post(tokenUrl, data='invited_by=&is_install=1', headers=headers2, verify=False).text
            data_ = self.aes_cbc_decrypt(response.strip(), self.src[src_type]['key'], self.src[src_type]['iv'])
            data = json.loads(data_).get('result', {})
            if src_type not in self.player_src:
                self.player_src[src_type] = {}
            token = data.get('user_info', {}).get('token', '')
            if not nocache and token: self.player_src[src_type]['token'] = token
        list_header = headers2.copy()
        cur_time = str(int(time.time() * 1000))
        sign = self.md5(f"{self.src[src_type]['salt']}{device_id}{cur_time}").upper()
        list_header.update({
            'sign': sign,
            'cur_time': cur_time,
            'token': token,
        })
        vod_collection = self.player_src[src_type]['vod_collection'].get(video_id)
        if not vod_collection or nocache:
            payload = {
                'sig': "",
                'nc_token': "",
                'code': "",
                'phone': "",
                'vod_id': video_id,
                'session_id': "",
                'cur_time': str(int(time.time() * 1000))
            }
            response = self.post(listUrl, data=payload, headers=list_header, verify=False).text
            data_ = self.aes_cbc_decrypt(response.strip(), self.src[src_type]['key'], self.src[src_type]['iv'])
            vod_collection = json.loads(data_).get('result', {}).get('vod_collection', [])
            if not nocache: self.player_src[src_type]['vod_collection'][video_id] = vod_collection
        collection_id, vod_token, collection_cur_time = None, None, None
        for i in vod_collection:
            if str(i['collection']) == collection:
                collection_id = i['id']
                vod_token = i['vod_token']
                collection_cur_time = i['cur_time']
                break
        if not (collection_id and vod_token and collection_cur_time):
            return {'url': '', 'headers': playerHeaders}
        payload = {
            'collection_id': collection_id,
            'sig': "",
            'nc_token': "",
            'code': "",
            'phone': "",
            'vod_id': video_id,
            'session_id': "",
            'vod_token': vod_token,
            'cur_time': collection_cur_time
        }
        header3 = list_header.copy()
        cur_time = str(int(time.time() * 1000))
        sign = self.md5(f"{self.src[src_type]['salt']}{device_id}{cur_time}").upper()
        header3.update({
            'sign': sign,
            'cur_time': cur_time,
            'token': token,
        })
        response = self.post(detailUrl, data=payload, headers=header3, verify=False).text
        data = self.aes_cbc_decrypt(response.strip(), self.src[src_type]['key'], self.src[src_type]['iv'])
        result = json.loads(data).get('result', {})
        if not isinstance(result, dict) or bool(result.get('check_page_url')):
            return {'url': 'check_page', 'headers': playerHeaders}
        vod_url = result.get('vod_url', '')
        ck_raw = result.get('ck', '')
        if ck_raw:
            try:
                ck = self.base64_decode(ck_raw)
            except Exception:
                ck = ck_raw
        else:
            ck = ''
        m3u8_url = self.proxyurl + f'&line={play_from}&url=' + quote(f"{vod_url}?{ck}",safe='')
        return {'url': m3u8_url, 'headers': playerHeaders}

    def src2(self, video_url):
        video_id, collection = video_url.split('@', 1)
        adUrl = self.src['src2']['adUrl']
        listUrl = self.src['src2']['listUrl']
        detailUrl = self.src['src2']['detailUrl']
        adBody = self.src['src2']['adBody']
        playerHeaders = {item["key"]: item["value"] for item in self.src['src2']['playerHeaders']}
        main_header = {item["key"]: item["value"] for item in self.src['src2']['headers']}
        headers2 = main_header.copy()
        headers2.update({
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
            'Content-Type': "text/plain; charset=UTF-8",
            'Device-Id': self.device_ids['hema'],
            'Cur-Time': self.timestamp(),
            'Mob-Mfr': "xiaomi",
            'Mob-Model': "xiaomi",
            'token': "",
            'timestamp': self.timestamp()
        })
        token = self.player_src.get('src2', {}).get('token')
        if not token:
            response = self.post(adUrl, data=adBody, headers=headers2, verify=False).json()
            data_ = self.des3(response['data'].strip(), self.src['src2']['key'], self.src['src2']['iv'])
            if not data_:
                return {'url': '', 'headers': playerHeaders}
            result = json.loads(data_).get('result', {})
            if 'src2' not in self.player_src:
                self.player_src['src2'] = {}
            token = result.get('user_info', {}).get('token', '')
            if token:
                self.player_src['src2']['token'] = token
            if 'sys_conf' in result:
                self.player_src['src2']['play_domain'] = result['sys_conf'].get('play_domain', '')
        list_header = main_header.copy()
        list_header.update({
            'Connection': 'Keep-Alive',
            'Accept-Encoding': 'gzip',
            'Device-Id': self.device_ids['hema'],
            'Cur-Time': self.timestamp(),
            'Mob-Mfr': 'xiaomi',
            'Mob-Model': 'xiaomi',
            'token': '',
            'timestamp': self.timestamp(),
        })
        map_list = self.player_src['src2']['map_list'].get(video_id)
        if not map_list:
            list_header['token'] = token
            response = self.post(listUrl, data={'vod_id': video_id}, headers=list_header, verify=False).json()
            data_ = self.des3(response['data'].strip(), self.src['src2']['key'], self.src['src2']['iv'])
            if not data_:
                return {'url': '', 'headers': playerHeaders}
            map_list = json.loads(data_).get('result', {}).get('map_list', [])
            self.player_src['src2']['map_list'][video_id] = map_list
        vod_map_id = None
        for i in map_list:
            if str(i['collection']) == collection:
                vod_map_id = i['id']
                break
        if not vod_map_id:  return {'url': '', 'headers': playerHeaders}
        payload = {
            'xz': "0",
            'vod_map_id': vod_map_id,
            'vod_id': video_id,
            'collection': collection
        }
        detail_header = list_header.copy()
        detail_header['token'] = token
        detail_header['timestamp'] = self.timestamp()
        response = self.post(detailUrl, data=payload, headers=detail_header, verify=False).json()
        data = self.des3(response['data'].strip(), self.src['src2']['key'], self.src['src2']['iv'])
        if not data:
            return {'url': '', 'headers': playerHeaders}
        result = json.loads(data).get('result', {})
        
        # 移植机制1：移植 check_url 拦截拦截逻辑
        if result.get('check_url'):
            return {'url': result['check_url'], 'headers': playerHeaders}
            
        vod_url = result['vod_url']
        try:
            ck = self.base64_decode(result['ck'])
        except Exception:
            ck = result['ck']
            
        # 移植机制2：对 .m3u8 与直链进行分离，精确进入本地 HLS 代理
        if vod_url and '.m3u8' in vod_url:
            m3u8_url = self.proxyurl + '&line=hema&url=' + quote(f"{vod_url}?{ck}", safe='')
            return {'url': m3u8_url, 'headers': playerHeaders}
        else:
            return {'url': vod_url, 'headers': playerHeaders}

    def decrypt(self, ciphertext_base64, key):
        key = key[:16].ljust(16, '0')
        ciphertext = base64.b64decode(ciphertext_base64)
        cipher = AES.new(key.encode('utf-8'), AES.MODE_ECB)
        plaintext = cipher.decrypt(ciphertext)
        padding_len = plaintext[-1]
        return plaintext[:-padding_len].decode('utf-8')

    def des3(self, base64_ciphertext, key, iv):
        try:
            ciphertext = base64.b64decode(base64_ciphertext)
            key_bytes = key.encode('utf-8')
            iv_bytes = iv.encode('utf-8')
            cipher = DES3.new(key_bytes, DES3.MODE_CBC, iv_bytes)
            plaintext_bytes = unpad(cipher.decrypt(ciphertext), DES3.block_size)
            return plaintext_bytes.decode('utf-8')
        except Exception:
            return None

    def aes_cbc_decrypt(self, base64_ciphertext, key, iv):
        try:
            ciphertext = base64.b64decode(base64_ciphertext)
            cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv.encode('utf-8'))
            plaintext_bytes = cipher.decrypt(ciphertext)
            padding_len = plaintext_bytes[-1]
            plaintext_bytes = plaintext_bytes[:-padding_len]
            return plaintext_bytes.decode('utf-8')
        except Exception as e:
            raise Exception(f"解密失败: {str(e)}")

    def random_device_id(self):
        hex_chars = '0123456789abcdef'
        android_id = ''.join(random.choice(hex_chars) for _ in range(16))
        return android_id

    def niuniu_m3u8_proxy(self, params):
        url = unquote(params['url'])
        line = params.get('line')
        if line == "xm3u8":
            src_type = 'src1'
        elif line == "hema":
            src_type = 'src2'
        elif line == "xiaocao":
            src_type = 'src7'
        else:
            return '未知line'
        if params.get('format') == "ts":
            # 移植机制3：完美重写 TS 分片文件的加密校验重定向
            signed_url = self.hls_sign(src_type, url)
            data = {"Location": signed_url, "Content-Length": "0"}
            return [302, "text/html; charset=utf-8", None, data]
        else:
            data = self.hema_modify_m3u8(line, url)
            return [200, "application/vnd.apple.mpegurl", data]

    def hema_modify_m3u8(self, niuniu_line, raw_url):
        if niuniu_line == "xm3u8":
            src_type = 'src1'
        elif niuniu_line == "hema":
            src_type = 'src2'
        elif niuniu_line == "xiaocao":
            src_type = 'src7'
        else:
            return '未知line'
        ck = raw_url.split('?')[1] if '?' in raw_url else ''
        
        # 移植机制4：使用全量带有校验参数的 m3u8_url 发起请求
        m3u8_url = self.hls_sign(src_type, raw_url)
        m3u8_content = self.fetch(m3u8_url, headers=self.play_headers, verify=False).text
        if not m3u8_content:
            raise ValueError("M3U8为空")
        content = m3u8_content
        parsed = urlparse(raw_url)
        base = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rsplit('/', 1)[0]}/"
        output_lines = []
        for line in content.splitlines():
            stripped_line = line.strip()
            if stripped_line and not stripped_line.startswith('#'):
                if not stripped_line.startswith(('http://', 'https://')):
                    full_url = urljoin(base, stripped_line)
                else:
                    full_url = stripped_line
                
                # 移植机制5：为每一个切片行（TS）注入原生的 ck 与代理标记
                signed_url = self.proxyurl + f'&line={niuniu_line}&format=ts&url=' + quote(full_url + ('&' + ck if ck else ''), safe='')
                output_lines.append(signed_url)
            else:
                output_lines.append(line)
        return '\n'.join(output_lines)

    def hls_sign(self, src, url):
        replaceEncryptDomain = self.src[src].get('replaceEncryptDomain', 'vT1RQRz8YzlzTgN26pIXNJ7Mi65juwSP')
        
        # 移植机制核心：如果为河马线路且已经成功捕获到动态 play_domain，则强制覆盖原有的 replaceDomain 配置
        if src == 'src2' and self.player_src.get('src2', {}).get('play_domain'):
            replaceDomain = self.player_src['src2']['play_domain']
        else:
            replaceDomain = self.src[src].get('replaceDomain', '')
            
        hex_time = self.hex_time()
        signUrl = url.split('?')[0]
        
        if replaceDomain:
            data = signUrl.replace(replaceDomain, replaceEncryptDomain) + hex_time
        else:
            data = signUrl + hex_time
            
        wsSecret = self.md5(data)
        separator = '&' if '?' in url else '?'
        return f"{url}{separator}wsSecret={wsSecret}&wsTime={hex_time}"

    def md5(self, str):
        md5_hash = hashlib.md5()
        md5_hash.update(str.encode('utf-8'))
        return md5_hash.hexdigest()

    def base64_decode(self, data):
        return base64.b64decode(data).decode('utf-8')

    def src3_parse(self, raw_url):
        try:
            cfg = self.src.get('src3') or {}
            y = cfg.get('yUrl', '')
            if not y or not raw_url:
                return ''
            response = self.fetch(y + raw_url, headers={'User-Agent': 'okhttp/4.9.0'}, verify=False)
            j = response.json()
            if not isinstance(j, dict) or j.get('type') != 'url':
                return ''
            u = j.get('url', '')
            if j.get('get') == '1':
                return u.replace('\\/', '/') if u.startswith('http') else ''
            body = j.get('body', '')
            if not (u and body):
                return ''
            headers = {}
            for line in (j.get('headers') or '').splitlines():
                if ':' in line:
                    k, v = line.split(':', 1)
                    headers[k.strip()] = v.strip()
            headers.setdefault('Referer', u.rsplit('/', 1)[0] + '/')
            headers.setdefault('User-Agent', self.play_headers.get('User-Agent', 'Mozilla/5.0'))
            resp = self.post(u, data=body, headers=headers, verify=False).text
            try:
                dec = base64.b64decode(resp[::-1].replace('-', '+').replace('_', '/')).decode('utf-8')
            except Exception:
                dec = resp
            m = re.search(r'https?://[^"\s\\]+?\.(m3u8|mp4)(\?[^"\s\\]*)?', dec)
            if m:
                return m.group(0).replace('\\/', '/')
            try:
                dj = json.loads(dec)
            except Exception:
                return ''
            def _f(o):
                if isinstance(o, str):
                    return o.replace('\\/', '/') if o.startswith('http') and re.search(r'\.(m3u8|mp4|flv)(\?|$)', o) else ''
                if isinstance(o, dict):
                    for k in ('url', 'm3u8', 'play_url', 'playUrl', 'video_url', 'src'):
                        if o.get(k):
                            v = _f(o[k])
                            if v:
                                return v
                    for v in o.values():
                        r = _f(v)
                        if r:
                            return r
                elif isinstance(o, list):
                    for v in o:
                        r = _f(v)
                        if r:
                            return r
                return ''
            return _f(dj)
        except Exception:
            return ''

    def timestamp(self):
        return str(int(time.time() * 1000))

    def hex_time(self):
        return hex(int(time.time()))[2:]

    def getName(self):
        return '牛牛'

    def isVideoFormat(self, url):
        return any(x in url for x in ['.m3u8', '.mp4', '.flv', '.mkv', '.avi', '.mov', '.wmv', '.webm'])

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass
