/*
 * @File   : mubai.js
 * @Desc   : 幕白影视 TVBox JS 源 融合完整版（第二版基础移植第一版全部缺失功能）
 * @Version: 20260709-fusion
 */
var MB_VERSION = "20260709-fusion";
var HOST = "https://m2.mubai.link";
var API = HOST + "/api";
var UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36";

// ========== 移植第一版：固定筛选配置 start ==========
const typeFilter = {
    "key": "type", "name": "类型", "value": [
        { "n": "全部", "v": "" },
        { "n": "动作", "v": "动作" },
        { "n": "喜剧", "v": "喜剧" },
        { "n": "爱情", "v": "爱情" },
        { "n": "科幻", "v": "科幻" },
        { "n": "恐怖", "v": "恐怖" },
        { "n": "剧情", "v": "剧情" },
        { "n": "战争", "v": "战争" },
        { "n": "悬疑", "v": "悬疑" },
        { "n": "动画", "v": "动画" }
    ]
};
function getYearFilter() {
    let years = [{ "n": "全部", "v": "" }];
    const currentYear = new Date().getFullYear();
    for (let y = currentYear; y >= 2000; y--) {
        years.push({ "n": String(y), "v": String(y) });
    }
    return { "key": "year", "name": "年份", "value": years };
}
function getAreaFilter() {
    return {
        "key": "area", "name": "地区", "value": [
            { "n": "全部", "v": "" },
            { "n": "大陆", "v": "大陆" },
            { "n": "香港", "v": "香港" },
            { "n": "台湾", "v": "台湾" },
            { "n": "美国", "v": "美国" },
            { "n": "日本", "v": "日本" },
            { "n": "韩国", "v": "韩国" },
            { "n": "英国", "v": "英国" },
            { "n": "法国", "v": "法国" },
            { "n": "德国", "v": "德国" },
            { "n": "泰国", "v": "泰国" },
            { "n": "其他", "v": "其他" }
        ]
    };
}
const commonFilters = [getAreaFilter(), getYearFilter(), typeFilter];
var filterMap = {};
// ========== 移植第一版：固定筛选配置 end ==========

// 固定一级分类（页面已正常显示）
var FIX_CLASSES = [
    { type_id: "1", type_name: "电影片" },
    { type_id: "2", type_name: "连续剧" },
    { type_id: "3", type_name: "综艺片" },
    { type_id: "4", type_name: "动漫片" }
];
var CLASSES = FIX_CLASSES;
var CATEGORIES = {};
var FILTERS = {};
var CAT_LOADED = false;

function log(msg) {
    try { console.log("[MB_FUSION] " + msg); } catch (e) {}
}
function toStr(v) { return v === undefined || v === null ? "" : String(v); }
function encode(s) { return encodeURIComponent(toStr(s)); }
// 移植第一版别名兼容
function urlEncode(s) { return encode(s); }

