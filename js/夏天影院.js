import cheerio from 'assets://js/lib/cheerio.min.js';

const appConfig = {
    siteName: "夏天影院",
    siteUrl: "https://cpsz.cc"
};
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

async function init(ext) {
    console.log("初始化爬虫:", appConfig.siteName);
}

const classList = [
    { type_id: "1", type_name: "电影" },
    { type_id: "35", type_name: "喜剧片" },
    { type_id: "36", type_name: "动作片" },
    { type_id: "37", type_name: "爱情片" },
    { type_id: "38", type_name: "科幻片" },
    { type_id: "39", type_name: "恐怖片" },
    { type_id: "40", type_name: "剧情片" },
    { type_id: "41", type_name: "战争片" },
    { type_id: "2", type_name: "电视剧" },
    { type_id: "42", type_name: "国产剧" },
    { type_id: "43", type_name: "港台剧" },
    { type_id: "44", type_name: "日韩剧" },
    { type_id: "45", type_name: "欧美剧" },
    { type_id: "3", type_name: "综艺" },
    { type_id: "46", type_name: "国内综艺" },
    { type_id: "47", type_name: "海外综艺" },
    { type_id: "4", type_name: "动漫" },
    { type_id: "48", type_name: "国内动漫" },
    { type_id: "49", type_name: "海外动漫" },
    { type_id: "9", type_name: "短视频" },
    { type_id: "57", type_name: "动画短片" },
    { type_id: "58", type_name: "短剧" }
];

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
            { "n": "印度", "v": "印度" },
            { "n": "其他", "v": "其他" }
        ]
    };
}

function getYearFilter() {
    let years = [{ "n": "全部", "v": "" }];
    const currentYear = new Date().getFullYear();
    for (let y = currentYear; y >= 2010; y--) {
        years.push({ "n": String(y), "v": String(y) });
    }
    return { "key": "year", "name": "年份", "value": years };
}

function getLangFilter() {
    return {
        "key": "lang", "name": "语言", "value": [
            { "n": "全部", "v": "" },
            { "n": "国语", "v": "国语" },
            { "n": "粤语", "v": "粤语" },
            { "n": "英语", "v": "英语" },
            { "n": "日语", "v": "日语" },
            { "n": "韩语", "v": "韩语" },
            { "n": "其他", "v": "其他" }
        ]
    };
}

function getTypeFilter() {
    return {
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
            { "n": "犯罪", "v": "犯罪" },
            { "n": "动画", "v": "动画" },
            { "n": "纪录", "v": "纪录" }
        ]
    };
}

const commonFilters = [getAreaFilter(), getYearFilter(), getLangFilter(), getTypeFilter()];

const myFilters = {};
classList.forEach(item => {
    myFilters[item.type_id] = commonFilters;
});

function fixUrl(u) {
    if (!u) return '';
    if (u.startsWith('http')) return u;
    if (u.startsWith('//')) return 'https:' + u;
    if (u.startsWith('/')) return appConfig.siteUrl + u;
    return u;
}

function parseListHtml(html) {
    const $ = cheerio.load(html);
    let list = [];
    let vodIds = {};

    // 兼容普通列表和搜索页的大图列表
    $(".stui-vodlist li, .stui-vodlist__media li, .img-list li, li[class*='col-md-'], li[class*='col-lg-'], li[class*='col-sm-']").each(function () {
        let $a = $(this).find("a[href*='/pgb/']").first();
        let vod_id = $a.attr("href");
        if (!vod_id || vodIds[vod_id]) return;

        let vod_name = $a.attr("title") || $a.find("img").attr("alt") || "";
        let vod_pic = fixUrl($a.attr("data-original") || $a.find("img").attr("data-original") || $a.find("img").attr("src") || "");
        let vod_remarks = ($(this).find(".pic-text, .vtitle, .vname, .text-right, .pic-tag").text() || "").trim();

        if (vod_name && vod_id) {
            vodIds[vod_id] = true;
            list.push({ vod_id, vod_name, vod_pic, vod_remarks });
        }
    });

    let pagecount = 1;
    $("a[href*='/pgbtype/'], a[href*='/pgbshow/'], a[href*='/search/']").each(function () {
        let href = $(this).attr("href") || '';
        let m = href.match(/-(\d+)\.html$/);
        if (m) {
            let p = parseInt(m[1]);
            if (p > pagecount) pagecount = p;
        }
    });

    if (pagecount === 1) {
        $("a[href*='/pgbtype/'], a[href*='/pgbshow/'], a[href*='/search/']").each(function () {
            let href = $(this).attr("href") || '';
            let m = href.match(/\/(?:pgbtype|pgbshow|search)\/\d+-?(\d*)/);
            if (m && m[1]) {
                let p = parseInt(m[1]);
                if (p > pagecount) pagecount = p;
            }
        });
    }

    return { list, pagecount };
}

