var HOST = "http://mtyy.lizhun.xn--6qq986b3xl";
var KEY = "d3799pudaccmtyyo";
var HEADERS = {
    "User-Agent": "okhttp/3.14.9",
    "App-Device-Id": "00000000000000000000000000000000",
    "App-Os-Type": "android",
    "App-Ui-Mode": "light",
    "App-Version-Code": "200",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
};
var HOME = null;

function text(value) {
    if (typeof value === "string") return value;
    if (!value) return "";
    var body = value.content || value.body || value.data || "";
    return typeof body === "string" ? body : JSON.stringify(body);
}

function json(value) {
    return JSON.stringify(value);
}

function form(data) {
    var values = [];
    data = data || {};
    Object.keys(data).forEach(function (key) {
        values.push(encodeURIComponent(key) + "=" + encodeURIComponent(data[key] == null ? "" : data[key]));
    });
    return values.join("&");
}

function decrypt(value) {
    try {
        if (typeof aesX === "function") return JSON.parse(aesX("AES/CBC/PKCS5", false, value, true, KEY, KEY, false));
        if (typeof CryptoJS !== "undefined") {
            var key = CryptoJS.enc.Utf8.parse(KEY);
            var plain = CryptoJS.AES.decrypt(value, key, {iv: key, mode: CryptoJS.mode.CBC, padding: CryptoJS.pad.Pkcs7}).toString(CryptoJS.enc.Utf8);
            return JSON.parse(plain);
        }
    } catch (e) {}
    return {};
}

function api(path, data) {
    try {
        var response = req(HOST + "/api/vod/" + path, {method: "POST", headers: HEADERS, body: form(data), timeout: 20000});
        var outer = JSON.parse(text(response) || "{}");
        if (Number(outer.code) !== 0) return {};
        return typeof outer.data === "string" ? decrypt(outer.data) : outer.data || {};
    } catch (e) {
        return {};
    }
}

function getHome() {
    if (!HOME) HOME = api("init", {});
    return HOME || {};
}

function vod(item) {
    item = item || {};
    return {
        vod_id: String(item.vod_id || ""),
        vod_name: item.vod_name || "",
        vod_pic: item.vod_pic || "",
        vod_remarks: item.vod_remarks || ""
    };
}

function filters(types) {
    var names = {"class": "类型", "area": "地区", "lang": "语言", "year": "年份", "sort": "排序"};
    var result = {};
    (types || []).forEach(function (type) {
        var values = [];
        (type.filter_type_list || []).forEach(function (group) {
            var options = [];
            (group.list || []).forEach(function (item) {
                var value = String(item);
                options.push({n: value, v: value === "全部" ? "" : value});
            });
            if (group.name && options.length) values.push({key: group.name, name: names[group.name] || group.name, value: options});
        });
        if (values.length) result[String(type.type_id)] = values;
    });
    return result;
}

function playId(vodId, source, episode) {
    return encodeURIComponent(JSON.stringify({
        v: String(vodId),
        s: String(source.id || ""),
        e: Number(episode.episode_index || 0),
        p: Number(source.player_parse_type || 1),
        a: source.parse_api || "",
        u: episode.url || ""
    }));
}