function fixUrl(u) {
    u = toStr(u).trim();
    if (!u) return "";
    if (u.indexOf("//") === 0) return "https:" + u;
    if (u.charAt(0) === "/") return HOST + u;
    if (/^https?:\/\//i.test(u)) return u;
    return "";
}

// 修复：TVBox 原生 req 函数，全版本兼容，替换失效的fetch
function requestJson(url) {
    var headers = {
        "User-Agent": UA,
        "Accept": "application/json,*/*;q=0.8",
        "Referer": HOST + "/"
    };
    try {
        var res = req(url, headers);
        return JSON.parse(res.content);
    } catch (e) {
        log("接口请求失败:" + url + " 错误:" + e);
        return null;
    }
}

function loadCategories() {
    if (CAT_LOADED) return;
    var data = requestJson(API + "/index");
    if (!data || !data.code || !data.data || !data.data.content) {
        log("首页接口返回异常，仅展示基础固定筛选");
        CAT_LOADED = true;
        // 接口异常兜底：使用第一版固定筛选
        for (var i = 0; i < FIX_CLASSES.length; i++) {
            var pid = FIX_CLASSES[i].type_id;
            FILTERS[pid] = JSON.parse(JSON.stringify(commonFilters));
        }
        return;
    }
    CAT_LOADED = true;
    var cats = {};
    var filters = {};
    var areasSet = {};
    var yearsSet = {};
    for (var i = 0; i < FIX_CLASSES.length; i++) {
        var pid = FIX_CLASSES[i].type_id;
        // 筛选缓存逻辑 移植第一版filterMap
        if(filterMap[pid]){
            filters[pid] = filterMap[pid];
            cats[pid] = [];
            continue;
        }
        var subcats = [];
        var seenIds = {};
        var targetTab = null;
        for (var t = 0; t < data.data.content.length; t++) {
            if (toStr(data.data.content[t].nav.id) === pid) {
                targetTab = data.data.content[t];
                break;
            }
        }
        if (targetTab) {
            var allMovies = (targetTab.movies || []).concat(targetTab.hot || []);
            for (var j = 0; j < allMovies.length; j++) {
                var m = allMovies[j];
                if (m.cid && !seenIds[m.cid]) {
                    seenIds[m.cid] = 1;
                    subcats.push({ type_id: m.cid, type_name: toStr(m.cName) });
                }
                if (m.area && !areasSet[m.area]) areasSet[m.area] = 1;
                if (m.year && !yearsSet[m.year]) yearsSet[m.year] = 1;
            }
        }
        if (data.data.category && data.data.category.children) {
            var treeRoots = data.data.category.children;
            for (var k = 0; k < treeRoots.length; k++) {
                if (toStr(treeRoots[k].id) === pid && treeRoots[k].children) {
                    var childNodes = treeRoots[k].children;
                    for (var ci = 0; ci < childNodes.length; ci++) {
                        var node = childNodes[ci];
                        if (node.id && !seenIds[node.id]) {
                            seenIds[node.id] = 1;
                            subcats.push({ type_id: node.id, type_name: toStr(node.name) });
                        }
                    }
                }
            }
        }
        cats[pid] = subcats;
        // 融合筛选：固定筛选在前 + 动态二级分类、排序在后
        var baseFilter = JSON.parse(JSON.stringify(commonFilters));
        var cateFilter = { key: "cate", name: "二级分类", value: [{n:"全部",v:""}].concat(subcats) };
        var sortFilter = {
            key: "sort", name: "排序", value: [
                { n: "默认", v: "" },
                { n: "热门", v: "hits" },
                { n: "评分", v: "score" }
            ]
        };
        var finalFilter = baseFilter.concat([cateFilter, sortFilter]);
        filters[pid] = finalFilter;
        // 存入筛选缓存
        filterMap[pid] = finalFilter;
    }
    CATEGORIES = cats;
    FILTERS = filters;
}

// 移植第一版多图片字段兼容 pic / img / picture
function formatListItem(m) {
    var vid = toStr(m.id || m.mid);
    var remark = toStr(m.remarks || m.year || "");
    var pic = toStr(m.picture || m.pic || m.img);
    return {
        vod_id: vid,
        vod_name: toStr(m.name || vid),
        vod_pic: fixUrl(pic),
        vod_remarks: remark
    };
}

function init(ext) {
    if (typeof ext === "string" && /^https?:\/\//i.test(ext.trim())) {
        HOST = ext.trim().replace(/\/+$/, "");
        API = HOST + "/api";
    }
    CAT_LOADED = false;
    CATEGORIES = {};
    FILTERS = {};
    filterMap = {};
    loadCategories();
}

function home(filter) {
    loadCategories();
    var list = [];
    var data = requestJson(API + "/index");
    if (data && data.data && data.data.content) {
        var map = {};
        for (var t = 0; t < data.data.content.length; t++) {
            var tab = data.data.content[t];
            var all = (tab.hot || []).concat(tab.movies || []);
            for (var i = 0; i < all.length; i++) {
                var item = formatListItem(all[i]);
                if (!map[item.vod_id]) {
                    map[item.vod_id] = 1;
                    list.push(item);
                }
            }
        }
    }
    return JSON.stringify({
        class: CLASSES,
        filters: FILTERS,
        list: list
    });
}

function homeVod() {
    var data = requestJson(API + "/index");
    var list = [];
    if (data && data.data && data.data.content) {
        data.data.content.forEach(tab => {
            var items = (tab.hot || []).concat(tab.movies || []);
            items.forEach(item => list.push(formatListItem(item)));
        });
    }
    var map = {};
    var result = [];
    list.forEach(item => {
        if (!map[item.vod_id]) {
            map[item.vod_id] = 1;
            result.push(item);
        }
    });
    return JSON.stringify({ list: result });
}


function category(tid, pg, filter, extend) {
    tid = toStr(tid || "1");
    pg = Math.max(parseInt(pg || 1), 1);
    extend = extend || {};
    var url = API + "/filmClassifySearch?Pid=" + encode(tid) + "&page=" + pg;
    // 移植第一版type筛选参数Class
    if (extend.type) url += "&Class=" + encode(extend.type);
    if (extend.cate) url += "&Category=" + encode(extend.cate);
    if (extend.area) url += "&Area=" + encode(extend.area);
    if (extend.year) url += "&Year=" + encode(extend.year);
    if (extend.sort) url += "&Sort=" + encode(extend.sort);
    var res = requestJson(url);
    var listData = (res && res.data && res.data.list) || [];
    var pageInfo = (res && res.data && res.data.page) || {};
    var list = listData.map(formatListItem);
    return JSON.stringify({
        page: pg,
        pagecount: parseInt(pageInfo.pageCount || 1),
        limit: parseInt(pageInfo.pageSize || 24),
        total: parseInt(pageInfo.total || list.length),
        list: list
    });
}

function detail(id) {
    var mid = toStr(id);
    var data = requestJson(API + "/filmDetail?id=" + encode(mid));
    var d = (data && data.code === 0 && data.data && data.data.detail) ? data.data.detail : null;
    if (!d) return JSON.stringify({ list: [{ vod_id: mid, vod_name: mid, vod_play_from: "提示", vod_play_url: "无资源$" }] });
    var vod = {
        vod_id: mid,
        vod_name: toStr(d.name),
        vod_pic: fixUrl(d.picture || d.pic || d.img),
        vod_remarks: toStr(d.remarks || d.year),
        type_name: toStr(d.cName),
        vod_year: toStr(d.year),
        vod_area: toStr(d.area),
        vod_director: toStr(d.director),
        vod_actor: toStr(d.actor),
        vod_content: toStr(d.content || d.blurb)
    };
    // 移植第一版双线路兼容 list / playList
    var playSource = (d.list || []).concat(d.playList || []);
    if (playSource && playSource.length > 0) {
        var playFrom = [];
        var playUrl = [];
        playSource.forEach(src => {
            if (!src.linkList || src.linkList.length === 0) return;
            playFrom.push(toStr(src.name || "线路"));
            var eps = [];
            src.linkList.forEach(ep => {
                var epName = toStr(ep.episode || "第" + (eps.length + 1) + "集");
                eps.push(epName + "$" + toStr(ep.link));
            });
            playUrl.push(eps.join("#"));
        });
        vod.vod_play_from = playFrom.join("$$$");
        vod.vod_play_url = playUrl.join("$$$");
    } else {
        vod.vod_play_from = "提示";
        vod.vod_play_url = "暂无播放资源$";
    }
    return JSON.stringify({ list: [vod] });
}

function play(flag, id, flags) {
    return JSON.stringify({
        parse: 0,
        url: toStr(id),
        header: { "User-Agent": UA, "Referer": HOST + "/" }
    });
}

function search(wd, quick, pg) {
    pg = Math.max(parseInt(pg || 1), 1);
    wd = toStr(wd).trim();
    if (!wd) return JSON.stringify({ list: [], page: 1, pagecount: 1, limit: 0, total: 0 });
    // 还原原版全局无分页搜索接口searchFilm，移除分页page参数
    var url = API + "/searchFilm?keyword=" + encode(wd);
    var res = requestJson(url);
    var listData = (res && res.data && res.data.list) || [];
    var pageInfo = (res && res.data && res.data.page) || {};
    var list = listData.map(m => ({
        vod_id: toStr(m.id),
        vod_name: toStr(m.name),
        vod_pic: fixUrl(m.picture || m.pic || m.img),
        vod_remarks: toStr(m.year || "")
    }));
    return JSON.stringify({
        list: list,
        page: pg,
        pagecount: parseInt(pageInfo.pageCount || 1),
        limit: list.length,
        total: parseInt(pageInfo.total || list.length)
    });
}


__JS_SPIDER__ = {
    init: init,
    home: home,
    homeVod: homeVod,
    category: category,
    detail: detail,
    play: play,
    search: search
};