async function home(filter) {
    let list = [];
    try {
        const html = (await req(appConfig.siteUrl, {
            method: "GET",
            headers: {
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            }
        })).content;
        const $ = cheerio.load(html);
        let seen = {};

        $(".stui-vodlist li, .stui-vodlist__media li, .img-list:not(.swiper-wrapper) li, li[class*='col-md-'], li[class*='col-lg-'], li[class*='col-sm-']").each(function () {
            let $a = $(this).find("a[href*='/pgb/']").first();
            let vod_id = $a.attr("href");
            if (!vod_id || seen[vod_id]) return;

            let vod_name = $a.attr("title") || $a.find("img").attr("alt") || "";
            let vod_pic = fixUrl($a.attr("data-original") || $a.find("img").attr("data-original") || $a.find("img").attr("src") || "");
            let vod_remarks = ($(this).find(".pic-text, .vtitle, .vname, .text-right, .pic-tag").text() || "").trim();

            if (vod_name && vod_id) {
                seen[vod_id] = true;
                list.push({ vod_id, vod_name, vod_pic, vod_remarks });
            }
        });
    } catch (e) {
        console.error("首页推荐获取失败:", e.message);
    }

    return JSON.stringify({
        class: classList,
        filters: myFilters,
        list: list.slice(0, 30)
    });
}

function buildCategoryUrl(tid, pg, extend) {
    extend = extend || {};
    let area = extend.area || '';
    let year = extend.year || '';
    let lang = extend.lang || '';
    let type = extend.type || '';

    if (area || year || lang || type) {
        let url = `/pgbshow/${tid}-${area}---${lang}--${type}---${year}---${pg}---.html`;
        return appConfig.siteUrl + url;
    } else {
        if (pg > 1) {
            return `${appConfig.siteUrl}/pgbtype/${tid}-${pg}.html`;
        } else {
            return `${appConfig.siteUrl}/pgbtype/${tid}.html`;
        }
    }
}

async function category(tid, pg, filter, extend) {
    pg = pg || 1;
    extend = extend || {};

    let url = buildCategoryUrl(tid, pg, extend);

    try {
        const html = (await req(url, {
            method: "GET",
            headers: {
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": appConfig.siteUrl
            }
        })).content;
        const result = parseListHtml(html);
        return JSON.stringify(result);
    } catch (e) {
        console.error("分类列表获取失败:", e.message);
        return JSON.stringify({ list: [], pagecount: 0 });
    }
}

async function search(wd, quick, page) {
    page = page || 1;
    try {
        // 修复：搜索URL从 /pgbsearch/ 改为 /search/
        const url = `${appConfig.siteUrl}/search/-------------.html?wd=${encodeURIComponent(wd)}&page=${page}`;
        const html = (await req(url, {
            method: "GET",
            headers: {
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": appConfig.siteUrl
            }
        })).content;
        const result = parseListHtml(html);
        return JSON.stringify(result);
    } catch (e) {
        console.error("搜索失败:", e.message);
        return JSON.stringify({ list: [], pagecount: 0 });
    }
}

