var KM_HOSTS = ["https://www.kmvod.fun", "https://www.kmvod.cc"];
var KM_ACTIVE_HOST = KM_HOSTS[0];
var KM_UA = "Mozilla/5.0 (Linux; Android 10; TVBox) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36";
var KM_COOKIE = "";
var KM_VERIFYING = false;
var KM_PROXY_HLS = false;

function kmHttp(url, options, ocrFlag) {
    if (typeof request === "function") return request(url, options, ocrFlag);
    var config = {}, source = options || {}, key;
    for (key in source) config[key] = source[key];
    if (config.toBase64) {
        config.buffer = 2;
        delete config.toBase64;
    }
    if (config.redirect === false) config.redirect = 0;
    var response = typeof req === "function" ? req(url, config) : "";
    var body = kmBody(response);
    if (!source.withHeaders) return body;
    var output = {}, headers = response && response.headers ? response.headers : {};
    for (key in headers) output[key] = headers[key];
    output.body = body;
    return JSON.stringify(output);
}

function kmStr(v) {
    return v === undefined || v === null ? "" : String(v);
}

function kmHeader(headers, name) {
    var key;
    for (key in (headers || {})) if (key.toLowerCase() === name.toLowerCase()) return kmStr(headers[key]);
    return "";
}

function kmResponse(raw) {
    if (raw && typeof raw === "object") return { body: kmBody(raw), headers: raw.headers || raw };
    var text = kmStr(raw);
    try {
        var obj = JSON.parse(text);
        if (obj && typeof obj === "object" && (obj.body !== undefined || obj.content !== undefined || obj.data !== undefined)) return { body: kmBody(obj), headers: obj };
    } catch (e) {}
    return { body: text, headers: {} };
}

function kmSetCookie(headers) {
    var value = kmHeader(headers, "set-cookie");
    if (Array.isArray(value)) value = value.join(",");
    return value;
}

function kmCookiePair(headers, name) {
    var raw = kmSetCookie(headers), re = new RegExp("(?:^|[,;]\\s*)" + name + "=([^;,\\s]+)", "gi"), match, value = "";
    while ((match = re.exec(raw)) !== null) value = match[1];
    return value && value !== "deleted" ? name + "=" + value : "";
}

function kmParamCookie() {
    var params = "";
    try { params = typeof rule !== "undefined" && rule ? rule.params : ""; } catch (e) {}
    if (!params) return "";
    if (typeof params === "object") return kmStr(params.cookie || params.Cookie || "").trim();
    var text = kmStr(params);
    try {
        var obj = JSON.parse(decodeURIComponent(text));
        if (obj && typeof obj === "object") return kmStr(obj.cookie || obj.Cookie || "").trim();
    } catch (e) {}
    try { text = decodeURIComponent(text); } catch (e) {}
    var match = /(?:^|[;&])(?:cookie|Cookie)=([^;&]+)/i.exec(text);
    return match ? match[1].trim() : /(?:PHPSESSID|captcha_login_sign)=/i.test(text) ? text.trim() : "";
}

function kmCookie() {
    var value = KM_COOKIE || kmParamCookie();
    try {
        if (!value && typeof getItem === "function") value = getItem("cookie", "") || "";
    } catch (e) {}
    return kmStr(value).trim();
}