function init(ext) {
    var value = ext;
    if (value && typeof value === "object") value = value.ext || value.host || "";
    if (typeof value === "string" && /^https?:\/\//.test(value)) HOST = value.replace(/\/$/, "");
    HOME = null;
}

function home(filter) {
    var data = getHome();
    var types = data.type_list || [];
    var classes = types.map(function (item) {
        return {type_id: String(item.type_id || ""), type_name: item.type_name || ""};
    }).filter(function (item) {
        return item.type_id && item.type_name;
    });
    if (!classes.length) classes = [{type_id: "20", type_name: "电影"}, {type_id: "21", type_name: "电视剧"}, {type_id: "22", type_name: "动漫"}, {type_id: "24", type_name: "综艺"}];
    return json({"class": classes, filters: filters(types)});
}

function homeVod() {
    var data = getHome();
    var types = data.type_list || [];
    var values = (data.banner_list || []).concat(data.recommend_list || []);
    types.forEach(function (type) {
        values = values.concat((type.recommend_list || []).slice(0, 3));
    });
    var seen = {};
    var list = [];
    values.forEach(function (item) {
        var value = vod(item);
        if (value.vod_id && !seen[value.vod_id]) {
            seen[value.vod_id] = true;
            list.push(value);
        }
    });
    return json({list: list});
}

function category(tid, pg, filter, extend) {
    var page = parseInt(pg || 1) || 1;
    var ext = extend && typeof extend === "object" ? extend : {};
    if (typeof extend === "string") try { ext = JSON.parse(extend); } catch (e) {}
    var params = {type_id: tid, page: page};
    ["class", "area", "lang", "year", "sort"].forEach(function (key) {
        if (ext[key]) params[key] = ext[key];
    });
    var data = api("typeFilterVodList", params);
    var list = (data.recommend_list || []).map(vod);
    var limit = Number(data.page_size || 36);
    var total = Number(data.total || 0);
    var pagecount = total ? Math.max(page, Math.ceil(total / limit)) : page + (list.length >= limit ? 1 : 0);
    return json({page: page, pagecount: pagecount, limit: limit, total: total, list: list});
}

function detail(id) {
    var value = Array.isArray(id) ? id[0] : id;
    var vodId = String(value || "").split("@@")[0];
    if (vodId.indexOf("$") >= 0) vodId = vodId.split("$").pop();
    var data = api("vodDetail", {vod_id: vodId});
    var info = data.vod || {};
    if (!info.vod_id) return json({list: []});
    var sources = {};
    (data.player_source_list || []).forEach(function (source) {
        sources[source.player_code] = source;
    });
    var from = [];
    var urls = [];
    (data.vod_play_url_list || []).forEach(function (group) {
        var source = sources[group.player_code] || {};
        if (!source.id || (Number(source.player_parse_type || 1) !== 1 && !source.parse_api)) return;
        var episodes = [];
        (group.urls || []).forEach(function (episode) {
            var name = String(episode.name || Number(episode.episode_index || 0) + 1).replace(/[$#]/g, " ");
            episodes.push(name + "$" + playId(vodId, source, episode));
        });
        if (!episodes.length) return;
        from.push(String(source.player_name || group.player_code || "线路").replace(/[$#]/g, " "));
        urls.push(episodes.join("#"));
    });
    var item = vod(info);
    item.vod_actor = info.vod_actor || "";
    item.vod_director = info.vod_director || "";
    item.vod_area = info.vod_area || "";
    item.vod_year = info.vod_year || "";
    item.vod_content = info.vod_content || info.vod_blurb || "";
    item.vod_play_from = from.join("$$$");
    item.vod_play_url = urls.join("$$$");
    return json({list: [item]});
}

function search(wd, quick, pg) {
    var page = parseInt(pg || 1) || 1;
    var data = api("searchList", {keywords: wd, type_id: 0, page: page});
    var list = (data.search_list || []).map(vod);
    return json({page: page, pagecount: list.length ? page + 1 : page, limit: list.length || 20, total: list.length, list: list});
}

function play(flag, id, flags) {
    try {
        var value = JSON.parse(decodeURIComponent(String(id || "")));
        if (Number(value.p) === 1) {
            var parsed = api("vodParse", {vod_id: value.v, player_source_id: value.s, episode_index: value.e, scene: 0});
            var serverUrl = parsed.play_url || "";
            if (serverUrl) return json({parse: /\.(m3u8|mp4|flv)(\?|$)/i.test(serverUrl) ? 0 : 1, url: serverUrl, header: HEADERS, headers: HEADERS});
        }
        var url = value.u || "";
        if (/\.(m3u8|mp4|flv)(\?|$)/i.test(url)) return json({parse: 0, url: url, header: HEADERS, headers: HEADERS});
        if (value.a) {
            var parserUrl = value.a + encodeURIComponent(url);
            try {
                var parser = JSON.parse(text(req(parserUrl, {method: "GET", headers: HEADERS, timeout: 20000})) || "{}");
                if (parser.url) return json({parse: 0, url: parser.url, header: HEADERS, headers: HEADERS});
            } catch (e) {}
            return json({parse: 1, jx: 0, url: parserUrl, header: HEADERS, headers: HEADERS});
        }
        return json({parse: 1, jx: 0, url: url, header: HEADERS, headers: HEADERS});
    } catch (e) {
        return json({parse: 0, url: ""});
    }
}

__JS_SPIDER__ = {init: init, home: home, homeVod: homeVod, category: category, detail: detail, search: search, play: play};