async function detail(id) {
    try {
        const html = (await req(appConfig.siteUrl + id, {
            method: "GET",
            headers: {
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": appConfig.siteUrl
            }
        })).content;
        const $ = cheerio.load(html);

        let vod_name = $("h1").first().text().trim() || $(".stui-content__detail .title").first().text().trim();

        let vod_pic = "";
        let $pic = $(".stui-content__thumb img, .details-pic img, .video-pic img, img[src*='upload'], img[data-original]").first();
        if ($pic.length > 0) {
            vod_pic = fixUrl($pic.attr("data-original") || $pic.attr("src") || "");
        }
        if (!vod_pic) {
            $("img").each(function () {
                let src = $(this).attr("src") || $(this).attr("data-original") || "";
                if ((src.includes('upload') || src.includes('cover')) && !vod_pic) {
                    vod_pic = fixUrl(src);
                }
            });
        }

        let vod_director = "";
        let vod_actor = "";
        let vod_area = "";
        let vod_year = "";
        let vod_content = "";
        let vod_class = "";
        let vod_remarks = "";
        let vod_lang = "";

        $(".stui-content__detail p, .stui-content__detail li, .details-info li, li").each(function () {
            let text = $(this).text();
            if (text.includes("导演") && !vod_director) {
                vod_director = $(this).find("a").map(function () { return $(this).text().trim(); }).get().filter(Boolean).join(',');
                if (!vod_director) vod_director = text.replace(/.*导演[：:]\s*/, "").trim();
            }
            if (text.includes("主演") && !vod_actor) {
                vod_actor = $(this).find("a").map(function () { return $(this).text().trim(); }).get().filter(Boolean).join(',');
                if (!vod_actor) vod_actor = text.replace(/.*主演[：:]\s*/, "").trim();
            }
            if (text.includes("类型") && !vod_class) {
                vod_class = $(this).find("a").map(function () { return $(this).text().trim(); }).get().filter(Boolean).join(',');
                if (!vod_class) vod_class = text.replace(/.*类型[：:]\s*/, "").trim();
            }
            if (text.includes("地区") && !vod_area) {
                vod_area = text.replace(/.*地区[：:]\s*/, "").trim();
            }
            if (text.includes("年份") && !vod_year) {
                vod_year = text.replace(/.*年份[：:]\s*/, "").trim();
            }
            if (text.includes("语言") && !vod_lang) {
                vod_lang = text.replace(/.*语言[：:]\s*/, "").trim();
            }
            if (text.includes("更新") && !vod_remarks) {
                vod_remarks = text.replace(/.*更新[：:]\s*/, "").trim();
            }
        });

        let $intro = $(".stui-content__desc, .txt-hidden, .content, .video-info-content, .details-content");
        if ($intro.length > 0) {
            vod_content = $intro.first().text().replace(/简介[：:]\s*/, "").trim();
        }

        let lines = [];
        let playlists = [];
        let seenEpisodes = new Set();

        // 修复：按HTML自然顺序遍历每个 .stui-content__playlist
        // 线路名从对应的 .stui-pannel__head .title 获取
        $(".stui-content__playlist").each(function () {
            // 获取线路名称：向上查找最近的 .stui-pannel__head 中的 .title
            let $panelHead = $(this).closest(".stui-pannel, .stui-pannel-box").find(".stui-pannel__head .title").first();
            let lineName = $panelHead.text().trim() || "默认";

            let episodes = [];
            let epArray = [];

            // 只在当前 playlist ul 内部选择播放链接，排除 .play-btn 区域
            $(this).find("a[href*='/pgbplay/']").each(function () {
                // 跳过可能存在的"立即播放"样式按钮
                if ($(this).hasClass("btn") || $(this).closest(".play-btn").length > 0) return;
                
                let name = $(this).text().trim();
                let href = $(this).attr('href') || '';
                if (name && href) {
                    let episodeKey = `${name}_${href}`;
                    if (!seenEpisodes.has(episodeKey)) {
                        seenEpisodes.add(episodeKey);
                        epArray.push({ name, href });
                    }
                }
            });

            // 正序排序：按集数数字排序
            epArray.sort((a, b) => {
                let numA = parseInt(a.name.match(/第(\d+)[集话]/i)?.[1] || a.name.match(/(\d+)/)?.[1] || 0);
                let numB = parseInt(b.name.match(/第(\d+)[集话]/i)?.[1] || b.name.match(/(\d+)/)?.[1] || 0);
                return numA - numB;
            });

            epArray.forEach(ep => {
                episodes.push(`${ep.name}$${ep.href}`);
            });

            if (episodes.length > 0) {
                lines.push(lineName);
                playlists.push(episodes);
            }
        });

        // 备用：如果没有找到 playlist
        if (lines.length === 0) {
            let episodes = [];
            let epArray = [];

            $(".play-list, .tab-pane").each(function () {
                $(this).find("a[href*='/pgbplay/']").each(function () {
                    if ($(this).hasClass("btn") || $(this).closest(".play-btn").length > 0) return;
                    
                    let name = $(this).text().trim();
                    let href = $(this).attr('href') || '';
                    if (name && href) {
                        let episodeKey = `${name}_${href}`;
                        if (!seenEpisodes.has(episodeKey)) {
                            seenEpisodes.add(episodeKey);
                            epArray.push({ name, href });
                        }
                    }
                });
            });

            if (epArray.length === 0) {
                // 最后的备用：全局选择但排除 .play-btn
                $("a[href*='/pgbplay/']").each(function () {
                    if ($(this).hasClass("btn") || $(this).closest(".play-btn").length > 0) return;
                    
                    let name = $(this).text().trim();
                    let href = $(this).attr('href') || '';
                    if (name && href) {
                        let episodeKey = `${name}_${href}`;
                        if (!seenEpisodes.has(episodeKey)) {
                            seenEpisodes.add(episodeKey);
                            epArray.push({ name, href });
                        }
                    }
                });
            }

            epArray.sort((a, b) => {
                let numA = parseInt(a.name.match(/第(\d+)[集话]/i)?.[1] || a.name.match(/(\d+)/)?.[1] || 0);
                let numB = parseInt(b.name.match(/第(\d+)[集话]/i)?.[1] || b.name.match(/(\d+)/)?.[1] || 0);
                return numA - numB;
            });

            epArray.forEach(ep => {
                episodes.push(`${ep.name}$${ep.href}`);
            });

            if (episodes.length > 0) {
                lines.push("默认");
                playlists.push(episodes);
            }
        }

        if (lines.length === 0) {
            lines.push("默认");
            playlists.push([`暂无播放地址$${id}`]);
        }

        const { vod_play_from, vod_play_url } = buildVodPlayData(lines, playlists);

        return JSON.stringify({
            list: [{
                vod_id: id,
                vod_name,
                vod_pic,
                vod_actor,
                vod_director,
                vod_remarks,
                vod_year,
                vod_area,
                vod_content,
                vod_class,
                vod_play_from,
                vod_play_url
            }]
        });
    } catch (error) {
        console.error(`解析详情页异常 [ID: ${id}]:`, error);
        return JSON.stringify({ list: [] });
    }
}