function kmDecode(v) {
    return kmStr(v)
        .replace(/&amp;/gi, "&")
        .replace(/&quot;/gi, "\"")
        .replace(/&#39;|&apos;/gi, "'")
        .replace(/&lt;/gi, "<")
        .replace(/&gt;/gi, ">")
        .replace(/&nbsp;/gi, " ")
        .replace(/&#(\d+);/g, function (_, n) { return String.fromCharCode(parseInt(n, 10)); });
}

function kmClean(v) {
    return kmDecode(v)
        .replace(/<script\b[\s\S]*?<\/script>/gi, " ")
        .replace(/<style\b[\s\S]*?<\/style>/gi, " ")
        .replace(/<br\s*\/?>/gi, " ")
        .replace(/<[^>]+>/g, " ")
        .replace(/\s+/g, " ")
        .trim();
}

function kmAttr(tag, name) {
    var quoted = new RegExp("\\b" + name + "\\s*=\\s*([\\\"'])([\\s\\S]*?)\\1", "i").exec(tag || "");
    if (quoted) return kmDecode(quoted[2]);
    var plain = new RegExp("\\b" + name + "\\s*=\\s*([^\\s>]+)", "i").exec(tag || "");
    return plain ? kmDecode(plain[1]) : "";
}

function kmPath(url) {
    var value = kmDecode(url).trim();
    if (!value) return "";
    if (/^https?:\/\//i.test(value)) return value.replace(/^https?:\/\/[^/]+/i, "") || "/";
    return value.charAt(0) === "/" ? value : "/" + value.replace(/^\.\//, "");
}

function kmAbsolute(url) {
    var value = kmDecode(url).trim();
    if (!value) return "";
    if (/^https?:\/\//i.test(value)) return value;
    if (value.indexOf("//") === 0) return "https:" + value;
    return KM_ACTIVE_HOST + (value.charAt(0) === "/" ? value : "/" + value);
}

function kmHeaders(referer, includeCookie) {
    var headers = {
        "User-Agent": KM_UA,
        "Referer": referer || KM_ACTIVE_HOST + "/",
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8"
    };
    var cookie = includeCookie === false ? "" : kmCookie();
    if (cookie) headers.Cookie = cookie;
    return headers;
}

function kmBody(response) {
    var value;
    if (typeof response === "string") value = response;
    else value = kmStr(response && (response.content || response.body || response.data));
    if (value && value.charAt(0) === '"') {
        try {
            var unwrapped = JSON.parse(value);
            if (typeof unwrapped === "string") value = unwrapped;
        } catch (e) {}
    }
    return value;
}

function kmValid(body) {
    var text = kmStr(body).trim();
    return !!text && !/^closed$/i.test(text) && !/系统安全验证|访问此数据需要输入验证码|class=["'][^"']*mac_verify/i.test(text) && !/<title>\s*404 Not Found\s*<\/title>/i.test(text) && !/<h1>\s*404 Not Found\s*<\/h1>/i.test(text);
}

function kmCaptchaPage(body) {
    return /系统安全验证|访问此数据需要输入验证码|class=["'][^"']*mac_verify/i.test(kmStr(body));
}

function kmCaptchaCode(image) {
    var code = "";
    try {
        if (typeof OcrApi !== "undefined" && OcrApi && typeof OcrApi.classification === "function") code = OcrApi.classification(image);
    } catch (e) {}
    if (!code) {
        try {
            code = kmHttp("https://api.nn.ci/ocr/b64/text", {
                method: "POST",
                body: image,
                headers: { "Content-Type": "text/plain", "User-Agent": KM_UA },
                timeout: 15000
            }, true);
        } catch (e) {}
    }
    try {
        var obj = JSON.parse(kmStr(code));
        code = obj.result || obj.code || obj.text || code;
    } catch (e) {}
    return kmStr(code).replace(/\s+/g, "").trim();
}

function kmVerifyCaptcha(host) {
    if (KM_VERIFYING || typeof request !== "function") return "";
    KM_VERIFYING = true;
    var result = "";
    try {
        var base = kmHeaders(host + "/", false);
        var first = kmResponse(kmHttp(host + "/", { headers: base, withHeaders: true, timeout: 15000 }));
        var sid = kmCookiePair(first.headers, "PHPSESSID");
        if (!kmCaptchaPage(first.body)) result = kmCookie();
        if (!sid && kmCaptchaPage(first.body)) {
            var old = kmCookie();
            sid = /PHPSESSID=/i.test(old) ? old.match(/(?:^|;\s*)PHPSESSID=[^;]+/i)[0].replace(/^;\s*/, "") : "";
        }
        if (sid && !result && kmCaptchaPage(first.body)) {
            for (var attempt = 0; attempt < 3 && !result; attempt++) {
                var cap = kmResponse(kmHttp(host + "/captcha.php?type=code&r=" + new Date().getTime() + attempt, {
                    headers: { "User-Agent": KM_UA, "Referer": host + "/", Cookie: sid },
                    withHeaders: true,
                    toBase64: true,
                    timeout: 15000
                }));
                var code = kmCaptchaCode(cap.body);
                if (!code) continue;
                var submitted = kmResponse(kmHttp(host + "/captcha.php", {
                    method: "POST",
                    headers: { "User-Agent": KM_UA, "Referer": host + "/", Cookie: sid, "Content-Type": "application/x-www-form-urlencoded" },
                    body: "type=verify&check=" + encodeURIComponent(code),
                    withHeaders: true,
                    timeout: 15000
                }));
                var verify = {};
                try { verify = JSON.parse(kmStr(submitted.body)) || {}; } catch (e) {}
                if (Number(verify.code) === 1) result = kmCookiePair(submitted.headers, "captcha_login_sign");
            }
        }
        if (result) {
            KM_COOKIE = result;
            try { if (typeof setItem === "function") setItem("cookie", result); } catch (e) {}
        }
    } catch (e) {}
    KM_VERIFYING = false;
    return result;
}

function kmRequest(path, options, skipVerify) {
    var raw = kmStr(path).trim();
    var absolute = /^https?:\/\//i.test(raw);
    var hosts = absolute ? [raw.replace(/^(https?:\/\/[^/]+).*$/i, "$1")] : [KM_ACTIVE_HOST];
    var i;
    for (i = 0; !absolute && i < KM_HOSTS.length; i++) {
        if (hosts.indexOf(KM_HOSTS[i]) < 0) hosts.push(KM_HOSTS[i]);
    }
    for (i = 0; i < hosts.length; i++) {
        var host = hosts[i];
        var url = absolute ? raw : host + (raw.charAt(0) === "/" ? raw : "/" + raw);
        try {
            var config = {};
            var sourceConfig = options || {};
            var optionKey;
            for (optionKey in sourceConfig) config[optionKey] = sourceConfig[optionKey];
            var headers = {};
            var baseHeaders = kmHeaders(host + "/");
            var key;
            for (key in baseHeaders) headers[key] = baseHeaders[key];
            for (key in (config.headers || {})) headers[key] = config.headers[key];
            config.headers = headers;
            var body = kmBody(kmHttp(url, config));
            if (kmCaptchaPage(body) && !skipVerify) {
                var verified = kmVerifyCaptcha(host);
                if (verified) {
                    delete config.headers.Cookie;
                    delete config.headers.cookie;
                    return kmRequest(path, config, true);
                }
            }
            if (kmValid(body)) {
                KM_ACTIVE_HOST = host;
                return body;
            }
        } catch (e) {}
    }
    return "";
}

function kmFixPic(url) {
    var pic = kmAbsolute(url);
    return pic.replace(/\s/g, "%20");
}

function kmParseCards(html) {
    var blocks = kmStr(html).match(/<a\b[^>]*class\s*=\s*["'][^"']*stui-vodlist__thumb[^"']*["'][^>]*>[\s\S]*?<\/a>/gi) || [];
    var list = [];
    var seen = {};
    for (var i = 0; i < blocks.length; i++) {
        var block = blocks[i];
        var open = (block.match(/^<a\b[^>]*>/i) || [""])[0];
        var href = kmAttr(open, "href");
        if (!/\/(?:voddetail|detail)\//i.test(href)) continue;
        var id = kmPath(href);
        if (!id || seen[id]) continue;
        seen[id] = true;
        var img = (block.match(/<img\b[^>]*>/i) || [""])[0];
        var style = kmAttr(open, "style") || kmAttr(img, "style");
        var stylePic = (/url\(\s*["']?([^"')]+)["']?\s*\)/i.exec(style) || ["", ""])[1];
        var name = kmAttr(open, "title") || kmAttr(img, "alt");
        if (!name) name = kmClean((/<h[1-6]\b[^>]*class\s*=\s*["'][^"']*title[^"']*["'][^>]*>([\s\S]*?)<\/h[1-6]>/i.exec(block) || ["", ""])[1]);
        var pic = kmAttr(open, "data-original") || kmAttr(open, "data-src") || kmAttr(open, "data-lazyload") || kmAttr(img, "data-original") || kmAttr(img, "data-src") || kmAttr(img, "data-lazyload") || kmAttr(img, "src") || stylePic;
        var remark = kmClean((/<(?:span|div)\b[^>]*class\s*=\s*["'][^"']*pic-text[^"']*["'][^>]*>([\s\S]*?)<\/(?:span|div)>/i.exec(block) || ["", ""])[1]);
        if (!name) continue;
        list.push({
            vod_id: id,
            vod_name: kmClean(name),
            vod_pic: kmFixPic(pic),
            vod_remarks: remark
        });
    }
    return list;
}

function kmOptions(values) {
    var list = [{ n: "全部", v: "" }];
    for (var i = 0; i < values.length; i++) list.push({ n: values[i], v: values[i] });
    return list;
}

function kmYears() {
    var list = [{ n: "全部", v: "" }];
    for (var year = 2026; year >= 2000; year--) list.push({ n: String(year), v: String(year) });
    return list;
}

function kmBuildFilters() {
    var years = kmYears();
    var sorts = [{ n: "默认", v: "" }, { n: "最近更新", v: "time" }, { n: "添加时间", v: "id" }, { n: "人气指数", v: "hits" }];
    var classes = {
        "1": ["喜剧", "爱情", "恐怖", "动作", "科幻", "剧情", "战争", "警匪", "犯罪", "动画", "奇幻", "武侠", "冒险", "枪战", "悬疑", "惊悚", "经典", "青春", "文艺", "微电影", "古装", "历史", "运动", "农村", "儿童", "网络电影"],
        "2": ["古装", "战争", "青春偶像", "喜剧", "家庭", "犯罪", "动作", "奇幻", "剧情", "历史", "经典", "乡村", "情景", "商战", "网剧", "其他"],
        "3": ["选秀", "情感", "访谈", "播报", "旅游", "音乐", "美食", "纪实", "曲艺", "生活", "游戏互动", "财经", "求职"],
        "4": ["情感", "科幻", "热血", "推理", "搞笑", "冒险", "萝莉", "校园", "动作", "机战", "运动", "战争", "少年", "少女", "社会", "原创", "亲子", "益智", "励志", "其他"]
    };
    var areas = {
        "1": ["大陆", "香港", "台湾", "美国", "法国", "英国", "日本", "韩国", "德国", "泰国", "印度", "意大利", "西班牙", "加拿大", "其他"],
        "2": ["内地", "韩国", "香港", "台湾", "日本", "美国", "泰国", "英国", "新加坡", "其他"],
        "3": ["内地", "港台", "日韩", "欧美"],
        "4": ["国产", "日本", "欧美", "其他"]
    };
    var languages = ["国语", "英语", "粤语", "闽南语", "韩语", "日语", "法语", "德语", "其它"];
    var filters = {};
    for (var tid in classes) {
        filters[tid] = [
            { key: "class", name: "类型", value: kmOptions(classes[tid]) },
            { key: "area", name: "地区", value: kmOptions(areas[tid]) },
            { key: "lang", name: "语言", value: kmOptions(languages) },
            { key: "year", name: "年份", value: years },
            { key: "by", name: "排序", value: sorts }
        ];
    }
    return filters;
}

function kmFilterState(value) {
    if (!value) return {};
    if (typeof value === "object") return value;
    try { return JSON.parse(value); } catch (e) { return {}; }
}

function kmHasFilter(value) {
    for (var key in value) if (kmStr(value[key]).trim()) return true;
    return false;
}

function kmMeta(html, property) {
    var tags = kmStr(html).match(/<meta\b[^>]*>/gi) || [];
    for (var i = 0; i < tags.length; i++) {
        var key = kmAttr(tags[i], "property") || kmAttr(tags[i], "name");
        if (key.toLowerCase() === property.toLowerCase()) return kmAttr(tags[i], "content");
    }
    return "";
}

function kmLineName(prefix, index) {
    var chunk = kmStr(prefix).slice(-2200);
    var re = /<(h2|h3|h4)\b[^>]*>([\s\S]*?)<\/\1>/gi;
    var match;
    var names = [];
    while ((match = re.exec(chunk)) !== null) {
        var name = kmClean(match[2]).replace(/[#$]/g, " ").trim();
        if (name && name.length <= 40 && !/剧情|简介|猜你喜欢|相关推荐|影片信息|详细信息/.test(name)) names.push(name);
    }
    var value = names.length ? names[names.length - 1] : "";
    if (!value || /播放地址|播放列表|在线播放|选集/.test(value)) value = "线路" + index;
    return value;
}

function kmParseEpisodes(block) {
    var anchors = kmStr(block).match(/<a\b[^>]*>[\s\S]*?<\/a>/gi) || [];
    var episodes = [];
    var seen = {};
    for (var i = 0; i < anchors.length; i++) {
        var open = (anchors[i].match(/^<a\b[^>]*>/i) || [""])[0];
        var url = kmAttr(open, "data-url") || kmAttr(open, "data-src") || kmAttr(open, "data-play") || kmAttr(open, "href");
        if (!url || /^javascript:/i.test(url)) continue;
        if (!/\/vodplay\//i.test(url) && !/\.(?:m3u8|mp4|flv)(?:\?|$)/i.test(url)) continue;
        var absolute = kmAbsolute(url);
        if (seen[absolute]) continue;
        seen[absolute] = true;
        var name = kmClean(anchors[i]).replace(/[#$]/g, " ").trim() || "播放" + (episodes.length + 1);
        episodes.push(name + "$" + absolute);
    }
    return episodes;
}

function kmParsePlaylists(html) {
    var source = kmStr(html);
    var re = /<ul\b[^>]*class\s*=\s*["'][^"']*stui-content__playlist[^"']*["'][^>]*>[\s\S]*?<\/ul>/gi;
    var labels = {};
    var labelRe = /<a\b[^>]*href\s*=\s*["']#playlist(\d+)["'][^>]*>([\s\S]*?)<\/a>/gi;
    var labelMatch;
    while ((labelMatch = labelRe.exec(source)) !== null) labels[labelMatch[1]] = kmClean(labelMatch[2]);
    var froms = [];
    var urls = [];
    var match;
    var index = 0;
    while ((match = re.exec(source)) !== null) {
        var episodes = kmParseEpisodes(match[0]);
        if (!episodes.length) continue;
        index++;
        var name = labels[String(index)] || kmLineName(source.slice(0, match.index), index);
        if (froms.indexOf(name) >= 0) name += "-" + index;
        froms.push(name);
        urls.push(episodes.join("#"));
    }
    if (!urls.length) {
        var all = kmParseEpisodes(source);
        if (all.length) {
            froms.push("默认线路");
            urls.push(all.join("#"));
        }
    }
    return { froms: froms, urls: urls };
}

function kmDetail(html, id) {
    var name = kmClean((/<(?:h1|h2|h3)\b[^>]*class\s*=\s*["'][^"']*title[^"']*["'][^>]*>([\s\S]*?)<\/(?:h1|h2|h3)>/i.exec(html) || ["", ""])[1]) || kmMeta(html, "og:title") || kmMeta(html, "title") || kmClean((/<h1\b[^>]*>([\s\S]*?)<\/h1>/i.exec(html) || ["", ""])[1]);
    name = name.replace(/\s*[-_|].*?(?:酷猫|在线观看|在线播放).*$/i, "").trim();
    var pic = kmMeta(html, "og:image") || kmMeta(html, "image");
    if (!pic) {
        var pos = kmStr(html).search(/class\s*=\s*["'][^"']*stui-content__thumb/i);
        var chunk = pos >= 0 ? kmStr(html).slice(pos, pos + 2600) : kmStr(html);
        var img = (chunk.match(/<img\b[^>]*>/i) || [""])[0];
        var thumb = (chunk.match(/<(?:a|div)\b[^>]*class\s*=\s*["'][^"']*stui-content__thumb[^"']*["'][^>]*>/i) || [""])[0];
        pic = kmAttr(thumb, "data-original") || kmAttr(thumb, "data-src") || kmAttr(img, "data-original") || kmAttr(img, "data-src") || kmAttr(img, "src");
    }
    var content = kmMeta(html, "og:description") || kmMeta(html, "description");
    if (!content) content = kmClean((/<(?:div|p)\b[^>]*class\s*=\s*["'][^"']*stui-content__desc[^"']*["'][^>]*>([\s\S]*?)<\/(?:div|p)>/i.exec(html) || ["", ""])[1]);
    var remark = kmClean((/<(?:span|p|div)\b[^>]*class\s*=\s*["'][^"']*(?:pic-text|score|data)[^"']*["'][^>]*>([\s\S]*?)<\/(?:span|p|div)>/i.exec(html) || ["", ""])[1]);
    var playlists = kmParsePlaylists(html);
    return {
        vod_id: id,
        vod_name: name || "酷猫影视",
        vod_pic: kmFixPic(pic),
        vod_remarks: remark,
        vod_content: kmClean(content),
        vod_play_from: playlists.froms.join("$$$"),
        vod_play_url: playlists.urls.join("$$$")
    };
}

function kmCategoryPath(tid, page, extend) {
    var filter = kmFilterState(extend);
    var segments = [
        kmStr(tid),
        kmStr(filter.area),
        kmStr(filter.by),
        kmStr(filter.class),
        kmStr(filter.lang),
        "",
        "",
        "",
        kmStr(page),
        "",
        "",
        kmStr(filter.year)
    ];
    for (var i = 0; i < segments.length; i++) segments[i] = encodeURIComponent(segments[i]);
    return "/vodshow/" + segments.join("-") + ".html";
}

function kmPostSearch(key) {
    var data = "wd=" + encodeURIComponent(key);
    return kmRequest("/vodsearch/-------------.html", {
        method: "POST",
        body: data,
        headers: { "Content-Type": "application/x-www-form-urlencoded" }
    });
}

function kmBalancedObject(source, marker) {
    var text = kmStr(source);
    var markerIndex = text.search(new RegExp("(?:var\\s+)?" + marker + "\\s*=", "i"));
    if (markerIndex < 0) return "";
    var start = text.indexOf("{", markerIndex);
    if (start < 0) return "";
    var depth = 0;
    var quote = "";
    var escaped = false;
    for (var i = start; i < text.length; i++) {
        var ch = text.charAt(i);
        if (quote) {
            if (escaped) escaped = false;
            else if (ch === "\\") escaped = true;
            else if (ch === quote) quote = "";
            continue;
        }
        if (ch === "\"" || ch === "'") quote = ch;
        else if (ch === "{") depth++;
        else if (ch === "}" && --depth === 0) return text.slice(start, i + 1);
    }
    return "";
}

function kmPlayerData(html) {
    var raw = kmBalancedObject(html, "player_aaaa") || kmBalancedObject(html, "player_data");
    if (!raw) return {};
    try { return JSON.parse(raw); } catch (e) {}
    var out = {};
    var url = /["']url["']\s*:\s*["']([\s\S]*?)["']\s*(?:,|})/i.exec(raw);
    var encrypt = /["']encrypt["']\s*:\s*["']?(\d+)/i.exec(raw);
    if (url) out.url = url[1];
    if (encrypt) out.encrypt = parseInt(encrypt[1], 10);
    return out;
}

function kmBase64(value) {
    try {
        if (typeof base64Decode === "function") return base64Decode(value);
        if (typeof atob === "function") return atob(value);
    } catch (e) {}
    var input = kmStr(value).replace(/[^A-Za-z0-9+/=]/g, "");
    var chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=";
    var output = "";
    var index = 0;
    while (index < input.length) {
        var e1 = chars.indexOf(input.charAt(index++));
        var e2 = chars.indexOf(input.charAt(index++));
        var e3 = chars.indexOf(input.charAt(index++));
        var e4 = chars.indexOf(input.charAt(index++));
        if (e1 < 0 || e2 < 0) break;
        var c1 = (e1 << 2) | (e2 >> 4);
        var c2 = ((e2 & 15) << 4) | (e3 >> 2);
        var c3 = ((e3 & 3) << 6) | e4;
        output += String.fromCharCode(c1);
        if (e3 !== 64 && e3 >= 0) output += String.fromCharCode(c2);
        if (e4 !== 64 && e4 >= 0) output += String.fromCharCode(c3);
    }
    return output || value;
}

function kmBase64Binary(value) {
    var input = kmStr(value).replace(/\s/g, "").replace(/-/g, "+").replace(/_/g, "/");
    while (input.length % 4) input += "=";
    try {
        if (typeof atob === "function") return atob(input);
    } catch (e) {}
    var chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=";
    var output = "";
    var index = 0;
    while (index < input.length) {
        var e1 = chars.indexOf(input.charAt(index++));
        var e2 = chars.indexOf(input.charAt(index++));
        var e3 = chars.indexOf(input.charAt(index++));
        var e4 = chars.indexOf(input.charAt(index++));
        if (e1 < 0 || e2 < 0) break;
        output += String.fromCharCode((e1 << 2) | (e2 >> 4));
        if (e3 !== 64 && e3 >= 0) output += String.fromCharCode(((e2 & 15) << 4) | (e3 >> 2));
        if (e4 !== 64 && e4 >= 0) output += String.fromCharCode(((e3 & 3) << 6) | e4);
    }
    return output;
}

function kmMd5(value) {
    try {
        if (typeof md5 === "function") return kmStr(md5(value));
    } catch (e) {}
    try {
        if (typeof CryptoJS !== "undefined" && CryptoJS && CryptoJS.MD5) return CryptoJS.MD5(value).toString();
    } catch (e) {}
    return value === "test" ? "098f6bcd4621d373cade4e832627b4f6" : "";
}

function kmDecodeCloudMode1(value) {
    try {
        var encrypted = kmBase64Binary(value);
        var key = kmMd5("test");
        if (!encrypted || !key) return "";
        var code = "";
        for (var i = 0; i < encrypted.length; i++) code += String.fromCharCode(encrypted.charCodeAt(i) ^ key.charCodeAt(i % key.length));
        var packed = kmBase64Binary(code);
        var parts = packed.split("/");
        if (parts.length < 3) return "";
        var first = JSON.parse(kmBase64Binary(parts[0]));
        var second = JSON.parse(kmBase64Binary(parts[1]));
        var tail = kmBase64Binary(parts.slice(2).join("/"));
        var result = "";
        for (var j = 0; j < tail.length; j++) {
            var ch = tail.charAt(j);
            if (/^[A-Za-z]$/.test(ch)) {
                var idx = second.indexOf(ch);
                result += idx >= 0 && first[idx] !== undefined ? first[idx] : ch;
            } else result += ch;
        }
        return result;
    } catch (e) {
        return "";
    }
}

function kmDecodeCloudMode2(value) {
    try {
        var raw = kmBase64Binary(value);
        var alphabet = "PXhw7UT1B0a9kQDKZsjIASmOezxYG4CHo5Jyfg2b8FLpEvRr3WtVnlqMidu6cN";
        var result = "";
        for (var i = 1; i < raw.length; i += 3) {
            var ch = raw.charAt(i), idx = alphabet.indexOf(ch);
            result += idx < 0 ? ch : alphabet.charAt((idx + 59) % 62);
        }
        return result;
    } catch (e) {
        return "";
    }
}

function kmIsMediaUrl(url) {
    return /^https?:\/\//i.test(kmStr(url)) && /\.(?:m3u8|mp4|flv)(?:[?#]|$)/i.test(kmStr(url));
}

function kmMediaHeaders(referer) {
    var headers = { "User-Agent": KM_UA };
    if (referer) headers.Referer = referer;
    return headers;
}

function kmMediaResult(url, referer) {
    var headers = kmMediaHeaders(referer);
    var result = { parse: 0, jx: 0, url: url, header: headers, headers: headers };
    if (/\.m3u8(?:[?#]|$)/i.test(kmStr(url))) result.format = "application/x-mpegURL";
    return result;
}

function kmJoinUrl(base, path) {
    var value = kmDecode(path).trim();
    if (!value) return "";
    if (/^https?:\/\//i.test(value)) return value;
    if (value.indexOf("//") === 0) return "https:" + value;
    try {
        if (typeof urljoin === "function") return urljoin(base, value);
    } catch (e) {}
    var origin = (/^https?:\/\/[^/]+/i.exec(base) || [""])[0];
    if (value.charAt(0) === "/") return origin + value;
    var clean = kmStr(base).replace(/[?#][\s\S]*$/, "").replace(/[^/]*$/, "") + value;
    var match = /^(https?:\/\/[^/]+)(\/[\s\S]*)$/i.exec(clean);
    if (!match) return clean;
    var parts = match[2].split("/"), out = [];
    for (var i = 0; i < parts.length; i++) {
        if (!parts[i] || parts[i] === ".") continue;
        if (parts[i] === "..") out.pop();
        else out.push(parts[i]);
    }
    return match[1] + "/" + out.join("/");
}

function kmProxyUrl(url) {
    if (!KM_PROXY_HLS || !/\.m3u8(?:[?#]|$)/i.test(kmStr(url))) return url;
    try {
        if (typeof getProxyUrl === "function") return getProxyUrl() + "&type=kmvod_m3u8&url=" + encodeURIComponent(url);
    } catch (e) {}
    return url;
}

function kmRewriteM3u8(body, sourceUrl) {
    var lines = kmStr(body).replace(/\r/g, "").split("\n"), output = [];
    for (var i = 0; i < lines.length; i++) {
        var line = lines[i].trim();
        if (!line) continue;
        if (line.charAt(0) === "#") {
            line = line.replace(/URI=(["'])([^"']+)\1/gi, function (_, quote, uri) {
                var absolute = kmJoinUrl(sourceUrl, uri);
                return "URI=" + quote + (/\.m3u8(?:[?#]|$)/i.test(absolute) ? kmProxyUrl(absolute) : absolute) + quote;
            });
            output.push(line);
        } else {
            var absolute = kmJoinUrl(sourceUrl, line);
            output.push(/\.m3u8(?:[?#]|$)/i.test(absolute) ? kmProxyUrl(absolute) : absolute);
        }
    }
    return output.join("\n") + "\n";
}

function kmDecodeCloudUrl(data) {
    var raw = kmDecode(data && data.url).replace(/\\\//g, "/").trim();
    if (kmIsMediaUrl(raw)) return raw;
    var mode = parseInt(data && data.urlmode, 10) || 0;
    var candidates = [];
    if (mode === 1) candidates = [kmDecodeCloudMode1(raw), kmDecodeCloudMode2(raw)];
    else if (mode === 2) candidates = [kmDecodeCloudMode2(raw), kmDecodeCloudMode1(raw)];
    else candidates = [raw, kmDecodeCloudMode2(raw), kmDecodeCloudMode1(raw)];
    for (var i = 0; i < candidates.length; i++) {
        var value = kmDecode(candidates[i]).replace(/\\\//g, "/").trim();
        if (kmIsMediaUrl(value)) return value;
    }
    return "";
}

function kmCloudData(player) {
    var token = kmStr(player && player.url).replace(/\\\//g, "/").trim();
    if (!token) return {};
    var body = "vid=" + encodeURIComponent(token);
    var response = kmRequest("/kmcloud/api.php", {
        method: "POST",
        body: body,
        headers: {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": kmAbsolute("/kmcloud/index.php")
        }
    });
    try {
        var obj = JSON.parse(kmStr(response));
        return obj && Number(obj.code) === 200 && obj.data ? obj.data : {};
    } catch (e) {
        return {};
    }
}

function kmDecodePlayUrl(data) {
    var url = kmDecode(data && data.url).replace(/\\\//g, "/");
    var encrypt = parseInt(data && data.encrypt, 10) || 0;
    try {
        if (encrypt === 1) url = unescape(url);
        else if (encrypt === 2) url = unescape(kmBase64(url));
        else if (/^https?%3A/i.test(url)) url = decodeURIComponent(url);
    } catch (e) {}
    return kmDecode(url).replace(/\\\//g, "/").trim();
}

var rule = {
    title: "酷猫影视",
    host: KM_HOSTS[0],
    homeUrl: "/",
    url: "/vodshow/fyclass-fyarea-fyby-fyfilter-fylang---fyPage---fyyear.html",
    searchUrl: "/vodsearch/**-------------.html",
    searchable: 1,
    quickSearch: 0,
    filterable: 1,
    headers: { "User-Agent": KM_UA, "Referer": KM_HOSTS[0] + "/" },
    timeout: 10000,
    limit: 24,
    play_parse: true,
    play_json: [
        { re: "\\.(?:m3u8|mp4|flv)(?:[?#]|$)", json: { parse: 0, jx: 0 } },
        { re: "(?:127\\.0\\.0\\.1|localhost).*/proxy\\?", json: { parse: 0, jx: 0 } }
    ],
    class_name: "电影&剧集&综艺&动漫",
    class_url: "1&2&3&4",
    filter_url: "{{fl.area}}-{{fl.by}}-{{fl.class}}-{{fl.lang}}---fyPage---{{fl.year}}",
    filter: kmBuildFilters(),
    __kmHome: function () {
        return kmParseCards(kmRequest("/"));
    },
    __kmCategory: function (tid, pageValue, filterValue) {
        var page = parseInt(pageValue, 10) || 1;
        tid = kmStr(tid || "1");
        var extend = kmFilterState(filterValue || {});
        var html = kmRequest(kmCategoryPath(tid, page, extend));
        var list = kmParseCards(html);
        if (!list.length && !kmHasFilter(extend)) {
            var fallback = page > 1 ? "/vodtype/" + encodeURIComponent(tid) + "-" + page + ".html" : "/vodtype/" + encodeURIComponent(tid) + ".html";
            list = kmParseCards(kmRequest(fallback));
        }
        return list;
    },
    __kmDetail: function (idValue) {
        var id = kmPath(idValue);
        var html = kmRequest(id);
        return kmDetail(html, id);
    },
    __kmSearch: function (keyValue) {
        var key = kmStr(keyValue).trim();
        var path = "/vodsearch/" + encodeURIComponent(key) + "-------------.html";
        var list = kmParseCards(kmRequest(path));
        if (!list.length) list = kmParseCards(kmPostSearch(key));
        return list;
    },
    __kmProxy: function (params) {
        var url = kmStr(params && (params.url || params.u)).trim();
        if (!/^https?:\/\//i.test(url)) {
            try { url = decodeURIComponent(url); } catch (e) {}
        }
        if (!/^https?:\/\//i.test(url)) return [400, "text/plain", "Bad Request"];
        try {
            var body = kmBody(kmHttp(url, { headers: kmMediaHeaders(), timeout: 20000 }));
            if (!/^\s*#EXTM3U/i.test(body)) return [502, "text/plain", "Upstream Error"];
            return [200, "application/vnd.apple.mpegurl", kmRewriteM3u8(body, url)];
        } catch (e) {
            return [502, "text/plain", "Upstream Error"];
        }
    },
    __kmLazy: function (idValue) {
        var id = kmStr(idValue).trim();
        if (kmIsMediaUrl(id)) {
            return kmMediaResult(kmProxyUrl(id));
        }
        var playUrl = kmAbsolute(id);
        var html = kmRequest(playUrl);
        var player = kmPlayerData(html);
        var url = kmDecodePlayUrl(player);
        if (!kmIsMediaUrl(url) && player && player.url) {
            var cloud = kmCloudData(player);
            url = kmDecodeCloudUrl(cloud);
        }
        if (!url) {
            var direct = /(https?:\\?\/\\?\/[^\s"'<>]+?\.(?:m3u8|mp4|flv)(?:\?[^\s"'<>]*)?)/i.exec(html);
            if (direct) url = direct[1].replace(/\\\//g, "/");
        }
        if (kmIsMediaUrl(url)) {
            return kmMediaResult(kmProxyUrl(url));
        }
        var fallbackHeaders = kmHeaders(KM_ACTIVE_HOST + "/");
        return { parse: 1, jx: 0, url: playUrl, header: fallbackHeaders, headers: fallbackHeaders };
    },
    推荐: "js:VODS=rule.__kmHome();",
    一级: "js:VODS=rule.__kmCategory(MY_CATE,MY_PAGE,MY_FL);",
    二级: "js:VOD=rule.__kmDetail(orId);",
    搜索: "js:VODS=rule.__kmSearch(KEY,MY_PAGE);",
    lazy: "js:input=rule.__kmLazy(input);",
    proxy_rule: "js:input=rule.__kmProxy(input);"
};

function kmJson(value) {
    return JSON.stringify(value);
}

function kmInit(ext) {
    var value = ext;
    if (value && typeof value === "object") value = value.cookie || value.Cookie || "";
    if (typeof value === "string" && value.trim()) {
        try {
            var parsed = JSON.parse(value);
            value = parsed.cookie || parsed.Cookie || "";
        } catch (e) {}
        if (/(?:PHPSESSID|captcha_login_sign)=/i.test(value)) KM_COOKIE = value.trim();
    }
}

function kmHomeContent(filter) {
    return kmJson({
        class: [
            { type_id: "1", type_name: "电影" },
            { type_id: "2", type_name: "剧集" },
            { type_id: "3", type_name: "综艺" },
            { type_id: "4", type_name: "动漫" }
        ],
        filters: rule.filter
    });
}

function kmHomeVodContent() {
    return kmJson({ list: rule.__kmHome() });
}

function kmCategoryContent(tid, pg, filter, extend) {
    var page = parseInt(pg, 10) || 1;
    var list = rule.__kmCategory(tid, page, extend || {});
    return kmJson({
        page: page,
        pagecount: list.length ? page + 1 : page,
        limit: list.length || rule.limit,
        total: list.length ? (page + 1) * list.length : 0,
        list: list
    });
}

function kmDetailContent(id) {
    var vod = rule.__kmDetail(id);
    return kmJson({ list: vod && vod.vod_id ? [vod] : [] });
}

function kmSearchContent(wd, quick, pg) {
    var page = parseInt(pg, 10) || 1;
    var list = rule.__kmSearch(wd);
    return kmJson({ page: page, pagecount: page, limit: list.length || 20, total: list.length, list: list });
}

function kmPlayContent(flag, id, flags) {
    var result = rule.__kmLazy(id);
    if (result && result.parse === 0 && /\.m3u8(?:[?#]|$)/i.test(kmStr(result.url))) result.format = "application/x-mpegURL";
    return kmJson(result);
}

function kmSniffer() {
    return false;
}

function kmIsVideo(url) {
    return /\.(?:m3u8|mp4|flv)(?:[?#]|$)/i.test(kmStr(url));
}

__JS_SPIDER__ = {
    init: kmInit,
    home: kmHomeContent,
    homeVod: kmHomeVodContent,
    category: kmCategoryContent,
    detail: kmDetailContent,
    search: kmSearchContent,
    play: kmPlayContent,
    sniffer: kmSniffer,
    isVideo: kmIsVideo
};