function buildVodPlayData(lines, playlists) {
    const processedPlaylists = playlists.map(eps => eps.join('#'));
    return {
        vod_play_from: lines.filter(Boolean).join('$$$'),
        vod_play_url: processedPlaylists.join('$$$')
    };
}

async function play(flag, id, flags) {
    try {
        if (id.startsWith("http")) {
            return JSON.stringify({
                parse: 0,
                header: { "User-Agent": UA, "Referer": appConfig.siteUrl },
                url: id
            });
        }

        const html = (await req(`${appConfig.siteUrl}${id}`, {
            method: "GET",
            headers: {
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": appConfig.siteUrl
            }
        })).content;

        // 解析 player_aaaa
        let playerMatch = html.match(/var player_aaaa\s*=\s*(\{.+?\});/);
        if (playerMatch) {
            try {
                let playerData = JSON.parse(playerMatch[1]);
                if (playerData.url) {
                    // 修复：正确处理转义URL
                    let playUrl = playerData.url.replace(/\\/g, '');
                    return JSON.stringify({
                        parse: 0,
                        header: { "User-Agent": UA, "Referer": appConfig.siteUrl },
                        url: playUrl
                    });
                }
            } catch (e) {
                console.error("解析player_aaaa失败:", e.message);
            }
        }

        // 尝试匹配 m3u8 URL
        let urlMatch = html.match(/"url"\s*[:=]\s*"([^"]+\.m3u8[^"]*)"/);
        if (urlMatch) {
            return JSON.stringify({
                parse: 0,
                header: { "User-Agent": UA, "Referer": appConfig.siteUrl },
                url: urlMatch[1].replace(/\\/g, '')
            });
        }

        // 尝试 iframe
        const $ = cheerio.load(html);
        let iframeSrc = $("iframe").attr("src");
        if (iframeSrc) {
            return JSON.stringify({
                parse: 1,
                header: { "User-Agent": UA, "Referer": appConfig.siteUrl },
                url: fixUrl(iframeSrc)
            });
        }

        return JSON.stringify({
            parse: 1,
            header: { "User-Agent": UA, "Referer": appConfig.siteUrl },
            url: appConfig.siteUrl + id
        });
    } catch (e) {
        console.error("播放失败:", e);
        return JSON.stringify({ parse: 0, url: "" });
    }
}

export default {
    init,
    home,
    category,
    detail,
    search,
    play
};